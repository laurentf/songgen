"""
Pydantic schemas for the SongGeneration RunPod worker.

Models:
  TrackSpec     — single track input (idx, gt_lyric, descriptions)
  BatchRequest  — wrapper for a list of tracks (matches RunPod input shape)

Helpers:
  parse_descriptions() — parse comma-separated descriptions string into structured dict
"""
from __future__ import annotations

import re

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class GenerationParams(BaseModel):
    """Optional generation parameters — overrides defaults per track."""

    cfg_coef: float = 1.5
    temperature: float = 1.0
    top_k: int = 50
    top_p: float = 0.0


class TrackSpec(BaseModel):
    """Single track specification from the caller."""

    idx: str
    gt_lyric: str
    descriptions: str | None = None
    gen_type: str = "mixed"
    params: GenerationParams = GenerationParams()

    @field_validator("idx")
    @classmethod
    def idx_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("idx must not be empty")
        return v

    @field_validator("gt_lyric")
    @classmethod
    def lyric_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("gt_lyric must not be empty")
        return v


class BatchRequest(BaseModel):
    """Top-level batch input — wraps a list of TrackSpec dicts.

    Matches RunPod job input shape: job["input"]["tracks"]
    """

    tracks: list[TrackSpec]


# ---------------------------------------------------------------------------
# Descriptions parser
# ---------------------------------------------------------------------------

# Known gender tokens
_GENDERS = {"male", "female"}

# BPM pattern: "the bpm is 120"
_BPM_RE = re.compile(r"^the\s+bpm\s+is\s+(\d+)$", re.IGNORECASE)

# Common genre keywords (non-exhaustive — used for heuristic classification)
_GENRES = {
    "pop", "rock", "jazz", "blues", "classical", "folk", "country", "metal",
    "hip-hop", "hip hop", "r&b", "rnb", "electronic", "edm", "lo-fi", "lofi",
    "indie", "soul", "funk", "reggae", "punk", "alternative", "ambient",
    "synth-pop", "synthpop", "bossa nova", "latin", "k-pop",
}

# Common mood keywords
_MOODS = {
    "sad", "happy", "chill", "energetic", "melancholic", "romantic", "dark",
    "uplifting", "sweet", "angry", "peaceful", "nostalgic", "epic", "calm",
    "loving", "playful", "dramatic", "hopeful", "dreamy",
}


def parse_descriptions(desc: str | None) -> dict[str, str | int | list[str]]:
    """Parse the descriptions field into structured dimensions.

    Input:  "female, pop, sad, piano and vinyl, the bpm is 85"
    Output: {"gender": "female", "genre": "pop", "mood": "sad",
             "bpm": 85, "instruments": ["piano and vinyl"]}

    Returns empty dict if desc is None or empty.
    All matching is case-insensitive. Unknown tokens go into "instruments".
    """
    if not desc:
        return {}

    parts = [p.strip().lower() for p in desc.split(",") if p.strip()]
    result: dict[str, str | int | list[str]] = {}
    instruments: list[str] = []

    for part in parts:
        if part in _GENDERS:
            result["gender"] = part
        elif bpm_match := _BPM_RE.match(part):
            result["bpm"] = int(bpm_match.group(1))
        elif part in _GENRES:
            result.setdefault("genre", part)
        elif part in _MOODS:
            result.setdefault("mood", part)
        else:
            # Treat as instrument description
            instruments.append(part)

    if instruments:
        result["instruments"] = instruments

    return result
