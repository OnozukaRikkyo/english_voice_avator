#!/usr/bin/env python3
"""Concatenate video part files into a single MP4.

Usage:
  python tools/concat_video.py [--project SLUG] [--force]

Input:  data/{project}/video/parts/{stem}_part*.mp4
Output: data/{project}/video/{stem}.mp4

Layout rule:
  video/parts/  ← intermediate part videos (heygen output)
  video/        ← final concatenated video (.mp4 lives here)

Uses ffmpeg concat demuxer (stream copy — no re-encoding, lossless and fast).
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.config import all_projects, stage_dir, parts_dir


def concat_video(project: str, *, force: bool = False) -> list[Path]:
    src_dir = parts_dir(project, "video")
    dst_dir = stage_dir(project, "video")

    if not src_dir.exists() or not list(src_dir.glob("*_part*.mp4")):
        print(f"  [skip] {project}: no part files in video/parts/")
        return []

    stems: dict[str, list[Path]] = {}
    for f in sorted(src_dir.glob("*_part*.mp4")):
        stem = f.stem[: f.stem.rfind("_part")]
        stems.setdefault(stem, []).append(f)

    results = []
    for stem, parts in stems.items():
        out = dst_dir / f"{stem}.mp4"
        if out.exists() and not force:
            print(f"  [skip] {out.name}")
            results.append(out)
            continue
        if out.exists():
            out.unlink()

        parts_sorted = sorted(parts)
        print(f"  {project}: {len(parts_sorted)} parts → {out.name}")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as lst:
            for p in parts_sorted:
                lst.write(f"file '{p.resolve()}'\n")
            list_path = Path(lst.name)

        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                 "-i", str(list_path), "-c", "copy", str(out)],
                check=True, capture_output=True,
            )
            print(f"    → {out.name} ({out.stat().st_size / 1024 / 1024:.1f} MB)")
            results.append(out)
        except subprocess.CalledProcessError as e:
            print(f"  ERROR: ffmpeg failed\n{e.stderr.decode()}", file=sys.stderr)
        finally:
            list_path.unlink(missing_ok=True)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Concatenate video parts → final .mp4")
    parser.add_argument("--project", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    projects = [args.project] if args.project else all_projects()
    if not projects:
        print("No projects found.", file=sys.stderr)
        sys.exit(1)
    for project in projects:
        concat_video(project, force=args.force)


if __name__ == "__main__":
    main()
