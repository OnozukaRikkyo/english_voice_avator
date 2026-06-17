#!/usr/bin/env python3
"""Concatenate video part files into a single MP4.

Usage:
  python tools/concat_video.py [--project SLUG]

Input:  data/{project}/video/{stem}_part*.mp4  (sorted by part number)
Output: data/{project}/video/{stem}.mp4

Uses ffmpeg concat demuxer (stream copy — no re-encoding, lossless and fast).
Skips projects that already have a final .mp4 file.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.config import all_projects, stage_dir


def concat_video(project: str, *, force: bool = False) -> list[Path]:
    video_dir = stage_dir(project, "video")
    if not video_dir.exists():
        print(f"  [skip] {project}: video/ does not exist")
        return []

    # Group part files by stem
    stems: dict[str, list[Path]] = {}
    for f in sorted(video_dir.glob("*_part*.mp4")):
        stem = f.stem[: f.stem.rfind("_part")]
        stems.setdefault(stem, []).append(f)

    if not stems:
        print(f"  [skip] {project}: no _part*.mp4 files found")
        return []

    results = []
    for stem, parts in stems.items():
        out = video_dir / f"{stem}.mp4"
        if out.exists() and not force:
            print(f"  [skip] {out.name} already exists")
            results.append(out)
            continue

        parts_sorted = sorted(parts)
        print(f"  {project}: concatenating {len(parts_sorted)} parts → {out.name}")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as lst:
            for p in parts_sorted:
                lst.write(f"file '{p.resolve()}'\n")
            list_path = Path(lst.name)

        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(list_path),
                    "-c", "copy",
                    str(out),
                ],
                check=True,
                capture_output=True,
            )
            size_mb = out.stat().st_size / 1024 / 1024
            print(f"    → {out.name} ({size_mb:.1f} MB)")
            results.append(out)
        except subprocess.CalledProcessError as e:
            print(f"  ERROR: ffmpeg failed\n{e.stderr.decode()}", file=sys.stderr)
        finally:
            list_path.unlink(missing_ok=True)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Concatenate video part files into a single MP4")
    parser.add_argument("--project", default=None, help="Project slug (default: all)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output MP4")
    args = parser.parse_args()

    projects = [args.project] if args.project else all_projects()
    if not projects:
        print("No projects found.", file=sys.stderr)
        sys.exit(1)

    for project in projects:
        concat_video(project, force=args.force)


if __name__ == "__main__":
    main()
