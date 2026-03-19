"""
SongGeneration v2 inference module.

Exposes:
  MODEL          — module-level LeVoInference singleton (loaded once at startup)
  generate_track(track: TrackSpec) -> tuple[bytes, float]
  generate_batch(tracks: list[dict]) -> list[dict]

Environment variables:
  USE_LOW_MEM        — "true" uses LeVoInferenceLowMem (10GB VRAM); default "false" (22GB)
  MODEL_CKPT_PATH    — path to model checkpoint dir; default "/app/songgeneration_v2_large"
  SONGGEN_REPO_PATH  — path to cloned SongGeneration repo; default "/app/SongGeneration"

The SongGeneration repo must be present at SONGGEN_REPO_PATH. It is NOT pip-installable.
"""
from __future__ import annotations

import os
import sys
import tempfile

import structlog
import torch
import torchaudio
import wave as _wave
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# torchaudio.info compatibility shim
# torchaudio>=2.x removed torchaudio.info; provide a drop-in using stdlib wave.
# Production code on torchaudio 2.6.0 (pinned in SongGeneration requirements.txt)
# will have the real torchaudio.info. This shim is for dev/test environments.
# ---------------------------------------------------------------------------
if not hasattr(torchaudio, "info"):
    class _AudioInfo:
        """Minimal AudioMetaData shim: exposes num_frames and sample_rate."""
        def __init__(self, num_frames: int, sample_rate: int) -> None:
            self.num_frames = num_frames
            self.sample_rate = sample_rate

    def _torchaudio_info(filepath: str) -> _AudioInfo:
        with _wave.open(filepath, "rb") as wf:
            return _AudioInfo(num_frames=wf.getnframes(), sample_rate=wf.getframerate())

    torchaudio.info = _torchaudio_info  # type: ignore[attr-defined]

from worker.schemas import TrackSpec, parse_descriptions
from worker.storage import upload_to_supabase

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
USE_LOW_MEM: bool = os.environ.get("USE_LOW_MEM", "false").lower() == "true"
CKPT_PATH: str = os.environ.get("SONGGEN_CKPT_PATH", os.environ.get("MODEL_CKPT_PATH", "/app/songgeneration_v2_large"))
SONGGEN_REPO_PATH: str = os.environ.get("SONGGEN_REPO_PATH", "/app/SongGeneration")

# ---------------------------------------------------------------------------
# Model loading — happens once at module import, before runpod.serverless.start()
# "Loading model" appears EXACTLY ONCE per worker lifetime (success criterion #3)
# ---------------------------------------------------------------------------
logger.info("Loading model", ckpt_path=CKPT_PATH, low_mem=USE_LOW_MEM)

# Add paths to sys.path:
# SongGeneration repo first (tools.gradio + tools.torch_tools both merged there)
# Flow1dVAE for model_1rvq.py imports
# ckpt dir for runtime modules
FLOW_VAE_PATH = os.path.join(SONGGEN_REPO_PATH, "codeclm", "tokenizer", "Flow1dVAE")
SHARED_CKPT_PATH: str = os.environ.get("SONGGEN_SHARED_CKPT_PATH", "/runpod-volume/ckpt")

for p in [FLOW_VAE_PATH, SHARED_CKPT_PATH, SONGGEN_REPO_PATH]:
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

# Symlink dirs into /app (cwd) so relative paths like ./ckpt and ./conf work
VOLUME_PATH = os.environ.get("RUNPOD_VOLUME_PATH", "/runpod-volume")

# Volume dirs → /app and /app/SongGeneration
for dirname in ["ckpt", "third_party"]:
    src = os.path.join(VOLUME_PATH, dirname)
    for parent in [SONGGEN_REPO_PATH, "/app"]:
        dst = os.path.join(parent, dirname)
        if os.path.isdir(src) and not os.path.exists(dst):
            os.symlink(src, dst)

# Repo dirs → /app (for ./conf/vocab.yaml etc.)
for dirname in ["conf"]:
    src = os.path.join(SONGGEN_REPO_PATH, dirname)
    dst = os.path.join("/app", dirname)
    if os.path.isdir(src) and not os.path.exists(dst):
        os.symlink(src, dst)

try:
    # Debug: log sys.path to understand import resolution
    logger.info("sys_path_debug", path=sys.path[:5], cwd=os.getcwd())
    if USE_LOW_MEM:
        from tools.gradio.levo_inference_lowmem import LeVoInference as _InferenceClass
    else:
        from tools.gradio.levo_inference import LeVoInference as _InferenceClass  # type: ignore[assignment]

    MODEL = _InferenceClass(ckpt_path=CKPT_PATH)
    MODEL.eval()
    logger.info("Model loaded", ckpt_path=CKPT_PATH, low_mem=USE_LOW_MEM)
