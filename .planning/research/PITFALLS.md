# Pitfalls Research

**Domain:** Batch GPU Audio Generation Service (RunPod)
**Researched:** 2026-03-18
**Confidence:** MEDIUM-HIGH (training knowledge; web tools unavailable for live verification — flag for spot-check before Phase 1)

---

## Critical Pitfalls

### Pitfall 1: VRAM Exhaustion From Concurrent Inference on a 24GB Budget

**What goes wrong:**
SongGeneration v2 consumes ~22GB at standard precision. Attempting 2-3 concurrent generations on a 24GB A5000/3090 causes OOM kills mid-batch. The worker process dies silently or the CUDA driver returns an unrecoverable error that corrupts the entire batch — not just the individual track.

**Why it happens:**
22GB model weight + 2GB+ per active inference pass (KV cache, diffusion latency buffers, intermediate activations) = 24GB headroom is effectively zero. Parallelism requires memory, not just time-sharing. Devs assume "the model fits, so two passes fit" — they don't. Additionally, Python's garbage collector does not reclaim GPU memory synchronously; `del tensor` does not free VRAM until `torch.cuda.empty_cache()` is called explicitly.

**How to avoid:**
- Treat 22GB as worst-case, not typical. Benchmark actual VRAM usage under `nvidia-smi` for a single generation before adding concurrency.
- If single-pass headroom is less than 3GB, disable concurrency entirely and run sequential. Accept the throughput cost.
- If concurrency is required, use `--low_mem` mode (10GB footprint per the model docs) and measure carefully.
- Never assume `torch.cuda.empty_cache()` is sufficient between tracks — check `torch.cuda.memory_reserved()` before launching the next generation.
- Set a VRAM high-water-mark check before each track: if reserved > threshold, wait or serialize.

**Warning signs:**
- `CUDA out of memory` errors that only appear on track 2 or 3 in a batch, never track 1
- Worker pod terminated by RunPod with exit code 137 (OOM kill from host kernel)
- First track succeeds, subsequent tracks hang at GPU allocation
- `torch.cuda.memory_reserved()` returning values close to total GPU memory after track 1

**Phase to address:** Phase 1 (model loading / single inference validation) — do not proceed to batch/concurrency until single-pass VRAM is measured empirically.

---

### Pitfall 2: Cold Start Timeout From Runtime Model Download

**What goes wrong:**
If model weights are not baked into the Docker image and the worker fetches them from HuggingFace on first invocation, cold start takes 5-15 minutes for a 22GB model. RunPod serverless has a configurable execution timeout, but the default handler timeout (often 300s) is exceeded before the model is ready. The first request fails, RunPod may retry it, and billing continues while doing nothing useful.

**Why it happens:**
Devs follow HuggingFace tutorials that use `from_pretrained("lglg666/SongGeneration-v2-large")` which downloads at runtime. In a notebook this is fine; in a serverless container where the first job must start within the timeout window, it is fatal.

**How to avoid:**
- During Docker image build, run a Python snippet that downloads the model to a fixed path (e.g., `/app/models/songgen-v2`) using `huggingface_hub.snapshot_download()` or equivalent.
- Set `TRANSFORMERS_CACHE` / `HF_HOME` env vars in the Dockerfile to point to this baked-in path so `from_pretrained` finds it locally on startup.
- Verify model is fully present by checking file count or a sentinel file in the build step.
- RunPod Network Volumes can serve as an alternative (model stored on volume, mounted at startup) — but this still incurs mount latency. Baked-in image is faster and more reliable for cold start SLA.
- Set `local_files_only=True` in `from_pretrained` to hard-fail if download is attempted at runtime.

**Warning signs:**
- First invocation after deploy consistently times out
- Worker logs show `Downloading model` or `tqdm` progress bars during handler startup
- Image size is suspiciously small (a 22GB model adds ~22GB to the image layer)
- HuggingFace download metrics show traffic when workers start

