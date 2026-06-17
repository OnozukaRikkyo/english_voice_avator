#!/usr/bin/env python3
"""Validate the data directory layout against the pipeline design rules.

Run automatically via Claude Code PostToolUse hook after every Edit/Write.
Also runnable manually: python tools/check_design.py

Design rules enforced:
  1. Intermediate part files (_part*.txt / _part*.mp4) must live in
     a `parts/` subdirectory, NOT directly in the stage directory.
  2. Final outputs live directly in the stage directory:
       narration/{stem}_full.txt
       video/{stem}.mp4
  3. No stale flat-layout directories (eng_mp3/, eng_text/, etc.) should exist.

Exit code: 0 = OK, 1 = violations found.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"

# Directories that belong to the OLD flat layout — must not exist
LEGACY_DIRS = {"input", "eng_mp3", "eng_text", "eng_split",
               "regen_mp3", "avatar_video", "concat_text", "voice_concat"}


def check() -> list[str]:
    violations: list[str] = []

    if not DATA.exists():
        return violations

    for project_dir in sorted(DATA.iterdir()):
        if not project_dir.is_dir():
            continue
        project = project_dir.name

        # Rule: no legacy flat directories
        if project in LEGACY_DIRS:
            violations.append(
                f"[LEGACY] data/{project}/ is a stale flat-layout directory — remove it"
            )
            continue

        # Check each stage for misplaced part files
        for stage in ("narration", "video"):
            stage_dir = project_dir / stage
            if not stage_dir.exists():
                continue

            ext = "txt" if stage == "narration" else "mp4"
            for f in stage_dir.glob(f"*_part*.{ext}"):
                violations.append(
                    f"[MISPLACED] {f.relative_to(ROOT)} — "
                    f"part files must be in {stage}/parts/, not in {stage}/ directly"
                )

    return violations


def main() -> None:
    violations = check()
    if violations:
        print("⚠ Design violations detected:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        sys.exit(1)
    # Silent on success — hook runs after every edit, noise is unwanted


if __name__ == "__main__":
    main()
