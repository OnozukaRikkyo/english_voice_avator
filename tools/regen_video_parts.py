#!/usr/bin/env python3
"""Regenerate named video parts, then concatenate again.

Input:  data/{project}/narration/parts/{stem}_part*.txt
Output: data/{project}/video/parts/{stem}_part*.mp4 → data/{project}/video/{stem}.mp4

1本だけ作り直したいことがある（末尾のノイズが消音でも直らない、表情が崩れた等）。
`--force` は全パートを作り直してしまい、20分の動画なら $20 前後を捨てることになる。
ここでは指定したパートの mp4 だけを消し、heygen の「無いものだけ作る」性質を使って
その1本を作り直す。結合は作り直しの直後に必ず行う（古い本編が残ると、直したはずの
ノイズが公開物に残る）。

    python tools/regen_video_parts.py part01
    python tools/regen_video_parts.py part01 part04 --project SLUG
    python tools/regen_video_parts.py 01 --dry-run       # 消す前に対象を確認する
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline import heygen
from pipeline.config import all_projects, parts_dir, STEP_IO
from tools.concat_video import concat_video

_IN, _OUT = STEP_IO["heygen"]


def resolve(project: str, names: list[str]) -> list[Path]:
    """`part01` / `01` / ファイル名 のいずれでも、その mp4 を指せるようにする。"""
    dst_dir = parts_dir(project, _OUT)
    videos = sorted(dst_dir.glob("*.mp4")) if dst_dir.exists() else []
    picked: list[Path] = []
    for name in names:
        key = Path(name).stem
        m = re.fullmatch(r"(?:part)?0*(\d+)", key, re.I)
        if m:
            n = int(m.group(1))
            hits = [v for v in videos if re.search(rf"_part0*{n}(?:_\d+)?$", v.stem)]
        else:
            hits = [v for v in videos if v.stem == key]
        if not hits:
            raise SystemExit(
                f"ERROR: {project} に該当する動画がありません: {name}\n"
                f"  ある動画: {[v.name for v in videos]}")
        picked.extend(hits)
    return sorted(set(picked))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("parts", nargs="+", help="作り直すパート（part01 / 01 / ファイル名）")
    ap.add_argument("--project", help="対象プロジェクト（既定: 1つだけなら自動）")
    ap.add_argument("--dry-run", action="store_true", help="消さずに対象だけ表示する")
    args = ap.parse_args()

    projects = all_projects()
    if args.project:
        project = args.project
    elif len(projects) == 1:
        project = projects[0]
    else:
        raise SystemExit(f"ERROR: --project を指定してください（候補: {projects}）")

    targets = resolve(project, args.parts)
    print(f"[{project}] 作り直す対象 {len(targets)} 本:")
    for t in targets:
        print(f"  - {t.name}")
    if args.dry_run:
        print("--dry-run のため、ここで終了します")
        return

    for t in targets:
        t.unlink()
    # heygen は mp4 が無いパートだけ作る。消した分だけが作り直される。
    heygen.run(project)
    # 作り直した直後に必ず結合する。古い本編を残すと、直した意味が無くなる。
    concat_video(project, force=True)


if __name__ == "__main__":
    main()
