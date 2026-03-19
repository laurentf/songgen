# SongGeneration v2 — Integration Notes

Notes on running SongGeneration v2-large in a Docker container. These issues were discovered during deployment on RunPod serverless.

## Dependency Conflicts

### wandb + protobuf

**Problem:** SongGeneration's `requirements.txt` installs `wandb` which depends on `protobuf`. The latest versions are incompatible with each other and with `descript-audiotools` (wants `protobuf <3.20`).

**Solution:** Exclude `wandb` from install entirely. It's only needed for experiment tracking during training, not for inference. Create a stub module so `flashy` (which imports `wandb`) doesn't crash:

```dockerfile
RUN grep -v 'wandb' requirements.txt > /tmp/req.txt && pip install -r /tmp/req.txt
RUN mkdir -p .../wandb/proto && echo "" > .../wandb/__init__.py
```

### audio-separator

**Problem:** `levo_inference.py` imports `from separator import Separator`. The pip package `audio-separator` doesn't provide the `separator` module on Python 3.11.

**Solution:** Stub it — only needed for `--separate_tracks` mode which we don't use:

```dockerfile
RUN mkdir -p .../separator && echo "class Separator: pass" > .../separator/__init__.py
```

### Missing deps not in requirements.txt

These packages are needed but not listed in SongGeneration's `requirements.txt`:
- `omegaconf` — config loading
- `lightning` — PyTorch Lightning (model checkpoint format)
- `audio-separator` — vocal separation (stubbed)

## Python Import Issues

### No `__init__.py` in `tools/`

**Problem:** `tools/` and `tools/gradio/` are not proper Python packages — missing `__init__.py`. Importing `from tools.gradio.levo_inference import LeVoInference` fails.

**Solution:** Create them at build time:

```dockerfile
RUN touch tools/__init__.py tools/gradio/__init__.py
```

### Two different `tools/` directories

**Problem:** SongGeneration has TWO unrelated `tools/` directories:
- `SongGeneration/tools/` — contains `gradio/levo_inference.py` (main inference code)
- `SongGeneration/codeclm/tokenizer/Flow1dVAE/tools/` — contains `torch_tools.py`, `stft.py`, etc.

When `model_1rvq.py` (in `Flow1dVAE/`) does `from tools.torch_tools import wav_to_fbank`, Python finds the wrong `tools/` (the repo root one instead of the local one).

**Solution:** Merge both tools/ into one at build time:

```dockerfile
RUN cp SongGeneration/codeclm/tokenizer/Flow1dVAE/tools/*.py SongGeneration/tools/
```

Now `SongGeneration/tools/` contains both `gradio/` AND `torch_tools.py`.

### `model_1rvq.py` not importable

**Problem:** `generate_1rvq.py` does `from model_1rvq import PromptCondAudioDiffusion` — a non-qualified import. The file `model_1rvq.py` is in `Flow1dVAE/` but Python doesn't look there.

**Solution:** Add `Flow1dVAE/` to `sys.path`:

```python
FLOW_VAE_PATH = os.path.join(SONGGEN_REPO_PATH, "codeclm", "tokenizer", "Flow1dVAE")
sys.path.insert(0, FLOW_VAE_PATH)
```

## File Path Issues

### Relative paths to checkpoints

**Problem:** The model code uses relative paths like `./ckpt/model_1rvq/model_2_fixed.safetensors` and `./ckpt/vae/stable_audio_1920_vae.json`. These are relative to the current working directory.

The model weights are on the RunPod network volume at `/runpod-volume/ckpt/`, but the Docker container's cwd is `/app`.

**Solution:** Create symlinks at runtime from both `/app/ckpt` and `/app/SongGeneration/ckpt` to the volume:

```python
for parent in [SONGGEN_REPO_PATH, "/app"]:
    dst = os.path.join(parent, "ckpt")
    if not os.path.exists(dst):
        os.symlink("/runpod-volume/ckpt", dst)
```

Same for `third_party/`.

### Volume mount path

**Problem:** RunPod serverless mounts network volumes at `/runpod-volume`, not `/workspace`. The env vars must match.

**Solution:** Set `SONGGEN_CKPT_PATH=/runpod-volume/songgeneration_v2_large` in the template env vars.

## Runtime Download

The model consists of two HuggingFace repos:
- `lglg666/SongGeneration-v2-large` (~2 GB) — model weights + config
- `lglg666/SongGeneration-Runtime` (~15 GB, 114 files) — runtime checkpoints (ckpt/ + third_party/)

The Runtime repo must be unpacked: `runtime/ckpt/` → `/runpod-volume/ckpt/`, `runtime/third_party/` → `/runpod-volume/third_party/`.

First download takes ~8-10 min. Cached on the network volume after that.

## sys.path Order

Final working sys.path order (added via `sys.path.insert(0)` in reverse):

1. `/app/SongGeneration` — `tools.gradio`, `tools.torch_tools`, `codeclm.*`
2. `/runpod-volume/ckpt` — runtime checkpoint modules
3. `/app/SongGeneration/codeclm/tokenizer/Flow1dVAE` — `model_1rvq`, `model_2rvq`, etc.
