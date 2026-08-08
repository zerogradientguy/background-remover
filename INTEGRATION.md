# AI Toolkit API — Developer Integration Guide

A single self-hosted **FastAPI** service that exposes image-processing endpoints backed by locally-loaded ML models. All inference runs on your own hardware — there are no external API dependencies and no keys to provision.

| Feature | Endpoint | Model |
|---|---|---|
| Background Remover | `POST /api/v1/background-remover` | BiRefNet (`ZhengPeng7/BiRefNet_lite`) |
| AI Blur BG | `POST /api/v1/ai-blur-bg` | BiRefNet mask + Gaussian composite |
| AI Enhancer | `POST /api/v1/ai-enhancer` | Real-ESRGAN x4plus + GFPGAN v1.3 (2× output — see §3.3) |

These three endpoints are the complete public surface of the service, alongside the two health probes below.

---

## 1. Quick reference

Base URL (local dev): `http://localhost:8000`
API prefix: `/api/v1` (configurable via `API_V1_PREFIX`)

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET` | `/health` | — | `{"status":"ok"}` |
| `GET` | `/api/v1/health` | — | JSON readiness + device + model flags |
| `POST` | `/api/v1/background-remover` | `multipart/form-data` | `image/png` (RGBA) |
| `POST` | `/api/v1/ai-blur-bg` | `multipart/form-data` | `image/png` (RGB) |
| `POST` | `/api/v1/ai-enhancer` | `multipart/form-data` | `image/png` (RGB) |

Interactive docs:

- Swagger UI — `http://localhost:8000/api/v1/docs`
- ReDoc — `http://localhost:8000/api/v1/redoc`
- OpenAPI JSON — `http://localhost:8000/api/v1/openapi.json`

**There is no authentication layer.** Every endpoint is open. Put the service behind an API gateway, reverse proxy, or your own auth middleware before exposing it publicly.

---

## 2. Core integration rules

These apply to all three endpoints — get these right and the rest is mechanical.

1. **Requests are `multipart/form-data`, never JSON.** The image goes in a form field literally named `file`.
2. **Responses are raw PNG bytes, not JSON.** On success (`200`) the body is the image itself with `Content-Type: image/png`. Do not call `.json()` on a success response.
3. **Errors are JSON.** Any non-200 returns `{"error": {"code": "...", "message": "..."}}` with `Content-Type: application/json`.
4. **Branch on status code**, not on content: `200` → treat body as binary image; anything else → parse JSON error.
5. **Accepted input formats:** anything Pillow can decode — PNG, JPEG, WEBP, BMP, TIFF, GIF. Output is always PNG.
6. **CORS is wide open** (`allow_origins=["*"]`, credentials disabled), so browser-side `fetch` works from any origin without a proxy.

### Canonical error shape

```json
{
  "error": {
    "code": "bad_input",
    "message": "Could not decode image: cannot identify image file"
  }
}
```

| Status | `code` | Meaning | What the client should do |
|---|---|---|---|
| `400` | `bad_input` | The uploaded bytes could not be decoded as an image | Show a validation message; do not retry |
| `422` | — (FastAPI shape) | Missing `file` field, or a form value out of range | Fix the request |
| `501` | `feature_unavailable` / `enhancer_failed` | Enhancer backend could not run (missing weights, OOM, etc.) | Surface a "temporarily unavailable" state |
| `503` | `model_not_ready` | BiRefNet is still warming up | Retry with backoff — see §7 |
| `500` | `internal_error` | Unhandled exception (details are logged server-side, not returned) | Fail and log |

Note that `422` uses FastAPI's default validation shape (`{"detail": [...]}`), not the `error` envelope — handle both.

---

## 3. Endpoints

### 3.1 Background Remover

`POST /api/v1/background-remover`

Runs BiRefNet segmentation, refines the foreground under the alpha matte (de-fringes hair and soft edges), and returns the subject over transparency.

**Form fields**

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | file | yes | Source image |

**Response:** `image/png`, **RGBA** — the alpha channel carries the matte. Preserve it: converting to JPEG on your side destroys the cutout.

```bash
curl -X POST http://localhost:8000/api/v1/background-remover \
  -F "file=@portrait.jpg" \
  -o cutout.png
```

---

