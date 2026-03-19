"""Download model to network volume if not already present."""
from __future__ import annotations

import os
import shutil


WORKSPACE = os.environ.get("RUNPOD_VOLUME_PATH", "/runpod-volume")
MODEL_DIR = os.path.join(WORKSPACE, "songgeneration_v2_large")
RUNTIME_DIR = os.path.join(WORKSPACE, "runtime")
CKPT_DIR = os.path.join(WORKSPACE, "ckpt")
THIRD_PARTY_DIR = os.path.join(WORKSPACE, "third_party")


def download_model(repo_id: str, local_dir: str) -> None:
    print(f"  Downloading {repo_id}...", flush=True)
    from huggingface_hub import snapshot_download
    token = os.environ.get("HF_TOKEN")
    snapshot_download(repo_id=repo_id, local_dir=local_dir, token=token)


def ensure_model() -> None:
    """Download model + runtime to volume if not cached."""
    os.makedirs(WORKSPACE, exist_ok=True)
    if not os.path.isfile(os.path.join(MODEL_DIR, "config.yaml")):
        print("[setup] Downloading model v2-large...", flush=True)
        download_model("lglg666/SongGeneration-v2-large", MODEL_DIR)
    else:
        print("[setup] Model cached.", flush=True)

    if not os.path.isdir(CKPT_DIR):
        print("[setup] Downloading runtime...", flush=True)
        download_model("lglg666/SongGeneration-Runtime", RUNTIME_DIR)
        runtime_ckpt = os.path.join(RUNTIME_DIR, "ckpt")
        runtime_tp = os.path.join(RUNTIME_DIR, "third_party")
        if os.path.isdir(runtime_ckpt):
            shutil.move(runtime_ckpt, CKPT_DIR)
        if os.path.isdir(runtime_tp):
            shutil.move(runtime_tp, THIRD_PARTY_DIR)
    else:
        print("[setup] Runtime cached.", flush=True)