**Phase to address:** Phase 1 (Docker image construction) — the image is either correct from the start or every test invocation will be broken.

---

### Pitfall 3: Blocking Model Load Inside the Request Handler

**What goes wrong:**
Model initialization (loading weights, moving to GPU, compiling if using `torch.compile`) happens inside the handler function that RunPod calls per job. Every job pays the full model load cost (30-90 seconds). Concurrent requests do not share the loaded model instance.

**Why it happens:**
Devs scaffold the worker as a simple function and add model loading to it because it "works" in testing. The RunPod Python SDK's `runpod.serverless.start({"handler": handler})` pattern calls `handler` per job — if model load is inside `handler`, it re-runs every time.

**How to avoid:**
- Load model once at module level (outside the handler function) or in an explicit `initialize()` function called before `runpod.serverless.start()`.
- RunPod supports a `concurrency_modifier` and `return_aggregate_stream` for batch-aware workers — understand the lifecycle before structuring the handler.
- Use a module-level singleton: `MODEL = None` with a `get_model()` lazy initializer that checks `MODEL is not None`.
- Keep the model as a global or in a class instance that persists between handler calls within the same worker lifetime.

**Warning signs:**
- Worker logs show "Loading model..." on every job
- Per-job latency is consistently 60+ seconds even for short audio
- GPU utilization spikes from zero at the start of every job (model transfer to GPU)

**Phase to address:** Phase 1 (worker scaffolding) — this is a structural decision that is hard to refactor later without rewriting the handler.

---

### Pitfall 4: Docker Layer Bloat Making Image Unusable

**What goes wrong:**
A naively built Docker image for GPU inference contains: base CUDA image (~6GB), PyTorch + dependencies (~4GB), model weights (~22GB), plus build artifacts = 35-40GB image. Docker Hub and GitHub Container Registry have push size limits. RunPod pulls the image on cold start; pulling a 35GB image takes 3-8 minutes depending on registry proximity and bandwidth.

**Why it happens:**
- Model downloaded during `RUN` step but not in a final stage — intermediate layers with failed downloads remain.
- `pip install` without `--no-cache-dir` leaves pip cache in the layer.
- Build tools (`gcc`, headers) installed but not removed.
- Model downloaded twice (once to verify, once to keep) in separate `RUN` steps.

**How to avoid:**
- Use multi-stage builds: build dependencies in one stage, copy only what's needed to final stage.
- Always `pip install --no-cache-dir` in Dockerfiles.
- Download model in a single `RUN` command and immediately verify — do not split into two layers.
- Remove apt caches: `rm -rf /var/lib/apt/lists/*` in the same `RUN` line as `apt-get install`.
- Use RunPod Network Volumes for model weights if image size is a hard constraint. This trades cold-start download for mount latency — measure both.
- Use `docker history <image>` to audit layer sizes before pushing.

**Warning signs:**
- `docker build` succeeds but `docker push` hangs or times out
- Image size reported by `docker images` exceeds 30GB
- RunPod worker takes more than 5 minutes to reach "ready" state from cold
- Registry reports layer upload errors

**Phase to address:** Phase 1 (Docker image build) — layer structure cannot be reorganized without a full rebuild.

---

### Pitfall 5: RunPod Job Timeout Misconfiguration Silently Killing Long Batches

**What goes wrong:**
A batch of 10 tracks at 3-5 minutes of audio each takes 30-50 minutes of GPU time. RunPod serverless has a per-job execution timeout (default varies by tier; commonly 600s). A batch that exceeds this timeout is killed mid-run. No partial results are returned. R2 uploads for completed tracks may still succeed but the job response contains nothing useful.

**Why it happens:**
Devs test with 1-2 track batches that complete within 10 minutes. They deploy without setting `execution_timeout` in the RunPod endpoint configuration. Production batches hit the default timeout.

