"""Shared configuration loaded from environment variables."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# RunPod
RUNPOD_API_KEY: str = os.environ.get("RUNPOD_API_KEY", "")
RUNPOD_ENDPOINT_ID: str = os.environ.get("RUNPOD_ENDPOINT_ID", "")

# Supabase
SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY", "")
SUPABASE_BUCKET: str = os.environ.get("SUPABASE_BUCKET", "songs")


def validate_config() -> list[str]:
    """Return list of missing required env vars."""
    missing: list[str] = []
    if not RUNPOD_API_KEY:
        missing.append("RUNPOD_API_KEY")
    if not RUNPOD_ENDPOINT_ID:
        missing.append("RUNPOD_ENDPOINT_ID")
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_KEY")
    return missing
