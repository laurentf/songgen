# Project Research Summary

**Project:** SongGen RunPod
**Domain:** Batch GPU Audio Generation Service
**Researched:** 2026-03-18
**Confidence:** MEDIUM

## Executive Summary

SongGen RunPod is a single-concern GPU inference worker: it receives a JSON batch of track specifications, runs them through the SongGeneration v2 model (lglg666/SongGeneration-v2-large, ~4B params), produces WAV and MP3 files, uploads them to Cloudflare R2, and returns structured URLs to the caller. The canonical pattern for this type of service on RunPod is a four-file architecture — Dockerfile, handler.py, generator.py, docker-compose.yml — with no framework layers, no internal queue, and no persistent state. The RunPod SDK's `runpod.serverless.start()` is the only supported entry point; everything else is application logic inside the handler and generator modules.

The central design constraint is a 24GB VRAM budget shared between a ~22GB model footprint and active inference passes. This forces a sequential-first approach to v1: run one track at a time, validate VRAM headroom empirically, and only introduce concurrency (via ThreadPoolExecutor with configurable `CONCURRENCY` env var) after single-track behaviour is fully characterised. The `--low_mem` flag drops model footprint to ~10GB and opens up 2-3 concurrent tracks; this is the correct path to throughput, not increasing `max_workers` blindly on a standard-precision model.

The highest-probability failure modes cluster around Docker image construction (baking the model in, installing ffmpeg, keeping layer size sane) and infrastructure wiring (R2 credentials validated before GPU time is spent, `local_files_only=True` on `from_pretrained` to hard-fail any runtime download attempt). All of these are Phase 1 concerns. Phase 2 concerns — concurrency, per-track error isolation, and job timeout configuration — must not be introduced until Phase 1 produces a clean, single-track end-to-end pass.

## Key Findings

### Recommended Stack

The stack is Python 3.11 on `nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04` with PyTorch 2.3 (CUDA 12.1 wheel, never default PyPI). HuggingFace Transformers >=4.40.0 and accelerate >=0.30.0 load and run the model; the RunPod SDK (>=1.6.0) is the serverless harness. boto3 uploads to Cloudflare R2 via its S3-compatible endpoint. soundfile writes WAV; pydub + system ffmpeg transcodes to MP3. Pydantic v2 validates all input before any GPU time is consumed. FastAPI and uvicorn are included only for local smoke-testing — they are not deployed.

See `.planning/research/STACK.md` for full version table, installation commands, and Dockerfile layer ordering.

**Core technologies:**
- Python 3.11: runtime — stable CUDA container baseline with PyTorch 2.3 wheel availability
- PyTorch 2.3 + CUDA 12.1: tensor backend — required wheel URL is `download.pytorch.org/whl/cu121`; default PyPI index ships CPU-only
- Transformers >=4.40.0: model loading — SongGeneration v2 uses AutoModelForCausalLM + diffusion components
- runpod >=1.6.0: serverless harness — `runpod.serverless.start({"handler": fn})` is the only supported entry point
- boto3 1.34.x: R2 upload — S3-compatible, requires explicit `endpoint_url`; no Cloudflare-specific SDK needed
- soundfile 0.12.x: WAV output — handles float32 arrays from PyTorch directly without normalization
- pydub 0.25.x + ffmpeg: MP3 transcode — ffmpeg must be explicitly installed via apt in the Dockerfile
- Pydantic v2: input validation — fast-fail on malformed payloads before GPU time is spent

### Expected Features

The MVP (v1) is 10 features that deliver a complete end-to-end pipeline. Concurrency and warm-worker optimisations are v1.x add-ons, deferred until single-track behaviour is validated. Audio post-processing, lyrics generation, and multi-GPU orchestration are explicitly out of scope.

See `.planning/research/FEATURES.md` for the full feature dependency graph and anti-feature rationale.

**Must have (table stakes — v1):**
- Structured batch input (JSON array, per-track: track_id, style, mood, bpm, lyrics, language)
- Model warm load — loaded once at worker init, reused across all tracks in the batch
- Per-track WAV generation — core value delivery
- WAV to MP3 transcode — dual format output via pydub + ffmpeg
- R2 upload for both formats — delivery mechanism; URL returned per track
- Structured response envelope — `{results: [{track_id, wav_url, mp3_url, duration_s}], errors: [{track_id, error}]}`
- Skip-and-continue on track failure — a single bad track must not kill the batch
- Per-track error logging — structured log line per error with track_id, error type, traceback
- Input validation — Pydantic schema, 422 on bad payload before GPU time is spent
- Env-var configuration — R2 creds, model path, LOW_MEM_MODE via environment