**How to avoid:**
- Set `execution_timeout` on the RunPod endpoint to match realistic worst-case batch time. For 10 tracks at 5 min each plus overhead: budget 60-90 minutes.
- Design the job handler to emit partial results progressively: upload each track to R2 as it completes and accumulate the URL list, so even a timeout can be diagnosed (check R2 for partial uploads).
- Consider breaking large batches into smaller jobs at the API level (5 tracks max per job) rather than relying on a single timeout window.
- Log job start time and remaining tracks at regular intervals so timeout can be detected in logs.

**Warning signs:**
- Jobs with >5 tracks fail consistently but jobs with 1-2 tracks succeed
- Worker exit code 143 (SIGTERM from RunPod scheduler) in logs
- R2 has partial uploads but the job API response shows error
- Batch duration in logs cut off at round numbers (600s, 1800s)

**Phase to address:** Phase 2 (batch processing logic) — but the endpoint timeout setting must be configured in Phase 1 before any multi-track testing.

---

### Pitfall 6: Concurrent Generation Race Conditions on Shared Model State

**What goes wrong:**
When running 2-3 generations concurrently with `asyncio` or `ThreadPoolExecutor`, if the model or its tokenizer has mutable state (sampling state, random seeds, attention masks stored as instance attributes), concurrent calls corrupt each other's outputs. One track's lyrics bleed into another. Outputs are wrong but no error is raised.

**Why it happens:**
PyTorch models are not inherently thread-safe. Many HuggingFace generation utilities use module-level state or rely on `torch.manual_seed()` which is global. Concurrent calls from multiple threads share this state without locking.

**How to avoid:**
- For concurrency, prefer `asyncio` with a thread pool (`loop.run_in_executor`) rather than raw threads — at minimum isolate each inference call.
- Set per-call seeds explicitly and reproducibly (e.g., derived from track ID) using `torch.Generator` objects rather than the global seed.
- Treat the model as read-only after loading. All mutable state (generation config, seed, conditioning tensors) must be created fresh per call, never reused.
- Test for output determinism: generate the same track twice sequentially and verify bit-identical output before enabling concurrency.
- If model has internal state mutation (some diffusion schedulers do), use a lock or process-per-track isolation.

**Warning signs:**
- Output quality degrades with concurrency enabled vs. sequential mode
- Tracks occasionally swap lyrics/style with neighboring tracks in the same batch
- Non-deterministic outputs even with fixed seeds
- Model occasionally returns empty audio or NaN tensors

**Phase to address:** Phase 2 (concurrency implementation) — do not enable concurrency until sequential mode is fully validated.

---

### Pitfall 7: MP3 Encoding Dependency Not Available in Container

**What goes wrong:**
`pydub` (common choice for WAV-to-MP3 conversion) requires `ffmpeg` to be installed as a system binary. If `ffmpeg` is not present in the Docker image, `pydub.AudioSegment.export(..., format="mp3")` raises a cryptic error (`FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'`). This is only discovered after model loading succeeds, wasting 30-60 seconds of worker startup before the failure.

**Why it happens:**
`ffmpeg` is not a Python package — it does not appear in `requirements.txt` and is invisible to Python dependency audits. Devs test locally where `ffmpeg` is globally installed (e.g., via Homebrew or system package manager) without realizing it is absent in the base CUDA image.

**How to avoid:**
- Add `RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*` to the Dockerfile explicitly.
- Alternatively use `soundfile` + `lameenc` (pure Python MP3 encoder) to avoid the binary dependency, though quality/speed may differ.
- Add a startup self-test that runs `ffmpeg -version` before the worker registers as ready.
- Consider `imageio-ffmpeg` which bundles a static ffmpeg binary as a Python package.

**Warning signs:**
- `pydub` works in local dev but fails in container
- Error message mentions `ffmpeg` subprocess or `FileNotFoundError`
- Only the WAV output is produced, MP3 step crashes
- Error occurs after model loads successfully (late in startup sequence)

**Phase to address:** Phase 1 (Docker image build) — validate both WAV and MP3 output in the very first end-to-end test.

