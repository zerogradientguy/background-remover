# AI Toolkit API

Backend for a 3-feature AI image toolkit. Single FastAPI service, models loaded once at startup, designed for self-hosted GPU deployment.

All inference runs locally — there are no external API dependencies and no API keys to provision.

## Features

| Endpoint | Backbone |
|---|---|
| `POST /api/v1/background-remover` | BiRefNet (`ZhengPeng7/BiRefNet_lite`) |
| `POST /api/v1/ai-blur-bg` | Reuses the BiRefNet mask + Gaussian composite |
| `POST /api/v1/ai-enhancer` | Real-ESRGAN x4plus + GFPGAN v1.3 (upscale + face restore) |

Meta: `GET /health` (liveness), `GET /api/v1/health` (readiness).

**See [INTEGRATION.md](INTEGRATION.md) for the full API contract, client examples, and operational notes.**

## Layout

```
main.py                  # uvicorn entry
app/
├── config.py            # pydantic-settings
├── server.py            # FastAPI app factory
├── core/                # logging, exceptions, lifespan, compat shims
├── api/
│   ├── health.py        # root-level /health liveness probe
│   ├── router.py        # aggregator + /api/v1/health readiness
│   └── v1/              # one router per feature
├── services/            # business logic (per feature)
│   └── ai_enhancer/     # Real-ESRGAN + GFPGAN
├── ml/                  # model engines + registry singleton
│   ├── birefnet_loader.py
│   ├── image_proc.py
│   └── registry.py
├── schemas/             # pydantic response models
└── utils/               # image IO + timing
```

## Run locally

```powershell
python -m venv venv
venv\Scripts\Activate.ps1      # Windows PowerShell
pip install -r requirements.txt
copy .env.example .env
python main.py
```

On macOS/Linux use `source venv/bin/activate` and `cp .env.example .env`.

Visit `http://localhost:8000/api/v1/docs` for the auto-generated Swagger UI.

The first startup downloads BiRefNet weights from Hugging Face. The first `/ai-enhancer` call downloads the Real-ESRGAN and GFPGAN checkpoints — those load lazily, not at startup.

## Configure

Edit `.env`:

- `BIREFNET_MODEL_ID` — defaults to `ZhengPeng7/BiRefNet_lite`. Switch to `ZhengPeng7/BiRefNet` for the full model.
- `ENHANCER_MAX_INPUT_SIDE` — set to e.g. `512` on CPU to keep enhancer latency and output size sane. `0` disables the cap.
- `API_V1_PREFIX` — moves every route, including the docs URLs.

Full table in [INTEGRATION.md](INTEGRATION.md#6-configuration).

## Deployment notes

- GPU is used automatically when `torch.cuda.is_available()`; otherwise it falls back to CPU. Confirm which you got via the `device` field on `/api/v1/health`.
- Recommended instance: `g5.xlarge` (A10G 24 GB) — fits BiRefNet and Real-ESRGAN + GFPGAN comfortably.
- Point load-balancer health checks at `/health` (dependency-free) and readiness probes at `/api/v1/health`.
- Persist the Hugging Face and torch cache directories across restarts so model weights are not re-downloaded on every deploy.
- Each worker process loads its own copy of the weights. Scale with replicas, not `uvicorn --workers N`, unless you have the memory to spare.
- `MAX_UPLOAD_MB` is declared in config but not enforced in code — cap request body size at your reverse proxy.
