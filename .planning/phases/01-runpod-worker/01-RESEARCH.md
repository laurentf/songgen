# Phase 1: RunPod Worker — Research

**Researched:** 2026-03-18
**Domain:** RunPod Serverless Worker / SongGeneration v2 Python API / Supabase Storage
**Confidence:** MEDIUM — core RunPod SDK and Supabase patterns are HIGH; SongGeneration v2 Python internals are MEDIUM (README is shell-focused; levo_inference.py details sourced from DeepWiki and GitHub code views)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **Python direct** — not generate.sh. Model loaded once at module level via Python API, reused across all tracks in a batch. No subprocess, no temp files.
- **Existing Docker image first** — try `juhayna/song-generation-levo:hf0613`, build custom only if incompatible with v2-large model
- **VRAM mode configurable** — `USE_LOW_MEM` env var (true/false), standard (22GB) by default
- **float16 + torch.inference_mode()** mandatory for VRAM efficiency on 24GB GPUs
- **Array JSON in body** — RunPod standard format: `{"input": {"tracks": [{idx, gt_lyric, descriptions}, ...]}}`
- **Validation**: lightweight — check idx present, gt_lyric non-empty. Don't over-engineer validation.
- **Fields per track**: `idx` (required, string), `gt_lyric` (required, string with segment tags), `descriptions` (optional, comma-separated tags)
- **Enriched response per track**: idx, url, duration, status (success/error), error_message (if error), + parsed descriptions (genre, mood, bpm, gender, instruments), file_size
- **Duration**: read from generated WAV header (Claude picks method)
- **Flat bucket** — all files in `songs/` bucket, no subfolders
- **Naming**: `{idx}_{timestamp}.wav` (e.g., `radio_lofi_001_20260318T100000.wav`)
- **Upload timing**: Claude's discretion (per-track recommended by research for crash resilience)
- **Credentials via env vars**: SUPABASE_URL, SUPABASE_KEY, SUPABASE_BUCKET
- **10 min timeout per track** — generous, covers long 4m30 songs on slower GPUs
- **Simple error reporting**: `status: "success" | "error"`, `error_message` string if error
- **No upload retry** — if Supabase upload fails, mark track as error immediately
- **Per-track isolation** — one track failing never kills the batch

### Claude's Discretion

- WAV duration reading method (scipy vs soundfile vs wave module)
- Upload timing strategy (per-track vs end of batch)
- Exact Pydantic validation schema depth
- Temp file cleanup strategy
- Logging format and verbosity

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| GEN-01 | Worker accepts JSONL batch input (idx, gt_lyric, descriptions per track) | Pydantic `TrackSpec` model validates the input dict; RunPod job dict structure confirmed |
| GEN-02 | Model loaded once at module level, reused across all tracks in batch | `LeVoInference` module-level singleton pattern — instantiate once before `runpod.serverless.start()` |
| GEN-03 | Generates WAV output up to 4m30 per track | `LeVoInference.forward()` returns tensor at 48kHz; `torchaudio.save()` writes WAV |
| GEN-04 | Supports multilingual lyrics (EN, FR, ES minimum) | v2-large supports "zh, en, es, ja, etc." per README — multilingual is built-in |
| GEN-05 | Runs on RunPod serverless (A5000/3090, 24GB VRAM) | 22GB standard, 10GB low_mem; sequential processing within 24GB headroom |
| GEN-06 | Docker image with CUDA + model pre-loaded (existing image or custom) | `juhayna/song-generation-levo:hf0613` as first attempt; custom `FROM nvidia/cuda:12.1.1` if incompatible |
| GEN-07 | float16 + torch.inference_mode() for VRAM efficiency | Wrap `LeVoInference.forward()` call in `torch.inference_mode()` context manager; model loaded with `torch_dtype=torch.float16` |
| BATCH-01 | Sequential processing of N tracks per job | Single for-loop in `generate_batch()`; `CONCURRENCY=1` default |
| BATCH-02 | Per-track error isolation — skip failed track, log error, continue batch | `try/except Exception` per track; append error dict to results; never re-raise |
| BATCH-03 | Track ID (idx) passthrough for input/output correlation | `idx` copied from input to every result entry (success and error) |
| BATCH-04 | Structured JSON response per track (url, idx, tags, duration, status) | Return list of dicts from handler; RunPod serializes as-is |
| STOR-01 | Upload generated WAV to Supabase Storage | `supabase.storage.from_(bucket).upload(path, bytes, file_options)` |
| STOR-02 | Return public URL for each uploaded file | `supabase.storage.from_(bucket).get_public_url(path)` |
| STOR-03 | Credentials via environment variables | `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_BUCKET` read at startup; fail-fast if missing |
</phase_requirements>

