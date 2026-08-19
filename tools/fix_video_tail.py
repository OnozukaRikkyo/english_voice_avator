#!/usr/bin/env python3
"""Mute the tail noise HeyGen sometimes leaves where the script asked for silence.

Input:  data/{project}/video/parts/*.mp4  +  data/{project}/narration/parts/*.txt
Output: 同じ mp4（音声だけ書き戻す。映像は copy で無劣化）

台本が `<break time="1.5s"/>` で終わっていれば、その秒数だけ無音で終わるはず。
合成音声がそこを喋り声で埋めることがあり、台本にも映像にも異常が出ないため、
公開して初めて気づく。生成時は pipeline/heygen.py が同じ検査をして直すので、
このツールが要るのは検査を入れる前に作った動画を直すときだけである。

    python tools/fix_video_tail.py                    # 全プロジェクトを点検
    python tools/fix_video_tail.py --project SLUG     # 1つだけ
    python tools/fix_video_tail.py --check            # 直さず報告だけ

直したパートがあれば結合をやり直す（--check のときは行わない）。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline import heygen, ssml
from pipeline.config import HEYGEN_MAX_CHARS, all_projects, parts_dir, STEP_IO
from tools.concat_video import concat_video

_IN, _OUT = STEP_IO["heygen"]


def script_for(video: Path, src_dir: Path) -> str | None:
    """その mp4 を作ったときに HeyGen へ渡した台本を復元する。

    1パート1本のときはパート名がそのまま対応する。上限を超えて枝番が付いた
    ときは、同じ分割をやり直して該当番号を取り出す（分割は決定論的）。
    """
    exact = src_dir / f"{video.stem}.txt"
    if exact.exists():
        return exact.read_text(encoding="utf-8").strip()

    base, _, tail = video.stem.rpartition("_")
    src = src_dir / f"{base}.txt"
    if tail.isdigit() and src.exists():
        pieces = ssml.split(src.read_text(encoding="utf-8").strip(), HEYGEN_MAX_CHARS)
        i = int(tail) - 1
        if 0 <= i < len(pieces):
            return pieces[i]
    return None


def fix_project(project: str, *, check_only: bool = False) -> list[Path]:
    src_dir, dst_dir = parts_dir(project, _IN), parts_dir(project, _OUT)
    videos = sorted(dst_dir.glob("*.mp4")) if dst_dir.exists() else []
    if not videos:
        print(f"  [skip] {project}: video/parts/ に mp4 がありません")
        return []

    fixed: list[Path] = []
    for video in videos:
        script = script_for(video, src_dir)
        if script is None:
            print(f"  [skip] {video.name}: 対応する台本が見つかりません")
            continue
        want = heygen._expected_tail_silence(script)
        got = heygen._measured_tail_silence(video)
        if not want:
            print(f"  [ok] {video.name}: 末尾に間の指定なし")
            continue
        if check_only or heygen._tail_problem(video, script) is None:
            state = "ok" if heygen._tail_problem(video, script) is None else "noisy"
            print(f"  [{state}] {video.name}: 指定 {want:.1f}秒 / 実測 {got:.2f}秒")
            continue
        try:
            print(f"  [repair] {video.name}: {heygen.repair_tail(video, script)}")
            fixed.append(video)
        except RuntimeError as e:
            print(f"  WARNING: {video.name}: {e}", file=sys.stderr)
    return fixed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", help="対象プロジェクト（既定: 全部）")
    ap.add_argument("--check", action="store_true", help="直さずに報告だけする")
    args = ap.parse_args()

    projects = [args.project] if args.project else all_projects()
    for project in projects:
        print(f"\n[{project}] 末尾の点検")
        fixed = fix_project(project, check_only=args.check)
        if fixed:
            print(f"  {len(fixed)} 本を直したので結合し直します")
            concat_video(project, force=True)


if __name__ == "__main__":
    main()
