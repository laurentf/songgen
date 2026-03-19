"""RunPod serverless handler for SongGeneration v2."""
import runpod

from worker.setup_model import ensure_model

print("=== SongGen Worker ===", flush=True)
ensure_model()

print("Starting handler...", flush=True)
from worker.generator import generate_batch


def handler(job):
    """Process a song generation job.

    Input:
        {"tracks": [{"idx": str, "gt_lyric": str, "descriptions": str, "params": {}}]}

    Output:
        {"results": [{"idx": str, "status": "success"|"error", "url": str, ...}]}
    """
    job_input = job.get("input", {})
    tracks = job_input.get("tracks", [])

    if not tracks:
        return {"error": "No tracks provided", "results": []}

    results = generate_batch(tracks)
    return {"results": results}


runpod.serverless.start({"handler": handler})
