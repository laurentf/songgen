# Feature Research

**Domain:** Batch GPU Audio Generation Service
**Researched:** 2026-03-18
**Confidence:** MEDIUM — WebSearch and WebFetch unavailable; derived from PROJECT.md constraints, established batch GPU inference patterns, RunPod serverless architecture (training knowledge), and audio pipeline engineering conventions.

---

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Structured batch input | Operator sends N tracks in one request; per-track: style, mood, bpm, lyrics, language | Low | Already defined in PROJECT.md. JSON array of track objects. |
| WAV + MP3 dual output per track | WAV for archival/quality; MP3 for distribution. Missing either breaks downstream | Low | ffmpeg conversion after generation. Decision already made. |
| R2 upload + URL return | Batch is useless without delivery. URLs must be stable and catalogue-ready | Medium | S3-compatible boto3 client. One upload per format per track. |
| Structured response envelope | Operator needs to know: which tracks succeeded, which failed, file URLs, duration | Low | JSON: `{results: [{track_id, wav_url, mp3_url, duration_s, tags}], errors: [{track_id, error}]}` |
| Skip-and-continue on track failure | Single bad track must not kill the batch. Operator submits 20 tracks, gets 18 | Low | try/except per track, append to errors list, continue loop |
| Per-track error logging | Errors must be diagnosable. Silent failure is worse than reported failure | Low | Structured log line per error: track_id, error type, message, traceback |
| Model loaded once, reused across batch | Loading 4B params per track would be unusably slow and expensive | High | Worker initialisation block; model stays in VRAM between tracks |
| Idempotent track IDs | Operator must be able to correlate input tracks to output results | Low | Pass-through: operator-supplied `track_id` echoed in response |
| Input validation with clear errors | Malformed input should fail fast before any GPU time is consumed | Low | Pydantic model for request schema; validation errors returned as 422 |
| Environment-based configuration | RunPod serverless has no persistent config store; env vars are the mechanism | Low | R2 creds, model path, concurrency setting all via env vars |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Concurrent track generation (2-3 tracks) | Reduces wall-clock time for a batch proportionally. A 10-track batch at 3x concurrency finishes in ~1/3 the time | High | ThreadPoolExecutor or asyncio with VRAM budget guard. Must not OOM on 24GB. Needs empirical tuning per model config (standard vs --low_mem). |
| Per-track generation metadata in response | Tags, detected BPM, duration returned alongside URLs let downstream catalogue skip a metadata extraction step | Medium | Some metadata available from model output; duration computable from audio length |
| Warm worker reuse (RunPod concurrency_modifier) | Keeping worker alive between jobs eliminates cold start for subsequent batches. Critical for throughput at scale | Medium | RunPod `concurrency_modifier` hook lets worker signal availability. Model stays loaded. |
| Partial batch resumability (track-level idempotency) | If a batch of 20 fails at track 15, operator can resubmit only the 15 failed tracks without regenerating the first 14 | Medium | Requires operator-supplied stable track IDs and operator-side retry logic. Service just needs to honour track_id passthrough faithfully. |
| Low-memory mode toggle | `--low_mem` drops VRAM from 22GB to 10GB, opening up cheaper GPUs. Operator-selectable via env var | Low | Already in model; just surface as `LOW_MEM_MODE=true` env var |
| Language-aware generation signal | Explicit `language` field per track (EN/FR/ES) prevents the model defaulting to a wrong language distribution | Low | Pass language hint through to model call. Already in scope but worth surfacing as deliberate feature |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Web UI / dashboard | Operators want visibility into batch status | Out of scope by design; adds frontend complexity, auth, hosting cost with no value for a pipeline service | RunPod's own console shows job status. Structured JSON logs are sufficient for operators. |
| Real-time streaming / progressive delivery | Users want to hear each track as it finishes rather than waiting for the whole batch | Incompatible with RunPod serverless synchronous job model. Adds webhook/SSE complexity. Batch-mode radio catalogue doesn't need it | Return all results in final response. If partial delivery needed, split into smaller batches at the call site. |
| Audio post-processing (mastering, EQ, normalisation) | Better-sounding output for distribution | Adds ffmpeg DSP complexity, non-deterministic output quality, and per-track latency. Model output quality should be validated first before adding transforms | Out of scope v1. Can add loudness normalisation (ffmpeg -af loudnorm) as a later feature if raw output is inconsistent. |
| Lyrics generation | End-to-end "topic → song" feels complete | Upstream already generates lyrics. Adding an LLM call here creates a second model dependency, more VRAM pressure, and scope creep | Lyrics are a required input field. Document this clearly. |
| Multi-GPU orchestration / sharding | Scale to larger batches | Single-GPU per RunPod worker is the architecture. Multi-GPU adds scheduler complexity that RunPod itself handles at the fleet level | Scale horizontally: submit multiple RunPod jobs from the caller side. |
| Per-track quality scoring / rejection | Auto-reject low-quality outputs | Requires a second audio quality model (e.g. DNSMOS), adds latency and another dependency. Premature optimisation before validating base generation quality | Log generation params alongside output. Let downstream catalogue apply quality gates. |
| Authentication / API keys on the worker | Secure the endpoint | RunPod serverless endpoints already have token-based auth at the gateway level. Implementing auth inside the worker duplicates this and adds complexity | Use RunPod's built-in endpoint authentication. Document the auth header. |
| Persistent job queue / database | Track historical batches | RunPod maintains job history. Adding a database to the worker breaks stateless architecture | Query RunPod job history API for audit trail. |

