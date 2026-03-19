# Architecture Research

**Domain:** Batch GPU Audio Generation Service
**Researched:** 2026-03-18
**Confidence:** HIGH (RunPod handler pattern is well-established; concurrent inference patterns are standard; R2/S3 boto3 integration is stable)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        RunPod Platform                          │
│                                                                 │
│   Caller ──POST──▶  RunPod Job Queue  ──▶  Worker Instance     │
│                                                  │              │
│                                        ┌─────────▼──────────┐  │
│                                        │   Docker Container  │  │
│                                        │                     │  │
│                                        │  handler.py         │  │
│                                        │  (RunPod entrypoint)│  │
│                                        │       │             │  │
│                                        │  generator.py       │  │
│                                        │  (model + upload)   │  │
│                                        └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                                  │
                                                  │ boto3 PUT
                                                  ▼
                                        Cloudflare R2 Bucket
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `Dockerfile` | Build the container image: CUDA base, Python deps, model download | `FROM runpod/pytorch:*-cuda*`, `RUN huggingface-cli download`, `CMD python handler.py` |
| `handler.py` | RunPod entrypoint — parse input, dispatch to generator, return structured result | `import runpod`, `runpod.serverless.start({"handler": handler})` |
| `generator.py` | Load model once at module level, expose `generate_batch()` function, upload to R2 | `MODEL = load_model()` at top level, `asyncio` or `ThreadPoolExecutor` for concurrency |
| `docker-compose.yml` | Local development — mount code, set env vars, GPU passthrough | `runtime: nvidia`, `environment:` for R2 creds |

## Recommended Project Structure

```
songgen-runpod/
├── Dockerfile                  # Image definition
├── docker-compose.yml          # Local dev / test harness
├── handler.py                  # RunPod serverless entrypoint
├── generator.py                # Model loading + inference + R2 upload
├── requirements.txt            # Python dependencies
├── test_input.json             # Sample batch payload for local testing
└── .planning/                  # GSD project planning
```

The four-file core (`Dockerfile`, `handler.py`, `generator.py`, `docker-compose.yml`) matches what RunPod's own examples ship. There is no reason to add layers (routers, services, repositories) — this is a single-concern worker.

## Data Flow

### Request Flow

```
Caller sends POST to RunPod endpoint
  │
  │  { "input": { "tracks": [ {style, mood, bpm, lyrics}, ... ] } }
  ▼
RunPod Job Queue holds job, assigns to warm or cold worker
  │
  ▼
handler.py: handler(job) receives job dict
  │
  │  job["input"]["tracks"]  →  list of track dicts
  ▼
generator.py: generate_batch(tracks)
  │
  │  MODEL already loaded (module-level init on cold start)
  │
  ├── ThreadPoolExecutor(max_workers=2 or 3)
  │     │
  │     ├── Thread 1: generate(track_0) → WAV bytes → MP3 bytes → upload to R2
  │     ├── Thread 2: generate(track_1) → WAV bytes → MP3 bytes → upload to R2
  │     └── (track_N: on failure, log + append error entry, do NOT raise)
  │
  │  Collect results as they complete
  ▼
handler.py: returns result dict
  │
  │  { "tracks": [ {url_wav, url_mp3, duration, tags, error?}, ... ] }
  ▼
RunPod delivers result to caller via job status poll or webhook
```

### Cold Start vs Warm Start

```
Cold start (first invocation or scaled-up worker):
  Container starts
    → Python imports execute
    → generator.py module-level: MODEL = SongGenModel.from_pretrained(...)
    → CUDA graph warm-up (optional but recommended)
    → handler() called with first job
  Total cold start: dominated by model load (~30-60s at 4B params)

Warm start (same worker, subsequent job):
  handler() called immediately
  MODEL already in VRAM — no reload
  Total: near-zero overhead before generation begins
```

This is the central architectural constraint: **model must be loaded at module level, not inside handler()**. Loading inside handler() turns every job into a cold start.

### Track-Level Error Isolation

```
generate_batch(tracks):
  results = []
  for future in as_completed(futures):
    try:
      result = future.result()
      results.append(result)
    except Exception as e:
      results.append({"track_id": ..., "error": str(e), "success": False})
  return results
```

A single track failure never raises to handler level — the batch continues and the error is embedded in the per-track result object.

### Upload Flow (per track)

```
generate(track) returns (wav_bytes, mp3_bytes, metadata)
  │
  ├── R2 key: f"{batch_id}/{track_id}.wav"
  ├── boto3 s3_client.put_object(Body=wav_bytes, ...)
  ├── R2 key: f"{batch_id}/{track_id}.mp3"
  └── boto3 s3_client.put_object(Body=mp3_bytes, ...)
       │
       └── return { url_wav, url_mp3, duration_s, tags }
```

Upload happens immediately after each track completes — no batching of uploads. This allows partial results to be accessible even if the worker crashes mid-batch.

