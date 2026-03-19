# SongGeneration v2 — Input Format

## Example Input

```json
{
  "idx": "song_001",
  "gt_lyric": "[intro-short]\n[verse] Walking through the city rain. Each step feels like a memory.\n[chorus] The warmth of yesterday remains. But you are gone.\n[verse] Streetlights flicker in the night. I wander through familiar corners.\n[chorus] The warmth of yesterday remains. But you are gone.\n[outro-short]",
  "descriptions": "female, pop, sad, piano, the bpm is 120"
}
```

## Lyrics Segments — Strict Rules

Purely instrumental segments must NOT contain lyrics:
- `[intro-short]`, `[intro-medium]` — intro without vocals
- `[inst-short]`, `[inst-medium]` — instrumental break
- `[outro-short]`, `[outro-medium]` — outro without vocals

Duration: `short` = ~0-10 seconds, `medium` = ~10-20 seconds.

Segments that require lyrics: `[verse]`, `[chorus]`, `[bridge]`.

### Formatting Rules

- Sections are separated by newlines
- Phrases in lyrical sections end with a period
- All punctuation must be half-width (English punctuation)

## The `descriptions` Field — 4 Dimensions

Controls up to four musical dimensions. Use comma-separated tags, never full sentences. All dimensions are optional and order is flexible.

```
"female, pop, sad, piano and drums, the bpm is 120"
 ──────  ───  ───  ───────────────  ───────────────
 gender genre mood   instrument(s)       bpm
```

### Examples

```
"female, synth-pop, sweet, synthesizer, drum machine, bass, backing vocals"
"rock, loving, electric guitar, bass guitar, drum kit"
"male, dark, jazz, the bpm is 95"
```