---

### Pitfall 8: R2 Upload Failure Causing Silent Data Loss

**What goes wrong:**
R2 credentials are injected as RunPod environment variables. If a variable name is misspelled (`R2_ACCESS_KEY` vs `AWS_ACCESS_KEY_ID`), the boto3/S3 client initializes with `None` credentials and fails with a 403 or 400 at upload time — but only when the first upload is attempted. All generation work is lost. The batch returns an error with no files in R2.

Additionally: R2 buckets require CORS and public access to be configured for the intended consumers. An upload that succeeds but produces a private URL that downstream systems cannot read is a silent failure.

**Why it happens:**
Environment variable naming conventions differ between boto3 (`AWS_ACCESS_KEY_ID`), R2 documentation examples (custom names like `R2_ACCESS_KEY_ID`), and RunPod's env var injection. Devs wire them up in one environment and forget to verify in another.

**How to avoid:**
- Add a startup validation step that checks required env vars are present and non-empty before model loading begins. Fail fast with a clear error rather than discovering it after generation.
- Test R2 upload with a tiny dummy file as part of the worker health check (pre-generation).
- Use a consistent naming convention for all env vars and document it in the Dockerfile and RunPod endpoint config.
- Log the R2 bucket name and key prefix at startup (never log credentials) to confirm correct configuration.
- Decide on URL signing strategy upfront: if downstream uses public URLs, configure the R2 bucket for public read access; if using presigned URLs, set expiry appropriate for the consumer's workflow.

**Warning signs:**
- Worker starts and model loads successfully but all batches return upload errors
- `boto3` raises `NoCredentialsError` or `ClientError: Access Denied` at first upload
- R2 bucket is empty after jobs complete
- Logs show correct generation completion but no R2 URLs in response

**Phase to address:** Phase 1 (infrastructure wiring) — validate R2 write access before any generation test.

---

### Pitfall 9: No Graceful Handling of Model Generation Failures Mid-Batch

**What goes wrong:**
The project spec says "skip failed tracks and continue." In practice, unhandled exceptions from the model (OOM, NaN output, tokenizer overflow on long lyrics) propagate up and kill the entire handler, not just the track. The batch returns nothing instead of partial results.

**Why it happens:**
Python's exception propagation is correct behavior — `try/except` must be explicitly placed around per-track generation calls. Devs wrap the outer batch loop but not the inner per-track generation, so the first track failure exits the loop.

**How to avoid:**
- Wrap each track's generation call in its own `try/except` block that catches `Exception` broadly, logs the full traceback, records the track as failed, and continues to the next track.
- Distinguish recoverable errors (long lyrics → truncate and retry, low VRAM → serialize) from unrecoverable ones (CUDA device lost → abort entire batch, no point continuing).
- Always return a structured response that includes both successes and failures. A batch where 9/10 tracks succeed and 1 fails should return 9 URLs plus 1 error entry — not a top-level error.
- After a track fails with an OOM error, call `torch.cuda.empty_cache()` and check VRAM before continuing — the next track may also fail if VRAM is not reclaimed.

**Warning signs:**
- Any single-track test failure returns a 500 from the worker
- Logs show exception traceback followed by worker exit rather than "skipping track N"
- Batch response contains no results even when only one track had malformed input
- Testing with intentionally bad input (empty lyrics, 0 BPM) crashes the entire worker

**Phase to address:** Phase 2 (batch processing logic) — error handling structure must be explicit from the first multi-track implementation.

---

### Pitfall 10: Audio Duration Estimation Mismatch With Actual Generation Time

**What goes wrong:**
The project targets songs up to 4m30 (270 seconds). Generation time for diffusion-based audio models is not linearly proportional to output duration. A 4m30 song may take 8-15x real-time to generate on a single A5000 (i.e., 36-67 minutes). This is not accounted for in timeout budgets, cost estimates, or batch size recommendations.

