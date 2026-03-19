"""Entry point — download model if needed, then start handler."""
from __future__ import annotations

from worker.setup_model import ensure_model

print("=== SongGen Worker ===", flush=True)
ensure_model()

print("Starting handler...", flush=True)
from worker.handler import handler
import runpod
runpod.serverless.start({"handler": handler})
