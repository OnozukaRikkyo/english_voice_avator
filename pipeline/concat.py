"""Concatenate per-part MP3s and text segments into single files per topic."""
import re
from pathlib import Path

from moviepy import AudioFileClip, concatenate_audioclips

from .config import DIR_REGEN_MP3, DIR_ENG_SPLIT, DIR_VOICE_CONCAT, DIR_CONCAT_TEXT


def _base_name(stem: str) -> str:
    return re.sub(r"_part\d+$", "", stem)


def run() -> dict[str, dict[str, Path]]:
    """Returns {base_name: {"audio": Path, "text": Path}} for each concatenated topic."""
    DIR_VOICE_CONCAT.mkdir(parents=True, exist_ok=True)
    DIR_CONCAT_TEXT.mkdir(parents=True, exist_ok=True)

    mp3_files = sorted(DIR_REGEN_MP3.glob("*.mp3"))
    if not mp3_files:
        print("  No mp3 files found in regen_mp3/")
        return {}

    # Group by base name
    groups: dict[str, list[Path]] = {}
    for f in mp3_files:
        base = _base_name(f.stem)
        groups.setdefault(base, []).append(f)

    results: dict[str, dict[str, Path]] = {}
    for base, parts in groups.items():
        parts = sorted(parts)
        audio_out = DIR_VOICE_CONCAT / f"{base}_concat.mp3"
        text_out = DIR_CONCAT_TEXT / f"{base}_concat.txt"

        if audio_out.exists() and text_out.exists():
            print(f"  [skip] {base} already concatenated")
            results[base] = {"audio": audio_out, "text": text_out}
            continue

        print(f"  Concatenating {len(parts)} parts for: {base}")

        # Audio
        clips = [AudioFileClip(str(p)) for p in parts]
        combined = concatenate_audioclips(clips)
        combined.write_audiofile(str(audio_out), logger=None)
        for c in clips:
            c.close()
        combined.close()
        print(f"    audio → {audio_out.name}")

        # Text
        texts: list[str] = []
        for p in parts:
            txt = DIR_ENG_SPLIT / f"{p.stem}.txt"
            if txt.exists():
                texts.append(txt.read_text(encoding="utf-8").strip())
            else:
                print(f"    [WARN] text not found: {txt}")
        text_out.write_text("\n\n".join(texts), encoding="utf-8")
        print(f"    text  → {text_out.name}")

        results[base] = {"audio": audio_out, "text": text_out}

    return results


if __name__ == "__main__":
    run()
