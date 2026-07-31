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
# どちらも必須ではない。使うモデルの側のキーだけあればよい（クライアントは遅延初期化）。
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY", "")

# ── Model constants ───────────────────────────────────────────────────────────
# **モデル名がプロバイダを決める**: "gpt-" で始まれば OpenAI、それ以外は Gemini。
# 以下の5定数が全モデルで、書き換えるだけで工程ごとに切り替わる
# （pipeline/llm.py が振り分ける）。モデル名を書く場所はここ以外に無い。
#
#   例) TRANSCRIBE_MODEL = "gpt-transcribe"    → OpenAI
#       TRANSCRIBE_MODEL = "gemini-2.5-flash"  → Gemini
#
# 現在の設定を一覧するには ./run_llm_check.sh
# この実行だけ変えるには ./run.sh --model-<工程> MODEL
TRANSCRIBE_MODEL = "gpt-transcribe"     # 音声 → テキスト
REWRITE_MODEL    = "gemini-3.5-flash"   # 文字起こし → ナレーション台本
TRANSLATE_MODEL  = "gemini-2.5-flash"   # 英語ナレーション → 日本語

# gpt-transcribe は専用の音声認識モデルで、必ず話された言語のまま逐語で書き起こす
# （prompt でも language でも英語化できないことを実測で確認済み）。そのため
# OpenAI 経路のみ、書き起こしのあとにこのモデルで英語化を1回挟む。
# Gemini 経路は直接英語で書き起こせるので使われない。
TRANSCRIBE_ENGLISH_MODEL = "gemini-2.5-flash"

# tools/gen_notebooklm_prompt.py 専用。用語の正式な英語表記を実際に検索させるため
# Web検索ツールを有効にして呼ぶ（OpenAI: web_search / Gemini: Google検索グラウンディング）。
# 上と同じ規約で切り替わる。
NOTEBOOKLM_PROMPT_MODEL = "gpt-5.6-luna"

# ── プロバイダ一括切り替え ────────────────────────────────────────────────────
# 上の5定数は工程ごとに最適なモデルを選ぶための「現在の設定」。
# 全部まとめて片方に寄せたいときのために、プロバイダ別プリセットを用意する。
#
#   ./run.sh --provider openai      全工程を OpenAI に
#   ./run.sh --provider gemini      全工程を Gemini に
#   ./run.sh --provider openai --model-rewrite gemini-3.5-flash   個別指定が優先
#
# プリセットを使わなければ上の5定数がそのまま使われる。
MODEL_SLOTS = ("transcribe", "transcribe_english", "rewrite", "translate", "notebooklm")

PRESETS: dict[str, dict[str, str]] = {
    "openai": {
        "transcribe":         "gpt-transcribe",
        "transcribe_english": "gpt-5.6-luna",
        "rewrite":            "gpt-5.6-luna",
        "translate":          "gpt-5.6-luna",
        "notebooklm":         "gpt-5.6-luna",
    },
    "gemini": {
        "transcribe":         "gemini-2.5-flash",
        "transcribe_english": "gemini-2.5-flash",  # Gemini 経路では使われない
        "rewrite":            "gemini-3.5-flash",
        "translate":          "gemini-2.5-flash",
        "notebooklm":         "gemini-2.5-flash",
    },
}


def current_models() -> dict[str, str]:
    """上の5定数を slot 名の dict にして返す（プリセット未指定時の既定）。"""
    return {
        "transcribe":         TRANSCRIBE_MODEL,
        "transcribe_english": TRANSCRIBE_ENGLISH_MODEL,
        "rewrite":            REWRITE_MODEL,
        "translate":          TRANSLATE_MODEL,
        "notebooklm":         NOTEBOOKLM_PROMPT_MODEL,
    }


def resolve_models(provider: str | None = None, **overrides: str | None) -> dict[str, str]:
    """実際に使うモデルを決める。

    優先順位: 個別指定 > プリセット > config.py の5定数。

    Args:
        provider: PRESETS のキー（"openai" / "gemini"）。None なら5定数をそのまま使う。
        **overrides: slot 名 → モデル名。None の項目は無視する。
    """
    if provider is not None and provider not in PRESETS:
        raise ValueError(f"未知のプロバイダ: {provider}（有効: {', '.join(PRESETS)}）")
    models = dict(PRESETS[provider]) if provider else current_models()
    for slot, model in overrides.items():
        if model:
            if slot not in MODEL_SLOTS:
                raise ValueError(f"未知のスロット: {slot}（有効: {', '.join(MODEL_SLOTS)}）")
            models[slot] = model
    return models


REWRITE_MAX_CHARS = 7000  # ナレーションを ≤7000 文字のパートに自然な切れ目で分割させる

# OpenAI /v1/audio/transcriptions のアップロード上限（25MB）。
# 超える音声は llm.py が時間で等分割して送る。
OPENAI_AUDIO_MAX_BYTES = 25 * 1024 * 1024

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
