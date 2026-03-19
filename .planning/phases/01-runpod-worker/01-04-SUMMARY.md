---
phase: 01-runpod-worker
plan: "04"
subsystem: infra
tags: [runpod, handler, requirements, python, serverless]

# Dependency graph
requires:
  - phase: 01-03
    provides: generator.py with generate_batch() and storage.py with upload_to_supabase()
provides:
  - handler.py — RunPod serverless entrypoint delegating to generate_batch()
  - requirements.txt — all Python dependencies with pinned versions and cu124 wheel note
  - test_input.json — sample RunPod job payloads for manual endpoint testing
affects: [Dockerfile, Docker build, RunPod endpoint deployment]

# Tech tracking
tech-stack:
  added: [runpod>=1.7.0, structlog>=23.0.0]
  patterns:
    - "Thin handler pattern: handler.py contains zero business logic — delegates entirely to generate_batch()"
    - "__main__ guard on runpod.serverless.start() for test import compatibility"
    - "Module-level import of generate_batch triggers model loading before worker starts"

key-files:
  created:
    - handler.py
    - requirements.txt
    - test_input.json
  modified: []

key-decisions:
  - "__main__ guard added to runpod.serverless.start() — unconditional call blocks test module import via SystemExit"
  - "torch 2.6.0 pinned with cu124 wheel URL — not cu121 (see RESEARCH Pitfall 4)"

patterns-established:
  - "RunPod handler is always a thin wrapper — handler() has no business logic, only input extraction and delegation"
  - "Importing generate_batch at module level in handler.py is the mechanism for warm model loading"

requirements-completed: [GEN-01, GEN-02, BATCH-01, BATCH-02, BATCH-03, BATCH-04]

# Metrics
duration: 8min
completed: 2026-03-19
---

# Phase 01 Plan 04: RunPod Entrypoint and Dependencies Summary

**RunPod serverless handler.py wired as thin wrapper over generate_batch(), requirements.txt pins torch==2.6.0 with cu124 wheel, and test_input.json provides 3 test scenarios for manual endpoint testing**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-19T01:51:29Z
- **Completed:** 2026-03-19T01:59:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- handler.py created as a thin RunPod serverless entrypoint — no business logic, delegates entirely to generate_batch()
- requirements.txt pins all 11 dependencies with correct cu124 torch wheel URL per RESEARCH Pitfall 4
- test_input.json provides 3 real-world test payloads: single French track, 3-track batch (pop/jazz/rock), and error isolation test
- All 23 unit tests pass (test_schemas x10, test_storage x4, test_handler x5, test_generator x4)

## Task Commits

Each task was committed atomically:

1. **Task 1: handler.py — RunPod entrypoint** - `7fca6f4` (feat)
2. **Task 2: requirements.txt and test_input.json** - `541dfd6` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `handler.py` — RunPod serverless entrypoint; thin wrapper calling generate_batch(); imports trigger model load; __main__ guard on runpod.serverless.start()
- `requirements.txt` — pinned Python dependencies: torch==2.6.0, torchaudio==2.6.0, runpod>=1.7.0, supabase>=2.0.0, pydantic>=2.7.0, structlog>=23.0.0, lightning>=2.5.2
- `test_input.json` — 3 manual test scenarios: single_track_french, three_track_batch, error_isolation_test

## Decisions Made

- Added `__main__` guard to `runpod.serverless.start()` call — the unconditional call caused `SystemExit(1)` during pytest import when `test_input.json` didn't exist yet. Guard preserves production behavior while enabling test imports.
- Torch cu124 wheel URL used per RESEARCH.md Pitfall 4 (cu121 does not have torch 2.6.0 builds).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added __main__ guard to runpod.serverless.start()**
- **Found during:** Task 1 (handler.py TDD — GREEN phase)
- **Issue:** `runpod.serverless.start()` at module level calls `asyncio.run()` immediately on import, which looks for `test_input.json` and calls `sys.exit(1)` if not found. The patch context manager imports `handler` to resolve "handler.generate_batch", triggering the start() call and crashing with `SystemExit: 1`.
- **Fix:** Wrapped `runpod.serverless.start({"handler": handler})` in `if __name__ == "__main__":`. This is standard Python practice and does not affect RunPod production behavior (RunPod executes `python handler.py` directly).
- **Files modified:** handler.py
- **Verification:** All 5 test_handler.py tests pass; full 23-test suite green.
- **Committed in:** `7fca6f4` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Auto-fix essential for test compatibility. No scope creep. Production behavior unchanged — RunPod executes `python handler.py` as __main__.

## Issues Encountered

- `runpod` package not pre-installed in dev environment — installed via pip as part of Task 1 resolution (Rule 3 - blocking). structlog was also missing; both installed together.

## User Setup Required

None - no external service configuration required for this plan. (Supabase credentials documented in prior plan 01-03.)

## Next Phase Readiness

- Python layer complete: schemas.py, storage.py, generator.py, handler.py all implemented
- All 23 unit tests green
- requirements.txt ready for Docker build
- test_input.json ready for manual RunPod endpoint testing
- Remaining: Dockerfile, Docker image build, RunPod endpoint deployment (Phase 2)

---
*Phase: 01-runpod-worker*
*Completed: 2026-03-19*

## Self-Check: PASSED

- FOUND: handler.py
- FOUND: requirements.txt
- FOUND: test_input.json
- FOUND: .planning/phases/01-runpod-worker/01-04-SUMMARY.md
- FOUND commit: 7fca6f4 (handler.py)
- FOUND commit: 541dfd6 (requirements.txt + test_input.json)