---

## Summary

SongGeneration v2 (LeVo) exposes a Python class `LeVoInference` in `tools/gradio/levo_inference.py` and a memory-optimized variant `LeVoInferenceLowMem` in `tools/gradio/levo_inference_lowmem.py`. Both share the same `forward(lyric, description, ...)` signature and return a single audio tensor at 48kHz. The primary integration challenge is that the model is not a standard HuggingFace Transformers model — it is a custom `CodecLM_PL` (PyTorch Lightning) checkpoint with its own config YAML, requiring the entire `tencent-ailab/SongGeneration` repository code to be present alongside the checkpoint files. The existing Docker image `juhayna/song-generation-levo:hf0613` likely contains the repo code but may not include v2-large weights (requiring download at image build time from `lglg666/SongGeneration-v2-large`).

The RunPod serverless SDK pattern is straightforward: `runpod.serverless.start({"handler": fn})` where `fn(job)` receives `job["input"]` and returns a serializable result. Model must be instantiated before calling `start()` so it persists across warm worker invocations. Supabase Storage upload uses `supabase.storage.from_(bucket).upload(path, bytes_data, {"content-type": "audio/wav"})` and public URL retrieval uses `get_public_url(path)`.

The key uncertainty is the exact checkpoint directory structure required by `LeVoInference.__init__(ckpt_path)` — it expects `config.yaml` and `model.pt` inside `ckpt_path`, plus separate `ckpt/` and `third_party/` runtime directories. The planner must include a Wave 0 task to audit the existing Docker image and verify what's present versus what needs downloading.

**Primary recommendation:** Use `LeVoInference` (or `LeVoInferenceLowMem` when `USE_LOW_MEM=true`) as a module-level singleton, call `forward()` inside `torch.inference_mode()`, save output tensor as WAV with `torchaudio.save()`, upload bytes to Supabase Storage, return structured JSON per track.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11 | Runtime | SongGeneration repo tested with 3.10/3.11; ComfyUI wrapper confirms Python 3.11 + torch 2.6 + cu124 works |
| torch | 2.6.0 | Model inference | **Pinned by SongGeneration requirements.txt** — do not change |
| torchaudio | 2.6.0 | Write WAV output | **Pinned by SongGeneration requirements.txt** — must match torch version |
| runpod | 1.8.1 | Serverless worker harness | Latest stable (Nov 2025); `runpod.serverless.start()` unchanged |
| supabase | 2.28.2 | Storage upload + public URL | Latest stable (Mar 2026); Python 3.9+ required |
| pydantic | >=2.7.0 | Input validation | Validate `TrackSpec` and `BatchRequest` schemas |
| structlog | >=23.0 | Structured JSON logging | RunPod captures stdout; JSON lines are queryable |
| python-dotenv | 1.0.x | Local dev env vars | Not deployed on RunPod; for docker-compose local testing |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| soundfile | >=0.12.0 | WAV duration reading | Read sample count + sample rate from header without loading audio data |
| lightning | >=2.5.2 | PyTorch Lightning (required by SongGeneration) | Pinned in SongGeneration requirements.txt |
| omegaconf | (pulled by SongGeneration) | Config YAML loading for model init | Required by `LeVoInference.__init__()` |
| huggingface_hub | ==0.25.2 | Download model weights at Docker build time | Pinned by SongGeneration requirements.txt |

**Note on soundfile for WAV duration:** `soundfile.info(path).frames / soundfile.info(path).samplerate` gives exact duration without loading the audio array into memory. This is the recommended approach — no scipy dependency needed and works on float32 WAV.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| soundfile for duration | Python `wave` stdlib module | `wave` module handles PCM int16 WAV only; torchaudio outputs float32 at 48kHz which may require soundfile or torchaudio.info() |
| supabase-py | boto3 with Supabase S3-compat endpoint | supabase-py is simpler; boto3 adds complexity without benefit since project already chose Supabase not R2 |
| structlog | stdlib logging | stdlib produces unstructured text; structlog JSON is queryable in RunPod logs viewer |

