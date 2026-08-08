#!/usr/bin/env bash
#
# Provision an Oracle Cloud Always Free ARM instance (Ampere A1, Ubuntu) to run
# the AI Toolkit API behind nginx.
#
# Usage, as a sudo-capable user on a fresh instance:
#   curl -fsSL https://raw.githubusercontent.com/zerogradientguy/background-remover/main/deploy/oracle/setup.sh -o setup.sh
#   sudo bash setup.sh
#
# Idempotent: safe to re-run. Re-running pulls the latest main and restarts.

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/zerogradientguy/background-remover.git}"
APP_USER="${APP_USER:-aitoolkit}"
APP_HOME="/opt/ai-toolkit"
APP_DIR="${APP_HOME}/app"
CACHE_DIR="${APP_HOME}/cache"
VENV="${APP_HOME}/venv"

log() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo bash setup.sh" >&2
  exit 1
fi

log "Architecture check"
ARCH="$(uname -m)"
echo "Detected: ${ARCH}"
if [[ "${ARCH}" != "aarch64" ]]; then
  echo "WARNING: expected aarch64 (Ampere A1). Continuing anyway." >&2
fi

log "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
# libgl1 + libglib2.0-0: basicsr/gfpgan pull in full opencv-python, which links
# against libGL. Without these the enhancer import fails on a headless server.
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-dev python3-pip \
  git nginx ca-certificates curl \
  build-essential pkg-config \
  libgl1 libglib2.0-0

log "Configuring swap (protects pip install torch from OOM)"
if ! swapon --show | grep -q '/swapfile'; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "4G swap enabled."
else
  echo "Swap already present, skipping."
fi

log "Creating service user and directories"
id -u "${APP_USER}" &>/dev/null || useradd --system --create-home --home-dir "${APP_HOME}" --shell /usr/sbin/nologin "${APP_USER}"
mkdir -p "${APP_DIR}" "${CACHE_DIR}/hf" "${CACHE_DIR}/torch"
chown -R "${APP_USER}:${APP_USER}" "${APP_HOME}"

log "Fetching application source"
if [[ -d "${APP_DIR}/.git" ]]; then
  sudo -u "${APP_USER}" git -C "${APP_DIR}" fetch --depth 1 origin main
  sudo -u "${APP_USER}" git -C "${APP_DIR}" reset --hard origin/main
else
  sudo -u "${APP_USER}" git clone --depth 1 "${REPO_URL}" "${APP_DIR}"
fi

log "Building Python environment (this takes 10-20 minutes on 2 OCPUs)"
[[ -d "${VENV}" ]] || sudo -u "${APP_USER}" python3 -m venv "${VENV}"
sudo -u "${APP_USER}" "${VENV}/bin/pip" install --upgrade pip wheel setuptools

# On aarch64 the PyPI torch wheels are already CPU-only — there is no ARM CUDA
# build. Do NOT use download.pytorch.org/whl/cpu here; that index carries no
# aarch64 wheels and pip would fall back to building from source.
sudo -u "${APP_USER}" "${VENV}/bin/pip" install --no-cache-dir torch torchvision

# basicsr's setup.py imports torch at build time, which fails inside pip's
# isolated build env. Install it against the venv that already has torch.
sudo -u "${APP_USER}" "${VENV}/bin/pip" install --no-cache-dir --no-build-isolation basicsr==1.4.2

sudo -u "${APP_USER}" "${VENV}/bin/pip" install --no-cache-dir -r "${APP_DIR}/requirements.txt"

log "Writing .env"
if [[ ! -f "${APP_DIR}/.env" ]]; then
  sudo -u "${APP_USER}" tee "${APP_DIR}/.env" >/dev/null <<'ENVEOF'
ENVIRONMENT=production
DEBUG=false
HOST=127.0.0.1
PORT=8000
LOG_LEVEL=INFO
API_V1_PREFIX=/api/v1
BIREFNET_MODEL_ID=ZhengPeng7/BiRefNet_lite
BIREFNET_INPUT_SIZE=1024
# CPU-only box: cap enhancer input so one large upload cannot pin both cores.
ENHANCER_MAX_INPUT_SIDE=512
MAX_UPLOAD_MB=25
WARMUP_IN_BACKGROUND=true
ENVEOF
  echo "Wrote ${APP_DIR}/.env"
else
  echo ".env already exists, leaving it alone."
fi

log "Installing systemd service"
install -m 0644 "${APP_DIR}/deploy/oracle/ai-toolkit.service" /etc/systemd/system/ai-toolkit.service
systemctl daemon-reload
systemctl enable ai-toolkit
systemctl restart ai-toolkit

log "Configuring nginx"
install -m 0644 "${APP_DIR}/deploy/oracle/nginx.conf" /etc/nginx/sites-available/ai-toolkit
ln -sf /etc/nginx/sites-available/ai-toolkit /etc/nginx/sites-enabled/ai-toolkit
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx

log "Opening ports 80/443 in the instance firewall"
# Oracle's Ubuntu images ship an iptables REJECT rule for inbound traffic that
# is NOT managed by ufw. Insert ACCEPT rules above it and persist them.
for port in 80 443; do
  if ! iptables -C INPUT -p tcp --dport "${port}" -m state --state NEW -j ACCEPT 2>/dev/null; then
    iptables -I INPUT 6 -p tcp --dport "${port}" -m state --state NEW -j ACCEPT
  fi
done
DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent
netfilter-persistent save

log "Done"
cat <<EOF

Service:  systemctl status ai-toolkit
Logs:     journalctl -u ai-toolkit -f

Local check (should answer immediately):
  curl http://127.0.0.1/health

Readiness (birefnet flips true once weights finish downloading):
  curl http://127.0.0.1/api/v1/health

If the public IP does not respond, the OCI Security List ingress rules for
TCP 80/443 are still missing — that is configured in the web console, not here.

EOF
