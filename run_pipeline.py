#!/usr/bin/env python3
"""Main pipeline orchestrator.

Usage:
  python run_pipeline.py [--steps STEP1,STEP2,...] [--project SLUG]

Steps (default: all):
  convert    raw/       → audio/
  transcribe audio/     → transcript/
  rewrite    transcript/→ narration/
  heygen     narration/ → video/

Each step is idempotent: already-generated files are skipped automatically.
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
                from pipeline import audio_convert
                audio_convert.run(project)

            elif step == "transcribe":
                from pipeline import transcribe
                transcribe.run(project)

            elif step == "rewrite":
                from pipeline import rewrite
                rewrite.run(project)

            elif step == "heygen":
                from pipeline import heygen
                heygen.run(project)

            print(f"  done in {time.time() - t1:.1f}s")

    print(f"\n{'='*60}")
    print(f"  Pipeline complete in {time.time() - t0:.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
