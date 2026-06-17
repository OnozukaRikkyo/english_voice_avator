"""Text → MP3 via MiniMax TTS with cloned voice.

Chunks are split at sentence boundaries and stitched with ffmpeg.
"""
import re
import subprocess
import tempfile
from pathlib import Path

import requests

from .config import (
    MINIMAX_API_KEY, MINIMAX_TTS_URL, MINIMAX_VOICE_ID,
    MINIMAX_MODEL, MINIMAX_EMOTION, MINIMAX_MAX_CHARS,
    DIR_ENG_SPLIT, DIR_REGEN_MP3,
)


def _split_text(text: str, max_chars: int = MINIMAX_MAX_CHARS) -> list[str]:
    sentences = re.split(r'(?<=\.)\s+', text)
    chunks: list[str] = []
    current = ""
    for s in sentences:
        if len(current) + len(s) + 1 > max_chars:
            if current:
                chunks.append(current.strip())
            current = s
        else:
            current = (current + " " + s).strip() if current else s
    if current:
        chunks.append(current.strip())
    return chunks


def _tts_chunk(text: str, output_file: str) -> None:
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MINIMAX_MODEL,
        "text": text,
        "language_boost": "English",
        "voice_setting": {"voice_id": MINIMAX_VOICE_ID},
        "emotion": MINIMAX_EMOTION,
        "long_text": 1,
    }
    resp = requests.post(MINIMAX_TTS_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    result = resp.json()

    if "base_resp" in result and result["base_resp"].get("status_code") != 0:
        raise RuntimeError(result["base_resp"].get("status_msg", "TTS error"))

    audio_bytes = bytes.fromhex(result["data"]["audio"])
    with open(output_file, "wb") as f:
        f.write(audio_bytes)


def synthesize(text: str, output_path: str) -> None:
    chunks = _split_text(text)
    print(f"    chunks: {len(chunks)}")

    if len(chunks) == 1:
        _tts_chunk(text, output_path)
        size = Path(output_path).stat().st_size
        print(f"    → {output_path} ({size / 1024:.1f} KB)")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        chunk_files: list[str] = []
        for i, chunk in enumerate(chunks):
            cp = str(tmp / f"chunk_{i:03d}.mp3")
            print(f"    chunk {i+1}/{len(chunks)} ({len(chunk)} chars) …")
            _tts_chunk(chunk, cp)
            chunk_files.append(cp)

        list_file = tmp / "list.txt"
        list_file.write_text("\n".join(f"file '{p}'" for p in chunk_files))
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(list_file), "-c", "copy", output_path],
            check=True, capture_output=True,
        )

    size = Path(output_path).stat().st_size
    print(f"    → {output_path} ({size / 1024:.1f} KB)")


def run() -> list[Path]:
    DIR_REGEN_MP3.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    for txt in sorted(DIR_ENG_SPLIT.glob("*.txt")):
        out = DIR_REGEN_MP3 / (txt.stem + ".mp3")
        if out.exists():
            print(f"  [skip] {out.name} already exists")
            results.append(out)
            continue
        content = txt.read_text(encoding="utf-8").strip()
        print(f"  TTS: {txt.name}")
        synthesize(content, str(out))
        results.append(out)

    return results


if __name__ == "__main__":
    run()