except Exception as _load_err:
    import traceback
    MODEL = None  # type: ignore[assignment]
    logger.error(
        "MODEL LOAD FAILED",
        error=str(_load_err),
        traceback=traceback.format_exc(),
        ckpt_path=CKPT_PATH,
        songgen_repo=SONGGEN_REPO_PATH,
        repo_exists=os.path.isdir(SONGGEN_REPO_PATH),
        ckpt_exists=os.path.isdir(CKPT_PATH),
        config_exists=os.path.isfile(os.path.join(CKPT_PATH, "config.yaml")),
    )


# ---------------------------------------------------------------------------
# Track generation
# ---------------------------------------------------------------------------

def generate_track(track: TrackSpec) -> tuple[bytes, float]:
    """Run inference for a single track and return (wav_bytes, duration_seconds).

    Args:
        track: Validated TrackSpec with idx, gt_lyric, descriptions.

    Returns:
        wav_bytes: Raw WAV file content as bytes (48kHz, stereo).
        duration:  Duration in seconds computed from WAV header.

    Raises:
        Any exception from MODEL.forward() or torchaudio.save() propagates to caller.
    """
    logger.info("Generating track", idx=track.idx)

    with torch.inference_mode():
        audio_tensor = MODEL.forward(
            lyric=track.gt_lyric,
            description=track.descriptions,
            gen_type=track.gen_type,
            params=track.params.model_dump(),
        )

    # Normalise tensor shape: MODEL returns [1, channels, samples] — squeeze batch dim
    audio_cpu = audio_tensor.cpu()
    if audio_cpu.dim() == 3:
        audio_cpu = audio_cpu.squeeze(0)  # → [channels, samples]
    # Ensure 2D for torchaudio.save()
    if audio_cpu.dim() == 1:
        audio_cpu = audio_cpu.unsqueeze(0)  # mono → [1, samples]

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        torchaudio.save(tmp_path, audio_cpu, sample_rate=48000)

        info = torchaudio.info(tmp_path)
        duration = info.num_frames / info.sample_rate

        with open(tmp_path, "rb") as f:
            wav_bytes = f.read()
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    logger.info("Track generated", idx=track.idx, duration=duration, size_bytes=len(wav_bytes))
    return wav_bytes, duration


# ---------------------------------------------------------------------------
# Batch orchestration
# ---------------------------------------------------------------------------

def generate_batch(tracks: list[dict]) -> list[dict]:
    """Process a list of raw track dicts and return a structured result per track.

    Processing is sequential (BATCH-01). Each track is isolated in its own
    try/except (BATCH-02). idx is always present in every result (BATCH-03).

    Args:
        tracks: List of raw dicts from job["input"]["tracks"].

    Returns:
        List of result dicts — one per input track, in order.
        Each result has at minimum: idx, status.
        Success results additionally have: url, duration, file_size, genre, mood, bpm, gender, instruments.
        Error results additionally have: error_message.
    """
    results: list[dict] = []

    for raw in tracks:
        # --- Validate input ---
        try:
            track = TrackSpec(**raw)
        except ValidationError as exc:
            logger.warning("Track validation failed", idx=raw.get("idx", "unknown"), error=str(exc))
            results.append({
                "idx": raw.get("idx", "unknown"),
                "status": "error",
                "error_message": f"Validation error: {exc}",
            })
            continue

        # --- Generate + upload ---
        try:
            wav_bytes, duration = generate_track(track)

            # Upload immediately after generation (crash resilience — don't wait for end of batch)
            url = upload_to_supabase(track.idx, wav_bytes)

            # Parse descriptions into structured fields for enriched response
            parsed = parse_descriptions(track.descriptions)

            results.append({
                "idx": track.idx,
                "status": "success",
                "url": url,
                "duration": round(duration, 3),
                "file_size": len(wav_bytes),
                "genre": parsed.get("genre"),
                "mood": parsed.get("mood"),
                "bpm": parsed.get("bpm"),
                "gender": parsed.get("gender"),
                "instruments": parsed.get("instruments", []),
            })

        except Exception as exc:
            logger.exception("Track failed", idx=track.idx, error=str(exc))
            # Reclaim VRAM so subsequent tracks don't OOM (PITFALL: VRAM creep)
            torch.cuda.empty_cache()
            results.append({
                "idx": track.idx,
                "status": "error",
                "error_message": str(exc),
            })

    return results
