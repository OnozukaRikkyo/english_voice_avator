#!/usr/bin/env python3
"""Split the inspected script back into parts for HeyGen.

Input:  data/{project}/narration/{stem}_full.txt
Output: data/{project}/narration/parts/{stem}_part*.txt

点検（polish）は全文に対して行うため、動画生成に渡す分割はその後になる。
分割の基準は HeyGen の入力上限（5,000字）だけで、意味の区切りではない。
切る位置は <break> に合わせる（pipeline/ssml.py）。

Debug: PIPELINE_DEBUG=1 python tools/split_narration.py  (first project only)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline import ssml
from pipeline.config import HEYGEN_MAX_CHARS, all_projects, stage_dir, parts_dir, STEP_IO

_IN, _OUT = STEP_IO["split"]


def split_narration(project: str, *, force: bool = False) -> list[Path]:
    src_dir, dst_dir = stage_dir(project, _IN), parts_dir(project, _OUT)
    dst_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    for full in sorted(src_dir.glob("*_full.txt")):
        stem = full.stem.removesuffix("_full")
        existing = sorted(dst_dir.glob(f"{stem}_part*.txt"))
        if existing and not force:
            print(f"  [skip] {stem}: {len(existing)} part(s)")
            results.extend(existing)
            continue
        # 前回の分割が残っていると、短くなったときに古いパートが動画に混ざる
        for f in existing:
            f.unlink()

        chunks = ssml.split(full.read_text(encoding="utf-8"), HEYGEN_MAX_CHARS)
        for i, chunk in enumerate(chunks, 1):
            out = dst_dir / f"{stem}_part{i:02d}.txt"
            out.write_text(chunk, encoding="utf-8")
            results.append(out)
        print(f"  {stem}: → {len(chunks)} part(s)（上限 {HEYGEN_MAX_CHARS:,}字）")

    return results


def run_all() -> None:
    projects = all_projects()
    if os.environ.get("PIPELINE_DEBUG"):
        projects = projects[:1]
        print("[debug] PIPELINE_DEBUG: first project only")
    for project in projects:
        print(f"\n[{project}] split")
        split_narration(project)


if __name__ == "__main__":
    run_all()
