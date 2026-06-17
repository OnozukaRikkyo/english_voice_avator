"""Audio format conversion: m4a/mp4 → mp3 via ffmpeg."""
import subprocess
from pathlib import Path

from .config import DIR_INPUT, DIR_ENG_MP3


def _convert(src: Path, dst: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-codec:a", "libmp3lame", "-q:a", "2", str(dst)],
        check=True, capture_output=True,
    )


def run() -> list[Path]:
    DIR_ENG_MP3.mkdir(parents=True, exist_ok=True)
    converted: list[Path] = []

    for ext in ("*.m4a", "*.mp4", "*.mp3"):
        for src in sorted(DIR_INPUT.glob(ext)):
            dst = DIR_ENG_MP3 / (src.stem + ".mp3")
            if dst.exists():
                print(f"  [skip] {dst.name} already exists")
                converted.append(dst)
                continue
            if src.suffix.lower() == ".mp3":
                import shutil
                shutil.copy2(src, dst)
            else:
                print(f"  Converting: {src.name} → {dst.name}")
                _convert(src, dst)
            print(f"  → {dst}")
            converted.append(dst)

    return converted


if __name__ == "__main__":
    run()