**Why it happens:**
Cost benchmarks (e.g., the $0.012/song figure from PROJECT.md) are typically measured for shorter outputs (30-60 second clips). Scaling to 270 seconds is not guaranteed to be linear — diffusion steps, attention complexity, and autoregressive decoding may have super-linear scaling.

**How to avoid:**
- Benchmark generation time explicitly for 30s, 60s, 120s, and 270s outputs before committing to batch size assumptions.
- Track generation time per second of output audio as a key metric from day one.
- If 270s generation takes 60+ minutes, the $0.012/song estimate may be wrong by 4-10x.
- Design the timeout budget with the worst-case duration (4m30) in mind, not the average.

**Warning signs:**
- Cost per song in production is 3-5x the estimated $0.012
- Long-format songs consistently hit job timeouts while short songs complete fine
- GPU utilization stays high for far longer than expected per track

**Phase to address:** Phase 1 (single-track validation) — benchmark duration scaling before designing batch sizes or pricing.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Model download at runtime (not baked in image) | Simpler Dockerfile, faster image builds during dev | Every cold start hits HuggingFace; production latency is broken | Never in production; acceptable in local dev only |
| Single global try/except around entire handler | Simple error handling code | First track failure kills batch; no partial results | Never — per-track isolation is required by the spec |
| Hardcoded env var names | Fast initial wiring | Breaks silently when deploying to new environment | Only with a startup env-var validation guard |
| Sequential-only (no concurrency) | Avoids all VRAM/thread-safety complexity | Slower throughput; may not meet throughput targets | Acceptable for v1 if single-track timing is within budget |
| `--low_mem` mode always on | Eliminates OOM risk entirely | Slower generation (extra host-GPU transfers); may impact quality | Acceptable if latency budget allows; benchmark first |
| Skipping MP3 output initially | One less dependency to manage | Downstream consumers may need MP3; WAV-only is a breaking change later | Acceptable as a Phase 1 shortcut if MP3 is deferred explicitly |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| RunPod env vars | Using custom names that clash with boto3 defaults (`AWS_*` vars) | Pick non-conflicting names and validate at startup; document the mapping |
| R2 via boto3 | Forgetting `endpoint_url` parameter (R2 is not AWS S3) | Always pass `endpoint_url="https://<accountid>.r2.cloudflarestorage.com"` explicitly |
| HuggingFace `from_pretrained` | Triggers download in container on first call | Set `local_files_only=True` and `TRANSFORMERS_CACHE` to the baked-in model path |
| RunPod serverless handler | Returning a dict vs. a generator vs. an async function — SDK behavior differs | Read RunPod Python SDK docs for the exact handler signature and return type expected |
| `pydub` MP3 export | Requires system `ffmpeg` binary not in CUDA base images | Explicitly `apt-get install ffmpeg` in Dockerfile or use `imageio-ffmpeg` |
| `torch.cuda.empty_cache()` | Called but VRAM not actually freed if tensors still referenced | Ensure all references to generation tensors are explicitly deleted before calling |
| R2 presigned URLs | Default expiry may be too short for downstream consumer | Set expiry based on consumer SLA; consider public bucket for catalogue use |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Model re-loaded per job | 60-90s overhead every invocation | Load at module level, not in handler | Always in production; only passes unnoticed in single-job tests |
| Concurrency with full VRAM model | OOM kill on track 2+ | Measure VRAM headroom; use `--low_mem` if headroom < 3GB | On first real concurrent batch |
| Synchronous R2 upload blocking generation | Total batch time = generation + upload time stacked | Upload in background thread or after all generation completes | When uploads are slow (large WAV files on congested network) |
| No VRAM cleanup between tracks | VRAM creep; track N+1 OOMs even though track N succeeded | `del tensors; torch.cuda.empty_cache()` between tracks | Manifests at batch size 3-5, invisible in single-track tests |
| MP3 encoding on CPU blocking GPU jobs | GPU idle waiting for CPU-bound ffmpeg | Run MP3 encoding in parallel with next generation | Noticeable at 270s audio (large file, long encoding time) |
| Image pull latency on cold start | >5 min worker startup | Optimize image layers; use RunPod-hosted registry for lower pull latency | Every cold start in production; hidden in warm-worker tests |

