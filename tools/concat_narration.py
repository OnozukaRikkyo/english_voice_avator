#!/usr/bin/env python3
"""Concatenate narration part files into a single text file.

Usage:
  python tools/concat_narration.py [--project SLUG]

Input:  data/{project}/narration/{stem}_part*.txt  (sorted by part number)
Output: data/{project}/narration/{stem}_full.txt

Skips projects that already have a _full.txt file.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.config import all_projects, stage_dir


def concat_narration(project: str, *, force: bool = False) -> list[Path]:
    narration_dir = stage_dir(project, "narration")
    if not narration_dir.exists():
        print(f"  [skip] {project}: narration/ does not exist")
        return []

    # Group part files by stem (strip _partNN suffix)
    stems: dict[str, list[Path]] = {}
    for f in sorted(narration_dir.glob("*_part*.txt")):
        stem = f.stem[: f.stem.rfind("_part")]
        stems.setdefault(stem, []).append(f)

    if not stems:
        print(f"  [skip] {project}: no _part*.txt files found")
        return []

    results = []
    for stem, parts in stems.items():
        out = narration_dir / f"{stem}_full.txt"
        if out.exists() and not force:
            print(f"  [skip] {out.name} already exists")
            results.append(out)
            continue

        combined = "\n\n".join(p.read_text(encoding="utf-8").strip() for p in sorted(parts))
        out.write_text(combined, encoding="utf-8")
        print(f"  {project}: {len(parts)} parts → {out.name} ({len(combined)} chars)")
        results.append(out)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Concatenate narration part files")
    parser.add_argument("--project", default=None, help="Project slug (default: all)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing _full.txt")
    args = parser.parse_args()

    projects = [args.project] if args.project else all_projects()
    if not projects:
        print("No projects found.", file=sys.stderr)
        sys.exit(1)

    for project in projects:
        concat_narration(project, force=args.force)


if __name__ == "__main__":
    main()
