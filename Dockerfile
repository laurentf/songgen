FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-dev python3-pip python3.11-venv \
    git wget ffmpeg libsndfile1 \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone SongGeneration repo
RUN git clone https://github.com/tencent-ailab/SongGeneration.git /app/SongGeneration

# Fix SongGeneration's broken Python package structure:
# 1. Make tools/ a proper Python package
# 2. Copy Flow1dVAE/tools/* into SongGeneration/tools/ so both tools.gradio AND tools.torch_tools work
RUN touch /app/SongGeneration/tools/__init__.py /app/SongGeneration/tools/gradio/__init__.py \
    && cp /app/SongGeneration/codeclm/tokenizer/Flow1dVAE/tools/*.py /app/SongGeneration/tools/

# Upgrade pip
RUN pip install --upgrade pip

# Install SongGeneration requirements WITHOUT wandb (not needed for inference)
RUN grep -v 'wandb' /app/SongGeneration/requirements.txt > /tmp/requirements_no_wandb.txt \
    && pip install --no-cache-dir -r /tmp/requirements_no_wandb.txt

# Stub out wandb and separator (not needed for inference, only for training/separation)
RUN mkdir -p /usr/local/lib/python3.11/dist-packages/wandb/proto \
    && echo "" > /usr/local/lib/python3.11/dist-packages/wandb/__init__.py \
    && echo "" > /usr/local/lib/python3.11/dist-packages/wandb/proto/__init__.py \
    && mkdir -p /usr/local/lib/python3.11/dist-packages/separator \
    && echo "class Separator: pass" > /usr/local/lib/python3.11/dist-packages/separator/__init__.py

# Flash Attention 2 — required by the model's transformer layers at inference time
# Pin to 2.7.4 — last series compatible with torch 2.6.0 C++ ABI
RUN pip install --no-cache-dir flash-attn==2.7.4.post1 --no-build-isolation --no-binary flash-attn

# Install our deps
RUN pip install --no-cache-dir \
    huggingface_hub runpod supabase pydantic structlog python-dotenv

# Verify LeVoInference imports correctly (fails the build if broken)
ENV SONGGEN_REPO_PATH=/app/SongGeneration
RUN python -c "import sys; sys.path.insert(0, '/app/SongGeneration'); from tools.gradio.levo_inference import LeVoInference; print('LeVoInference import OK')"

# Copy worker code
COPY worker/ /app/worker/
COPY handler.py /app/handler.py

# Env defaults — model paths point to network volume (/runpod-volume is RunPod's default mount)
ENV SONGGEN_CKPT_PATH=/runpod-volume/songgeneration_v2_large
ENV SONGGEN_SHARED_CKPT_PATH=/runpod-volume/ckpt
ENV RUNPOD_VOLUME_PATH=/runpod-volume
ENV USE_LOW_MEM=false

CMD ["python3", "-u", "/app/handler.py"]
