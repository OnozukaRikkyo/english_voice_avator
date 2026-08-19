"""Pipeline configuration — single source of truth.

Data layout
-----------
data/
  {project}/
    raw/          raw input files  (m4a / mp4 / mp3)
    audio/        converted mp3
    transcript/   English transcript, verbatim
    draft/
      parts/      generated chunks (_part*.txt)
      _full.txt   assembled script, before inspection
    narration/    English narration script (_full.txt = final)
      _defects.md what polish fixed and what remains
      parts/      split for heygen only (_part*.txt)
    translation/  Japanese translation of narration (_ja.txt)
    video/        avatar video mp4 (final .mp4)   ← 保留中
      parts/      per-segment videos (_part*.mp4) — heygen output

Adding a new step
-----------------
1. Add the new stage name to STAGES (in the correct position).
2. Add the new step to STEP_IO with its (input_stage, output_stage).
3. Create the module with a run(project) function — pipeline/{step}.py for a
   stage that calls an API, tools/{step}.py for a local-only one (concat_*).
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
# 以下の4定数が全モデルで、書き換えるだけで工程ごとに切り替わる
# （pipeline/llm.py が振り分ける）。モデル名を書く場所はここ以外に無い。
#
#   例) TRANSCRIBE_MODEL = "gpt-transcribe"    → OpenAI
#       TRANSCRIBE_MODEL = "gemini-3.6-flash"  → Gemini
#
# 変更方法は4通り。優先順位は上から強い順:
#   1. コマンドの引数   ./run.sh --model-rewrite MODEL
#   2. プリセット       ./run.sh --provider openai
#   3. .env             REWRITE_MODEL=gemini-3.6-flash   ← コード編集なしで変えられる
#   4. 下の既定値       このファイルを編集する
#
# 現在の設定を一覧するには ./tool_llm_check.sh


def _model(env_name: str, default: str) -> str:
    """モデル定数。.env に同名の変数があればそちらを優先する。"""
    return os.environ.get(env_name, default)


TRANSCRIBE_MODEL = _model("TRANSCRIBE_MODEL", "gpt-transcribe")      # 音声 → テキスト
# rewrite は全工程で最も難しい（用語の正確さ・行間の分析・冗長の削り込みを同時に要求する）。
# flash 系だと言い回しを変えた同じ主張を重ねて字数を稼ぐため、上位モデルを既定にする。
# rewrite.py は effort="high" を渡しており、これが効くのは OpenAI 経路だけである。
REWRITE_MODEL    = _model("REWRITE_MODEL",    "gpt-5.6-luna")        # 文字起こし → ナレーション台本
# review は台本を「放送できるニュース解説か」の観点で点検して直す工程。
# 裏付けのない断定・見出し的な煽り・片側だけの視点を見つける仕事なので、
# rewrite と同じく上位モデルを使う（安いモデルは問題を見つけられない）。
REVIEW_MODEL     = _model("REVIEW_MODEL",     "gpt-5.6-luna")        # 台本の点検・修正
TRANSLATE_MODEL  = _model("TRANSLATE_MODEL",  "gemini-3.6-flash")    # 英語ナレーション → 日本語

# tools/gen_notebooklm_prompt.py 専用。用語の正式な英語表記を実際に検索させるため
# Web検索ツールを有効にして呼ぶ（OpenAI: web_search / Gemini: Google検索グラウンディング）。
# 上と同じ規約で切り替わる。
NOTEBOOKLM_PROMPT_MODEL = _model("NOTEBOOKLM_PROMPT_MODEL", "gpt-5.6-luna")

# ── プロバイダ一括切り替え ────────────────────────────────────────────────────
# 上の4定数は工程ごとに最適なモデルを選ぶための「現在の設定」。
# 全部まとめて片方に寄せたいときのために、プロバイダ別プリセットを用意する。
#
#   ./run.sh --provider openai      全工程を OpenAI に
#   ./run.sh --provider gemini      全工程を Gemini に
#   ./run.sh --provider openai --model-rewrite gemini-3.5-flash   個別指定が優先
#
# プリセットを使わなければ上の4定数がそのまま使われる。
MODEL_SLOTS = ("transcribe", "rewrite", "review", "translate", "notebooklm")

PRESETS: dict[str, dict[str, str]] = {
    "openai": {
        "transcribe":         "gpt-transcribe",
        "rewrite":            "gpt-5.6-luna",
        "review":             "gpt-5.6-luna",
        "translate":          "gpt-5.6-luna",
        "notebooklm":         "gpt-5.6-luna",
    },
    "gemini": {
        "transcribe":         "gemini-3.6-flash",
        "rewrite":            "gemini-3.6-flash",
        "review":             "gemini-3.6-flash",
        "translate":          "gemini-3.6-flash",
        "notebooklm":         "gemini-3.6-flash",
    },
}


def current_models() -> dict[str, str]:
    """上のモデル定数を slot 名の dict にして返す（プリセット未指定時の既定）。"""
    return {
        "transcribe":         TRANSCRIBE_MODEL,
        "rewrite":            REWRITE_MODEL,
        "review":             REVIEW_MODEL,
        "translate":          TRANSLATE_MODEL,
        "notebooklm":         NOTEBOOKLM_PROMPT_MODEL,
    }


def resolve_models(provider: str | None = None, **overrides: str | None) -> dict[str, str]:
    """実際に使うモデルを決める。

    優先順位: 個別指定 > プリセット > .env > config.py の既定値。

    Args:
        provider: PRESETS のキー（"openai" / "gemini"）。None なら4定数をそのまま使う。
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


