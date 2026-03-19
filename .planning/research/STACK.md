# Stack Research

**Domain:** Batch GPU Audio Generation Service
**Researched:** 2026-03-18
**Confidence:** MEDIUM — all versions based on training data (cutoff Aug 2025). No live PyPI/GitHub access was available. Pin versions with `pip index versions <pkg>` before writing `requirements.txt`.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11 | Runtime | 3.11 is the stable CUDA container baseline. PyTorch wheels for CUDA 12.x ship for 3.11. 3.12 is usable but fewer GPU container base images pre-bake it — stick to 3.11 for broad RunPod image compatibility. |
| PyTorch | 2.3.x (CUDA 12.1) | Tensor backend for model inference | SongGeneration v2 is a HuggingFace Transformers model; PyTorch 2.3 + CUDA 12.1 is the combination that A5000/3090 drivers on RunPod support reliably. Use the official wheel index, not PyPI. |
| Transformers | >=4.40.0 | Load and run the HuggingFace model | SongGeneration v2 (lglg666/SongGeneration-v2-large) uses `AutoModelForCausalLM` + diffusion components exposed through the `transformers` API. 4.40+ includes music-generation pipeline improvements. |
| runpod | >=1.6.0 | RunPod serverless worker harness | The official SDK provides `runpod.serverless.start({"handler": fn})` — the only supported entry point for serverless workers. No alternative. |
| FastAPI | 0.111.x | Local dev / smoke-test HTTP server | Not deployed on RunPod (the handler is invoked directly). Used in Docker for `docker run -p 8000:8000` local testing. Avoids re-writing test logic. |
| uvicorn | 0.29.x | ASGI server for FastAPI local dev | Standard pairing with FastAPI. Only active in local mode via `CMD` switch. |
| Pydantic | v2 (2.7.x) | Input validation, schema typing | The project's CONVENTIONS.md uses Pydantic v2 idioms (`model_config = ConfigDict`, `Annotated` fields). Validates `BatchRequest` / `TrackSpec` payloads before generation starts. |
| boto3 | 1.34.x | Upload WAV/MP3 to Cloudflare R2 | R2 exposes an S3-compatible endpoint. boto3 with a custom `endpoint_url` is the standard pattern — no Cloudflare-specific SDK needed. Mature, well-tested. |
| soundfile | 0.12.x | Write WAV from numpy/tensor output | `soundfile.write()` handles float32 arrays from PyTorch directly. Simpler and more reliable than `scipy.io.wavfile` for 24-bit/32-bit float audio. |
| pydub | 0.25.x | Convert WAV to MP3 | Wraps ffmpeg for format conversion. One-liner: `AudioSegment.from_wav().export(mp3_path, format="mp3")`. ffmpeg must be in the Docker image. |
| accelerate | >=0.30.0 | HuggingFace model loading helpers | Required by Transformers for device placement (`device_map="auto"`). Handles splitting model layers across VRAM correctly when using `--low_mem` mode. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| huggingface_hub | >=0.23.0 | Download model at Docker build time | `snapshot_download("lglg666/SongGeneration-v2-large")` baked into `Dockerfile` so cold start is model-loading, not model-downloading. Always use during image build. |
| python-dotenv | 1.0.x | Load `.env` for local dev | R2 credentials (`R2_ACCOUNT_ID`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_BUCKET`) from env. Only active locally — RunPod injects env vars natively. |
| structlog | 23.x | Structured JSON logging | RunPod captures stdout/stderr. Structured logs (JSON lines) make per-track error tracing queryable. Use instead of bare `logging`. |
| tenacity | 8.x | Retry logic for R2 uploads | Network hiccups on large WAV uploads (50–200 MB) to R2 should retry with backoff, not fail the whole batch. Wrap `boto3.upload_file` in `@retry`. |
| pytest | 8.x | Test harness | Unit tests for payload validation, R2 upload mocking (with `moto`), and handler response format. |
| moto | 5.x | Mock S3/R2 in tests | Intercepts `boto3` calls so upload tests don't hit real R2. Covers the S3-compatible endpoint used by R2. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Docker (CUDA base) | Container runtime | Use `nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04` as base — matches PyTorch 2.3 CUDA 12.1 wheels and RunPod's GPU runtime. NOT the `devel` image; `runtime` is smaller and sufficient for inference. |
| ffmpeg (system package) | MP3 encoding via pydub | `apt-get install -y ffmpeg` in Dockerfile. pydub delegates all encoding to the system ffmpeg binary. |
| uv | Fast pip replacement for Docker layer caching | `pip install uv && uv pip install -r requirements.txt` inside Docker build. Dramatically faster than pip for large dependency trees (PyTorch + HuggingFace). |
| ruff | Linting and formatting | Matches the project's modern Python conventions. Single tool replacing flake8 + isort + black. |
| mypy | Type checking | The project CONVENTIONS.md uses Protocol, Self, Never — mypy enforces these at CI time. |

---

## Installation

```bash
# Install PyTorch with correct CUDA wheel (not from PyPI default index)
pip install torch==2.3.1+cu121 torchaudio==2.3.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

# Core inference and serving
pip install \
    transformers>=4.40.0 \
    accelerate>=0.30.0 \
    huggingface_hub>=0.23.0 \
    runpod>=1.6.0 \
    fastapi==0.111.0 \
    uvicorn==0.29.0 \
    pydantic>=2.7.0 \
    boto3>=1.34.0 \
    soundfile>=0.12.0 \
    pydub>=0.25.0 \
    tenacity>=8.0.0 \
    structlog>=23.0.0 \
    python-dotenv>=1.0.0

# Dev / test only
pip install pytest>=8.0.0 moto>=5.0.0 ruff mypy
```

**Note on PyTorch:** Always install via `--index-url https://download.pytorch.org/whl/cu121` — the default PyPI index ships CPU-only PyTorch. This is the most common cause of "CUDA not available" on first setup.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| boto3 | cloudflare-workers-sdk, rclone | Never for Python. boto3's S3-compatible mode covers R2 fully. rclone adds ops complexity. |
| soundfile | scipy.io.wavfile | scipy is fine for int16 PCM WAV, but soundfile handles float32 without manual normalization — cleaner for model output. |
| pydub + ffmpeg | torchaudio.save() for MP3 | torchaudio can write MP3 via libsox but requires the `[sox]` extra and sox system lib. pydub + ffmpeg is simpler and more portable in Docker. |
| structlog | Python stdlib logging | stdlib logging produces unstructured text lines. structlog JSON output is far easier to parse in RunPod's log viewer. |
| tenacity | manual retry loops | tenacity's `@retry(stop=stop_after_attempt(3), wait=wait_exponential())` is cleaner and battle-tested. |
| FastAPI (local dev only) | Flask | FastAPI's Pydantic integration lets the same `BatchRequest` schema validate both the RunPod handler payload and the local HTTP endpoint — zero duplication. |
| nvidia/cuda:12.1.1-cudnn8-runtime | pytorch/pytorch official image | The official PyTorch image is larger and less controlled. The CUDA runtime base + manual PyTorch wheel install gives explicit version control and a smaller image. |
| Python 3.11 | Python 3.12 | 3.12 works but fewer `nvidia/cuda` base images pre-install it. Avoids `apt` Python version juggling inside Dockerfile. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `pip install torch` (default index) | Ships CPU-only build — CUDA will not be available at runtime. Silent failure: model loads but inference runs on CPU at 100x slower. | `pip install torch --index-url https://download.pytorch.org/whl/cu121` |
| `nvidia/cuda:*-devel` base image | The `devel` image includes compiler toolchain (~5 GB extra). Inference needs only the runtime libs. Pushes image toward 20+ GB unnecessarily. | `nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04` |
| Downloading model at container startup | Cold start would take 3–8 minutes just for model download (4B params ~8 GB). RunPod will timeout. | `huggingface_hub.snapshot_download()` at Docker build time, model baked into image. |
| `asyncio.run()` inside RunPod handler | The `runpod` SDK's handler loop is synchronous by default. Mixing `asyncio.run()` causes event loop conflicts. | Use `async def handler(job)` if async is needed — the SDK supports async handlers natively. |
| `model.generate()` without `torch.no_grad()` | Keeps gradient computation graph in VRAM. On a 4B model this wastes ~3–4 GB of the 24 GB budget. | Always wrap inference in `with torch.no_grad():` or `@torch.inference_mode()`. |
| Pydantic v1 | The project conventions use v2 patterns (`model_config`, `ConfigDict`). Mixing causes import conflicts if any HuggingFace dep pins v1. | Pin `pydantic>=2.7.0` and use `from pydantic import BaseModel, ConfigDict`. |
| `bfloat16` on 3090 | RTX 3090 does not have hardware bfloat16 support (Ampere limitation). Falls back to software emulation — slower than float16. | Use `torch_dtype=torch.float16` for 3090. A5000 also supports float16 natively. bfloat16 only for Hopper/Ada (H100/4090). |
| celery / redis for task queue | Unnecessary for a RunPod serverless model. RunPod handles job queuing externally. Adding a queue inside the worker adds complexity with zero benefit. | Process the entire batch inside a single handler invocation. |

---

## Dockerfile Structure Note

The recommended layer order (to maximise Docker cache reuse during development):

```dockerfile
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# 1. System packages (changes rarely)
RUN apt-get update && apt-get install -y python3.11 python3-pip ffmpeg git

# 2. PyTorch (changes rarely, large layer — cache aggressively)
RUN pip install torch==2.3.1+cu121 torchaudio==2.3.1+cu121 \
    --index-url https://download.pytorch.org/whl/cu121

# 3. Python deps (changes occasionally)
COPY requirements.txt .
RUN pip install -r requirements.txt

# 4. Model download (changes only when model version changes)
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('lglg666/SongGeneration-v2-large')"

# 5. Application code (changes frequently — last layer)
COPY . /app
WORKDIR /app
```

This order ensures the ~10 GB model layer is only re-downloaded when the `snapshot_download` step changes, not on every code edit.

---

## Sources

All version numbers are from training data (knowledge cutoff August 2025). No live network verification was possible (WebSearch, WebFetch, and Bash tools were unavailable in this research session).

**Verify these before pinning in requirements.txt:**
- `runpod` latest: https://pypi.org/project/runpod/
- `transformers` latest: https://pypi.org/project/transformers/
- `torch` CUDA wheel availability: https://download.pytorch.org/whl/cu121
- `boto3` latest: https://pypi.org/project/boto3/
- SongGeneration v2 model card and deps: https://huggingface.co/lglg666/SongGeneration-v2-large

**Confidence by area:**

| Area | Confidence | Reason |
|------|------------|--------|
| RunPod handler pattern | HIGH | Core SDK API is stable; `runpod.serverless.start()` unchanged since v1.3 |
| PyTorch CUDA wheel URL | HIGH | The `download.pytorch.org/whl/cu121` pattern has been stable for years |
| boto3 + R2 S3-compat | HIGH | R2's S3-compatible API is documented by Cloudflare; boto3 `endpoint_url` pattern is standard |
| SongGeneration v2 deps | MEDIUM | Model card not directly checked; transformers/accelerate deps inferred from HuggingFace norm |
| Exact package versions | LOW | Training data cutoff Aug 2025; march 2026 may have newer stable releases |

---

*Stack research for: Batch GPU Audio Generation Service*
*Researched: 2026-03-18*
