#!/usr/bin/env python3
"""Main pipeline orchestrator.

Usage:
  python run_pipeline.py [--steps STEP1,STEP2,...] [--project SLUG]
                         [--force] [--max-chars N]

Steps (default: all):
  convert    raw/       → audio/
  transcribe audio/     → transcript/
  rewrite    transcript/→ narration/
  heygen     narration/ → video/

Flags:
  --force          Force re-run even if output files already exist.
  --max-chars N    Override REWRITE_MAX_CHARS for the rewrite step only.
                   Use -1 for unlimited (single file), or N for max chars per segment.

Each step is idempotent by default: already-generated files are skipped.
"""
import argparse
import sys
import time

from pipeline.config import all_projects, ensure_project_dirs


ALL_STEPS = ["convert", "transcribe", "rewrite", "heygen"]


def main() -> None:
    parser = argparse.ArgumentParser(description="English Voice Avatar pipeline")
    parser.add_argument(
        "--steps",
        default=",".join(ALL_STEPS),
        help=f"Comma-separated steps to run (default: all). Choices: {', '.join(ALL_STEPS)}",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Run only this project slug (default: all projects)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-run even if output files already exist",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=None,
        dest="max_chars",
        help="Override REWRITE_MAX_CHARS for the rewrite step (-1 = unlimited)",
    )
    args = parser.parse_args()

    steps = [s.strip() for s in args.steps.split(",")]
    unknown = set(steps) - set(ALL_STEPS)
    if unknown:
        print(f"Unknown steps: {unknown}", file=sys.stderr)
        sys.exit(1)

    projects = [args.project] if args.project else all_projects()
    if not projects:
        print("No projects found. Place source files in data/{project}/raw/", file=sys.stderr)
        sys.exit(1)

    if args.force:
        print("[--force] Existing output files will be overwritten.")
    if args.max_chars is not None:
        print(f"[--max-chars {args.max_chars}] Overriding REWRITE_MAX_CHARS for rewrite step.")

    t0 = time.time()

    for project in projects:
        ensure_project_dirs(project)
        print(f"\n{'='*60}")
        print(f"  Project: {project}")
        print(f"{'='*60}")

        for step in steps:
            print(f"\n--- {step} ---")
            t1 = time.time()

            if step == "convert":
                from pipeline import convert
                convert.run(project, force=args.force)

            elif step == "transcribe":
                from pipeline import transcribe
                transcribe.run(project, force=args.force)

            elif step == "rewrite":
                from pipeline import rewrite
                rewrite.run(project, force=args.force, max_chars=args.max_chars)

            elif step == "heygen":
                from pipeline import heygen
                heygen.run(project, force=args.force)

            print(f"  done in {time.time() - t1:.1f}s")

    print(f"\n{'='*60}")
    print(f"  Pipeline complete in {time.time() - t0:.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
