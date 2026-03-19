"""Tests for Supabase Storage upload helpers. Covers STOR-01, STOR-02, STOR-03."""
import os
import pytest
from unittest.mock import patch, MagicMock


def test_upload_called_with_bytes(sample_wav_bytes, mock_supabase_client):
    """STOR-01: upload() is called with bytes, correct filename pattern, content-type."""
    with patch("worker.storage._client", mock_supabase_client):
        from worker.storage import upload_to_supabase
        url = upload_to_supabase("radio_lofi_001", sample_wav_bytes)

    bucket = mock_supabase_client.storage.from_.return_value
    call_args = bucket.upload.call_args
    assert call_args is not None
    # path arg must match pattern: idx_TIMESTAMP.wav
    path_arg = call_args.kwargs.get("path") or call_args.args[0]
    assert path_arg.startswith("radio_lofi_001_")
    assert path_arg.endswith(".wav")
    # file arg must be bytes
    file_arg = call_args.kwargs.get("file") or call_args.args[1]
    assert isinstance(file_arg, bytes)
    assert len(file_arg) == len(sample_wav_bytes)


def test_public_url_returned(sample_wav_bytes, mock_supabase_client):
    """STOR-02: Public URL string is returned from get_public_url."""
    with patch("worker.storage._client", mock_supabase_client):
        from worker.storage import upload_to_supabase
        url = upload_to_supabase("radio_lofi_001", sample_wav_bytes)

    assert url.startswith("https://")
    assert "supabase" in url or "storage" in url


def test_content_type_is_audio_wav(sample_wav_bytes, mock_supabase_client):
    """Upload uses content-type audio/wav."""
    with patch("worker.storage._client", mock_supabase_client):
        from worker.storage import upload_to_supabase
        upload_to_supabase("test_idx", sample_wav_bytes)

    bucket = mock_supabase_client.storage.from_.return_value
    call_args = bucket.upload.call_args
    file_options = call_args.kwargs.get("file_options") or call_args.args[2]
    assert file_options.get("content-type") == "audio/wav"


def test_missing_supabase_url_raises(monkeypatch):
    """STOR-03: Missing SUPABASE_URL env var raises at module import / startup."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_BUCKET", raising=False)
    import importlib
    import worker.storage as storage_mod
    # Re-importing with missing vars should raise KeyError or RuntimeError
    with pytest.raises((KeyError, RuntimeError, Exception)):
        importlib.reload(storage_mod)
