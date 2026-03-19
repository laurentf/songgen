"""Tests for batch processing via generate_batch. Covers BATCH-01, BATCH-02, BATCH-03, BATCH-04."""
from __future__ import annotations

from unittest.mock import patch


def _success_result(idx: str) -> dict:
    return {
        "idx": idx,
        "status": "success",
        "url": f"https://test.supabase.co/storage/v1/object/public/songs/{idx}.wav",
        "duration": 180.0,
        "file_size": 16000000,
        "genre": "pop",
        "mood": "sad",
        "bpm": 120,
        "gender": "female",
        "instruments": ["piano"],
    }


def test_batch_3_tracks_returns_3_results(sample_track_dict: dict) -> None:
    """BATCH-01: 3-track input -> 3-result output."""
    tracks = [dict(sample_track_dict, idx=f"track_{i}") for i in range(3)]

    with patch("worker.generator.generate_track", return_value=(b"fake_wav", 180.0)), \
         patch("worker.generator.upload_to_supabase", return_value="https://test.url/ok.wav"):
        from worker.generator import generate_batch
        results = generate_batch(tracks)

    assert len(results) == 3


def test_per_track_isolation(sample_track_dict: dict) -> None:
    """BATCH-02: One error track doesn't kill others."""
    tracks = [dict(sample_track_dict, idx=f"track_{i}") for i in range(3)]
    call_count = 0

    def fake_generate(track):
        nonlocal call_count
        call_count += 1
        if track.idx == "track_1":
            raise RuntimeError("Simulated GPU error")
        return b"fake_wav", 180.0

    with patch("worker.generator.generate_track", side_effect=fake_generate), \
         patch("worker.generator.upload_to_supabase", return_value="https://test.url/ok.wav"), \
         patch("torch.cuda.empty_cache"):
        from worker.generator import generate_batch
        results = generate_batch(tracks)

    statuses = [r["status"] for r in results]
    assert statuses.count("success") == 2
    assert statuses.count("error") == 1


def test_idx_passthrough(sample_track_dict: dict) -> None:
    """BATCH-03: idx from input appears in every result."""
    tracks = [dict(sample_track_dict, idx="my_unique_idx")]

    with patch("worker.generator.generate_track", return_value=(b"fake_wav", 180.0)), \
         patch("worker.generator.upload_to_supabase", return_value="https://test.url/ok.wav"):
        from worker.generator import generate_batch
        results = generate_batch(tracks)

    assert results[0]["idx"] == "my_unique_idx"


def test_result_schema_success(sample_track_dict: dict) -> None:
    """BATCH-04: Success result contains url, duration, status, idx, file_size."""
    tracks = [sample_track_dict]

    with patch("worker.generator.generate_track", return_value=(b"fake_wav", 180.0)), \
         patch("worker.generator.upload_to_supabase", return_value="https://test.url/ok.wav"):
        from worker.generator import generate_batch
        results = generate_batch(tracks)

    result = results[0]
    for key in ("idx", "status", "url", "duration", "file_size"):
        assert key in result, f"Missing key: {key}"
    assert result["status"] == "success"
    assert result["url"].startswith("https://")


def test_empty_tracks_returns_empty() -> None:
    """Empty tracks list -> empty results, no crash."""
    from worker.generator import generate_batch
    results = generate_batch([])

    assert results == []
