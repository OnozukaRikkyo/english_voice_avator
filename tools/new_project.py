#!/usr/bin/env python3
"""Create a new pipeline project from an audio file.

Usage:
  python tools/new_project.py /path/to/audio.m4a

What it does:
  1. Derives a safe ASCII slug from the audio filename stem via slugify()
  2. Creates data/{slug}/raw/
  3. Copies the audio file into raw/ (original filename preserved)
  4. Creates all stage directories
  5. Prints the slug to use with --project

The project slug is always derived automatically from the audio filename.
Users never need to choose or type a project name.
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.config import slugify, DATA, STAGES, stage_dir


def new_project(audio_path: Path) -> str:
    if not audio_path.exists():
        print(f"ERROR: file not found: {audio_path}", file=sys.stderr)
        sys.exit(1)
    if audio_path.suffix.lower() not in (".m4a", ".mp4", ".mp3"):
        print(f"ERROR: unsupported format {audio_path.suffix} (use .m4a / .mp4 / .mp3)", file=sys.stderr)
        sys.exit(1)

    slug = slugify(audio_path.stem)
    project_dir = DATA / slug

    if (project_dir / "raw" / audio_path.name).exists():
        print(f"[skip] Project already exists: {slug}")
        return slug

    # Create all stage directories
    for stage in STAGES:
        stage_dir(slug, stage).mkdir(parents=True, exist_ok=True)

    # Copy audio into raw/ with original filename
    dst = project_dir / "raw" / audio_path.name
    shutil.copy2(audio_path, dst)

    print(f"Created project: {slug}")
    print(f"  audio → data/{slug}/raw/{audio_path.name}")
    print(f"\nNext step:")
    print(f"  python run_pipeline.py --project {slug}")
    return slug


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a new project from an audio file")
    parser.add_argument("audio", type=Path, help="Path to audio file (.m4a / .mp4 / .mp3)")
    args = parser.parse_args()
    new_project(args.audio)


if __name__ == "__main__":
    main()