**Should have (competitive — v1.x, after v1 validated):**
- Concurrent track generation (2-3 parallel) — needs empirical VRAM profiling first; use CONCURRENCY env var
- Warm worker / concurrency_modifier — reduces cold-start cost for sustained catalogue runs
- Low-memory mode toggle (USE_LOW_MEM=true) — enables 10GB VRAM path for cheaper GPUs
- Per-track metadata in response (tags, duration) — catalogue ingestion convenience

**Defer (v2+):**
- Loudness normalisation (ffmpeg -af loudnorm) — only if raw output levels are inconsistent
- Partial batch resumability — stable track_id passthrough already supported; retry logic is caller-side
- Batch size guardrails — reject oversized batches before timeout

### Architecture Approach

The architecture is intentionally flat: four files, no layers. `Dockerfile` bakes the model into the image at build time. `generator.py` loads the model once at module level and exposes `generate_batch()`, which uses a ThreadPoolExecutor (configurable `CONCURRENCY`, default 1) to run per-track inference, WAV encoding, MP3 transcode, and R2 upload. `handler.py` is a thin wrapper: validate input with Pydantic, call `generate_batch()`, return the result dict to `runpod.serverless.start()`. `docker-compose.yml` provides local GPU passthrough for development. The build order mirrors the dependency graph — Dockerfile first, generator.py second (owns all hard problems), handler.py third, docker-compose.yml last.

See `.planning/research/ARCHITECTURE.md` for full data flow diagrams, VRAM arithmetic, and env var reference.

**Major components:**
1. `Dockerfile` — CUDA base, Python deps, ffmpeg, model baked in via `snapshot_download()`, env vars for cache paths
2. `generator.py` — module-level model singleton, `generate_batch()` with ThreadPoolExecutor, per-track WAV/MP3/upload pipeline, VRAM cleanup between tracks
3. `handler.py` — Pydantic validation, `generate_batch()` dispatch, structured result return to RunPod SDK

### Critical Pitfalls

Research identified 10 pitfalls; the five highest-impact ones that must be addressed in Phase 1 are:

1. **VRAM exhaustion from concurrent inference** — the 22GB model leaves ~2.5GB headroom on a 24GB card. Never enable concurrency without first measuring single-pass VRAM with `nvidia-smi`. Default `CONCURRENCY=1`; only increase with `--low_mem` mode and empirical confirmation.
2. **Runtime model download on cold start** — `from_pretrained()` without a local cache downloads 22GB at job time, exceeding RunPod's execution timeout. Bake the model into the Docker image via `snapshot_download()` at build time; set `local_files_only=True` in code to hard-fail any download attempt.
3. **Model loaded inside the handler function** — every job pays the full 30-90s model load cost. Load at module level so the singleton persists across jobs on warm workers. Logs should show "Loading model" exactly once at startup.
4. **ffmpeg missing from container** — pydub silently depends on a system `ffmpeg` binary absent from CUDA base images. Add `apt-get install -y ffmpeg` explicitly in the Dockerfile; validate with a startup `ffmpeg -version` check.
5. **R2 credential failure after generation completes** — env var misspelling or missing `endpoint_url` causes upload failure after GPU work is done. Run a startup health check that uploads a 1-byte test object before model loading begins.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Container and Single-Track Foundation

**Rationale:** All other work runs inside the Docker container, and all meaningful system behaviour depends on a single clean generation passing end-to-end. The most disruptive pitfalls (cold start from runtime download, model loaded per job, missing ffmpeg, R2 credential failure, VRAM baseline unknown) are all Phase 1 concerns. Resolving them first means every subsequent test is meaningful.

**Delivers:**
- Working Docker image: CUDA base, all Python deps, ffmpeg, model baked in (~30GB image), correct cache env vars
- `generator.py` with module-level model load, single-track `generate()`, WAV output, MP3 transcode, R2 upload
- `handler.py` with Pydantic validation and single-track dispatch
- `docker-compose.yml` for local GPU testing
- Startup health check: env var presence, R2 write test, model load confirmation
- Benchmark: generation time at 30s / 60s / 120s / 270s audio duration; VRAM usage under `nvidia-smi`

