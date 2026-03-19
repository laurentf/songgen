# Phase 1: RunPod Worker - Context

**Gathered:** 2026-03-18
**Status:** Ready for planning

<domain>
## Phase Boundary

A RunPod serverless worker that accepts JSON array batches of tracks (idx, gt_lyric, descriptions), generates WAV audio via SongGeneration v2 (Python API, not generate.sh), uploads files to Supabase Storage, and returns structured JSON responses with URLs, parsed metadata, and duration. Sequential processing, per-track error isolation.

</domain>

<decisions>
## Implementation Decisions

### Model Integration
- **Python direct** — not generate.sh. Model loaded once at module level via Python API, reused across all tracks in a batch. No subprocess, no temp files.
- **Existing Docker image first** — try `juhayna/song-generation-levo:hf0613`, build custom only if incompatible with v2-large model
- **VRAM mode configurable** — `USE_LOW_MEM` env var (true/false), standard (22GB) by default
- **float16 + torch.inference_mode()** mandatory for VRAM efficiency on 24GB GPUs

### Input Contract
- **Array JSON in body** — RunPod standard format: `{"input": {"tracks": [{idx, gt_lyric, descriptions}, ...]}}`
- **Validation**: lightweight if not complex — check idx present, gt_lyric non-empty. Don't over-engineer validation.
- **Fields per track**: `idx` (required, string), `gt_lyric` (required, string with segment tags), `descriptions` (optional, comma-separated tags)

### Output Contract
- **Enriched response per track**: idx, url, duration, status (success/error), error_message (if error), + parsed descriptions (genre, mood, bpm, gender, instruments), file_size
- **Duration**: read from generated WAV header (Claude picks method — scipy/soundfile/wave)

### Supabase Upload
- **Flat bucket** — all files in `songs/` bucket, no subfolders
- **Naming**: `{idx}_{timestamp}.wav` (e.g., `radio_lofi_001_20260318T100000.wav`)
- **Upload timing**: Claude's discretion (per-track recommended by research for crash resilience)
- **Credentials via env vars**: SUPABASE_URL, SUPABASE_KEY, SUPABASE_BUCKET

### Error Handling
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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Model
- `docs/songgen-input-format.md` — SongGeneration v2 input format: JSONL structure, lyric segment rules, descriptions field dimensions
- GitHub repo `tencent-ailab/SongGeneration` — Python API, model loading, generation parameters

### RunPod
- RunPod serverless handler pattern — `runpod.serverless.start({"handler": fn})`

### Research
- `.planning/research/STACK.md` — Recommended stack (PyTorch 2.3, CUDA 12.1, boto3, etc.)
- `.planning/research/ARCHITECTURE.md` — Component boundaries, data flow, module-level model loading pattern
- `.planning/research/PITFALLS.md` — VRAM management, cold start, Docker image construction pitfalls

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project

### Established Patterns
- None — first phase establishes patterns

### Integration Points
- Supabase Storage (S3-compatible via supabase-py or boto3 with endpoint_url)
- RunPod serverless SDK (runpod package)
- SongGeneration v2 Python API (from HuggingFace model)

</code_context>

<specifics>
## Specific Ideas

- RunPod input format example provided by user:
  ```json
  {
    "input": {
      "tracks": [
        {
          "idx": "radio_lofi_001",
          "gt_lyric": "[intro-medium]\n[verse] Le train siffle...\n[chorus] Laisse-moi partir...\n[outro-medium]",
          "descriptions": "female, lo-fi, chill, piano and vinyl, the bpm is 85"
        }
      ]
    }
  }
  ```
- The .jsonl format is for local batch preparation; the worker receives JSON array
- `descriptions` and `prompt_audio_path` are mutually exclusive (prompt_audio_path is v2 scope)
- RTF 0.82 on H20 → expect ~3-4 min compute per 3 min song on A5000

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-runpod-worker*
*Context gathered: 2026-03-18*