## VRAM Concurrency Constraint

With a 4B param hybrid LLM+Diffusion model at ~22GB VRAM on a 24GB card:

```
Available VRAM:  24,576 MB
Model footprint: ~22,000 MB
Headroom:         ~2,576 MB

Concurrent inference headroom per extra track: ~1,000-1,500 MB (activations)
Practical safe concurrency: 1 (safe) to 2 (tight) on 24GB

--low_mem flag: ~10GB model footprint → concurrency of 2-3 is viable
```

The `max_workers` value in `ThreadPoolExecutor` should be a configurable env var (`CONCURRENCY`, default `1`) so it can be tuned without a rebuild. When using `--low_mem`, set `CONCURRENCY=2`.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| RunPod Serverless | `runpod.serverless.start({"handler": fn})` in `handler.py` | SDK wraps Flask/uvicorn internally; handler receives `{"id": ..., "input": {...}}` |
| HuggingFace Hub | `huggingface-cli download` during Docker build | Model baked into image — no runtime download; requires `HF_TOKEN` build arg if private |
| Cloudflare R2 | boto3 `s3_client` with `endpoint_url=https://<account>.r2.cloudflarestorage.com` | Credentials via env: `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_ENDPOINT_URL` |
| NVIDIA CUDA | PyTorch CUDA device; CUDA toolkit in base image | `torch.cuda.is_available()` guard; model to `device="cuda"` |

### Environment Variables

```
# R2 storage
R2_ENDPOINT_URL=https://<account_id>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=<key>
R2_SECRET_ACCESS_KEY=<secret>
R2_BUCKET=<bucket_name>
R2_PUBLIC_BASE_URL=https://<custom_domain_or_r2_public_url>

# Inference tuning
CONCURRENCY=1          # ThreadPoolExecutor max_workers
USE_LOW_MEM=false      # pass --low_mem to model if true

# Optional
LOG_LEVEL=INFO
```

## Build Order Implications

The component dependency graph determines what to build first:

```
1. Dockerfile (base image, CUDA, deps, model)
        ↓ (nothing works without a valid image)
2. generator.py (model load + generate + upload — core logic)
        ↓ (handler is just a thin wrapper around generator)
3. handler.py (RunPod wiring — validate input, call generator, format output)
        ↓ (docker-compose enables local end-to-end testing)
4. docker-compose.yml (local test harness — mounts code, injects env vars)
```

**Rationale for this order:**

- `Dockerfile` first because all subsequent work runs inside it. A broken image blocks everything.
- `generator.py` second because it owns all the hard problems: model loading, inference, concurrency, upload. This is where most debugging happens. It can be tested independently by calling `generate_batch()` directly in a Python shell inside the container.
- `handler.py` third because it is trivially thin once `generator.py` works. Its job is input validation, calling `generate_batch()`, and returning the result dict.
- `docker-compose.yml` last (or alongside `handler.py`) because it is purely a local development convenience. It can be written speculatively and refined once the other three are stable.

## Anti-Patterns to Avoid

| Anti-Pattern | Consequence | Correct Approach |
|--------------|-------------|-----------------|
| Load model inside `handler()` | Every job pays full cold-start cost (~30-60s) | Load at module level so it persists across jobs on warm workers |
| `ThreadPoolExecutor` larger than VRAM headroom allows | OOM crash mid-batch, job fails entirely | Default `CONCURRENCY=1`, tune up with `--low_mem` only after profiling |
| Upload all files after generation completes | Partial results lost if container crashes | Upload immediately after each track completes |
| Raise exceptions for track failures inside batch loop | Entire batch fails for one bad track | Catch per-track, embed error in result, continue loop |
| Store WAV/MP3 on container filesystem | Files lost after worker terminates; disk may be limited | Stream bytes directly to R2 via `put_object(Body=bytes_buffer)` |
| Hard-code R2 credentials | Security exposure in image; no env overrides | Always read from env vars; never bake into image |

## Sources

- RunPod serverless handler pattern: training knowledge (HIGH confidence — stable SDK pattern since 2023, `runpod.serverless.start` API unchanged)
- HuggingFace model pre-bake in Dockerfile: standard RunPod worker pattern (HIGH confidence)
- boto3 S3-compatible R2 integration: Cloudflare R2 docs pattern (HIGH confidence — S3 API compatibility is explicit Cloudflare guarantee)
- VRAM budget estimates: derived from PROJECT.md stated values (22GB standard, 10GB low_mem) combined with standard PyTorch activation overhead estimates (MEDIUM confidence — exact activation overhead depends on sequence length and batch size at inference time)
- Concurrency recommendation (default 1, max 2-3 on low_mem): derived from VRAM arithmetic (MEDIUM confidence — requires empirical validation against actual model)

---
*Architecture research for: Batch GPU Audio Generation Service*
*Researched: 2026-03-18*