### 3.2 AI Blur BG

`POST /api/v1/ai-blur-bg`

Reuses the same BiRefNet mask, then composites a sharp foreground over a Gaussian-blurred copy of the original — a portrait/bokeh effect. The subject is never re-encoded, so edges stay crisp.

**Form fields**

| Field | Type | Required | Default | Range | Notes |
|---|---|---|---|---|---|
| `file` | file | yes | — | — | Source image |
| `blur_radius` | integer | no | `18` | `1`–`100` | Gaussian blur radius in pixels |

An out-of-range `blur_radius` returns `422`. The radius is absolute in pixels, so it is **resolution-dependent** — `18` reads as a strong blur on a 800 px image and as a mild one on a 4000 px image. If you want a consistent look across uploads, scale it client-side against the longest side (e.g. `round(max(w, h) * 0.015)`).

**Response:** `image/png`, **RGB** (fully opaque — the background is kept, only blurred).

```bash
curl -X POST http://localhost:8000/api/v1/ai-blur-bg \
  -F "file=@portrait.jpg" \
  -F "blur_radius=30" \
  -o blurred.png
```

---

### 3.3 AI Enhancer

`POST /api/v1/ai-enhancer`

Real-ESRGAN x4plus upscales the image while GFPGAN restores faces. There is no scale parameter — the scale is fixed server-side.

**The output is 2× the input dimensions on each axis** (4× the pixel count), measured across square and non-square inputs. Size your client-side layout and storage against 2×.

> Be aware of a naming mismatch in the code: the endpoint summary says "4× upscale" and `app/api/v1/ai_enhancer.py` passes `scale=4`, but the delivered output is 2×. `GFPGANer` is constructed with `upscale=2` (`app/services/ai_enhancer/real_esrgan_gfpgan.py`), and it builds its internal `FaceRestoreHelper` with that factor at init time — so the per-request `restorer.upscale = scale` assignment does not change the final canvas size. If you want true 4×, construct `GFPGANer` with `upscale=4` rather than reassigning the attribute per request, then re-measure. Left as-is here so behavior is unchanged; documented so you are not surprised.

**Form fields**

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | file | yes | Source image |

**Response:** `image/png`, **RGB**.

```bash
curl -X POST http://localhost:8000/api/v1/ai-enhancer \
  -F "file=@low-res.jpg" \
  -o enhanced.png
```

**Integration warnings — read before wiring this up:**

- **Response payloads get large.** A 1024×1024 input yields a 2048×2048 PNG — several MB, and PNG is lossless so it does not compress like JPEG. Stream the response to disk or storage rather than buffering it in memory, and raise any proxy/CDN response-size limits on this route.
- **This is the slowest endpoint by a wide margin**, especially on CPU. Set generous client timeouts (see §7).
- **Cap input size** via the `ENHANCER_MAX_INPUT_SIDE` env var. When set to a non-zero value, the server downscales the input's longest side to that value *before* enhancing — essential for keeping CPU latency and output size manageable. `0` (the default) means no cap.
- Model weights (`RealESRGAN_x4plus.pth`, `GFPGANv1.3.pth`) are **downloaded on the first request**, not at startup. The first call after a cold start therefore includes a multi-hundred-MB download. Warm the endpoint during deploy if first-request latency matters.

---

### 3.4 Health endpoints

Two distinct probes — do not mix them up.

**`GET /health`** — liveness. Dependency-free, returns `200` the moment the process accepts connections, even before models finish loading. This is the one to point ALB target groups and Kubernetes liveness probes at.

```json
{"status": "ok"}
```

**`GET /api/v1/health`** — readiness. Reports the compute device and per-model load state.

```json
{
  "status": "ok",
  "device": "cpu",
  "models": { "birefnet": true }
}
```

Use `models.birefnet` as the readiness gate for Background Remover and AI Blur BG. Gate a Kubernetes readiness probe on this endpoint so traffic only arrives once BiRefNet is loaded.

`models` reflects load state only — it does **not** track the enhancer, which loads lazily on first use and is therefore never reported here.

---

## 4. Client examples

### JavaScript / TypeScript (browser or Node 18+)