---

## "Looks Done But Isn't" Checklist

- [ ] Model loads and generates audio — but only tested with 1 track, never 2-3 concurrent
- [ ] R2 upload works — but with hardcoded test credentials, not the production env vars via RunPod
- [ ] MP3 output works locally — but `ffmpeg` is not in the Docker image
- [ ] Error handling catches exceptions — but at the batch level, not per-track (first failure kills batch)
- [ ] Cold start tested — but with a warm worker that already had the image pulled; true cold start not measured
- [ ] Job completes under timeout — but only tested with 1-2 short tracks; 10x 4m30 tracks not tested
- [ ] Cost estimate validated — but only for short audio; 270s output duration not benchmarked
- [ ] VRAM fits — confirmed for sequential mode but not measured under concurrency
- [ ] `torch.cuda.empty_cache()` called between tracks — but old tensor references not deleted, so memory not actually freed
- [ ] Response includes failed track info — but error response format not tested with intentionally bad input
- [ ] R2 URLs in response are accessible — but bucket ACL not confirmed for downstream consumer

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| VRAM exhaustion from concurrency | Phase 1: Single-track validation — measure VRAM before enabling concurrency | `nvidia-smi` during generation; `torch.cuda.memory_reserved()` logged |
| Cold start from runtime model download | Phase 1: Docker image build | `docker run` container with no internet access; confirm model loads from local path |
| Model loaded inside handler | Phase 1: Worker scaffolding | Check logs — "Loading model" should appear once at startup, not per job |
| Docker layer bloat | Phase 1: Docker image build | `docker images` shows size; test image push to registry |
| Job timeout on large batches | Phase 1: Endpoint config + Phase 2: batch sizing | Test with max batch size (10 tracks x 270s) with timeout configured |
| Concurrent generation race conditions | Phase 2: Concurrency implementation | Determinism test: same track twice concurrently, verify output matches |
| MP3 encoding missing ffmpeg | Phase 1: Docker image build | Run `ffmpeg -version` in container; test end-to-end WAV+MP3 output |
| R2 upload credential failure | Phase 1: Infrastructure wiring | Startup health check uploads a 1-byte test file before model loads |
| No per-track error isolation | Phase 2: Batch processing logic | Inject a deliberately bad track; verify other tracks still succeed |
| Audio duration scaling | Phase 1: Single-track benchmarking | Time generation at 30s / 60s / 120s / 270s; plot scaling curve |

---

## Sources

- RunPod serverless worker architecture: training knowledge, MEDIUM confidence (RunPod docs unavailable for live verification — spot-check https://docs.runpod.io/serverless/workers/overview)
- PyTorch VRAM management patterns (`empty_cache`, tensor lifecycle): training knowledge, HIGH confidence (well-documented PyTorch behavior)
- HuggingFace `from_pretrained` `local_files_only` flag: training knowledge, HIGH confidence
- Docker multi-stage build patterns for GPU inference: training knowledge, HIGH confidence (industry-standard practice)
- boto3 + R2 endpoint_url requirement: training knowledge, HIGH confidence (Cloudflare R2 docs consistently document this)
- `pydub` + `ffmpeg` binary dependency: training knowledge, HIGH confidence (well-known pydub constraint)
- RunPod job timeout behavior: training knowledge, MEDIUM confidence (default values change; verify in RunPod console)
- SongGeneration v2 `--low_mem` mode (10GB): from PROJECT.md, sourced from model documentation
- Diffusion model generation time scaling: training knowledge, MEDIUM confidence (model-specific; must be benchmarked empirically)

---

*Pitfalls research for: Batch GPU Audio Generation Service (RunPod)*
*Researched: 2026-03-18*
