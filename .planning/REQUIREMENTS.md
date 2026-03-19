# Requirements: Radio AI — SongGeneration Pipeline

**Defined:** 2026-03-18
**Core Value:** Reliably generate batches of songs from structured JSONL input and deliver them as catalogued, tagged audio files ready for automated radio scheduling.

## v1 Requirements

### Generation

- [x] **GEN-01**: Worker accepts JSONL batch input (idx, gt_lyric, descriptions per track)
- [x] **GEN-02**: Model loaded once at module level, reused across all tracks in batch
- [x] **GEN-03**: Generates WAV output up to 4m30 per track
- [x] **GEN-04**: Supports multilingual lyrics (EN, FR, ES minimum)
- [x] **GEN-05**: Runs on RunPod serverless (A5000/3090, 24GB VRAM)
- [x] **GEN-06**: Docker image with CUDA + model pre-loaded (existing image or custom)
- [x] **GEN-07**: float16 + torch.inference_mode() for VRAM efficiency

### Batch Processing

- [x] **BATCH-01**: Sequential processing of N tracks per job
- [x] **BATCH-02**: Per-track error isolation — skip failed track, log error, continue batch
- [x] **BATCH-03**: Track ID (idx) passthrough for input/output correlation
- [x] **BATCH-04**: Structured JSON response per track (url, idx, tags, duration, status)

### Storage

- [x] **STOR-01**: Upload generated WAV to Supabase Storage
- [x] **STOR-02**: Return public URL for each uploaded file
- [x] **STOR-03**: Credentials via environment variables

### Post-Processing

- [ ] **POST-01**: FFmpeg conversion WAV → MP3 320kbps
- [ ] **POST-02**: Mutagen ID3 tag injection (title, artist, genre, mood, BPM, gender, instruments)
- [ ] **POST-03**: Custom TXXX tags (ai_model, radio_tags, generated_at)

### Catalogue

- [ ] **CAT-01**: Insert song metadata into Supabase PostgreSQL (idx, title, file_url, duration, genre, mood, gender, bpm, instruments, tags)
- [ ] **CAT-02**: Query catalogue by tags/genre/mood/bpm
- [ ] **CAT-03**: Track play count per song


## v2 Requirements

### Concurrency

- **CONC-01**: Concurrent generation (2-3 tracks parallel) gated on VRAM profiling
- **CONC-02**: `--low_mem` mode toggle via env var for concurrency headroom
- **CONC-03**: Warm worker reuse (RunPod concurrency_modifier)

### Radio (deferred — needs local RTX 3090)

- **RAD-01**: Scheduler selects next song based on rules (time of day, mood, energy, genre)
- **RAD-02**: Liquidsoap integration for audio playout
- **RAD-03**: Icecast2 or HLS output stream
- **RAD-04**: Maintain >2h content buffer ahead of playback

### API (deferred — needs local RTX 3090)

- **API-01**: POST /generate/batch — submit N songs from JSONL, return job_id
- **API-02**: GET /job/{job_id} — job status + URLs of generated songs
- **API-03**: GET /catalogue — list songs with tag filtering
- **API-04**: POST /radio/next — next song per scheduling rules

### Advanced Features

- **ADV-01**: Voice cloning via prompt_audio_path (28GB VRAM — needs larger GPU)
- **ADV-02**: Separate tracks output (vocal + instrumental) via --separate_tracks
- **ADV-03**: Batch size guardrails (max tracks per job based on timeout)
- **ADV-04**: Per-track generation time estimation

## Out of Scope

| Feature | Reason |
|---------|--------|
| Web UI / Dashboard | API-only service, no frontend needed |
| Lyrics generation | Pre-generated upstream via Claude API |
| Multi-GPU orchestration | Single GPU per worker, scale via RunPod auto-scaling |
| Audio mastering / EQ | Raw model output + basic FFmpeg conversion only |
| Real-time generation streaming | Batch processing, results delivered after completion |
| User authentication | Internal service, RunPod gateway handles access |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| GEN-01 | Phase 1 | Complete |
| GEN-02 | Phase 1 | Complete |
| GEN-03 | Phase 1 | Complete |
| GEN-04 | Phase 1 | Complete |
| GEN-05 | Phase 1 | Complete |
| GEN-06 | Phase 1 | Complete |
| GEN-07 | Phase 1 | Complete |
| BATCH-01 | Phase 1 | Complete |
| BATCH-02 | Phase 1 | Complete |
| BATCH-03 | Phase 1 | Complete |
| BATCH-04 | Phase 1 | Complete |
| STOR-01 | Phase 1 | Complete |
| STOR-02 | Phase 1 | Complete |
| STOR-03 | Phase 1 | Complete |
| POST-01 | Phase 2 | Pending |
| POST-02 | Phase 2 | Pending |
| POST-03 | Phase 2 | Pending |
| CAT-01 | Phase 2 | Pending |
| CAT-02 | Phase 2 | Pending |
| CAT-03 | Phase 2 | Pending |

**Coverage:**
- v1 requirements: 20 total
- Mapped to phases: 20
- Unmapped: 0
- Deferred to v2: 8 (RAD-01→04, API-01→04)

---
*Requirements defined: 2026-03-18*
*Last updated: 2026-03-18 — traceability populated after roadmap creation*
