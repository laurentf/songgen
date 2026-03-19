"""
Supabase Storage client and upload helper.

Environment variables required at startup (raises KeyError if absent):
  SUPABASE_URL    — e.g. https://abcdef.supabase.co
  SUPABASE_KEY    — service role key or anon key with storage write access
  SUPABASE_BUCKET — bucket name, e.g. "songs"

The songs bucket MUST be configured as public in the Supabase dashboard
(Storage > Bucket > Make Public) before get_public_url() URLs will be accessible.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import structlog
from supabase import create_client

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Fail-fast: validate required env vars at import time
# ---------------------------------------------------------------------------
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_KEY"]
SUPABASE_BUCKET: str = os.environ["SUPABASE_BUCKET"]

# ---------------------------------------------------------------------------
# Module-level Supabase client (reused across all uploads in the worker lifetime)
# ---------------------------------------------------------------------------
_client = create_client(SUPABASE_URL, SUPABASE_KEY)

logger.info("Supabase client initialised", bucket=SUPABASE_BUCKET)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upload_to_supabase(idx: str, wav_bytes: bytes) -> str:
    """Upload WAV bytes to Supabase Storage and return the public URL.

    Args:
        idx:       Track identifier — used as filename prefix.
        wav_bytes: Raw WAV file content as bytes.

    Returns:
        Public URL string for the uploaded file.

    Raises:
        Exception: Any Supabase upload error (no retry — caller handles as track error).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    filename = f"{idx}_{timestamp}.wav"

    logger.info("Uploading to Supabase", idx=idx, filename=filename, size_bytes=len(wav_bytes))

    _client.storage.from_(SUPABASE_BUCKET).upload(
        path=filename,
        file=wav_bytes,
        file_options={"content-type": "audio/wav", "upsert": "false"},
    )

    url: str = _client.storage.from_(SUPABASE_BUCKET).get_public_url(filename)
    logger.info("Upload complete", idx=idx, url=url)
    return url