# **transcript を何文字ずつモデルに渡すか。** -1 なら分割せず全文を1回で渡す。
#
# モデルは渡された transcript 全体を見て「どれだけ書くか」を決めるため、
# 長い transcript をまとめて渡すと圧縮する。同じ38,410字の transcript での実測:
#
#     全文を1回で渡す        → 60%（26〜45% とぶれる）
#     先頭7,000字だけ渡す    → 92%
#     7,000字ずつに分けて渡す → 95%
#
# 出力の分割幅ではない点に注意。出力側を小さくしても効果はなく、
# むしろ悪化した（3,500字指定で32〜37%）。効くのは入力の量である。
#
# 塊は独立に書かせず、位置と直前の台本の末尾を渡して1本に繋げる
# （rewrite.py の _POSITION / _CONTEXT_BLOCK）。
# API 呼び出しは塊の数だけ増える（36分の音声で6回）。
REWRITE_MAX_CHARS = 7000

# OpenAI /v1/audio/transcriptions のアップロード上限（25MB）。
# 超える音声は llm.py が時間で等分割して送る。
OPENAI_AUDIO_MAX_BYTES = 25 * 1024 * 1024

# HeyGen /v2/video/generate の入力テキスト上限（1〜5,000字）。動画長は最大30分。
# rewrite が作る台本パートはこれを超えることがあるため（実測 6,416〜9,483字）、
# heygen が送る前に pipeline/ssml.py で <break> の位置に合わせて割る。
# 出典: https://developers.heygen.com/docs/usage-limits
HEYGEN_MAX_CHARS = 5000

# ── ナレーションの定型オープニング ────────────────────────────────────────────
# 台本の冒頭に必ず入る挨拶。rewrite が part01 の <speak> の中へ差し込む。
# モデルには書かせない — 毎回まったく同じ文言にするため。
#
# 差し替えは .env の NARRATION_OPENING で行う（コード編集不要）。
# 空文字にすると挿入しない。
#
#   NARRATION_OPENING=Hello everyone, and welcome. <break time="0.5s"/> I'm ...
#
# 「新しい旅の始まり」は開設回向けの文言である。回を重ねたら
# 「Hello everyone, and welcome back.」のような定型へ差し替えること。
NARRATION_OPENING = os.environ.get(
    "NARRATION_OPENING",
    'Hello everyone, and welcome. <break time="0.5s"/> '
    "I'm Bogdan Parkhomenko, and this is the beginning of a new journey. "
    '<break time="1.5s"/>',
)

# 点検（A検出→Bパッチ→C検証）を何周回すか。
#
# ゼロ欠陥を追うと収束しない。文体の反復のような「好み」に近い指摘は、
# 直すたびに別の指摘が生まれる。実害のあるもの（構造・文意の破綻・事実）は
# 1〜2周で片付き、残りは記録して人が判断すればよい。
# 1周あたり検出・パッチ・検証の3回 API を呼ぶ。
POLISH_ROUNDS = int(os.environ.get("POLISH_ROUNDS", "2"))

# 台本の末尾に必ず入る締め。挨拶（NARRATION_OPENING）と対になるもので、
# tools/assemble.py が全文を組み立てるときに足す。モデルには書かせない。
# 空にすれば入れない。
NARRATION_CLOSING = os.environ.get(
    "NARRATION_CLOSING",
    "That's where I'll leave it. <break time=\"0.5s\"/> "
    "If you enjoyed this video, consider subscribing. <break time=\"0.5s\"/> "
    "I'm Bogdan Parkhomenko, and I'll be back with another story "
    "underneath the next headline.",
)

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
    "transcript",   # English transcript, verbatim
    "draft",        # narration draft, before the news review
    "narration",    # English narration script (SSML)
    "translation",  # Japanese translation of narration
    "video",        # avatar video (mp4)
]

# Human-readable label for each stage (used in generated docs).
# モデル名は書かない — 上のモデル定数と二重管理になり、片方だけ古くなる。
STAGE_LABELS: dict[str, str] = {
    "raw":         "Raw input (m4a / mp4 / mp3)",
    "audio":       "Converted audio (mp3)",
    "transcript":  "English transcript (verbatim)",
    "draft":       "Generated draft, before inspection",
    "narration":   "English narration script (SSML)",
    "translation": "Japanese translation of the narration",
    "video":       "Avatar video (mp4, HeyGen)",
}

# step_name → (input_stage, output_stage)
# Note: translate and heygen both read from narration/ but different files:
#   translate → reads narration/{stem}_full.txt
#   heygen    → reads narration/parts/{stem}_part*.txt
STEP_IO: dict[str, tuple[str, str]] = {
    "convert":          ("raw",         "audio"),
    "transcribe":       ("audio",       "transcript"),
    "rewrite":          ("transcript",  "draft"),
    "assemble":         ("draft",       "draft"),
    "polish":           ("draft",       "narration"),
    "factcheck":        ("narration",   "narration"),
    "split":            ("narration",   "narration"),
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
