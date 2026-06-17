#!/usr/bin/env python3
"""Main pipeline orchestrator.

Usage:
  python run_pipeline.py [--steps STEP1,STEP2,...] [--heygen-mode audio|text]

Steps (default: all):
  convert    m4a/mp4/mp3 → eng_mp3/
  transcribe eng_mp3/    → eng_text/
  rewrite    eng_text/   → eng_split/
  tts        eng_split/  → regen_mp3/
  concat     regen_mp3/  → voice_concat/ + concat_text/
  heygen     concat_text/ + voice_concat/ → avatar_video/

Each step is idempotent: already-generated files are skipped automatically.
"""
import argparse
import sys
import time
from pipeline.config import ensure_dirs


ALL_STEPS = ["convert", "transcribe", "rewrite", "tts", "concat", "heygen"]


def main() -> None:
    parser = argparse.ArgumentParser(description="English Voice Avatar pipeline")
    parser.add_argument(
        "--steps",
        default=",".join(ALL_STEPS),
        help=f"Comma-separated steps to run (default: all). Choices: {', '.join(ALL_STEPS)}",
    )
    parser.add_argument(
        "--heygen-mode",
        choices=["audio", "text"],
        default="audio",
        help="HeyGen video mode: 'audio' uses MiniMax MP3, 'text' uses HeyGen TTS (default: audio)",
    )
    args = parser.parse_args()

    steps = [s.strip() for s in args.steps.split(",")]
    unknown = set(steps) - set(ALL_STEPS)
    if unknown:
        print(f"Unknown steps: {unknown}", file=sys.stderr)
        sys.exit(1)

    ensure_dirs()
    t0 = time.time()

    for step in steps:
        print(f"\n{'='*50}")
        print(f"  Step: {step}")
        print(f"{'='*50}")
        t1 = time.time()

        if step == "convert":
            from pipeline import audio_convert
            audio_convert.run()

        elif step == "transcribe":
            from pipeline import transcribe
            transcribe.run()

        elif step == "rewrite":
            from pipeline import rewrite
            rewrite.run()

        elif step == "tts":
            from pipeline import tts
            tts.run()

        elif step == "concat":
            from pipeline import concat
            concat.run()

        elif step == "heygen":
            from pipeline import heygen
            heygen.run(mode=args.heygen_mode)

        print(f"  done in {time.time() - t1:.1f}s")

    print(f"\n{'='*50}")
    print(f"  Pipeline complete in {time.time() - t0:.1f}s")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
