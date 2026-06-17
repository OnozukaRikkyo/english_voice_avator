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
You are given a long transcript of a two-person dialogue in podcast format,
where two speakers discuss and analyze a news topic together.

Your job is to:
1. Rewrite the content as a clear, engaging news explanation delivered by a single narrator
   for use as a video narration script read by an AI voice synthesis system.
2. Organize the rewritten narration into multiple paragraphs (segments).
3. Each paragraph MUST satisfy ALL of the following:
   - It is a coherent unit of meaning (do NOT cut sentences in the middle).
   - It is at most {max_chars} characters long (including spaces).
   - Together, all segments cover ALL information and analysis from the original transcript
     without omissions or additions.

Rewriting requirements:
- Narration voice: first-person singular OR neutral third-person narrator, not a dialogue.
- Preserve all key facts, arguments, and analytical insights from the original.
- Remove conversational fillers ("uh", "you know", "right", "exactly", "yeah", etc.).
- Merge back-and-forth exchanges into a single, coherent monologue.
- Maintain the logical structure and depth of analysis from the original.
- Tone: clear, informative, suitable for news / documentary narration.
- Do NOT add new information or opinions not in the original.
- Start with the most compelling conclusion or striking insight from the story,
  with an attention-grabbing opening line that hooks an audience interested in international news.
- Include all information from the original input without omission.
- Keep sentences concise and easy to understand; avoid redundancy.
- Style: persuasive, conversational storytelling that speaks directly to the audience.
- Energy: similar to a popular news website for younger audiences — punchy, accessible, engaging.

Output format:
- Return a JSON array.
- Each element is an object: {{ "index": <int starting from 1>, "text": <string> }}
- The combined "text" fields must reconstruct the full narration.
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
