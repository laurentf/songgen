"""Bootstrap script — installs deps, downloads model, starts handler.

Entry point from RunPod Docker Command. First run installs everything
on the network volume (~15 min). Subsequent runs skip to handler (~30s).
"""
from __future__ import annotations

import os
import subprocess
import sys


WORKSPACE = "/workspace"
MODEL_DIR = os.path.join(WORKSPACE, "songgeneration_v2_large")
RUNTIME_DIR = os.path.join(WORKSPACE, "runtime")
CKPT_DIR = os.path.join(WORKSPACE, "ckpt")
THIRD_PARTY_DIR = os.path.join(WORKSPACE, "third_party")
SONGGEN_DIR = os.path.join(WORKSPACE, "SongGeneration")
DEPS_FLAG = os.path.join(WORKSPACE, ".deps_ok")


def run(cmd: str) -> None:
    print(f"  → {cmd}", flush=True)
    subprocess.run(cmd, shell=True, check=True)


def download_model(repo_id: str, local_dir: str) -> None:
    print(f"  → downloading {repo_id} to {local_dir}", flush=True)
    from huggingface_hub import snapshot_download
    token = os.environ.get("HF_TOKEN")
    snapshot_download(repo_id=repo_id, local_dir=local_dir, token=token)


def main() -> None:
    print("=== SongGen Setup ===", flush=True)

    # 1. Install system packages (python3, pip, git, ffmpeg)
    if not os.path.exists(DEPS_FLAG):
        print("[1/5] Installing system packages...", flush=True)
        run("apt-get update -qq && apt-get install -y -qq python3-pip git ffmpeg libsndfile1 > /dev/null 2>&1")

    # 2. Clone SongGeneration repo
    if not os.path.isdir(SONGGEN_DIR):
        print("[2/5] Cloning SongGeneration repo...", flush=True)
        run(f"git clone https://github.com/tencent-ailab/SongGeneration.git {SONGGEN_DIR}")
    else:
        print("[2/5] SongGeneration repo present.", flush=True)

    # 3. Install Python deps (clean, no conflicts)
    if not os.path.exists(DEPS_FLAG):
        print("[3/5] Installing Python dependencies...", flush=True)
        # SongGeneration requirements first (torch, lightning, etc.)
        run(f"pip install -q --root-user-action=ignore -r {SONGGEN_DIR}/requirements.txt")
        # Our deps
        run("pip install -q --root-user-action=ignore huggingface_hub runpod supabase pydantic structlog python-dotenv audio-separator")
        open(DEPS_FLAG, "w").close()
    else:
        print("[3/5] Dependencies cached.", flush=True)

    # 4. Download model
    if not os.path.isfile(os.path.join(MODEL_DIR, "config.yaml")):
        print("[4/5] Downloading model v2-large...", flush=True)
        download_model("lglg666/SongGeneration-v2-large", MODEL_DIR)
    else:
        print("[4/5] Model cached.", flush=True)

    # 5. Download runtime (ckpt + third_party)
    if not os.path.isdir(CKPT_DIR):
        print("[5/5] Downloading runtime...", flush=True)
        download_model("lglg666/SongGeneration-Runtime", RUNTIME_DIR)
        import shutil
        runtime_ckpt = os.path.join(RUNTIME_DIR, "ckpt")
        runtime_tp = os.path.join(RUNTIME_DIR, "third_party")
        if os.path.isdir(runtime_ckpt):
            shutil.move(runtime_ckpt, CKPT_DIR)
        if os.path.isdir(runtime_tp):
            shutil.move(runtime_tp, THIRD_PARTY_DIR)
    else:
        print("[5/5] Runtime cached.", flush=True)

    print("=== Starting handler ===", flush=True)
    os.execvp(sys.executable, [sys.executable, "-m", "worker.handler"])


if __name__ == "__main__":
    main()