---

## Feature Dependencies

```
Input validation (Pydantic) → must exist before any generation begins

Model initialisation (warm load) → required before:
  - Concurrent generation
  - Any per-track generation

Per-track generation → required before:
  - WAV/MP3 encoding
  - R2 upload
  - Metadata extraction

WAV encoding → required before MP3 encoding (MP3 transcode from WAV)

R2 upload (both formats) → required before URL inclusion in response

Per-track error capture → feeds into structured response envelope

Structured response envelope → final return to RunPod job system

---

Concurrency is parallel at the generation step only:
  Track A: [generate] → [encode WAV] → [encode MP3] → [upload WAV] → [upload MP3]
  Track B: [generate] → [encode WAV] → [encode MP3] → [upload WAV] → [upload MP3]
  Track C: [generate] → ...
  (2-3 tracks in parallel, VRAM budget permitting)

Low-memory mode toggle → affects model initialisation; must be set before model load
```

---

## MVP Definition

### Launch With (v1)

These are the minimum set to validate the pipeline end-to-end and deliver to the radio catalogue.

1. **Structured batch input** — JSON array, per-track: track_id, style, mood, bpm, lyrics, language
2. **Model warm load** — loaded once at worker init, reused across all tracks in batch
3. **Per-track WAV generation** — core value delivery
4. **WAV to MP3 transcode** — dual format output
5. **R2 upload for both formats** — delivery mechanism
6. **Structured response** — {results, errors} with track_id, wav_url, mp3_url, duration_s
7. **Skip-and-continue on failure** — batch resilience
8. **Per-track error logging** — diagnosability
9. **Input validation** — fast-fail on bad requests before GPU time is spent
10. **Env-var configuration** — R2 creds, model path, optional LOW_MEM_MODE

### Add After Validation (v1.x)

Once v1 is running in production and base quality is confirmed:

11. **Concurrent track generation (2-3 parallel)** — throughput optimisation; needs empirical VRAM profiling first to set safe concurrency limit
12. **Warm worker / concurrency_modifier** — reduce cold-start cost for sustained catalogue generation runs
13. **Low-memory mode toggle** — enables 10GB VRAM path for cheaper GPU options
14. **Per-track metadata in response** — adds tags, detected duration to response for catalogue ingestion

### Future Consideration (v2+)

Only if v1 validates and the catalogue pipeline has real throughput needs:

15. **Loudness normalisation** — ffmpeg -af loudnorm pass after encoding if raw output has inconsistent levels
16. **Partial batch resumability** — resubmit-failed-tracks workflow, requires stable track_id discipline on caller side
17. **Batch size guardrails** — reject batches above N tracks with clear error to prevent single-job timeouts on RunPod

---

## Sources

- `C:/DEV/sunoapi/.planning/PROJECT.md` — primary constraints, out-of-scope decisions, GPU/VRAM targets (HIGH confidence — authoritative project document)
- RunPod serverless architecture patterns — training knowledge re: worker lifecycle, concurrency_modifier, job response schema (MEDIUM confidence — verify against current RunPod docs at https://docs.runpod.io/serverless)
- Batch GPU inference design patterns — generalised from established ML serving patterns (threadpool concurrency, warm model, VRAM budgeting) (MEDIUM confidence)
- Audio pipeline conventions (WAV-first, MP3 transcode, S3-compatible upload) — widely established practice (HIGH confidence)

---

*Feature research for: Batch GPU Audio Generation Service*
*Researched: 2026-03-18*
