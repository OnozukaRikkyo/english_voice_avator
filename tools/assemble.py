#!/usr/bin/env python3
"""Assemble the generated parts into one script, before it is inspected.

Input:  data/{project}/draft/parts/{stem}_part*.txt
Output: data/{project}/draft/{stem}_full.txt

rewrite が塊ごとに書いたものを1本に繋ぐ。ここから先の工程は**全文**を扱う。
台本の性質のうち、定型句の総回数・冒頭の伏線への引き戻し・締めの回帰は
塊を見ても判定できないので、点検（polish）はこの出力に対して行う。

定型の挨拶とアウトロもここで入れる。台本全体に1回だけ現れるものは、
塊ごとの生成ではなく連結の時点で足すのが正しい（rewrite に書かせると
毎回ぶれるし、part01 だけに差し込む特別扱いも要らなくなる）。

Debug: PIPELINE_DEBUG=1 python tools/assemble.py  (first project only)
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline import rewrite, ssml
from pipeline.config import (
    NARRATION_OPENING, NARRATION_CLOSING, all_projects, stage_dir, parts_dir, STEP_IO,
)

_IN, _OUT = STEP_IO["assemble"]

# パートの境目は元々トピックの切れ目なので、段落相当の間を入れる
_PART_BREAK = '\n<break time="1.0s"/>\n'


def _merge_ssml(parts: list[Path]) -> str:
    """パートを1つの妥当な SSML 文書にまとめる。

    各パートは <speak>…</speak> で包まれている（rewrite が検証済み）。
    素朴に連結すると <speak> 要素が並んだ壊れた XML になるので、
    中間のタグを外して包み直す。
    """
    bodies = [ssml.unwrap(p.read_text(encoding="utf-8")) for p in parts]
    body = _PART_BREAK.join(b for b in bodies if b.strip())

    opening, closing = NARRATION_OPENING.strip(), NARRATION_CLOSING.strip()
    if opening:
        body = opening + "\n\n" + body
    if closing:
        body = body + '\n<break time="1.5s"/>\n' + closing
    # 挨拶の末尾の間と本文の先頭の間が重なることがある
    return ssml.merge_breaks(ssml.wrap(body))


def assemble(project: str, *, force: bool = False) -> list[Path]:
    src_dir, dst_dir = parts_dir(project, _IN), stage_dir(project, _OUT)

    if not src_dir.exists() or not list(src_dir.glob("*_part*.txt")):
        print(f"  [skip] {project}: no part files in {_IN}/parts/")
        return []

    stems: dict[str, list[Path]] = {}
    for f in sorted(src_dir.glob("*_part*.txt")):
        if f.stem.endswith("_review"):
            continue
        stems.setdefault(f.stem[: f.stem.rfind("_part")], []).append(f)

    results = []
    for stem, parts in stems.items():
        # rewrite が途中で終わったプロジェクトは、パートが揃って見えても未完成。
        # ここで結合すると欠けた台本が点検・翻訳・動画生成まで流れてしまう。
        if rewrite.state_path(src_dir, stem).exists():
            print(f"  [skip] {stem}: rewrite が未完了です（./run.sh で続きから作られます）")
            continue
        out = dst_dir / f"{stem}_full.txt"
        if out.exists() and not force:
            print(f"  [skip] {out.name}")
            results.append(out)
            continue
        combined = _merge_ssml(sorted(parts))
        out.write_text(combined, encoding="utf-8")
        print(f"  {project}: {len(parts)} parts → {out.name} ({len(combined):,} chars)")
        results.append(out)

    return results


def run_all() -> None:
    projects = all_projects()
    if os.environ.get("PIPELINE_DEBUG"):
        projects = projects[:1]
        print("[debug] PIPELINE_DEBUG: first project only")
    for project in projects:
        print(f"\n[{project}] assemble")
        assemble(project)


if __name__ == "__main__":
    run_all()
