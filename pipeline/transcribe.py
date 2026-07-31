"""Stage audio→transcript: mp3 → English text (Gemini).

The output is ALWAYS English, whatever language is spoken in the audio.
Non-English speech is translated, not transcribed verbatim — the downstream
rewrite step expects an English transcript.
"""
import io
import time
from pathlib import Path

from google import genai

from .config import GEMINI_API_KEY, GEMINI_TRANSCRIBE_MODEL, stage_dir, all_projects, STEP_IO

_IN, _OUT = STEP_IO["transcribe"]
_client: genai.Client | None = None

_PROMPT = (
    "Transcribe this audio. The output MUST be in English, and in English only.\n"
    "- If the audio is spoken in English, transcribe it verbatim.\n"
    "- If the audio is spoken in any other language, translate it into English "
    "as you transcribe. Do NOT output the original language.\n"
    "Cover the entire audio from start to finish — do not summarize or omit anything.\n"
    "Output the English text only: no preamble, no language labels, no commentary."
)


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
            contents=[uploaded, _PROMPT],
        )
        out.write_text(response.text, encoding="utf-8")
        client.files.delete(name=uploaded.name)
        print(f"  → {out.name}")
        results.append(out)

    return results


def run_all() -> None:
    import os
    projects = all_projects()
    if os.environ.get("PIPELINE_DEBUG"):
        projects = projects[:1]
        print("[debug] PIPELINE_DEBUG: first project only")
    for project in projects:
        print(f"\n[{project}] transcribe")
        run(project)


if __name__ == "__main__":
    run_all()