```ts
const BASE = "http://localhost:8000/api/v1";

type ApiError = { error: { code: string; message: string } };

async function callImageEndpoint(
  path: string,
  file: File | Blob,
  fields: Record<string, string | number> = {},
): Promise<Blob> {
  const form = new FormData();
  form.append("file", file);
  for (const [k, v] of Object.entries(fields)) form.append(k, String(v));

  // Do NOT set Content-Type — the browser must add the multipart boundary itself.
  const res = await fetch(`${BASE}${path}`, { method: "POST", body: form });

  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiError | null;
    throw new Error(body?.error?.message ?? `Request failed: ${res.status}`);
  }
  return res.blob(); // image/png
}

export const removeBackground = (file: File) =>
  callImageEndpoint("/background-remover", file);

export const blurBackground = (file: File, blurRadius = 18) =>
  callImageEndpoint("/ai-blur-bg", file, { blur_radius: blurRadius });

export const enhance = (file: File) =>
  callImageEndpoint("/ai-enhancer", file);

// Render it
const png = await removeBackground(input);
img.src = URL.createObjectURL(png); // remember to revokeObjectURL when done
```

### Python

```python
import httpx

BASE = "http://localhost:8000/api/v1"

def call(path: str, image_path: str, timeout: float = 120.0, **fields) -> bytes:
    with open(image_path, "rb") as fh:
        files = {"file": (image_path, fh, "application/octet-stream")}
        data = {k: str(v) for k, v in fields.items()}
        r = httpx.post(f"{BASE}{path}", files=files, data=data, timeout=timeout)

    if r.status_code != 200:
        err = r.json().get("error", {})
        raise RuntimeError(f"{err.get('code', r.status_code)}: {err.get('message', r.text)}")
    return r.content  # PNG bytes

open("cutout.png", "wb").write(call("/background-remover", "in.jpg"))
open("blur.png",   "wb").write(call("/ai-blur-bg", "in.jpg", blur_radius=30))
open("hi-res.png", "wb").write(call("/ai-enhancer", "in.jpg", timeout=600.0))
```

### Streaming the enhancer response to disk

Because enhancer output is large, avoid loading it fully into memory:

```python
with httpx.stream("POST", f"{BASE}/ai-enhancer", files=files, timeout=600.0) as r:
    if r.status_code != 200:
        r.read()
        raise RuntimeError(r.json())
    with open("hi-res.png", "wb") as out:
        for chunk in r.iter_bytes():
            out.write(chunk)
```

---

## 5. Architecture

```
main.py                     # uvicorn entrypoint; python main.py
app/
├── config.py               # pydantic-settings — all env vars land here
├── server.py               # create_app(): FastAPI factory, CORS, routers, docs URLs
├── core/
│   ├── lifespan.py         # startup: build registry + warmup; shutdown: unload
│   ├── dependencies.py     # get_registry() pulls off app.state
│   ├── exceptions.py       # AppError hierarchy -> JSON error envelope
│   ├── logging.py
│   └── compat.py           # torchvision functional_tensor shim for basicsr
├── api/
│   ├── health.py           # root-level /health liveness probe
│   ├── router.py           # aggregates v1 routers + /api/v1/health readiness
│   └── v1/                 # one thin router per feature (HTTP only, no logic)
├── services/               # business logic per feature
│   └── ai_enhancer/        # Real-ESRGAN + GFPGAN, lazy singleton
├── ml/
│   ├── registry.py         # ModelRegistry — owns all heavy engines
│   ├── birefnet_loader.py  # BiRefNetEngine: predict_mask() / cutout()
│   └── image_proc.py       # alpha-aware foreground refinement (CPU + CUDA paths)
├── schemas/                # pydantic response models
└── utils/image.py          # decode / encode PNG / composite helpers
```

**Request flow:** router (`api/v1/*`) → decode bytes with `read_image_bytes` → service (`services/*`) → model engine off the registry → `to_png_bytes` → `Response(media_type="image/png")`.

**Key design points a developer should know:**

