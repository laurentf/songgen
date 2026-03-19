"""Shared fixtures for Phase 1 tests."""
from __future__ import annotations

import os
import struct

# Set test env vars BEFORE any app imports (storage.py reads at import time)
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("SUPABASE_BUCKET", "songs")

import pytest
import torch
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_track_dict() -> dict[str, str]:
    """Minimal valid track input dict."""
    return {
        "idx": "radio_lofi_001",
        "gt_lyric": "[intro-medium]\n[verse] Le train siffle dans la nuit.\n[chorus] Laisse-moi partir.\n[outro-medium]",
        "descriptions": "female, lo-fi, chill, piano and vinyl, the bpm is 85",
    }


@pytest.fixture
def sample_track_dict_no_descriptions() -> dict[str, str]:
    """Valid track with no descriptions (optional field)."""
    return {
        "idx": "radio_pop_002",
        "gt_lyric": "[intro-short]\n[verse] Walking through the city rain.\n[outro-short]",
    }


@pytest.fixture
def sample_wav_bytes() -> bytes:
    """Minimal valid WAV file bytes (44-byte header + 1 second of silence at 48kHz mono)."""
    sample_rate = 48000
    num_channels = 1
    bits_per_sample = 16
    num_samples = sample_rate  # 1 second
    data_size = num_samples * num_channels * (bits_per_sample // 8)
    byte_rate = sample_rate * num_channels * (bits_per_sample // 8)
    block_align = num_channels * (bits_per_sample // 8)

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,                # PCM chunk size
        1,                 # PCM format
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    audio_data = bytes(data_size)
    return header + audio_data


@pytest.fixture
def mock_model() -> MagicMock:
    """Mock LeVoInference that returns a fake audio tensor."""
    model = MagicMock()
    # forward() returns tensor shape [1, 2, 48000] (1s stereo at 48kHz)
    model.forward.return_value = torch.zeros(1, 2, 48000)
    return model


@pytest.fixture
def mock_supabase_client() -> MagicMock:
    """Mock Supabase client with storage methods."""
    client = MagicMock()
    storage = MagicMock()
    bucket = MagicMock()
    bucket.upload.return_value = {"Key": "songs/radio_lofi_001_20260318T100000.wav"}
    bucket.get_public_url.return_value = (
        "https://test.supabase.co/storage/v1/object/public/songs/radio_lofi_001_20260318T100000.wav"
    )
    storage.from_.return_value = bucket
    client.storage = storage
    return client
