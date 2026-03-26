# SongGen RunPod

[![Docker Hub](https://img.shields.io/docker/v/naturelbenton/songgen-worker?label=Docker%20Hub)](https://hub.docker.com/r/naturelbenton/songgen-worker)
[![RunPod](https://api.runpod.io/badge/laurentf/songgen)](https://console.runpod.io/hub/laurentf/songgen)

Batch song generation powered by [SongGeneration v2](https://github.com/tencent-ailab/SongGeneration) (Tencent AI Lab). One command generates songs on RunPod serverless and uploads them to Supabase Storage.

```bash
python scripts/generate.py examples/batch_test.jsonl
```

Worker spins up, generates songs, uploads to Supabase, scales to zero.

## How It Works

```
Your machine                         RunPod Serverless
───────────                         ─────────────────
scripts/generate.py input.jsonl
    │
    ├─ POST /runsync ─────────────→ Worker cold-starts (~30s)
    │                                ├─ Docker image has all deps
    │                                ├─ Model loaded from network volume
    │                                ├─ Generates WAV per track
    │                                └─ Uploads each to Supabase Storage
    │
    ├─ Receives results ←─────────  {url, idx, duration, tags, status}
    │
    └─ Done                          Worker scales to zero ($0)
```

First run downloads model to volume (~8 min). After that: ~30s cold start + generation time.

## Run locally (Docker)

You can run the worker as a standalone Docker container without RunPod — useful for local testing or self-hosting.

**Requirements:** NVIDIA GPU with 30 GB VRAM (or 10 GB with `USE_LOW_MEM=true`), NVIDIA Container Toolkit.

```bash
docker run --gpus all \
  -e SONGGEN_CKPT_PATH=/models/songgeneration_v2_large \
  -e SONGGEN_SHARED_CKPT_PATH=/models/ckpt \
  -e SUPABASE_URL=https://xxx.supabase.co \
  -e SUPABASE_KEY=your_secret_key \
  -e SUPABASE_BUCKET=songs \
  -v /your/local/models:/models \
  naturelbenton/songgen-worker:latest
```

On first run, model weights (~17 GB) are downloaded from HuggingFace into the mounted volume. Set `HF_TOKEN` if needed.

**Or build from source:**

```bash
docker build -t songgen-worker .
docker run --gpus all \
  -e SONGGEN_CKPT_PATH=/models/songgeneration_v2_large \
  -e SONGGEN_SHARED_CKPT_PATH=/models/ckpt \
  -e SUPABASE_URL=... \
  -e SUPABASE_KEY=... \
  -e SUPABASE_BUCKET=songs \
  -v /your/local/models:/models \
  songgen-worker
```

## Setup (one time)

### 1. Supabase

1. Create a project at [supabase.com](https://supabase.com) (free tier works)
2. **Storage** → **New Bucket** → name: `songs` → **Make Public**
3. **Settings** → **API** → copy **URL** and **Secret key**

### 2. RunPod — Network Volume

1. [runpod.io](https://runpod.io) → **Storage** → **New Network Volume**
2. Size: **50 GB**
3. Region: pick one with GPU availability

### 3. RunPod — API Key

1. **Settings** → **API Keys** → **Create**
2. `api.runpod.io/graphql` → **Read / Write**
3. `api.runpod.ai` → **Read / Write**

### 4. RunPod — Serverless Template

1. **Serverless** → **New Template** → **Custom**

| Field | Value |
|-------|-------|
| Template Name | `songgen-worker` |
| Container Image | `naturelbenton/songgen-worker:latest` |
| Container Disk | `20 GB` |
| Docker Command | **leave empty** |

Do NOT fill the "Model" field.

2. **Environment Variables:**

| Key | Value |
|-----|-------|
| `SUPABASE_URL` | your Supabase project URL |
| `SUPABASE_KEY` | your Supabase secret key |
| `SUPABASE_BUCKET` | `songs` |
| `SONGGEN_CKPT_PATH` | `/runpod-volume/songgeneration_v2_large` |
| `SONGGEN_SHARED_CKPT_PATH` | `/runpod-volume/ckpt` |
| `USE_LOW_MEM` | `false` |
| `HF_TOKEN` | your HuggingFace token (if needed for gated repos) |

Do NOT set `SONGGEN_REPO_PATH` — defaults to `/app/SongGeneration` (baked in image).

3. **Save**

### 5. RunPod — Serverless Endpoint

1. **Serverless** → **New Endpoint**

| Field | Value |
|-------|-------|
| Endpoint Name | `songgen` |
| Template | `songgen-worker` |
| GPU | any with >=48 GB VRAM (A40, A100) or >=10 GB with `USE_LOW_MEM=true` |
| Active (Min) Workers | `0` |
| Max Workers | `1` |
| Idle Timeout | `5` seconds |
| Execution Timeout | `1200` (first run) / `600` (after model cached) |
| Network Volume | your volume |

2. **Deploy**
3. Copy the **Endpoint ID**

### 6. Local Config

```bash
git clone https://github.com/laurentf/songgen.git
cd songgen
pip install requests python-dotenv structlog
cp .env.example .env
```

Fill in `.env`:

```bash
RUNPOD_API_KEY=your_key
RUNPOD_ENDPOINT_ID=your_endpoint_id
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your_secret_key
SUPABASE_BUCKET=songs
```

## Usage

```bash
# Dry run
python scripts/generate.py examples/batch_test.jsonl --dry-run

# Generate
python scripts/generate.py examples/batch_test.jsonl

# Custom timeout
python scripts/generate.py input.jsonl --timeout 900
```

### Timing

| Scenario | Duration |
|----------|----------|
| First ever run | ~8 min (model download) |
| Cold start (cached, low_mem=false) | ~4 min (full model load to VRAM) |
| Cold start (cached, low_mem=true) | ~30s (model loaded per track) |
| Per song, low_mem=false | ~2-3 min |
| Per song, low_mem=true | ~5-6 min (includes LM reload) |

## Input Format (JSONL)

One track per line:

```jsonl
{"idx":"song_001","gt_lyric":"[intro-short]\n[verse] Walking through the rain.\n[chorus] The warmth remains.\n[outro-short]","descriptions":"female, pop, sad, piano, the bpm is 120"}
```

### Track fields

| Field | Required | Description |
|-------|----------|-------------|
| `idx` | yes | Unique track ID — becomes the filename |
| `gt_lyric` | yes | Structured lyrics with segment tags |
| `descriptions` | no | Comma-separated tags: gender, genre, mood, instruments, BPM |
| `gen_type` | no | `"mixed"` (default, vocals+instruments) or `"bgm"` (instrumental only) |
| `params` | no | Generation parameters override (see below) |

### Generation parameters

Optional `params` object per track. Omitted fields use defaults.

| Param | Default | Description |
|-------|---------|-------------|
| `cfg_coef` | `1.5` | Classifier-free guidance — higher = follows prompt more strictly |
| `temperature` | `1.0` | Sampling randomness — lower = more predictable |
| `top_k` | `50` | Keep top K tokens — higher = more variety |
| `top_p` | `0.0` | Nucleus sampling — `0.0` = disabled (uses top_k) |

Example with params:

```jsonl
{"idx":"song_001","gt_lyric":"...","descriptions":"...","params":{"temperature":0.8,"top_k":100}}
```

### Lyrics segments

**Instrumental:** `[intro-short]` `[intro-medium]` `[inst-short]` `[inst-medium]` `[outro-short]` `[outro-medium]`

**With lyrics:** `[verse]` `[chorus]` `[bridge]`

Rules: phrases end with `.`, English punctuation only, sections separated by `\n`. See [docs/songgen-input-format.md](docs/songgen-input-format.md).

### Descriptions

```
"female, pop, sad, piano and drums, the bpm is 120"
 ──────  ───  ───  ───────────────  ───────────────
 gender genre mood   instrument(s)       bpm
```

## Output

```json
{
  "idx": "song_001",
  "status": "success",
  "url": "https://xxx.supabase.co/storage/v1/object/public/songs/song_001_20260320T080000.wav",
  "duration": 187.5,
  "file_size": 18000000,
  "genre": "pop",
  "mood": "sad",
  "bpm": 120,
  "gender": "female",
  "instruments": ["piano and drums"]
}
```

Failed tracks return `"status": "error"` with `error_message` — the batch continues.

## Docker Image

`naturelbenton/songgen-worker:latest`

Contains: CUDA 12.4, Python 3.11, flash-attn 2.7.4, all deps, SongGeneration code with patched imports.

**Not in the image:** model weights (on network volume), secrets (in env vars).

### Rebuild

```bash
docker build -t songgen-worker .
docker tag songgen-worker naturelbenton/songgen-worker:vX.X
docker push naturelbenton/songgen-worker:vX.X
```

See [docs/songgen-integration-notes.md](docs/songgen-integration-notes.md) for details on the patches needed to make SongGeneration work in Docker.

## Project Structure

```
songgen/
├── .runpod/
│   ├── hub.json                # RunPod Hub marketplace config
│   ├── tests.json              # RunPod Hub test cases
│   └── handler.py              # RunPod Hub handler (override)
├── handler.py                  # RunPod Hub handler entry point
├── Dockerfile                  # Worker image (deps + patched imports)
├── scripts/
│   └── generate.py             # CLI: submit batch jobs
├── services/
│   ├── config.py               # Env vars, validation
│   └── runpod.py               # Job submission + polling
├── worker/                     # Baked into Docker image
│   ├── start.py                # Entry: download model + start handler
│   ├── setup_model.py          # Download model to volume if not cached
│   ├── handler.py              # RunPod serverless handler
│   ├── generator.py            # Model singleton + batch generation
│   ├── storage.py              # Supabase Storage upload
│   └── schemas.py              # Pydantic input/output contracts
├── tests/                      # Unit tests
├── examples/
│   ├── one_shot_test.jsonl
│   └── batch_test.jsonl
├── .env.example
└── docs/
    ├── songgen-input-format.md
    └── songgen-integration-notes.md
```

## Cost

| Item | Cost |
|------|------|
| Network Volume 50 GB | ~$3.50/month |
| Per song (~3 min) | ~$0.02 |
| 100 songs | ~$2 |
| Idle | $0 (scales to zero) |

## Troubleshooting

### `MODEL LOAD FAILED`
Check the `error` field in the log. Common causes:
- Missing deps → rebuild image
- Wrong path → check env vars point to `/runpod-volume/...`
- Module not found → see [integration notes](docs/songgen-integration-notes.md)

### Model re-downloads every time
Network volume not attached to endpoint. Edit endpoint → select volume.

### Docker Hub rate limit
Add Docker Hub credentials in RunPod: Settings → Container Registry Auth.

### Worker keeps restarting
Delete endpoint + recreate.

### `flash_attn` errors
Image v1.4+ includes flash-attn 2.7.4 (pinned for torch 2.6.0 ABI compatibility). If you see `undefined symbol` errors, the flash-attn version doesn't match your torch — rebuild with `--no-binary flash-attn`.

## Model

- **SongGeneration v2-large** (LeVo 2) — Tencent AI Lab
- 4B parameters, Apache-2.0 license
- Hybrid LLM + Diffusion, voice + instruments in one pass
- Up to 4m30 per song, multilingual (EN, FR, ES, ZH, JA)
- VRAM: ~30 GB standard (`USE_LOW_MEM=false`), ~10 GB low-mem mode (`USE_LOW_MEM=true`)

## License

Apache-2.0
