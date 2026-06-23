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
- Energy: High-impact, like a top geopolitics YouTube channel aimed at a global audience.

4. Coverage — CRITICAL:
- You MUST cover EVERY topic, event, location, and analytical point mentioned in the transcript.
- Do NOT summarize, condense, or omit any section of the transcript.
- The narration script must be long enough to fully address all content in the transcript. \
A 50,000-character transcript should produce a narration of comparable length and depth — \
not a short summary.
- If in doubt, expand with analysis rather than cut content.

5. SSML Formatting — REQUIRED:
- Wrap the entire text of each segment in <speak> ... </speak>.
- Insert <break time="Xs"/> tags at natural spoken pauses. Use these guidelines:
  - Between sentences: <break time="0.5s"/>
  - Between paragraphs or topic shifts: <break time="1.0s"/>
  - At major section transitions (e.g., hook → body, body → conclusion): <break time="1.5s"/>
- Do NOT add breaks in the middle of a sentence.
- Example: <speak>Russia's air defense failed last night. <break time="0.5s"/> Here is why that matters. <break time="1.0s"/> The Pantsir systems...</speak>\
"""

# ── Unlimited mode: no mention of splitting ────────────────────────────────────

_PROMPT_UNLIMITED = _ROLE + """

# Output Format
Return a JSON array with a single element containing the full narration:
- {{ "index": 1, "text": <the complete narration script in SSML: wrapped in <speak>...</speak> with <break> tags> }}
"""

# ── Limited mode: splitting instructions included ──────────────────────────────

_PROMPT_LIMITED = _ROLE + """

# Segmentation Rules
After writing the COMPLETE narration (covering all content), divide it into segments:
- Each segment MUST be a coherent unit of meaning — do NOT cut a sentence in the middle.
- Each segment MUST be at most {max_chars} characters long (including spaces and punctuation).
- ALL segments combined MUST contain the complete narration — zero omissions.
- Use as many segments as needed. Do not limit the number of segments.

# Output Format
Return a JSON array of narration segments for AI voice synthesis:
- Each element: {{ "index": <integer starting from 1>, "text": <SSML string> }}
- Each "text" MUST be wrapped in <speak>...</speak> and contain <break> tags at natural pauses.
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
    if not paragraphs:
        raise RuntimeError(f"Gemini returned empty result for {txt_path.name}")

    results: list[Path] = []
    for p in paragraphs:
        idx = p["index"]
        part_text = p["text"].strip()
        if len(part_text) < 50:
            raise RuntimeError(
                f"Part {idx:02d} of {txt_path.name} is too short ({len(part_text)} chars) — likely a generation error"
            )
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
            invalid = [f for f in existing if len(f.read_text(encoding="utf-8").strip()) < 50]
            if invalid:
                print(f"  [invalid] {len(invalid)} part(s) too short, regenerating: {[f.name for f in invalid]}")
                for f in existing:
                    f.unlink()
            else:
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
    import os
    projects = all_projects()
    if os.environ.get("PIPELINE_DEBUG"):
        projects = projects[:1]
        print("[debug] PIPELINE_DEBUG: first project only")
    for project in projects:
        print(f"\n[{project}] rewrite")
        run(project)


if __name__ == "__main__":
    run_all()
