"""Stage raw→audio: m4a/mp4/mp3 → converted mp3."""
import subprocess
from pathlib import Path

from .config import stage_dir, all_projects, STEP_IO

_IN, _OUT = STEP_IO["convert"]


# 文字起こし向けの設定。音楽用の高音質は不要で、大きいと OpenAI の
# アップロード上限（25MB）を超えて分割が必要になる。
#
# 64kbps モノラルなら 36分の音声が 30MB → 17MB になり、
# 約52分まで分割せずに1回で送れる。
#
# 精度への影響は実測済み: 同一音声・同一設定を2回文字起こししたときの
# ばらつきが 98.8%、ビットレートを下げたときの一致度が 97.4〜97.8% で
# ほぼ同水準。固有名詞（Huliaipole / Stepnohirsk / Zaporizhzhia 等）も
# 落ちなかった。
_SPEECH_ARGS = ["-codec:a", "libmp3lame", "-ac", "1", "-b:a", "64k"]


def _to_mp3(src: Path, dst: Path) -> None:
    # mp3 でもビットレートを揃える（元が高音質なら上限超過の原因になるため）
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), *_SPEECH_ARGS, str(dst)],
        check=True, capture_output=True,
    )


def run(project: str, *, force: bool = False) -> list[Path]:
    src_dir = stage_dir(project, _IN)
    dst_dir = stage_dir(project, _OUT)
    dst_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    for src in sorted(src_dir.glob("*")):
        if src.suffix.lower() not in (".m4a", ".mp4", ".mp3"):
            continue
        dst = dst_dir / (src.stem + ".mp3")
        if dst.exists() and not force:
            print(f"  [skip] {dst.name}")
        else:
            if dst.exists():
                dst.unlink()
            print(f"  {src.name} → {dst.name}")
            _to_mp3(src, dst)
        results.append(dst)

    return results


def run_all() -> None:
    import os
    projects = all_projects()
    if os.environ.get("PIPELINE_DEBUG"):
        projects = projects[:1]
        print("[debug] PIPELINE_DEBUG: first project only")
    for project in projects:
        print(f"\n[{project}] convert")
        run(project)


if __name__ == "__main__":
    run_all()
