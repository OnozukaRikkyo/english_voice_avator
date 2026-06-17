"""Stage transcript→narration: English text → YouTube narration (Gemini).

REWRITE_MAX_CHARS in config.py controls segment size:
  -1  → unlimited: full narration in one file, no split instructions in prompt
  N   → each segment is at most N characters
"""
import json
from pathlib import Path

from google import genai
from google.genai import types

from .config import (
    GEMINI_API_KEY, GEMINI_REWRITE_MODEL, REWRITE_MAX_CHARS,
    stage_dir, parts_dir, all_projects, STEP_IO,
)

_IN, _OUT = STEP_IO["rewrite"]
_client: genai.Client | None = None

# ── Shared role + content instructions ────────────────────────────────────────

_ROLE = """\
# Role & Objective
You are an expert geopolitical analyst, military OSINT (Open Source Intelligence) specialist, \
and high-impact YouTube scriptwriter. You will receive a transcript of a two-person dialogue \
discussing international geopolitical or military news. Your task is to transform it into a \
compelling, sophisticated English commentary narration script for a YouTube audience.

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
- Energy: High-impact, like a top geopolitics YouTube channel aimed at a global audience.\
"""

# ── Unlimited mode: no mention of splitting ────────────────────────────────────

_PROMPT_UNLIMITED = _ROLE + """

# Output Format
Return a JSON array with a single element containing the full narration:
- {{ "index": 1, "text": <the complete narration script as one string> }}
"""

# ── Limited mode: splitting instructions included ──────────────────────────────

_PROMPT_LIMITED = _ROLE + """

# Segmentation Rules
Divide the completed narration script into multiple segments. Each segment MUST satisfy ALL of the following:
- It is a coherent unit of meaning — do NOT cut a sentence in the middle.
- It is at most {max_chars} characters long (including spaces and punctuation).
- Together, all segments must cover the ENTIRE narration without any omissions.

# Output Format
Return a JSON array of narration segments for AI voice synthesis:
- Each element: {{ "index": <integer starting from 1>, "text": <string> }}
- Each "text" MUST be at most {max_chars} characters (never cut mid-sentence).
- Together, all segments must form the complete narration script without omissions.
"""


def _build_prompt(max_chars: int, transcript: str) -> str:
    if max_chars == -1:
        return _PROMPT_UNLIMITED + "\n\n" + transcript
    return _PROMPT_LIMITED.format(max_chars=max_chars) + "\n\n" + transcript


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def rewrite_file(txt_path: Path, output_dir: Path, max_chars: int = REWRITE_MAX_CHARS) -> list[Path]:
    client = _get_client()
    text = txt_path.read_text(encoding="utf-8")
    print(f"  Total chars: {len(text)}  |  max_chars={'unlimited' if max_chars == -1 else max_chars}")

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
        contents=[_build_prompt(max_chars, text)],
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
        # Always use _partNN suffix — final merged file lives in parent (stage) dir
        out = output_dir / f"{txt_path.stem}_part{idx:02d}.txt"
        out.write_text(part_text, encoding="utf-8")
        print(f"    part {idx:02d}: {len(part_text)} chars → {out.name}")
        results.append(out)

    return results


def run(project: str, *, force: bool = False, max_chars: int | None = None) -> list[Path]:
    """Run rewrite for a project.

    Parts are written to narration/parts/ (intermediate).
    The merged full file lives in narration/ (final output, via concat_narration.py).

    Args:
        force: Delete existing parts and re-run.
        max_chars: Override REWRITE_MAX_CHARS (-1=unlimited, N=split at N chars).
    """
    effective_max = max_chars if max_chars is not None else REWRITE_MAX_CHARS
    src_dir = stage_dir(project, _IN)
    dst_dir = parts_dir(project, _OUT)   # ← narration/parts/
    dst_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []

    for txt in sorted(src_dir.glob("*.txt")):
        existing = sorted(dst_dir.glob(f"{txt.stem}_part*.txt"))
        if existing and not force:
            print(f"  [skip] {txt.stem} → {len(existing)} part(s) in narration/parts/")
            results.extend(existing)
            continue
        if existing and force:
            for f in existing:
                f.unlink()
            print(f"  [force] removed {len(existing)} existing part(s)")
        print(f"  Rewriting: {txt.name}  (max_chars={'unlimited' if effective_max == -1 else effective_max})")
        parts = rewrite_file(txt, dst_dir, max_chars=effective_max)
        results.extend(parts)

    return results


def run_all() -> None:
    for project in all_projects():
        print(f"\n[{project}] rewrite")
        run(project)


if __name__ == "__main__":
    run_all()
