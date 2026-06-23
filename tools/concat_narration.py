#!/usr/bin/env python3
"""Concatenate narration part files into a single text file.

Input:  data/{project}/narration/parts/{stem}_part*.txt
Output: data/{project}/narration/{stem}_full.txt

Debug: PIPELINE_DEBUG=1 python tools/concat_narration.py  (first project only)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.config import all_projects, stage_dir, parts_dir


def concat_narration(project: str, *, force: bool = False) -> list[Path]:
    src_dir = parts_dir(project, "narration")
    dst_dir = stage_dir(project, "narration")

    if not src_dir.exists() or not list(src_dir.glob("*_part*.txt")):
        print(f"  [skip] {project}: no part files in narration/parts/")
        return []

    stems: dict[str, list[Path]] = {}
    for f in sorted(src_dir.glob("*_part*.txt")):
        stem = f.stem[: f.stem.rfind("_part")]
        stems.setdefault(stem, []).append(f)

    results = []
    for stem, parts in stems.items():
        out = dst_dir / f"{stem}_full.txt"
        if out.exists() and not force:
            print(f"  [skip] {out.name}")
            results.append(out)
            continue
        combined = "\n\n".join(p.read_text(encoding="utf-8").strip() for p in sorted(parts))
        out.write_text(combined, encoding="utf-8")
        print(f"  {project}: {len(parts)} parts → {out.name} ({len(combined)} chars)")
        results.append(out)

    return results


def run_all() -> None:
    projects = all_projects()
    if os.environ.get("PIPELINE_DEBUG"):
        projects = projects[:1]
        print("[debug] PIPELINE_DEBUG: first project only")
    for project in projects:
        print(f"\n[{project}] concat_narration")
        concat_narration(project)


if __name__ == "__main__":
    run_all()
