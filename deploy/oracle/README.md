# Deploying to Oracle Cloud (Always Free ARM)

Runs the API on an Always Free Ampere A1 instance — **2 OCPU / 12 GB RAM**, free
indefinitely. CPU-only, so inference is slow but every endpoint works.

> Oracle halved this allowance in June 2026 (it was 4 OCPU / 24 GB) without an
> announcement. 12 GB is still ample here, but do not assume it is permanent.

## Part 1 — Console (browser, ~15 min)

1. **Sign up** at <https://www.oracle.com/cloud/free/>. A credit card is required
   for identity verification; Always Free resources are not charged. Pick your
   home region carefully — **it cannot be changed later**, and ARM capacity
   varies by region.

2. **Create the instance**: Compute → Instances → *Create instance*.
   - **Image**: Ubuntu 24.04 — you must choose the **non-minimal** image;
     the minimal build does not support aarch64 here.
   - **Shape**: *Ampere* → `VM.Standard.A1.Flex` → **2 OCPUs, 12 GB RAM**.
   - **SSH keys**: upload your public key (or let Oracle generate and download
     the private key — you cannot retrieve it later).
   - **Boot volume**: 50 GB is plenty. The free allowance is 200 GB total.

   If you get **"Out of host capacity"**, that is normal for free ARM. Retry
   later, or try another availability domain in your region. It can take days.

3. **Open the firewall** (network layer): Networking → Virtual Cloud Networks →
   your VCN → Security Lists → *Default Security List* → **Add Ingress Rules**:

   | Source CIDR | IP Protocol | Destination Port |
   |---|---|---|
   | `0.0.0.0/0` | TCP | `80` |
   | `0.0.0.0/0` | TCP | `443` |

   This is separate from the instance's own firewall, which `setup.sh` handles.
   Both layers must allow the traffic.

## Part 2 — Server (one command)

SSH in using the instance's public IP:

```bash
ssh ubuntu@<PUBLIC_IP>
```

Then:

```bash
curl -fsSL https://raw.githubusercontent.com/zerogradientguy/background-remover/main/deploy/oracle/setup.sh -o setup.sh
sudo bash setup.sh
```

Takes 15–30 minutes, most of it building PyTorch's dependency tree on 2 cores.
The script installs system packages, adds 4 GB of swap, creates a service user,
builds the virtualenv, writes `.env`, and installs the systemd unit, the nginx
reverse proxy, and the instance firewall rules. It is idempotent — re-run it to
deploy the latest `main`.

## Part 3 — Verify

```bash
# On the box — answers immediately, even while weights download
curl http://127.0.0.1/health

# Readiness: birefnet flips to true when BiRefNet finishes loading
curl http://127.0.0.1/api/v1/health

# From your laptop
curl http://<PUBLIC_IP>/health
```

First boot downloads BiRefNet from Hugging Face, so `birefnet` stays `false` for
a few minutes and the image endpoints return `503 model_not_ready` until it
flips. That is expected — see the retry guidance in `INTEGRATION.md`.

Then try a real request:

```bash
curl -X POST http://<PUBLIC_IP>/api/v1/background-remover \
  -F "file=@photo.jpg" -o cutout.png
```

## Operating it

```bash
systemctl status ai-toolkit          # state
journalctl -u ai-toolkit -f          # live logs, incl. per-request timings
sudo systemctl restart ai-toolkit    # restart
sudo bash setup.sh                   # redeploy latest main
```

## HTTPS

The setup ships HTTP only, because certificates need a domain name — Let's
Encrypt will not issue for a bare IP. Once you have a domain pointed at the
instance:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.yourdomain.com
```

Certbot rewrites the nginx config in place and sets up renewal. Until then the
API is unauthenticated **and** unencrypted — do not put real user uploads
through it.

## Expected performance

Two shared ARM cores, no GPU:

| Endpoint | Typical |
|---|---|
| `/background-remover`, `/ai-blur-bg` | ~10–60s depending on resolution |
| `/ai-enhancer` | minutes; capped at 512px input via `ENHANCER_MAX_INPUT_SIDE` |

Requests serialize — the models are single instances and there are only two
cores. This suits demos and low-volume batch work, not interactive traffic. If
the enhancer is central to your product, it wants a GPU host.

## Notes and gotchas

- **Do not use `ufw`.** Oracle's images manage inbound rules directly in
  iptables, and enabling ufw on top of that is a well-known way to lock yourself
  out. `setup.sh` edits iptables and persists via `iptables-persistent`.
- **Both firewall layers matter.** A missing OCI Security List rule looks
  exactly like a broken app: `curl` works on the box, times out from outside.
- **aarch64 torch comes from PyPI, not the CPU wheel index.** ARM wheels on PyPI
  are already CPU-only; `download.pytorch.org/whl/cpu` has no aarch64 builds and
  pip would try to compile from source.
- **`basicsr` needs `--no-build-isolation`** because its `setup.py` imports
  torch at build time.
- **`libgl1` is required** even though `requirements.txt` asks for
  opencv-headless — `basicsr`/`gfpgan` pull in the full `opencv-python`.