**Duration reading recommendation:** Use `torchaudio.info(path).num_frames / torchaudio.info(path).sample_rate` — torchaudio is already a project dependency, no extra package needed, and handles 48kHz float32 WAV natively.

### Installation

```bash
# SongGeneration dependencies (from their requirements.txt — pin these exactly)
pip install torch==2.6.0 torchaudio==2.6.0 torchvision==0.21.0 \
    --index-url https://download.pytorch.org/whl/cu124

# SongGeneration Python deps
pip install -r requirements.txt  # from tencent-ailab/SongGeneration repo

# Worker-specific additions not in SongGeneration requirements.txt
pip install \
    runpod>=1.7.0 \
    supabase>=2.0.0 \
    pydantic>=2.7.0 \
    structlog>=23.0.0 \
    python-dotenv>=1.0.0 \
    soundfile>=0.12.0
```

**CRITICAL:** torch 2.6.0 is pinned by SongGeneration's requirements.txt. Previous research suggested PyTorch 2.3 + CUDA 12.1 — this is now superseded. Use torch 2.6.0 with the CUDA 12.4 wheel index. The existing `juhayna/song-generation-levo:hf0613` image uses an older PyTorch (confirmed by the sm_50–sm_90 CUDA capability list reported in GitHub Issue #24), which means it predates torch 2.6.0. A custom Docker image is likely needed.

---

## Architecture Patterns

### Recommended Project Structure

```
songgen-runpod/               # repo root
├── Dockerfile                # Custom image (if juhayna image is incompatible)
├── docker-compose.yml        # Local dev + GPU passthrough
├── handler.py                # RunPod entrypoint — thin wrapper
├── generator.py              # LeVoInference singleton + generate_track() + upload
├── schemas.py                # Pydantic models: TrackSpec, BatchRequest, TrackResult
├── storage.py                # Supabase upload + get_public_url helpers
├── requirements.txt          # Worker-specific deps (merged with SongGeneration deps)
├── test_input.json           # Sample 1-track and 3-track payloads
├── tests/
│   ├── test_schemas.py       # TrackSpec validation unit tests
│   ├── test_storage.py       # Storage upload mocked with unittest.mock
│   └── test_handler.py       # Handler response format tests
└── SongGeneration/           # Cloned repo (or COPY of its codeclm/, tools/ etc.)
    ├── codeclm/
    ├── tools/gradio/levo_inference.py
    ├── tools/gradio/levo_inference_lowmem.py
    ├── conf/
    └── ...
```

### Pattern 1: Module-Level Model Singleton

**What:** Instantiate `LeVoInference` (or `LeVoInferenceLowMem`) once before `runpod.serverless.start()` is called.

**When to use:** Always — the only supported pattern for warm worker reuse.

**Example:**
```python
# generator.py
import os
import torch

USE_LOW_MEM = os.environ.get("USE_LOW_MEM", "false").lower() == "true"
CKPT_PATH = os.environ.get("MODEL_CKPT_PATH", "/app/songgeneration_v2_large")

# Import the appropriate inference class from the cloned SongGeneration repo
if USE_LOW_MEM:
    from tools.gradio.levo_inference_lowmem import LeVoInference
else:
    from tools.gradio.levo_inference import LeVoInference

import structlog
log = structlog.get_logger()

log.info("Loading model", ckpt_path=CKPT_PATH, low_mem=USE_LOW_MEM)
MODEL = LeVoInference(ckpt_path=CKPT_PATH)
MODEL.eval()
log.info("Model loaded")
```

