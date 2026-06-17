#!/usr/bin/env python3
"""Validate the data directory layout against the pipeline design rules.

Run automatically via Claude Code PostToolUse hook after every Edit/Write.
Also runnable manually: python tools/check_design.py

Design rules enforced:
  1. Intermediate part files (_part*.txt / _part*.mp4) must live in
     a `parts/` subdirectory, NOT directly in the stage directory.
  2. Final outputs live directly in the stage directory:
       narration/{stem}_full.txt    ← concat_narration output
       translation/{stem}_ja.txt   ← translate output (no parts/ needed)
       video/{stem}.mp4             ← concat_video output
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


def check() -> tuple[list[str], list[str]]:
    """Returns (violations, warnings).

    violations → exit 1  (must fix: misplaced files, legacy dirs)
    warnings   → exit 0  (should fix eventually: non-ASCII slugs)
    """
    violations: list[str] = []
    warnings: list[str] = []

    if not DATA.exists():
        return violations, warnings

    for project_dir in sorted(DATA.iterdir()):
        if not project_dir.is_dir():
            continue
        project = project_dir.name

        # Hard violation: legacy flat-layout directories must not exist
        if project in LEGACY_DIRS:
            violations.append(
                f"[LEGACY] data/{project}/ is a stale flat-layout directory — remove it"
            )
            continue

        # Warning: project slug should be ASCII-safe
        # Existing non-ASCII projects cannot be renamed, so this is non-blocking.
        # New projects must be created via: python tools/new_project.py <audio_file>
        try:
            project.encode("ascii")
        except UnicodeEncodeError:
            warnings.append(
                f"[NON-ASCII] data/{project}/ — slug has non-ASCII chars. "
                f"Future projects: use python tools/new_project.py <audio_file>"
            )

        # Hard violation: part files must live in stage/parts/, not stage/ directly
        for stage in ("narration", "video"):
            stage_path = project_dir / stage
            if not stage_path.exists():
                continue
            ext = "txt" if stage == "narration" else "mp4"
            for f in stage_path.glob(f"*_part*.{ext}"):
                violations.append(
                    f"[MISPLACED] {f.relative_to(ROOT)} — "
                    f"part files must be in {stage}/parts/, not in {stage}/ directly"
                )

    return violations, warnings


def main() -> None:
    violations, warnings = check()
    if warnings:
        print("⚠ Design warnings:", file=sys.stderr)
        for w in warnings:
            print(f"  {w}", file=sys.stderr)
    if violations:
        print("✗ Design violations (must fix):", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        sys.exit(1)
    # Silent on clean success


if __name__ == "__main__":
    main()
