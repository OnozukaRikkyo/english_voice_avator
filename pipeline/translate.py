"""Stage narration→translation: English narration → Japanese (Gemini).

Reads:  narration/{stem}_full.txt   (full English narration)
Writes: translation/{stem}_ja.txt   (Japanese translation)

The _ja suffix makes the language explicit, enabling future additions
like _zh.txt, _ko.txt without ambiguity.
"""
from pathlib import Path

from google import genai

from .config import (
    GEMINI_API_KEY, GEMINI_TRANSLATE_MODEL,
    stage_dir, all_projects, STEP_IO,
)

_IN, _OUT = STEP_IO["translate"]
_client: genai.Client | None = None

_PROMPT = """\
You are a professional Japanese translator specializing in geopolitical analysis \
and military OSINT content for YouTube audiences.

Translate the following English narration script into natural, fluent Japanese. \
Preserve the analytical, authoritative tone and all proper nouns \
(place names, weapon systems, unit names) in their standard Japanese usage \
as seen in NHK, Asahi, or Yomiuri reporting. \
Do not add explanations or translator notes. Output the Japanese text only.

"""


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def translate_file(src: Path, dst: Path) -> Path:
    text = src.read_text(encoding="utf-8").strip()
    print(f"  Translating: {src.name} ({len(text)} chars)")

    response = _get_client().models.generate_content(
        model=GEMINI_TRANSLATE_MODEL,
        contents=[_PROMPT + text],
    )
    translated = response.text.strip()
    dst.write_text(translated, encoding="utf-8")
    print(f"    → {dst.name} ({len(translated)} chars)")
    return dst


def run(project: str, *, force: bool = False) -> list[Path]:
    src_dir = stage_dir(project, _IN)    # narration/
    dst_dir = stage_dir(project, _OUT)   # translation/
    dst_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    for full_txt in sorted(src_dir.glob("*_full.txt")):
        base = full_txt.stem.removesuffix("_full")
        out = dst_dir / f"{base}_ja.txt"
        if out.exists() and not force:
            print(f"  [skip] {out.name}")
            results.append(out)
            continue
        translate_file(full_txt, out)
        results.append(out)

    return results


def run_all() -> None:
    for project in all_projects():
        print(f"\n[{project}] translate")
        run(project)


if __name__ == "__main__":
    run_all()
