---
phase: 01-runpod-worker
plan: "05"
subsystem: docker
tags: [docker, cuda, nvidia, model-download, supabase, devops]
dependency_graph:
  requires:
    - 01-03  # handler.py, generator.py, storage.py, schemas.py must exist for COPY
  provides:
    - Dockerfile  # deployable RunPod image definition
    - docker-compose.yml  # local GPU testing environment
    - .env.example  # credential documentation template
  affects:
    - RunPod endpoint deployment
    - local development workflow
tech_stack:
  added:
    - nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04 (base image)
    - python3.11 (runtime)
    - torch==2.6.0 + cu124 wheels
    - huggingface_hub[cli] (build-time model download)
    - docker-compose v3.9
  patterns:
    - model-weights-at-build-time (cold start elimination)
    - source-volume-mounts (dev iteration without rebuild)
    - env-file-loading (secrets isolation)
key_files:
  created:
    - Dockerfile
    - docker-compose.yml
    - .env.example
  modified:
    - .gitignore (added !.env.example negation)
decisions:
  - "Custom CUDA 12.4 image required: juhayna/song-generation-levo:hf0613 predates torch 2.6.0 and v2-large model (RESEARCH.md Pitfall 3)"
  - "Model weights downloaded at build time via huggingface-cli to eliminate cold start cost per job"
  - "huggingface_hub[cli] installed separately before model downloads to keep layer caching efficient"
  - ".env.example negation added to .gitignore to allow template tracking while blocking real secrets"
metrics:
  duration_seconds: 102
  completed_date: "2026-03-19"
  tasks_completed: 2
  tasks_total: 2
  files_created: 4
  files_modified: 1
---

# Phase 01 Plan 05: Docker Image Definition Summary

**One-liner:** Custom CUDA 12.4 Dockerfile downloads SongGeneration v2-large weights at build time via huggingface-cli, eliminating cold start cost for RunPod serverless workers.

## What Was Built

### Task 1: Dockerfile (commit fb014bf)

Custom Docker image from `nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04` that:
- Installs Python 3.11 as system default
- Clones `tencent-ailab/SongGeneration` repo to `/app/SongGeneration` (source-only, not pip-installable)
- Installs torch 2.6.0 + torchaudio 2.6.0 with cu124 wheel URL (not cu121 — Pitfall 4)
- Downloads `lglg666/SongGeneration-v2-large` weights to `/app/songgeneration_v2_large` at build time
- Downloads `lglg666/SongGeneration-ckpt` to `/app/ckpt` at build time
- Copies worker code (handler.py, generator.py, storage.py, schemas.py)
- Sets ENV defaults for MODEL_CKPT_PATH, SONGGEN_REPO_PATH, USE_LOW_MEM
- CMD targets `handler.py` — "Loading model" appears once at worker start

### Task 2: docker-compose.yml + .env.example (commit febce62)

- **docker-compose.yml**: GPU passthrough via nvidia container toolkit, `env_file: .env` loading, source volume mounts for all 4 Python files enabling dev iteration without image rebuilds
- **.env.example**: Documents SUPABASE_URL, SUPABASE_KEY, SUPABASE_BUCKET, USE_LOW_MEM with explanatory comments including the Supabase bucket public requirement (Pitfall 5)
- **.gitignore**: Added `!.env.example` negation to allow the template to be tracked while keeping `.env.*` pattern blocking real secrets

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] .gitignore negation for .env.example**
- **Found during:** Task 2 commit
- **Issue:** `.gitignore` had `.env.*` wildcard which blocked `.env.example` from being committed — the template would be invisible to other developers
- **Fix:** Added `!.env.example` negation line after `.env.*` pattern in `.gitignore`
- **Files modified:** `.gitignore`
- **Commit:** febce62 (same task commit)

## Success Criteria Check

- [x] Dockerfile: CUDA 12.4 base (`nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04`)
- [x] Dockerfile: Python 3.11
- [x] Dockerfile: SongGeneration repo cloned at build time
- [x] Dockerfile: torch 2.6.0 with cu124 wheel URL (two occurrences as --index-url and --extra-index-url)
- [x] Dockerfile: Model weights downloaded at build time (huggingface-cli download, 2 repos)
- [x] Dockerfile: CMD targets handler.py
- [x] Dockerfile: Does NOT use AutoModel.from_pretrained (Pitfall 1)
- [x] docker-compose.yml: GPU passthrough via nvidia driver
- [x] docker-compose.yml: env_file loading
- [x] docker-compose.yml: Source volume mounts for development iteration
- [x] .env.example: SUPABASE_URL, SUPABASE_KEY, SUPABASE_BUCKET, USE_LOW_MEM documented
- [x] .env.example: Supabase bucket public requirement noted (Pitfall 5)
- [x] .gitignore: Contains .env (pre-existing) and allows .env.example tracking

## Self-Check: PASSED