This ensures "Loading model" appears exactly once per worker lifetime (success criterion #3).

### Pattern 2: Track Generation with inference_mode

**What:** Wrap the `forward()` call in `torch.inference_mode()` context to prevent gradient tracking.

**When to use:** Every inference call.

**Example:**
```python
# generator.py
def generate_track(track: TrackSpec) -> tuple[bytes, float]:
    """Returns (wav_bytes, duration_seconds)."""
    with torch.inference_mode():
        audio_tensor = MODEL.forward(
            lyric=track.gt_lyric,
            description=track.descriptions,
            gen_type="mixed"
        )
    # audio_tensor shape: [1, channels, samples] at 48kHz
    # Save to temp file then read bytes
    import tempfile, torchaudio, os
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        audio_cpu = audio_tensor.cpu()
        if audio_cpu.dim() == 3:
            audio_cpu = audio_cpu.squeeze(0)  # [channels, samples]
        torchaudio.save(tmp_path, audio_cpu, sample_rate=48000)
        info = torchaudio.info(tmp_path)
        duration = info.num_frames / info.sample_rate
        with open(tmp_path, "rb") as f:
            wav_bytes = f.read()
    finally:
        os.unlink(tmp_path)

    return wav_bytes, duration
```

### Pattern 3: Per-Track Error Isolation

**What:** Each track's generation and upload is wrapped in its own try/except that never propagates to the batch loop.

**When to use:** Always — the only pattern that satisfies BATCH-02.

**Example:**
```python
# generator.py
def generate_batch(tracks: list[dict]) -> list[dict]:
    results = []
    for raw_track in tracks:
        try:
            track = TrackSpec(**raw_track)
        except ValidationError as e:
            results.append({
                "idx": raw_track.get("idx", "unknown"),
                "status": "error",
                "error_message": f"Validation error: {e}"
            })
            continue

        try:
            wav_bytes, duration = generate_track(track)
            url = upload_to_supabase(track.idx, wav_bytes)
            results.append(build_success_result(track, url, duration, len(wav_bytes)))
        except Exception as e:
            log.exception("Track failed", idx=track.idx, error=str(e))
            torch.cuda.empty_cache()  # Reclaim VRAM after failure
            results.append({
                "idx": track.idx,
                "status": "error",
                "error_message": str(e)
            })

    return results
```

### Pattern 4: RunPod Handler Wiring

**What:** Thin handler that delegates to `generate_batch()`.

**Example:**
```python
# handler.py
import runpod
from generator import generate_batch

def handler(job):
    job_input = job["input"]
    tracks = job_input.get("tracks", [])
    if not tracks:
        return {"error": "No tracks provided", "results": []}
    results = generate_batch(tracks)
    return {"results": results}

runpod.serverless.start({"handler": handler})
```

### Pattern 5: Supabase Storage Upload

**What:** Upload WAV bytes to Supabase flat bucket, return public URL.

**Example:**
```python
# storage.py
import os
from datetime import datetime, timezone
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
SUPABASE_BUCKET = os.environ["SUPABASE_BUCKET"]

_client = create_client(SUPABASE_URL, SUPABASE_KEY)

def upload_to_supabase(idx: str, wav_bytes: bytes) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    filename = f"{idx}_{timestamp}.wav"
    _client.storage.from_(SUPABASE_BUCKET).upload(
        path=filename,
        file=wav_bytes,
        file_options={"content-type": "audio/wav", "upsert": "false"}
    )
    return _client.storage.from_(SUPABASE_BUCKET).get_public_url(filename)
```

### Anti-Patterns to Avoid

- **Loading model inside `handler()`**: Every job pays 60–90s cold start cost. Load at module level before `runpod.serverless.start()`.
- **Using subprocess to call generate.sh**: Creates temp files, adds latency, loses the warm model state between tracks. Use Python API directly.
- **Catching exceptions at batch level only**: First track failure kills entire batch. Each track needs its own try/except.
- **Not calling `torch.cuda.empty_cache()` after a failed track**: VRAM creep — subsequent tracks OOM even though they'd fit normally.
- **Uploading all tracks after all generation**: If worker crashes mid-batch, zero files reach Supabase. Upload per-track immediately.
- **`bfloat16` on RTX 3090**: RTX 3090 Ampere does not have hardware bfloat16; falls back to software emulation. Use `float16` only.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Input validation | Custom dict checks | Pydantic `BaseModel` with field validators | Type coercion, error messages, required/optional in one place |
| Audio duration reading | `struct.unpack` WAV header parsing | `torchaudio.info(path).num_frames / sample_rate` | torchaudio already in project; handles float32 48kHz WAV |
| Public URL construction | String concatenation with Supabase URL | `supabase.storage.from_(bucket).get_public_url(path)` | Handles URL encoding and bucket configuration |
| Structured logging | `print()` or custom log formatter | `structlog` with JSON renderer | RunPod log viewer parses JSON; key=value pairs are filterable |
| descriptions parsing | Regex splitting | Simple comma-split + keyword matching on known tags | `descriptions` field is informal — over-engineering regex adds fragility |

**Key insight:** The SongGeneration repo is not a pip-installable package — it must be present as source code in the Docker image. Don't try to install it with pip; clone the repo or COPY it into the Docker image directly.

---

## Common Pitfalls

### Pitfall 1: LeVoInference is NOT a HuggingFace Transformers Model

**What goes wrong:** Treating SongGeneration v2 like a standard HuggingFace model and calling `AutoModel.from_pretrained("lglg666/SongGeneration-v2-large")`. This fails — the model uses a custom `CodecLM_PL` PyTorch Lightning checkpoint structure, not a Transformers-compatible format.

**Why it happens:** The HuggingFace model card for `lglg666/SongGeneration-v2-large` has an empty README, making it look like a standard HuggingFace model.

**How to avoid:** Use `LeVoInference(ckpt_path="./songgeneration_v2_large")` where `ckpt_path` is the directory containing `config.yaml` and `model.pt`. The `tencent-ailab/SongGeneration` GitHub repo code must be present in the Python path.

**Warning signs:** `ImportError` for `codeclm`, `ModuleNotFoundError` for `tools.gradio.levo_inference`.

---

### Pitfall 2: Checkpoint Directory Structure is Non-Standard

**What goes wrong:** Pointing `LeVoInference(ckpt_path=...)` at the wrong directory or missing the separate `ckpt/` and `third_party/` runtime folders.

**Why it happens:** SongGeneration v2 requires MULTIPLE directories:
- `./songgeneration_v2_large/` — the model weights (from `lglg666/SongGeneration-v2-large`)
- `./ckpt/` — shared runtime checkpoint files
- `./third_party/` — Demucs separator model and other runtime deps

All three must be present at the expected relative paths from the working directory.

**How to avoid:** In Dockerfile, download all three from HuggingFace and place them in the project root. Verify structure by running a dummy inference during image build.

**Warning signs:** `FileNotFoundError: config.yaml not found in ckpt_path`, KeyError on config keys at startup.

---

### Pitfall 3: Existing Docker Image Likely Predates v2-large

**What goes wrong:** Pulling `juhayna/song-generation-levo:hf0613` and assuming it works with the v2-large model. The image uses PyTorch with CUDA capabilities sm_50–sm_90, which predates torch 2.6.0. The v2-large checkpoint was released March 9, 2026 — after the image was built.

**Why it happens:** The hf0613 tag suggests a June 2023 or similar build date, well before v2-large.

**How to avoid:** Audit the image first with `docker run juhayna/song-generation-levo:hf0613 python -c "import torch; print(torch.__version__)"`. If torch version is below 2.6.0 or the SongGeneration repo code is v1 only, build a custom image from scratch.

**Warning signs:** `AttributeError` on new v2 model features, version mismatch errors, missing `levo_inference_lowmem.py`.

---

### Pitfall 4: torch 2.6.0 CUDA Wheel URL Changed

**What goes wrong:** Installing torch with the cu121 wheel URL (`https://download.pytorch.org/whl/cu121`) fails to find torch 2.6.0 — that version ships with cu124 wheels.

**How to avoid:** Use `--index-url https://download.pytorch.org/whl/cu124` for torch 2.6.0. The A5000 and 3090 support CUDA 12.4 drivers on RunPod.

**Warning signs:** pip reports "No matching distribution found for torch==2.6.0" when using cu121 wheel URL.

---

### Pitfall 5: Supabase Storage Upload Requires Bucket to Be Public

**What goes wrong:** `get_public_url()` returns a URL that returns 403 when accessed. The method does NOT verify bucket publicity — it just constructs a URL string.

**How to avoid:** Configure the `songs` bucket as public in the Supabase dashboard (Storage > Bucket > Make Public) before running any tests. This is a one-time setup step, not code.

**Warning signs:** `get_public_url()` returns a URL, but HTTP GET on that URL returns 403 or 400.

---

### Pitfall 6: RunPod Default executionTimeout is 600s (10 min)

**What goes wrong:** A single track that generates a 4m30 song on an A5000 may take 8–15 minutes (RTF ~0.82 on H20 means much slower on A5000). Default 10-minute timeout kills the job mid-generation.

**Why it happens:** The `executionTimeout` endpoint setting defaults to 600 seconds. A 3-track batch at 10 min each = 30 min needed, but default allows only 10 min total.

**How to avoid:** Set `executionTimeout` in the RunPod endpoint "Advanced" settings BEFORE testing multi-track batches. For 10-track worst-case at 15 min each: set to 10800s (3 hours). Can also override per-request via `executionTimeout` in job policy.

**Warning signs:** Job shows `FAILED` after exactly 600 seconds. Logs cut off mid-generation.

---

### Pitfall 7: supabase-py upload() Accepts bytes, Not File Path

**What goes wrong:** Calling `upload(path="...", file="/tmp/output.wav")` with a file path string instead of bytes. The method expects a `BinaryIO` object or bytes.

**How to avoid:** Read file as bytes: `open(path, "rb").read()` or pass `io.BytesIO(wav_bytes)`. Or use a temp file approach and pass the open file handle in binary mode.

---

## Code Examples

Verified patterns from official sources:

### LeVoInference Loading (DeepWiki, GitHub source)
```python
# Source: tools/gradio/levo_inference.py (tencent-ailab/SongGeneration)
import sys
sys.path.insert(0, "/app/SongGeneration")  # Make repo code importable

from tools.gradio.levo_inference import LeVoInference
from tools.gradio.levo_inference_lowmem import LeVoInference as LeVoInferenceLowMem

# ckpt_path must contain config.yaml and model.pt
MODEL = LeVoInference(ckpt_path="/app/songgeneration_v2_large")
MODEL.eval()
```

### LeVoInference forward() call
```python
# Source: tools/gradio/levo_inference.py — forward() method signature confirmed
import torch

with torch.inference_mode():
    audio_tensor = MODEL.forward(
        lyric=track.gt_lyric,         # str with [verse], [chorus] tags
        description=track.descriptions,  # str or None — "female, pop, sad"
        gen_type="mixed"              # "mixed" = vocals + accompaniment
    )
# Returns: tensor shape [1, channels, samples] at 48kHz sample rate
```

### Save tensor as WAV + get duration
```python
# torchaudio.save — official torchaudio docs
import torchaudio, tempfile, os

with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
    tmp_path = tmp.name

audio_cpu = audio_tensor.cpu()
if audio_cpu.dim() == 3:
    audio_cpu = audio_cpu.squeeze(0)  # [channels, samples]
torchaudio.save(tmp_path, audio_cpu, sample_rate=48000)

info = torchaudio.info(tmp_path)
duration_seconds = info.num_frames / info.sample_rate  # e.g., 270.0
```

### RunPod handler pattern
```python
# Source: https://docs.runpod.io/serverless/workers/handler-functions
import runpod

def handler(job):
    job_input = job["input"]   # Dict from caller's {"input": {...}}
    # ... process ...
    return {"results": [...]}  # Must be JSON-serializable

runpod.serverless.start({"handler": handler})
```

### Supabase Storage upload + public URL
```python
# Source: https://supabase.com/docs/reference/python/storage-from-upload
# Source: https://supabase.com/docs/reference/python/storage-from-getpublicurl
from supabase import create_client

client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Upload bytes
client.storage.from_(SUPABASE_BUCKET).upload(
    path=filename,          # "radio_lofi_001_20260318T100000.wav"
    file=wav_bytes,         # bytes
    file_options={
        "content-type": "audio/wav",
        "upsert": "false"
    }
)

# Get public URL (bucket must be configured as public in Supabase dashboard)
url = client.storage.from_(SUPABASE_BUCKET).get_public_url(filename)
# Returns: "https://<project>.supabase.co/storage/v1/object/public/songs/filename.wav"
```

### descriptions parsing
```python
# Simple extraction from "female, lo-fi, chill, piano and vinyl, the bpm is 85"
import re

def parse_descriptions(desc: str | None) -> dict:
    if not desc:
        return {}
    parts = [p.strip().lower() for p in desc.split(",")]
    result = {}
    for part in parts:
        if part in ("male", "female"):
            result["gender"] = part
        elif m := re.match(r"the bpm is (\d+)", part):
            result["bpm"] = int(m.group(1))
        # genre, mood, instruments: collect remaining as lists
    return result
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PyTorch 2.3 + CUDA 12.1 | PyTorch 2.6.0 + CUDA 12.4 | SongGeneration requirements.txt pinned 2026-03 | Must use cu124 wheel URL, not cu121 |
| boto3 + Cloudflare R2 | supabase-py + Supabase Storage | Project decision 2026-03-18 | Different auth model; supabase-py not boto3 |
| generate.sh subprocess | LeVoInference Python class directly | v2 release 2026-03 | No temp files, model persists, proper VRAM control |
| torchaudio.save() → FLAC | torchaudio.save() → WAV | Project decision | Phase 1 outputs WAV; MP3 is Phase 2 |

**Deprecated/outdated (from earlier research):**
- `transformers>=4.40.0` for SongGeneration: Not a Transformers model — do not use `AutoModel.from_pretrained`. Use `LeVoInference` class.
- `pydub` + `ffmpeg` for audio output: Not needed in Phase 1. Phase 1 outputs WAV only; MP3 conversion is Phase 2.
- `boto3` for upload: Not needed; project uses supabase-py.
- PyTorch 2.3 cu121: Superseded by 2.6.0 from SongGeneration requirements.txt.

---

## Open Questions

1. **Does `juhayna/song-generation-levo:hf0613` include v2-large weights?**
   - What we know: Image was built before March 2026 v2-large release; GitHub Issue #24 shows PyTorch predates 5xxx series, suggesting old build
   - What's unclear: Whether v1 or v2 weights are baked in; whether LeVoInference class is present
   - Recommendation: Wave 0 task — `docker run juhayna/song-generation-levo:hf0613 python -c "import torch; print(torch.__version__); from tools.gradio.levo_inference import LeVoInference; print('OK')"`. If fails, build custom image.

2. **Exact `config.yaml` keys required by `LeVoInference.__init__()`**
   - What we know: OmegaConf loads config.yaml; configures LM, audio tokenizer, separator; `ckpt_path` contains `config.yaml` and `model.pt`
   - What's unclear: Whether config.yaml is part of the model download or the repo — and exact expected key names
   - Recommendation: After cloning repo and downloading weights, inspect `./songgeneration_v2_large/config.yaml` structure before writing generator.py init code.

3. **Exact tensor shape from `LeVoInference.forward()` — [1, 2, N] or [2, N]?**
   - What we know: Returns `wav_seperate[0]`; DeepWiki says shape `[1, channels, samples]`; output is 48kHz stereo
   - What's unclear: Whether the outer batch dimension is always 1, and whether it's pre-squeezed
   - Recommendation: Add a shape assertion + normalization in `generate_track()`: `if tensor.dim() == 3: tensor = tensor.squeeze(0)`.

4. **RunPod endpoint timeout for multi-track batches**
   - What we know: Default `executionTimeout` is 600s; max is 7 days; configurable in "Advanced" settings
   - What's unclear: Actual per-track generation time on A5000 for a 4m30 song (RTF known for H20 at 0.82, A5000 likely 2–4x slower)
   - Recommendation: Phase 1 Wave 1 task — benchmark a single 3-min track on A5000 before planning batch timeouts.

---

## Validation Architecture

nyquist_validation is enabled in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | none — Wave 0 creates `pytest.ini` |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| GEN-01 | TrackSpec validates required fields | unit | `pytest tests/test_schemas.py -x` | Wave 0 |
| GEN-01 | Missing idx raises ValidationError | unit | `pytest tests/test_schemas.py::test_missing_idx -x` | Wave 0 |
| GEN-01 | Missing gt_lyric raises ValidationError | unit | `pytest tests/test_schemas.py::test_missing_lyric -x` | Wave 0 |
| GEN-02 | "Loading model" appears once in logs | manual/smoke | `pytest tests/test_handler.py::test_model_loaded_once` | Wave 0 |
| GEN-03 | WAV output has non-zero duration | integration | manual — requires GPU | manual-only |
| GEN-04 | French lyrics accepted without error | integration | manual — requires GPU | manual-only |
| GEN-05 | Single track completes without OOM | integration | manual — requires RunPod A5000 | manual-only |
| GEN-06 | Docker image builds successfully | smoke | `docker build . --no-cache` | manual-only |
| GEN-07 | inference_mode used in generate_track | unit | `pytest tests/test_generator.py::test_inference_mode` | Wave 0 |
| BATCH-01 | 3-track batch returns 3 results | unit (mocked) | `pytest tests/test_handler.py::test_batch_3_tracks` | Wave 0 |
| BATCH-02 | Invalid track returns error, others succeed | unit (mocked) | `pytest tests/test_handler.py::test_per_track_isolation` | Wave 0 |
| BATCH-03 | idx is present in every result entry | unit (mocked) | `pytest tests/test_handler.py::test_idx_passthrough` | Wave 0 |
| BATCH-04 | Success result has url, duration, status, tags | unit (mocked) | `pytest tests/test_handler.py::test_result_schema` | Wave 0 |
| STOR-01 | Supabase upload called with wav bytes | unit (mocked) | `pytest tests/test_storage.py::test_upload_called` | Wave 0 |
| STOR-02 | Public URL returned for uploaded file | unit (mocked) | `pytest tests/test_storage.py::test_public_url` | Wave 0 |
| STOR-03 | Missing SUPABASE_URL raises at startup | unit | `pytest tests/test_storage.py::test_missing_env_fails` | Wave 0 |

**Note on GPU tests:** GEN-03, GEN-04, GEN-05 require actual GPU inference and cannot be automated in CI. They are manual smoke tests run against a RunPod endpoint.

### Sampling Rate

- **Per task commit:** `pytest tests/ -x -q` (unit tests only, < 10s)
- **Per wave merge:** `pytest tests/ -v` (full unit suite)
- **Phase gate:** Full unit suite green + manual GPU smoke test documented in verification checklist

### Wave 0 Gaps

- [ ] `tests/test_schemas.py` — Pydantic validation for TrackSpec, BatchRequest
- [ ] `tests/test_handler.py` — Handler response format with mocked generate_batch
- [ ] `tests/test_storage.py` — Supabase upload with `unittest.mock.patch`
- [ ] `tests/test_generator.py` — generate_track() with mocked MODEL.forward()
- [ ] `pytest.ini` — test discovery config
- [ ] `tests/conftest.py` — shared fixtures (sample TrackSpec, mock wav bytes)

---

## Sources

### Primary (HIGH confidence)

- `https://github.com/tencent-ailab/SongGeneration/blob/main/tools/gradio/levo_inference.py` — `LeVoInference` class, `forward()` signature, return value
- `https://github.com/tencent-ailab/SongGeneration/blob/main/tools/gradio/levo_inference_lowmem.py` — `LeVoInferenceLowMem` (same forward() signature, OffloadProfiler internals)
- `https://github.com/tencent-ailab/SongGeneration/blob/main/requirements.txt` — pinned versions: torch==2.6.0, torchaudio==2.6.0, transformers==4.37.2
- `https://docs.runpod.io/serverless/workers/handler-functions` — handler function signature, job dict structure, return types
- `https://docs.runpod.io/serverless/references/endpoint-configurations` — executionTimeout default 600s, max 7 days
- `https://supabase.com/docs/reference/python/storage-from-upload` — upload() method signature
- `https://supabase.com/docs/reference/python/storage-from-getpublicurl` — get_public_url() method
- `https://pypi.org/project/supabase/` — v2.28.2 (Mar 2026)
- `https://pypi.org/project/runpod/` — v1.8.1 (Nov 2025)

### Secondary (MEDIUM confidence)

- `https://deepwiki.com/tencent-ailab/SongGeneration` — checkpoint structure, ckpt_path layout, `LeVoInference.__init__()` details, 48kHz sample rate
- `https://github.com/tencent-ailab/SongGeneration/blob/main/README.md` — v2-large VRAM requirements (22GB/28GB), multilingual support, checkpoint download instructions
- `https://github.com/tencent-ailab/SongGeneration/issues/24` — confirms existing Docker image predates torch 2.6.0; sm_50–sm_90 CUDA caps only

### Tertiary (LOW confidence — needs validation)

- Tensor output shape `[1, channels, samples]` — inferred from DeepWiki architecture diagrams; validate empirically on first run
- `juhayna/song-generation-levo:hf0613` contents — unconfirmed; Docker Hub page did not return readable metadata

---

## Metadata

**Confidence breakdown:**

| Area | Level | Reason |
|------|-------|--------|
| Standard stack (torch version) | HIGH | Pinned in SongGeneration requirements.txt — definitive |
| RunPod handler pattern | HIGH | Official RunPod docs verified live |
| Supabase Storage API | HIGH | Official Supabase docs verified live; v2.28.2 confirmed |
| LeVoInference class API | MEDIUM | Source code viewed via GitHub; key details from DeepWiki synthesis |
| Checkpoint directory structure | MEDIUM | README + DeepWiki confirm 3-directory layout; exact file names need empirical verification |
| Output tensor shape | LOW | Inferred from architecture diagrams; must be confirmed on first run |
| Existing Docker image compatibility | LOW | Cannot inspect image internals without pulling; strong circumstantial evidence it's incompatible with v2-large |

**Research date:** 2026-03-18
**Valid until:** 2026-04-18 (SongGeneration is actively developed; check for repo updates before building)
