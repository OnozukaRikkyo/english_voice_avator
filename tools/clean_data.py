#!/usr/bin/env python3
"""Delete all generated data under data/.

Removes:
  - data/inbox/*          audio files waiting to be processed
  - data/<project>/       all generated project directories
  - data/senario_jp/*     source documents and generated prompts

The data/ directory itself and its subdirectory structure are preserved.

Usage:
  python tools/clean_data.py          # show what will be deleted, then confirm
  python tools/clean_data.py --force  # delete without confirmation
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
INBOX_DIR   = DATA / "inbox"
SENARIO_DIR = DATA / "senario_jp"

SKIP_DIRS = {"inbox", "senario_jp"}


def collect_targets() -> list[Path]:
    targets: list[Path] = []

    # Files in inbox/
    if INBOX_DIR.exists():
        targets.extend(sorted(INBOX_DIR.iterdir()))

    # Project directories (everything under data/ except inbox/ and senario_jp/)
    if DATA.exists():
        for child in sorted(DATA.iterdir()):
            if child.is_dir() and child.name not in SKIP_DIRS:
                targets.append(child)

    # Contents of senario_jp/ (docs + prompts/)
    if SENARIO_DIR.exists():
        targets.extend(sorted(SENARIO_DIR.iterdir()))

    return targets


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete all generated data under data/")
    parser.add_argument("--force", action="store_true", help="Delete without confirmation")
    args = parser.parse_args()

    targets = collect_targets()
    if not targets:
        print("Nothing to delete.")
        return

    print("The following will be deleted:\n")
    for t in targets:
        rel = t.relative_to(ROOT)
        marker = "/" if t.is_dir() else ""
        print(f"  {rel}{marker}")

    print()

    if not args.force:
        answer = input("Delete all of the above? [y/N] ").strip().lower()
        if answer != "y":
            print("Cancelled.")
            sys.exit(0)

    for t in targets:
        if t.is_dir():
            shutil.rmtree(t)
        else:
            t.unlink()
        print(f"  deleted: {t.relative_to(ROOT)}")

    print("\nDone.")


if __name__ == "__main__":
    main()
