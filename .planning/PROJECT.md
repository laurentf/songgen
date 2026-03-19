# Radio AI — SongGeneration Pipeline

## What This Is

A complete AI radio pipeline: batch song generation on RunPod (SongGeneration v2), post-processing (FFmpeg + mutagen), storage on Supabase (files + PostgreSQL catalogue), radio scheduling (Liquidsoap), and a FastAPI API. Generates WAV from JSONL input, converts to MP3 with metadata, catalogues, and streams 24/7.

## Core Value

Reliably generate batches of songs from structured JSONL input and deliver them as catalogued, tagged audio files ready for automated radio scheduling — fully autonomous music pipeline.

## Requirements

### Validated

(None yet — ship to validate)

### Active

**Generation (RunPod worker):**
- [ ] Accept JSONL batch input (idx, gt_lyric, descriptions per track)
- [ ] Load SongGeneration v2 model once at module level, reuse across batch
- [ ] Generate WAV output up to 4m30, multilingual (EN, FR, ES, etc.)
- [ ] Sequential batch processing with per-track error isolation (skip + log)
- [ ] Upload WAV to Supabase Storage
- [ ] Return structured JSON response (URL, tags, duration per track)
- [ ] Run as RunPod serverless worker (A5000/3090 24GB)
- [ ] Docker image with CUDA + model (use existing image if compatible)

**Post-processing:**
- [ ] FFmpeg WAV → MP3 320kbps conversion
- [ ] Mutagen ID3 tag injection (title, artist, genre, mood, BPM, etc.)
- [ ] Insert song metadata into Supabase PostgreSQL catalogue

**Radio:**
- [ ] Scheduler with rules (time of day, mood, energy, genre)
- [ ] Liquidsoap → Icecast2/HLS streaming
- [ ] Maintain >2h content buffer ahead

**API (FastAPI):**
- [ ] POST /generate/batch — submit N songs, return job_id
- [ ] GET /job/{job_id} — job status + URLs
- [ ] GET /catalogue — list songs with tags
- [ ] POST /radio/next — next song per scheduling rules

### Out of Scope

- Web UI or dashboard — API-only
- Lyrics generation — pre-generated upstream via Claude API
- Multi-GPU orchestration — single GPU per worker
- Audio mastering/EQ — raw model output + basic FFmpeg conversion only
- Voice cloning (prompt_audio_path) — v2+ feature

## Context

- **Model:** `lglg666/SongGeneration-v2-large` (HuggingFace), Apache-2.0, 4B params
- **Source code:** `github.com/tencent-ailab/SongGeneration`
- **Existing Docker image:** `juhayna/song-generation-levo:hf0613` (to verify compatibility)
- **Architecture:** Hybrid LLM (LeLM) + Diffusion, voice + instruments in one pass
- **Generation:** Uses `generate.sh` with JSONL input
- **VRAM:** 22GB standard (no audio ref), 10GB `--low_mem` mode
- **RTF:** 0.82 on H20 → ~3-4 min compute per 3 min song on A5000
- **Performance:** ~$0.012/song on A5000 at $0.27/h
- **Lyrics precision:** PER 8.55% (vs Suno v5's 12.4%)
- **Target GPUs:** A5000 or 3090 (24GB VRAM)
- **Storage:** Supabase Storage (files) + Supabase PostgreSQL (catalogue)
- **Radio stack:** Liquidsoap → Icecast2/HLS
- **Cost estimate:** ~$50/month for 24/7 radio (~120 songs/day)
- **Input format:** JSONL with idx, gt_lyric (structured segments), descriptions (tags)
- **`descriptions` and `prompt_audio_path` are mutually exclusive**

## Constraints

- **GPU VRAM**: 24GB max (A5000/3090) — concurrency deferred until VRAM profiled
- **Runtime**: RunPod serverless — cold start matters, model must be in image
- **Cost**: ~$0.012/song target — ~$50/month total for 24/7 radio
- **Model**: Must use `lglg666/SongGeneration-v2-large` specifically
- **Local GPU**: Not powerful enough — RunPod only for generation
- **Lyrics format**: Strict segment rules (see docs/songgen-input-format.md)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| SongGeneration v2 over Suno API | Open-source, better lyric precision, self-hosted cost control | — Pending |
| RunPod serverless over dedicated GPU | Pay-per-use, auto-scaling, no idle cost | — Pending |
| Supabase over R2 | Simpler — storage + PostgreSQL catalogue in one service | — Pending |
| WAV generation, MP3 post-processing | Keep worker lean, convert downstream | — Pending |
| Sequential first, concurrency later | 22GB model on 24GB GPU — no safe headroom without profiling | — Pending |
| Existing Docker image if compatible | Saves build time, model already baked in | — Pending |
| Skip + log on failure | Don't block entire batch for one bad track | — Pending |
| Liquidsoap + Icecast2 | Standard open-source radio stack | — Pending |

---
*Last updated: 2026-03-18 after scope expansion to full radio pipeline*