**Addresses:** Input validation, model warm load, per-track WAV generation, WAV-to-MP3 transcode, R2 upload, env-var configuration (all v1 must-haves)

**Avoids:** Cold start timeout, runtime model download, model-per-job re-load, missing ffmpeg, R2 credential failure, VRAM baseline unknown

### Phase 2: Batch Processing and Error Isolation

**Rationale:** Phase 1 proves a single track works. Phase 2 extends to N tracks with correct error containment. The skip-and-continue requirement and structured response envelope are batch-only concerns. Job timeout configuration must be set before any multi-track test. Concurrency is explicitly excluded until sequential batch mode is validated.

**Delivers:**
- `generate_batch()` iterating over all tracks sequentially
- Per-track `try/except` with structured error capture (track_id, error type, message)
- Structured response: `{results: [...], errors: [...]}` with track_id passthrough
- RunPod endpoint timeout configured for worst-case batch (10 tracks x 270s ~ 60-90 min budget)
- Test with intentionally malformed tracks confirming skip-and-continue behaviour
- VRAM cleanup (`del tensors; torch.cuda.empty_cache()`) between tracks validated

**Addresses:** Skip-and-continue on failure, per-track error logging, structured response envelope, idempotent track IDs (all v1 must-haves)

**Avoids:** Single track failure killing the batch, job timeout on large batches, VRAM creep across sequential tracks

### Phase 3: Throughput Optimisation (v1.x)

**Rationale:** Sequential batch mode is the safe baseline. Concurrency introduces VRAM race conditions and thread-safety risks (Pitfalls 1 and 6) that cannot be debugged without a working sequential baseline to compare against. Phase 3 is gated on Phase 2 being production-validated.

**Delivers:**
- `CONCURRENCY` env var wiring to `ThreadPoolExecutor(max_workers=...)`
- Empirical VRAM headroom measurement under concurrency (standard precision and `--low_mem`)
- `USE_LOW_MEM` env var enabling `--low_mem` model load path
- Determinism test: same track twice concurrently, verify output matches sequential mode
- RunPod `concurrency_modifier` hook for warm worker signalling
- Updated throughput and cost benchmarks

**Addresses:** Concurrent track generation, warm worker / concurrency_modifier, low-memory mode toggle (all v1.x differentiators)

**Avoids:** VRAM exhaustion from blind concurrency, concurrent generation race conditions on shared model state

### Phase 4: Hardening and Observability (v1.x)

**Rationale:** Once concurrent batch mode is stable, remaining gaps are operational: per-track metadata enrichment, batch size guardrails, and ensuring R2 URLs are accessible to downstream consumers. These are incremental improvements with no architectural risk.

**Delivers:**
- Per-track metadata in response (duration_s computed from audio array, tags from model output)
- Batch size guardrail: reject batches above N tracks with clear 422 before any GPU time
- R2 URL accessibility confirmation (bucket ACL or presigned URL expiry matching consumer SLA)
- Structured logging via structlog (JSON lines per track with track_id, duration, VRAM metrics)

**Addresses:** Per-track metadata in response, batch size guardrails (v1.x and v2 features)

### Phase Ordering Rationale

