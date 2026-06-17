"""Rewrite dialogue transcript → narration segments using Gemini.

Each output file is a single cohesive paragraph of at most REWRITE_MAX_CHARS chars,
named <stem>_part01.txt, <stem>_part02.txt, …
"""
import json
from pathlib import Path

from google import genai
from google.genai import types

from .config import (
    GEMINI_API_KEY, GEMINI_REWRITE_MODEL, REWRITE_MAX_CHARS,
    DIR_ENG_TEXT, DIR_ENG_SPLIT,
)

_client: genai.Client | None = None

SYSTEM_PROMPT_TEMPLATE = """\
# Role & Objective
You are an expert geopolitical analyst, military OSINT (Open Source Intelligence) specialist, \
and high-impact YouTube scriptwriter. You will receive a transcript of a two-person dialogue \
discussing international geopolitical or military news. Your task is to transform it into a \
compelling, sophisticated English commentary narration script for a YouTube audience, \
then split it into voice-synthesis-ready segments.

# Core Instructions

1. Precise Terminology:
- Identify all place names, village/settlement names, frontlines, oblasts, weapon systems, \
drone models, electronic warfare systems, and military unit designations mentioned in the transcript.
- Use the exact, globally recognized English spellings and designations used by international \
media (ISW, BBC, Reuters) and OSINT communities — not informal or approximate terms.

2. Strategic & Novel Insights (Go Beyond the Transcript):
- Do not merely summarize what the speakers said. Read between the lines to uncover the \
underlying strategic intent, operational logic, or broader geopolitical implications.
- Add sharp, original analytical perspective: e.g., "Why this specific advance matters for \
the broader campaign" or "How this technological shift changes the cost-asymmetry of the conflict."

3. Script Structure & Tone:
- Hook/Introduction: Open with a powerful, attention-grabbing line that immediately \
communicates the stakes and hooks the viewer.
- Body: Deliver the news seamlessly integrated with deep strategic analysis. \
Use rhetorical questions and smooth transitions to maintain viewer retention.
- Conclusion/Outro: Close with a forward-looking thought — what to watch next.
- Tone: Analytical, authoritative, engaging, and objective.
- Voice: Single narrator (no dialogue). Remove all conversational fillers \
("uh", "you know", "right", "exactly", "yeah", etc.).
- Energy: High-impact, like a top geopolitics YouTube channel aimed at a global audience.

# Output Format
Return a JSON array of narration segments for AI voice synthesis:
- Each element: {{ "index": <integer starting from 1>, "text": <string> }}
- Each "text" MUST be at most {max_chars} characters (never cut mid-sentence).
- Together, all segments must form the complete narration script without omissions.
"""


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def rewrite_file(txt_path: Path, output_dir: Path, max_chars: int = REWRITE_MAX_CHARS) -> list[Path]:
    client = _get_client()
    text = txt_path.read_text(encoding="utf-8")
    print(f"  Total chars: {len(text)}")

    schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "required": ["index", "text"],
            "properties": {
                "index": {"type": "INTEGER"},
                "text": {"type": "STRING"},
            },
        },
    }

    response = client.models.generate_content(
        model=GEMINI_REWRITE_MODEL,
        contents=[SYSTEM_PROMPT_TEMPLATE.format(max_chars=max_chars) + "\n\n" + text],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )

    paragraphs = sorted(json.loads(response.text or "[]"), key=lambda x: x["index"])
    results: list[Path] = []
    for p in paragraphs:
        idx = p["index"]
        part_text = p["text"].strip()
        out = output_dir / f"{txt_path.stem}_part{idx:02d}.txt"
        out.write_text(part_text, encoding="utf-8")
        print(f"    part {idx:02d}: {len(part_text)} chars → {out.name}")
        results.append(out)

    return results


def run() -> list[Path]:
    DIR_ENG_SPLIT.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    for txt in sorted(DIR_ENG_TEXT.glob("*.txt")):
        existing = sorted(DIR_ENG_SPLIT.glob(f"{txt.stem}_part*.txt"))
        if existing:
            print(f"  [skip] {txt.stem} already split into {len(existing)} parts")
            results.extend(existing)
            continue
        print(f"  Rewriting: {txt.name}")
        parts = rewrite_file(txt, DIR_ENG_SPLIT)
        results.extend(parts)

    return results


if __name__ == "__main__":
    run()
