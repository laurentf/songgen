"""
Tests for schemas.py — TrackSpec, BatchRequest, parse_descriptions.

All tests must pass (GREEN) after schemas.py is implemented.
"""
import pytest
import pydantic


# ---------------------------------------------------------------------------
# TrackSpec validation tests
# ---------------------------------------------------------------------------

def test_valid_track():
    """A fully specified TrackSpec with all required fields succeeds."""
    from worker.schemas import TrackSpec

    track = TrackSpec(**{"idx": "song_001", "gt_lyric": "[verse] Walking through the rain."})
    assert track.idx == "song_001"
    assert track.gt_lyric == "[verse] Walking through the rain."


def test_missing_idx_raises():
    """TrackSpec without idx raises ValidationError."""
    from worker.schemas import TrackSpec

    with pytest.raises(pydantic.ValidationError):
        TrackSpec(**{"gt_lyric": "[verse] some lyric."})


def test_missing_lyric_raises():
    """TrackSpec without gt_lyric raises ValidationError."""
    from worker.schemas import TrackSpec

    with pytest.raises(pydantic.ValidationError):
        TrackSpec(**{"idx": "song_001"})


def test_empty_lyric_raises():
    """TrackSpec with empty gt_lyric raises ValidationError."""
    from worker.schemas import TrackSpec

    with pytest.raises(pydantic.ValidationError):
        TrackSpec(**{"idx": "song_001", "gt_lyric": ""})


def test_descriptions_optional():
    """TrackSpec without descriptions defaults to None."""
    from worker.schemas import TrackSpec

    track = TrackSpec(**{"idx": "song_001", "gt_lyric": "[verse] text."})
    assert track.descriptions is None


# ---------------------------------------------------------------------------
# parse_descriptions tests
# ---------------------------------------------------------------------------

def test_parse_descriptions_all_fields():
    """Full descriptions string is parsed into all 4 dimensions."""
    from worker.schemas import parse_descriptions

    result = parse_descriptions("female, pop, sad, piano and drums, the bpm is 120")
    assert result["gender"] == "female"
    assert result["bpm"] == 120
    assert result.get("genre") == "pop"
    assert result.get("mood") == "sad"
    assert "piano and drums" in result.get("instruments", [])


def test_parse_descriptions_none():
    """parse_descriptions(None) returns empty dict."""
    from worker.schemas import parse_descriptions

    assert parse_descriptions(None) == {}


def test_parse_descriptions_bpm_only():
    """parse_descriptions with only BPM returns {"bpm": N}."""
    from worker.schemas import parse_descriptions

    result = parse_descriptions("the bpm is 95")
    assert result == {"bpm": 95}


# ---------------------------------------------------------------------------
# BatchRequest tests
# ---------------------------------------------------------------------------

def test_batch_request_valid():
    """BatchRequest wrapping a single TrackSpec dict succeeds."""
    from worker.schemas import BatchRequest

    req = BatchRequest(tracks=[{"idx": "song_001", "gt_lyric": "[verse] text."}])
    assert len(req.tracks) == 1
    assert req.tracks[0].idx == "song_001"


def test_batch_request_empty_list():
    """BatchRequest with an empty tracks list is valid (0 tracks)."""
    from worker.schemas import BatchRequest

    req = BatchRequest(tracks=[])
    assert req.tracks == []
