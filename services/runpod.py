"""RunPod serverless API client — submit jobs and poll results."""
from __future__ import annotations

import time

import requests
import structlog

from services.config import RUNPOD_API_KEY, RUNPOD_ENDPOINT_ID

logger = structlog.get_logger(__name__)

API_BASE = "https://api.runpod.ai/v2"


def _headers() -> dict:
    return {"Authorization": f"Bearer {RUNPOD_API_KEY}"}


def run_job(tracks: list[dict], *, timeout: int = 600) -> dict:
    """Submit a job and wait for results.

    Uses /runsync first. If still processing, polls /status.
    """
    endpoint_id = RUNPOD_ENDPOINT_ID
    logger.info("submitting_job", endpoint_id=endpoint_id, track_count=len(tracks))

    resp = requests.post(
        f"{API_BASE}/{endpoint_id}/runsync",
        headers=_headers(),
        json={"input": {"tracks": tracks}},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    status = data.get("status")

    if status == "COMPLETED":
        logger.info("job_completed_sync", job_id=data.get("id"))
        return data.get("output", {})

    if status in ("IN_PROGRESS", "IN_QUEUE"):
        return _poll_job(endpoint_id, data["id"], timeout=timeout)

    if status == "FAILED":
        raise RuntimeError(f"Job failed: {data.get('error', 'unknown')}")

    raise RuntimeError(f"Unexpected job status: {status}")


def _poll_job(endpoint_id: str, job_id: str, *, timeout: int = 600) -> dict:
    """Poll a job until completion."""
    logger.info("polling_job", job_id=job_id)
    start = time.time()

    while time.time() - start < timeout:
        resp = requests.get(
            f"{API_BASE}/{endpoint_id}/status/{job_id}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        status = data.get("status")
        if status == "COMPLETED":
            logger.info("job_completed", job_id=job_id)
            return data.get("output", {})
        elif status == "FAILED":
            raise RuntimeError(f"Job failed: {data.get('error', 'unknown')}")

        elapsed = int(time.time() - start)
        logger.info("job_in_progress", job_id=job_id, status=status, elapsed=f"{elapsed}s")
        time.sleep(5)

    raise TimeoutError(f"Job {job_id} timed out after {timeout}s")