- Phase 1 before everything else because the Docker image is the execution environment — a broken image invalidates all other work. The pitfall research shows 7 of 10 pitfalls are discoverable in Phase 1; eliminating them first makes every subsequent test meaningful rather than confounded.
- Phase 2 before concurrency because the feature research explicitly flags concurrency as a v1.x add-on that requires sequential validation first. The architecture research confirms concurrency parameters (`max_workers`) should be configurable via env var rather than hardcoded, allowing Phase 3 to tune without a rebuild.
- Phase 3 is gated by Phase 2 production validation because thread-safety failures (Pitfall 6: race conditions on shared model state) produce wrong outputs rather than crashes — they are only detectable by comparing against a known-good sequential baseline.
- Phase 4 is purely additive and carries no architectural risk; it can overlap with Phase 3 testing if resources allow.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** SongGeneration v2 model-specific load pattern — the model card at `lglg666/SongGeneration-v2-large` was not directly accessed during research. Verify `from_pretrained` kwargs, `--low_mem` flag API, and exact tokenizer/processor requirements before writing generator.py. Check the model card for any non-standard generation pipeline.
- **Phase 3:** RunPod `concurrency_modifier` API — the exact hook signature and behaviour for warm-worker signalling should be verified against current RunPod docs (https://docs.runpod.io/serverless) before implementation. Training knowledge confidence is MEDIUM.

Phases with standard patterns (research-phase likely unnecessary):
- **Phase 2:** Batch loop with per-track error isolation is a well-established pattern; the architecture research provides a complete reference implementation. No novel integration points.
- **Phase 4:** structlog JSON logging, boto3 R2 URL construction, and Pydantic response schema extension are all standard library patterns with HIGH confidence documentation.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Core patterns (RunPod SDK, PyTorch CUDA wheels, boto3 R2, pydub+ffmpeg) are HIGH confidence. Exact package versions are LOW — training data cutoff Aug 2025, verify with `pip index versions` before pinning. |
| Features | MEDIUM | MVP feature set is HIGH confidence (derived from PROJECT.md, an authoritative document). Concurrency throughput and cost estimates are MEDIUM — depend on empirical VRAM and generation-time benchmarks not yet available. |
| Architecture | HIGH | RunPod handler pattern (`runpod.serverless.start`), module-level model loading, and boto3 S3-compatible R2 are stable, well-documented patterns with multiple corroborating sources. VRAM arithmetic is MEDIUM — activation overhead estimates require empirical validation. |
| Pitfalls | MEDIUM-HIGH | Most pitfalls are derived from well-documented PyTorch, Docker, and RunPod behaviours (HIGH). RunPod job timeout defaults and SongGeneration v2 generation-time scaling are MEDIUM — must be benchmarked empirically. |

**Overall confidence:** MEDIUM

### Gaps to Address

- **SongGeneration v2 model card:** Load API, `--low_mem` flag exact syntax, tokenizer requirements, and generation parameters not directly verified. Read the model card at `https://huggingface.co/lglg666/SongGeneration-v2-large` before writing `generator.py`.
- **Package versions:** All versions from training data (cutoff Aug 2025). Run `pip index versions <pkg>` for runpod, transformers, boto3, and soundfile before writing `requirements.txt`.
- **Generation time scaling:** The $0.012/song cost estimate from PROJECT.md is likely benchmarked at short durations. Measure empirically at 30s, 60s, 120s, and 270s before committing to batch size and timeout configuration.
- **RunPod endpoint timeout defaults:** Default timeout values may have changed. Verify in RunPod console before any multi-track test.
- **R2 bucket ACL:** Confirm whether downstream consumers access URLs via public bucket or presigned URLs, and set expiry accordingly. This affects URL construction in the upload step.

## Sources

### Primary (HIGH confidence)
- `C:/DEV/sunoapi/.planning/PROJECT.md` — project constraints, GPU/VRAM targets, model identity, cost estimates
- RunPod Python SDK (`runpod.serverless.start` pattern) — training knowledge, stable since SDK v1.3
- PyTorch CUDA wheel index (`download.pytorch.org/whl/cu121`) — stable URL pattern, well-documented
- boto3 + Cloudflare R2 S3-compatible endpoint pattern — explicit Cloudflare R2 guarantee
- Docker multi-stage build + `--no-cache-dir` patterns — industry-standard practice
- PyTorch VRAM lifecycle (`empty_cache`, `no_grad`, tensor deletion) — well-documented PyTorch behaviour
- HuggingFace `from_pretrained` `local_files_only` flag — well-documented API

### Secondary (MEDIUM confidence)
- HuggingFace Transformers >=4.40.0 music generation pipeline support — inferred from HuggingFace release patterns
- VRAM activation overhead estimates (~1-1.5GB per concurrent inference pass) — derived from VRAM arithmetic, requires empirical validation
- RunPod `concurrency_modifier` hook API — training knowledge; verify against current docs
- SongGeneration v2 dependency requirements — inferred from HuggingFace norms; model card not directly accessed
- Diffusion model generation time scaling behaviour — training knowledge; must be benchmarked

### Tertiary (LOW confidence)
- Exact package versions (runpod >=1.6.0, transformers >=4.40.0, boto3 1.34.x, etc.) — training data cutoff Aug 2025; verify with `pip index versions` before pinning
- RunPod serverless job timeout default values — verify in RunPod console; documented defaults change across tiers

---
*Research completed: 2026-03-18*
*Ready for roadmap: yes*
