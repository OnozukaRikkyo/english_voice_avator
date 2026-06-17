"""Transcribe English MP3 → text using Gemini."""
import io
import time
from pathlib import Path

from google import genai

from .config import GEMINI_API_KEY, GEMINI_TRANSCRIBE_MODEL, DIR_ENG_MP3, DIR_ENG_TEXT

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def transcribe_file(mp3_path: Path, output_path: Path) -> Path:
    client = _get_client()
    buf = io.BytesIO(mp3_path.read_bytes())
    buf.name = "upload.mp3"
    uploaded = client.files.upload(file=buf, config={"mime_type": "audio/mp3"})

    while uploaded.state.name == "PROCESSING":
        time.sleep(5)
        uploaded = client.files.get(name=uploaded.name)

    response = client.models.generate_content(
        model=GEMINI_TRANSCRIBE_MODEL,
        contents=[
            uploaded,
            "This audio is in English. Please transcribe it in English. Output the text only.",
        ],
    )
    output_path.write_text(response.text, encoding="utf-8")
    client.files.delete(name=uploaded.name)
    return output_path


def run() -> list[Path]:
    DIR_ENG_TEXT.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    for mp3 in sorted(DIR_ENG_MP3.glob("*.mp3")):
        out = DIR_ENG_TEXT / (mp3.stem + ".txt")
        if out.exists():
            print(f"  [skip] {out.name} already exists")
            results.append(out)
            continue
        print(f"  Transcribing: {mp3.name}")
        transcribe_file(mp3, out)
        print(f"  → {out}")
        results.append(out)

    return results


if __name__ == "__main__":
    run()
