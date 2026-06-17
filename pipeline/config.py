"""Pipeline configuration — single source of truth.

Data layout
-----------
data/
  {project}/
    raw/         raw input files  (m4a / mp4 / mp3)
    audio/       converted mp3
    transcript/  English transcription (Gemini)
    narration/   rewritten YouTube script (Gemini)
    video/       avatar video mp4 (HeyGen)

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
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── API keys ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY  = os.environ["GEMINI_API_KEY"]
MINIMAX_API_KEY = os.environ["MINIMAX_API_KEY"]
HEYGEN_API_KEY  = os.environ.get("HEYGEN_API_KEY", "")

# ── Model / service constants ─────────────────────────────────────────────────
GEMINI_TRANSCRIBE_MODEL = "gemini-2.5-flash"
GEMINI_REWRITE_MODEL    = "gemini-3.5-flash"
REWRITE_MAX_CHARS       = -1   # -1 = unlimited (one output file)

MINIMAX_TTS_URL   = "https://api.minimax.io/v1/t2a_v2"
MINIMAX_VOICE_ID  = "moss_audio_10fc0153-4b51-11f1-8d50-22f63c968931"
MINIMAX_MODEL     = "speech-2.8-hd"
MINIMAX_EMOTION   = "calm"
MINIMAX_MAX_CHARS = 5000

HEYGEN_BASE_URL  = "https://api.heygen.com"
HEYGEN_AVATAR_ID = os.environ.get("HEYGEN_AVATAR_ID", "")
HEYGEN_VOICE_ID  = os.environ.get("HEYGEN_VOICE_ID", "")
HEYGEN_RATIO     = "16:9"

# ── Pipeline stages ───────────────────────────────────────────────────────────
# Ordered list — the ORDER defines the pipeline sequence.
# To insert a step: add the stage name here in the right position.
# Directory names are stable; insertion never requires renaming.
STAGES: list[str] = [
    "raw",         # source input files
    "audio",       # converted mp3
    "transcript",  # English transcription
    "narration",   # rewritten YouTube narration script
    "video",       # avatar video (mp4)
]

# Human-readable label for each stage (used in generated docs)
STAGE_LABELS: dict[str, str] = {
    "raw":        "Raw input (m4a / mp4 / mp3)",
    "audio":      "Converted audio (mp3)",
    "transcript": "English transcript",
    "narration":  "Narration script (YouTube style, Gemini 3.5 Flash)",
    "video":      "Avatar video (mp4, HeyGen)",
}

# step_name → (input_stage, output_stage)
# This is the single definition of what each pipeline step reads and writes.
STEP_IO: dict[str, tuple[str, str]] = {
    "convert":    ("raw",        "audio"),
    "transcribe": ("audio",      "transcript"),
    "rewrite":    ("transcript", "narration"),
    "heygen":     ("narration",  "video"),
}

# ── Path helpers ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"


def stage_dir(project: str, stage: str) -> Path:
    """Return the data directory for a given project and stage name."""
    return DATA / project / stage


def all_projects() -> list[str]:
    """Return all project slugs (directories that contain a 'raw' subdirectory)."""
    if not DATA.exists():
        return []
    return sorted(p.name for p in DATA.iterdir() if p.is_dir() and (p / "raw").is_dir())


def ensure_project_dirs(project: str) -> None:
    """Create all stage directories for a project."""
    for stage in STAGES:
        stage_dir(project, stage).mkdir(parents=True, exist_ok=True)
