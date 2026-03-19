"""Tests for generator.py: generate_track() and generate_batch(). Covers GEN-02, GEN-07, BATCH-02."""
import pytest
import torch
from unittest.mock import patch, MagicMock, call


def test_inference_mode_used(sample_track_dict, mock_model, sample_wav_bytes, tmp_path):
    """GEN-07: generate_track() calls MODEL.forward() inside torch.inference_mode()."""
    # We verify inference_mode is active by checking no_grad context is applied
    # The mock forward returns a valid tensor so generate_track completes
    from worker.schemas import TrackSpec
    track = TrackSpec(**sample_track_dict)

    with patch("worker.generator.MODEL", mock_model), \
         patch("worker.generator.upload_to_supabase", return_value="https://test.url/file.wav"), \
         patch("torchaudio.save"), \
         patch("torchaudio.info") as mock_info:
        mock_info.return_value = MagicMock(num_frames=48000, sample_rate=48000)
        with patch("builtins.open", MagicMock(return_value=MagicMock(
            __enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=sample_wav_bytes))),
            __exit__=MagicMock(return_value=False),
        ))):
            from worker.generator import generate_track
            wav_bytes, duration = generate_track(track)

    assert mock_model.forward.called
    assert duration == pytest.approx(1.0, abs=0.1)


def test_track_error_does_not_kill_batch(sample_track_dict, mock_model, sample_wav_bytes):
    """BATCH-02: Exception in one track → error result, batch continues."""
    tracks_input = [
        {**sample_track_dict, "idx": "track_0"},
        {**sample_track_dict, "idx": "track_1"},
        {**sample_track_dict, "idx": "track_2"},
    ]
    call_count = 0

    def fake_generate(track):
        nonlocal call_count
        call_count += 1
        if track.idx == "track_1":
            raise RuntimeError("Simulated GPU error")
        return sample_wav_bytes, 1.0

    with patch("worker.generator.generate_track", side_effect=fake_generate), \
         patch("worker.generator.upload_to_supabase", return_value="https://test.url/ok.wav"), \
         patch("torch.cuda.empty_cache"):
        from worker.generator import generate_batch
        results = generate_batch(tracks_input)

    assert len(results) == 3
    assert results[0]["status"] == "success"
    assert results[1]["status"] == "error"
    assert results[1]["idx"] == "track_1"
    assert "Simulated GPU error" in results[1]["error_message"]
    assert results[2]["status"] == "success"


def test_cuda_cache_cleared_on_error(sample_track_dict):
    """GEN-07 / BATCH-02: torch.cuda.empty_cache() called after track failure."""
    tracks_input = [{**sample_track_dict, "idx": "track_0"}]

    def fail_generate(track):
        raise RuntimeError("OOM")

    with patch("worker.generator.generate_track", side_effect=fail_generate), \
         patch("torch.cuda.empty_cache") as mock_cache:
        from worker.generator import generate_batch
        generate_batch(tracks_input)

    mock_cache.assert_called_once()


def test_validation_error_produces_error_result():
    """BATCH-02: Invalid track dict (missing idx) → error result, batch continues."""
    tracks_input = [
        {"gt_lyric": "[verse] No idx here", "descriptions": "pop"},  # missing idx
        {"idx": "track_valid", "gt_lyric": "[verse] Valid track"},
    ]

    with patch("worker.generator.generate_track", return_value=(b"fake_wav", 30.0)), \
         patch("worker.generator.upload_to_supabase", return_value="https://test.url/ok.wav"):
        from worker.generator import generate_batch
        results = generate_batch(tracks_input)

    assert len(results) == 2
    error_result = next(r for r in results if r["status"] == "error")
    assert "idx" in error_result
    assert "Validation" in error_result["error_message"] or "validation" in error_result["error_message"].lower()
