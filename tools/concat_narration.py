#!/usr/bin/env python3
"""Concatenate narration part files into a single text file.

Usage:
  python tools/concat_narration.py [--project SLUG] [--force]

Input:  data/{project}/narration/parts/{stem}_part*.txt
Output: data/{project}/narration/{stem}_full.txt

Layout rule:
  narration/parts/  ← intermediate split files (rewrite output, heygen input)
  narration/        ← final full narration (_full.txt lives here)
"""
import argparse
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Concatenate narration parts → _full.txt")
    parser.add_argument("--project", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    projects = [args.project] if args.project else all_projects()
    if not projects:
        print("No projects found.", file=sys.stderr)
        sys.exit(1)
    for project in projects:
        concat_narration(project, force=args.force)


if __name__ == "__main__":
    main()
