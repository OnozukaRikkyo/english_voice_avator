"""Stage raw→audio: m4a/mp4/mp3 → converted mp3."""
import shutil
import subprocess
from pathlib import Path

from .config import stage_dir, all_projects, STEP_IO

_IN, _OUT = STEP_IO["convert"]


def _to_mp3(src: Path, dst: Path) -> None:
    if src.suffix.lower() == ".mp3":
        shutil.copy2(src, dst)
    else:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-codec:a", "libmp3lame", "-q:a", "2", str(dst)],
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
