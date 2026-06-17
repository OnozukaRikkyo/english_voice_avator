"""Stage audio→transcript: mp3 → English text (Gemini)."""
import io
import time
from pathlib import Path

from google import genai

from .config import GEMINI_API_KEY, GEMINI_TRANSCRIBE_MODEL, stage_dir, all_projects, STEP_IO

_IN, _OUT = STEP_IO["transcribe"]
_client: genai.Client | None = None


def _client_get() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def run(project: str, *, force: bool = False) -> list[Path]:
    src_dir = stage_dir(project, _IN)
    dst_dir = stage_dir(project, _OUT)
    dst_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    for mp3 in sorted(src_dir.glob("*.mp3")):
        out = dst_dir / (mp3.stem + ".txt")
        if out.exists() and not force:
            print(f"  [skip] {out.name}")
            results.append(out)
            continue
        if out.exists() and force:
            out.unlink()

        print(f"  Transcribing: {mp3.name}")
        client = _client_get()
        buf = io.BytesIO(mp3.read_bytes())
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
        out.write_text(response.text, encoding="utf-8")
        client.files.delete(name=uploaded.name)
        print(f"  → {out.name}")
        results.append(out)

    return results


def run_all() -> None:
    for project in all_projects():
        print(f"\n[{project}] transcribe")
        run(project)


if __name__ == "__main__":
    run_all()
