"""Generate songs via RunPod serverless endpoint.

Usage:
    python scripts/generate.py examples/batch_test.jsonl
    python scripts/generate.py input.jsonl --dry-run
    python scripts/generate.py input.jsonl --timeout 900
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from services.config import RUNPOD_ENDPOINT_ID, SUPABASE_BUCKET, validate_config
from services.runpod import run_job


def read_jsonl(path: Path) -> list[dict]:
    """Read tracks from a JSONL file."""
    tracks: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                tracks.append(json.loads(line))
    return tracks


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate songs via RunPod serverless")
    parser.add_argument("input", type=Path, help="JSONL file with tracks")
    parser.add_argument("--dry-run", action="store_true", help="Show tracks without generating")
    parser.add_argument("--timeout", type=int, default=600, help="Max wait time (seconds)")
    args = parser.parse_args()

    missing = validate_config()
    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your values.")
        sys.exit(1)

    tracks = read_jsonl(args.input)
    if not tracks:
        print("No tracks found in input file.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  SongGen — {len(tracks)} track(s)")
    print(f"  Endpoint: {RUNPOD_ENDPOINT_ID}")
    print(f"  Storage: Supabase ({SUPABASE_BUCKET})")
    print(f"{'='*60}\n")

    if args.dry_run:
        for t in tracks:
            print(f"  [{t.get('idx', '?')}] {t.get('descriptions', 'no descriptions')}")
        print("\n--dry-run: no job submitted.")
        return

    try:
        print("Submitting job...")
        print("  (first run may cold-start ~2-15 min, then ~30s)\n")

        output = run_job(tracks, timeout=args.timeout)
        results = output.get("results", [])

        print(f"{'='*60}")
        print(f"  Results")
        print(f"{'='*60}\n")

        success = 0
        for r in results:
            if r.get("status") == "success":
                success += 1
                print(f"  ✓ [{r.get('idx')}] {r.get('url', '')}")
                print(f"    duration={r.get('duration')}s  genre={r.get('genre')}  mood={r.get('mood')}")
            else:
                print(f"  ✗ [{r.get('idx', '?')}] {r.get('error_message', 'unknown error')}")

        print(f"\n  {success}/{len(results)} tracks generated successfully.\n")

    except KeyboardInterrupt:
        print("\n\nInterrupted. Job may still be running on RunPod.")
    except Exception as exc:
        print(f"\nError: {exc}")


if __name__ == "__main__":
    main()
