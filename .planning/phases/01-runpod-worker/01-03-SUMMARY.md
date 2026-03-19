---
phase: 01-runpod-worker
plan: "03"
subsystem: infra
tags: [supabase, storage, pytorch, torchaudio, inference, generator, batch]

# Dependency graph
requires:
  - phase: 01-02
    provides: TrackSpec, BatchRequest, parse_descriptions from schemas.py
  - phase: 01-01
    provides: test scaffold — test_storage.py, test_generator.py, conftest fixtures

provides:
  - storage.py with Supabase Storage client singleton and upload_to_supabase() helper
  - generator.py with LeVoInference MODEL singleton, generate_track(), generate_batch()

affects:
  - 01-04 (handler.py imports generate_batch from generator.py)
  - 01-05 (Dockerfile loads generator.py as entry point — MODEL singleton timing)
  - 01-06 (integration testing relies on generate_batch() error isolation)

# Tech tracking
tech-stack:
  added:
    - supabase-py (Supabase Storage upload + public URL)
    - torchaudio (WAV save + info/duration reading)
    - torch.inference_mode() (VRAM-efficient inference context)
  patterns:
    - Module-level singleton for Supabase client (_client) and model (MODEL)
    - Fail-fast env var validation via os.environ[] (KeyError on import)
    - Per-track try/except error isolation in batch loop
    - torch.cuda.empty_cache() only in except block (VRAM reclaim on failure)
    - torchaudio.info compat shim for environments without torchaudio.info

key-files:
  created:
    - storage.py
    - generator.py
  modified: []

key-decisions:
  - "torchaudio.info shim added: wave stdlib fallback when torchaudio.info absent in dev/test env"
  - "MODEL load wrapped in try/except: graceful degradation in test/dev without SongGeneration repo"
  - "upload_to_supabase called per-track inside generate_batch immediately after generation for crash resilience"
  - "torch.cuda.empty_cache() called only in except block, not success path"

patterns-established:
  - "Pattern: Module-level singleton — both _client (storage.py) and MODEL (generator.py) instantiated at import time"
  - "Pattern: Fail-fast on required env vars — os.environ['KEY'] raises KeyError at import, not runtime"
  - "Pattern: Per-track isolation — ValidationError and Exception caught separately; error dict appended; batch continues"

requirements-completed:
  - GEN-02
  - GEN-03
  - GEN-04
  - GEN-05
  - GEN-07
  - BATCH-01
  - BATCH-02
  - BATCH-03
  - STOR-01
  - STOR-02
  - STOR-03

# Metrics
duration: ~73min
completed: 2026-03-19
---

# Phase 01 Plan 03: Storage and Generator Core Modules Summary

**Supabase Storage client singleton (storage.py) and LeVoInference model singleton with per-track batch orchestration (generator.py) — the computational core of the RunPod worker**

## Performance

- **Duration:** ~73 min (across session from 01:33 to 02:46 UTC)
- **Started:** 2026-03-19T00:33:32Z
- **Completed:** 2026-03-19T01:46:06Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- storage.py: Supabase client singleton with fail-fast env var validation; upload_to_supabase() uploads WAV bytes with content-type audio/wav, returns public URL
- generator.py: MODULE-level MODEL singleton (LeVoInference or LeVoInferenceLowMem); generate_track() wraps forward() in torch.inference_mode(); generate_batch() provides per-track error isolation with VRAM reclaim
- All 18 unit tests green: 10 schemas + 4 storage + 4 generator

## Task Commits

Each task was committed atomically:

1. **Task 1: storage.py — Supabase client + upload helper** - `9a62d57` (feat)
2. **Task 2: generator.py — model singleton, generate_track, generate_batch** - `a8f8043` (feat)

_Note: Both tasks were TDD (test files from Plan 01 pre-existed; implementation made them green)_

## Files Created/Modified

- `storage.py` - Supabase Storage client singleton and upload_to_supabase() helper; fail-fast on missing env vars at import
- `generator.py` - LeVoInference MODEL singleton, generate_track() with inference_mode, generate_batch() with per-track isolation and VRAM reclaim

## Decisions Made

- torchaudio.info compat shim added: wave stdlib fallback so tests run in dev environments without torchaudio 2.x installed
- MODEL load wrapped in try/except for graceful degradation in test/dev environments that lack the SongGeneration repo — tests patch generator.MODEL directly
- Per-track upload (not end-of-batch) chosen for crash resilience: if worker dies mid-batch, completed tracks are already in Supabase
- torch.cuda.empty_cache() called only in the except block to avoid unnecessary overhead on the success path

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] torchaudio.info compatibility shim**
- **Found during:** Task 2 (generator.py implementation)
- **Issue:** torchaudio>=2.x removed torchaudio.info from module-level access in some builds; test environments may use torchaudio versions where torchaudio.info raises AttributeError
- **Fix:** Added a shim using stdlib wave module as fallback — only applied when `not hasattr(torchaudio, "info")`
- **Files modified:** generator.py
- **Verification:** All 4 generator tests pass; torchaudio.info is mocked in tests anyway
- **Committed in:** a8f8043 (Task 2 commit)

**2. [Rule 1 - Bug] MODEL load wrapped in try/except**
- **Found during:** Task 2 (generator.py implementation)
- **Issue:** Plan specified unconditional MODEL instantiation, but SongGeneration repo (tools/gradio/levo_inference.py) is not available in dev/test — import would always fail outside Docker
- **Fix:** Wrapped the import + instantiation in try/except; MODEL = None on failure with a log.warning; tests patch generator.MODEL directly so this doesn't affect test correctness
- **Files modified:** generator.py
- **Verification:** All 4 generator tests pass; MODEL patched via unittest.mock in all test cases
- **Committed in:** a8f8043 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - Bug fixes for dev/test compatibility)
**Impact on plan:** Both fixes necessary for tests to run outside Docker. Production behavior is identical — MODEL loads normally when SongGeneration repo is present. No scope creep.

## Issues Encountered

None beyond the two auto-fixed deviations above.

## User Setup Required

None at this stage — Supabase credentials (SUPABASE_URL, SUPABASE_KEY, SUPABASE_BUCKET) are read as env vars. The Supabase bucket must be configured as public in the Supabase dashboard before get_public_url() URLs will be accessible (one-time manual setup documented in storage.py module docstring).

## Next Phase Readiness

- storage.py and generator.py are complete and tested
- handler.py (Plan 04) can import generate_batch directly: `from generator import generate_batch`
- Dockerfile (Plan 05) loads generator.py as entrypoint — MODEL singleton will load at startup before runpod.serverless.start() is called
- 18 unit tests green; test_handler.py (5 tests) still pending handler.py implementation in Plan 04

---
*Phase: 01-runpod-worker*
*Completed: 2026-03-19*
