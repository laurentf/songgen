# Roadmap: Radio AI — SongGeneration Pipeline

## Overview

Two phases deliver the generation and enrichment pipeline. Phase 1 builds and validates the RunPod worker — Docker image, model loading, single-track generation, batch processing, and Supabase Storage upload. This is the critical path: nothing downstream exists without generated audio. Phase 2 converts WAV to MP3, injects ID3 metadata, and populates the Supabase PostgreSQL catalogue. Radio scheduling and API (Phase 3) deferred until a local RTX 3090 is available.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: RunPod Worker** - Docker image + batch generation + Supabase Storage upload
- [ ] **Phase 2: Post-Processing and Catalogue** - WAV→MP3 conversion, ID3 tags, PostgreSQL catalogue

## Phase Details

### Phase 1: RunPod Worker
**Goal**: A RunPod serverless worker that accepts JSONL batches, generates WAV audio via SongGeneration v2, and uploads files to Supabase Storage with structured JSON responses
**Depends on**: Nothing (first phase)
**Requirements**: GEN-01, GEN-02, GEN-03, GEN-04, GEN-05, GEN-06, GEN-07, BATCH-01, BATCH-02, BATCH-03, BATCH-04, STOR-01, STOR-02, STOR-03
**Success Criteria** (what must be TRUE):
  1. Submitting a valid JSONL batch to the RunPod endpoint returns a structured JSON response with one result entry per track containing a public Supabase Storage URL, duration, tags, and status
  2. A track with malformed input is skipped and logged with its idx; the remaining tracks in the batch complete normally and their results are returned
  3. The Docker image starts without downloading the model at runtime — "Loading model" appears exactly once in logs at container startup, never at job time
  4. Submitting a 3-track batch where one track's lyrics are invalid produces two WAV files in Supabase Storage and one error entry in the response — the batch does not fail entirely
  5. The worker runs on a RunPod A5000 or 3090 (24GB VRAM) without OOM errors on batches up to 10 tracks
**Plans**: 6 plans

Plans:
- [ ] 01-01-PLAN.md — Test scaffold: pytest infrastructure, conftest fixtures, all test stubs (Wave 1)
- [ ] 01-02-PLAN.md — schemas.py: TrackSpec, BatchRequest, parse_descriptions (Wave 1)
- [ ] 01-03-PLAN.md — storage.py + generator.py: Supabase upload and model singleton (Wave 2)
- [ ] 01-04-PLAN.md — handler.py + requirements.txt + test_input.json: RunPod wiring (Wave 3)
- [ ] 01-05-PLAN.md — Dockerfile + docker-compose.yml + .env.example: container image (Wave 3)
- [ ] 01-06-PLAN.md — RunPod smoke tests: deploy and verify all success criteria (Wave 4)

### Phase 2: Post-Processing and Catalogue
**Goal**: Every generated WAV is converted to MP3 320kbps with full ID3 metadata and inserted into the Supabase PostgreSQL catalogue, making content queryable by tags, genre, mood, and BPM
**Depends on**: Phase 1
**Requirements**: POST-01, POST-02, POST-03, CAT-01, CAT-02, CAT-03
**Success Criteria** (what must be TRUE):
  1. A WAV file produced by Phase 1 is converted to a 320kbps MP3 with correct ID3 tags (title, artist, genre, mood, BPM, gender, instruments) and custom TXXX tags (ai_model, radio_tags, generated_at) readable by a standard audio player
  2. Every processed song appears in the Supabase PostgreSQL catalogue with its idx, title, file_url, duration, genre, mood, gender, bpm, instruments, and tags populated
  3. A catalogue query filtered by genre="pop" and mood="energetic" returns only matching songs
  4. Play count increments by 1 each time a song entry is marked as played
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. RunPod Worker | 3/6 | In Progress|  |
| 2. Post-Processing and Catalogue | 0/TBD | Not started | - |
