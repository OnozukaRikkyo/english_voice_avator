#!/usr/bin/env python3
"""Concatenate video part files into a single MP4.

Input:  data/{project}/video/parts/{stem}_part*.mp4
Output: data/{project}/video/{stem}.mp4

Debug: PIPELINE_DEBUG=1 python tools/concat_video.py  (first project only)
"""
import os
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
            out_mb   = out.stat().st_size / 1024 / 1024
            parts_mb = sum(p.stat().st_size for p in parts_sorted) / 1024 / 1024
            ratio    = out_mb / parts_mb if parts_mb else 0
            print(f"    → {out.name} ({out_mb:.1f} MB / parts total {parts_mb:.1f} MB, ratio {ratio:.2f})")
            if ratio < 0.95:
                print(f"  WARNING: output is only {ratio*100:.0f}% of parts total — possible concat failure", file=sys.stderr)
            else:
                results.append(out)
        except subprocess.CalledProcessError as e:
            print(f"  ERROR: ffmpeg failed\n{e.stderr.decode()}", file=sys.stderr)
        finally:
            list_path.unlink(missing_ok=True)

    return results


def run_all() -> None:
    projects = all_projects()
    if os.environ.get("PIPELINE_DEBUG"):
        projects = projects[:1]
        print("[debug] PIPELINE_DEBUG: first project only")
    for project in projects:
        print(f"\n[{project}] concat_video")
        concat_video(project)


if __name__ == "__main__":
    run_all()