- **`ModelRegistry` is a startup singleton** built in `lifespan.py` and stored on `app.state.registry`. Weights are never reloaded per request. Endpoints reach it through the `get_registry` FastAPI dependency.
- **BiRefNet loads eagerly at startup**; the enhancer stack loads lazily on first request. That keeps cold start fast at the cost of a slow first enhance.
- **Background Remover and AI Blur BG share one model.** Blur BG's marginal cost over a cutout is just a Gaussian blur plus a composite — they are the cheapest pair of features to run together.
- **Device selection is automatic**: `cuda` if `torch.cuda.is_available()`, else `cpu`. There is no config override. Check the `device` field on `/api/v1/health` to confirm what you actually got.
- **Single worker assumed.** Each worker process loads its own full copy of the model weights. Scale with replicas/containers, not `uvicorn --workers N`, unless you have the RAM/VRAM to spare.

---

## 6. Configuration

Copy `.env.example` to `.env`. Every field on the `Settings` class maps to an env var of the same name, case-insensitive.

| Variable | Default | Relevant to |
|---|---|---|
| `APP_NAME` | `AI Toolkit API` | Swagger title |
| `ENVIRONMENT` | `development` | `development` \| `staging` \| `production` |
| `DEBUG` | `false` | Also enables uvicorn auto-reload via `main.py` |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Bind port |
| `LOG_LEVEL` | `INFO` | Logging + uvicorn log level |
| `API_V1_PREFIX` | `/api/v1` | Changing this moves **every** route, including the docs URLs |
| `BIREFNET_MODEL_ID` | `ZhengPeng7/BiRefNet_lite` | Use `ZhengPeng7/BiRefNet` for higher quality at more VRAM/latency |
| `BIREFNET_INPUT_SIZE` | `1024` | Inference resolution; the mask is resized back to the original dimensions |
| `ENHANCER_MAX_INPUT_SIDE` | `0` | Longest-side cap before enhancing. `0` = no cap. Set to `512` on CPU |
| `MAX_UPLOAD_MB` | `25` | **Declared but not currently enforced** — see below |

Two behaviors worth planning around:

- **`MAX_UPLOAD_MB` is not wired to any check.** No middleware or route reads it, so the service will happily accept a 500 MB upload and attempt to decode it. Enforce upload size at your reverse proxy (`client_max_body_size` in nginx, ALB/API-Gateway limits) or add the check yourself.
- **`API_V1_PREFIX` moves the docs too.** `docs_url` and `redoc_url` are derived from it in `server.py`, which is why Swagger is at `/api/v1/docs` and not the FastAPI default `/docs`.

Also note `server.py` mounts a static directory at `/` when a `static/` folder exists at the repo root. It does not currently exist, so `/` returns 404 — that is expected, not a broken deploy.

---

## 7. Operational notes for client integration

**Set per-endpoint timeouts.** These are not uniform-latency endpoints. Background Remover and Blur BG are one forward pass; the Enhancer runs a tiled 4× super-resolution plus face restoration.

| Endpoint | Suggested client timeout (GPU) | Suggested client timeout (CPU) |
|---|---|---|
| `/background-remover` | 30 s | 120 s |
| `/ai-blur-bg` | 30 s | 120 s |
| `/ai-enhancer` | 180 s | 600 s+ (or cap input size) |

Treat these as starting points and tune against your own hardware — the actual numbers depend heavily on GPU model and input resolution.

**Handle the warm-up window.** Between process start and BiRefNet finishing its load, `/health` returns `200` but the two segmentation endpoints return `503 model_not_ready`. Clients should retry `503` with exponential backoff (3–5 attempts) rather than surfacing it as a hard failure. Server-side, poll `/api/v1/health` until `models.birefnet` is `true` before routing traffic.

**Expect serialized inference.** Requests hitting the same model contend for one GPU/CPU. Concurrent requests do not run in parallel in any meaningful way — put a queue in front for bursty traffic instead of relying on the HTTP layer to absorb it.

**Log correlation.** Every request logs a timing line (`background-remover (1024, 768) in 1.42s`). Unhandled exceptions are logged with a full traceback server-side but return only a generic message to the client, so server logs are the only place to diagnose a `500`.

---

## 8. Running the service

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python main.py
```

Or directly with uvicorn:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

The first startup downloads BiRefNet weights from Hugging Face; the first `/ai-enhancer` call downloads the Real-ESRGAN and GFPGAN checkpoints. In containers, persist the Hugging Face and torch cache directories across restarts so this happens once rather than on every deploy.

Then open **http://localhost:8000/api/v1/docs** and try the endpoints from the browser.
