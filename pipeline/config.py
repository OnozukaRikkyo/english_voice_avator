"""Pipeline configuration — single source of truth.

Data layout
-----------
data/
  {project}/
    raw/          raw input files  (m4a / mp4 / mp3)
    audio/        converted mp3
    transcript/   English transcription (Gemini)
    narration/    rewritten YouTube narration (_full.txt = final)
      parts/      split segments (_part*.txt) — heygen input
    translation/  Japanese translation of narration (_ja.txt)
    video/        avatar video mp4 (final .mp4)
      parts/      per-segment videos (_part*.mp4) — heygen output

Adding a new step
-----------------
1. Add the new stage name to STAGES (in the correct position).
2. Add the new step to STEP_IO with its (input_stage, output_stage).
3. Create pipeline/{step}.py with a run(project) function.
4. Add the step to ALL_STEPS in run_pipeline.py.
tools/gen_spec.py will automatically regenerate CLAUDE.md.

Stage insertion does NOT require renaming existing directories.
"""
import os
import re
import unicodedata
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── API keys ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY", "")

# ── Model / service constants ─────────────────────────────────────────────────
GEMINI_TRANSCRIBE_MODEL = "gemini-2.5-flash"
GEMINI_REWRITE_MODEL    = "gemini-3.5-flash"
GEMINI_TRANSLATE_MODEL  = "gemini-2.5-flash"
REWRITE_MAX_CHARS       = 7000  # Gemini splits narration into parts of ≤7000 chars at natural break points

HEYGEN_BASE_URL  = "https://api.heygen.com"
HEYGEN_AVATAR_ID = os.environ.get("HEYGEN_AVATAR_ID", "")
HEYGEN_VOICE_ID  = os.environ.get("HEYGEN_VOICE_ID", "")
HEYGEN_RATIO     = "16:9"

# ── Pipeline stages ───────────────────────────────────────────────────────────
# Ordered list — the ORDER defines the pipeline sequence.
# To insert a step: add the stage name here in the right position.
# Directory names are stable; insertion never requires renaming.
STAGES: list[str] = [
    "raw",          # source input files
    "audio",        # converted mp3
    "transcript",   # English transcription
    "narration",    # rewritten YouTube narration script
    "translation",  # Japanese translation of narration
    "video",        # avatar video (mp4)
]

# Human-readable label for each stage (used in generated docs)
STAGE_LABELS: dict[str, str] = {
    "raw":         "Raw input (m4a / mp4 / mp3)",
    "audio":       "Converted audio (mp3)",
    "transcript":  "English transcript",
    "narration":   "Narration script (YouTube style, Gemini 3.5 Flash)",
    "translation": "Japanese translation of narration (Gemini 2.5 Flash)",
    "video":       "Avatar video (mp4, HeyGen)",
}

# step_name → (input_stage, output_stage)
# Note: translate and heygen both read from narration/ but different files:
#   translate → reads narration/{stem}_full.txt
#   heygen    → reads narration/parts/{stem}_part*.txt
STEP_IO: dict[str, tuple[str, str]] = {
    "convert":          ("raw",         "audio"),
    "transcribe":       ("audio",       "transcript"),
    "rewrite":          ("transcript",  "narration"),
    "concat_narration": ("narration",   "narration"),
    "translate":        ("narration",   "translation"),
    "heygen":           ("narration",   "video"),
    "concat_video":     ("video",       "video"),
}

# ── Path helpers ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
INBOX_DIR = DATA / "inbox"  # drop zone: place audio files here, run_pipeline.py picks them up

# Intermediate split files (e.g. _part01.txt) live here, inside their stage dir.
# Final outputs (e.g. _full.txt, .mp4) live directly in the stage dir.
# Rule: never put _part* files directly in a stage dir — always use parts/.
PARTS_SUBDIR = "parts"


def slugify(stem: str) -> str:
    """Convert an audio filename stem to a safe ASCII project slug.

    Rules:
      - Unicode normalization (NFKD) then drop non-ASCII bytes
      - Replace runs of non-word characters with _
      - Strip leading/trailing underscores
      - If result is empty (fully non-ASCII stem), use hex hash as fallback

    Examples:
      "Russia’s_Seventeen_Kilometer_Map_Lie" → "Russias_Seventeen_Kilometer_Map_Lie"
      "NATO Summit June-2026"                      → "NATO_Summit_June_2026"
      "中東情勢レポート"                            → "a3f2b1c4"  (hash fallback)
    """
    normalized = unicodedata.normalize("NFKD", stem)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^\w]+", "_", ascii_only).strip("_")
    if not safe:
        import hashlib
        safe = hashlib.md5(stem.encode()).hexdigest()[:8]
    return safe


def stage_dir(project: str, stage: str) -> Path:
    """Return the data directory for a given project and stage name."""
    return DATA / project / stage


def parts_dir(project: str, stage: str) -> Path:
    """Return the parts/ subdirectory for intermediate split files within a stage."""
    return stage_dir(project, stage) / PARTS_SUBDIR


def all_projects() -> list[str]:
    """Return all project slugs (directories that contain a 'raw' subdirectory)."""
    if not DATA.exists():
        return []
    return sorted(p.name for p in DATA.iterdir() if p.is_dir() and (p / "raw").is_dir())


def ensure_project_dirs(project: str) -> None:
    """Create all stage directories for a project."""
    for stage in STAGES:
        stage_dir(project, stage).mkdir(parents=True, exist_ok=True)
