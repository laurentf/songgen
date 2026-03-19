---
phase: 01-runpod-worker
plan: "02"
subsystem: validation
tags: [pydantic, schemas, input-validation, parse-descriptions, trackspec]

# Dependency graph
requires: []
provides:
  - "TrackSpec Pydantic model: idx (required, non-empty), gt_lyric (required, non-empty), descriptions (optional)"
  - "BatchRequest Pydantic model: wraps list[TrackSpec] matching RunPod input shape"
  - "parse_descriptions() helper: extracts gender, bpm, genre, mood, instruments from comma-separated string"
affects:
  - generator.py (imports TrackSpec)
  - handler.py (imports BatchRequest)
  - tests/test_generator.py (uses TrackSpec fixtures)
  - tests/test_handler.py (uses BatchRequest)

# Tech tracking
tech-stack:
  added: [pydantic>=2.7.0, pytest>=9.0]
  patterns:
    - "Pydantic v2 field_validator for non-empty string enforcement"
    - "Heuristic keyword matching for comma-separated descriptions parsing"
    - "TDD red-green cycle: test file committed before implementation"

key-files:
  created:
    - schemas.py
    - tests/test_schemas.py
  modified: []

key-decisions:
  - "TrackResult stays as plain dict in generator.py — not a Pydantic model in schemas.py"
  - "parse_descriptions uses heuristic keyword sets (_GENRES, _MOODS, _GENDERS) instead of fragile regex"
  - "Unknown tokens fall through to instruments list — open-world assumption for instrument names"

patterns-established:
  - "Pattern: field_validator with @classmethod for non-empty string enforcement"
  - "Pattern: parse_descriptions returns {} for None/empty input, never raises"

requirements-completed: [GEN-01, GEN-04, BATCH-03, BATCH-04]

# Metrics
duration: 8min
completed: 2026-03-18
---

# Phase 1 Plan 02: schemas.py — TrackSpec, BatchRequest, parse_descriptions Summary

**Pydantic v2 input validation layer with TrackSpec (idx+lyric validation), BatchRequest (RunPod wrapper), and keyword-based parse_descriptions() extracting gender/bpm/genre/mood/instruments from free-text strings**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-18T21:12:06Z
- **Completed:** 2026-03-18T21:20:00Z
- **Tasks:** 1 (TDD: 2 commits — test + implementation)
- **Files modified:** 2

## Accomplishments

- TrackSpec enforces idx and gt_lyric as required non-empty strings via Pydantic field_validators; descriptions is Optional[str] defaulting to None
- BatchRequest wraps list[TrackSpec] with coercion from raw dicts, matching RunPod's `{"input": {"tracks": [...]}}` shape
- parse_descriptions() extracts all 4 dimensions (gender, bpm, genre, mood) via keyword sets + BPM regex; unknown tokens collected as instruments list
- All 10 test_schemas.py tests pass on Python 3.13 + pydantic 2.12.5

## Task Commits

Each task was committed atomically:

1. **Task 1 RED — test_schemas.py (failing)** - `de9cd3d` (test)
2. **Task 1 GREEN — schemas.py (implementation)** - `74752bb` (feat)

_TDD task: test commit before implementation commit_

## Files Created/Modified

- `schemas.py` — TrackSpec, BatchRequest Pydantic models and parse_descriptions() helper; single source of truth for all input contracts
- `tests/test_schemas.py` — 10 unit tests covering validation happy paths, error cases, and descriptions parsing edge cases

## Decisions Made

- TrackResult kept as plain dict in generator.py (not a Pydantic model here) — schemas.py is input-only; output assembly is generator's responsibility
- parse_descriptions uses static keyword sets (not regex) per RESEARCH.md "don't hand-roll" guidance — comma-split + keyword match is more robust for informal free-text
- Empty string for idx/gt_lyric checked via `.strip()` — whitespace-only strings correctly rejected

## Deviations from Plan

None — plan executed exactly as written. schemas.py implementation matches the action block verbatim. pydantic and pytest installed as they were missing from the environment (Rule 3 — blocking), but that was expected for a greenfield project.

## Issues Encountered

- pydantic and pytest not installed in environment — installed via pip before running tests. Expected for a greenfield project with no existing requirements.txt.
- pytest.ini was already present from a prior plan (01-01), correctly configured for test discovery.

## User Setup Required

None — no external service configuration required for this plan.

## Next Phase Readiness

- schemas.py is ready for import by generator.py (`from schemas import TrackSpec`) and handler.py (`from schemas import BatchRequest`)
- parse_descriptions() returns the structured dict format that build_success_result() in generator.py will merge into track results
- All downstream plans in Phase 1 can rely on these contracts as stable

## Self-Check: PASSED

- schemas.py: FOUND
- tests/test_schemas.py: FOUND
- commit de9cd3d (test RED): FOUND
- commit 74752bb (feat GREEN): FOUND
- pytest tests/test_schemas.py: 10 passed in 0.11s

---
*Phase: 01-runpod-worker*
*Completed: 2026-03-18*
