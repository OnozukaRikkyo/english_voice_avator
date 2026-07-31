#!/usr/bin/env python3
"""Auto-generate human-facing documentation in docs/.

Each public function generates one markdown file.
To add a new document:
  1. Add a function  gen_<name>() -> str  that returns the markdown content.
  2. Add it to DOCS_REGISTRY at the bottom of this file.
  3. Save — the PostToolUse hook regenerates all docs automatically.

Never edit files in docs/ by hand; edit this file instead.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs"

sys.path.insert(0, str(ROOT))
from pipeline.config import (
    STEP_IO, NOTEBOOKLM_PROMPT_MODEL,
    TRANSCRIBE_MODEL, TRANSCRIBE_ENGLISH_MODEL, REWRITE_MODEL, TRANSLATE_MODEL,
)
from run_pipeline import ALL_STEPS  # active steps only — suspended ones are commented out there


def _provider(model: str) -> str:
    """モデル名がプロバイダを決める — pipeline/llm.py と同じ規約。"""
    return "OpenAI" if model.startswith("gpt-") else "Gemini"

# Steps that exist in STEP_IO but are not in ALL_STEPS are on hold.
SUSPENDED_STEPS = [s for s in STEP_IO if s not in ALL_STEPS]


# ── Document generators ────────────────────────────────────────────────────────

def gen_video_guide() -> str:
    """docs/video_guide.md — how to turn an audio file into a narration script."""
    steps_list = " → ".join(ALL_STEPS)
    suspended = ""
    if SUSPENDED_STEPS:
        suspended = (
            "\n"
            "## 保留中のステップ\n"
            "\n"
            f"`{'` / `'.join(SUSPENDED_STEPS)}` は現在**実行されません**。\n"
            "HeyGen の画面字幕を消す方法が未解決のため保留しています。\n"
            "\n"
            "調査は `./run_investigate_caption.sh` で実行できます（実 API 呼び出しと\n"
            "動画フレームの画素解析で字幕バーの位置を測定し、\n"
            "`data/caption_investigation/report.md` に結果を出力します）。\n"
            "\n"
            "再開するには `run_pipeline.py` の `ALL_STEPS` にある該当行と、\n"
            "`main()` 内の対応する分岐のコメントを外してください。\n"
            "モジュール本体（`pipeline/heygen.py` / `tools/concat_video.py`）は残してあります。\n"
        )
    return (
        "# 音声から台本を作る手順\n"
        "\n"
        "## 手順\n"
        "\n"
        "### 1. 音声ファイルを inbox に置く\n"
        "\n"
        "```\n"
        "data/inbox/\n"
        "  your_audio.m4a   ← ここに置く\n"
        "```\n"
        "\n"
        "対応フォーマット: `.m4a` / `.mp4` / `.mp3`\n"
        "\n"
        "音声の言語は問いません。英語以外の音声は文字起こしの時点で英訳され、\n"
        "`transcript/` には**常に英語**が出力されます。\n"
        "\n"
        "### 2. パイプラインを実行する\n"
        "\n"
        "```bash\n"
        "./run.sh\n"
        "```\n"
        "\n"
        "これだけです。以下がすべて自動で実行されます：\n"
        "\n"
        "1. `data/inbox/` をスキャンし、ファイル名からプロジェクトを自動作成\n"
        f"2. パイプライン実行: `{steps_list}`\n"
        "\n"
        "最終成果物は以下の2つです：\n"
        "\n"
        "- `data/{project}/narration/*_full.txt` — 英語ナレーション台本（SSML）\n"
        "- `data/{project}/translation/*_ja.txt` — その日本語訳\n"
        f"{suspended}"
        "\n"
        "## トラブルシューティング\n"
        "\n"
        "### HeyGen API / アバターIDの確認\n"
        "\n"
        "```bash\n"
        "python heygen_check.py\n"
        "```\n"
        "\n"
        "### 生成物をすべて消してやり直す\n"
        "\n"
        "```bash\n"
        "python tools/clean_data.py\n"
        "```\n"
        "\n"
        "`data/` 配下は丸ごと git 管理外です。すべて元音声から再生成できます。\n"
    )


def gen_notebooklm_guide() -> str:
    """docs/notebooklm_guide.md — how to generate a NotebookLM prompt from a document."""
    return (
        "# NotebookLM プロンプトの生成手順\n"
        "\n"
        "NotebookLM で音声を作る際に貼り付ける**システムプロンプト**を、\n"
        "手元の日本語資料から自動生成します。\n"
        "\n"
        "生成するのはプロンプトだけです。音声そのものは NotebookLM 側で作ります。\n"
        "\n"
        "## 手順\n"
        "\n"
        "### 1. 日本語資料を置く\n"
        "\n"
        "```\n"
        "data/senario_jp/\n"
        "  your_document.docx   ← ここに置く\n"
        "```\n"
        "\n"
        "対応フォーマット: `.docx` / `.pdf`\n"
        "\n"
        "### 2. 生成する\n"
        "\n"
        "```bash\n"
        "./gen_notebooklm_prompt.sh\n"
        "```\n"
        "\n"
        "### 3. 出力を NotebookLM に貼り付ける\n"
        "\n"
        "```\n"
        "data/senario_jp/prompts/\n"
        "  your_document_prompt.txt   ← これをそのまま貼り付ける\n"
        "```\n"
        "\n"
        "## 生成されるプロンプトの中身\n"
        "\n"
        f"`{NOTEBOOKLM_PROMPT_MODEL}` が資料を読んでドメイン（戦争・政治・経済・技術など）を\n"
        "判定し、そのドメインに合わせて次の3つを書き起こします。\n"
        "Google 検索ツールを有効にしているため、用語の英語表記は実際に検索して確認されます。\n"
        "\n"
        "1. **Role & Objective** — ドメインに合った専門家の役割設定\n"
        "2. **Document-Specific Vocabulary Guide** — 資料に出てくる難解語の用語集。\n"
        "   対象読者は「その分野の知識がない一般的なアメリカ人成人」で、\n"
        "   本当に分からない語（マイナーな地名・型式名・略語・専門用語）だけを選びます\n"
        "3. **Core Instructions** — 参照すべき権威ある英語サイトの実名\n"
        "   （紛争なら isw.org、経済なら imf.org など）、資料に明示されていない\n"
        "   独自の分析視点の見つけ方（具体例2つ）、トーンと構成\n"
        "\n"
        "## 注意\n"
        "\n"
        "- `data/` は丸ごと git 管理外です。生成したプロンプトはローカルにのみ残ります\n"
        "- 用語集は自動生成なので、そのまま使う前に内容を確認してください\n"
        "  （生成物自身にもその旨の注記が入ります）\n"
        "- 生成元: `tools/gen_notebooklm_prompt.py`（プロンプト定義は `_META_PROMPT`）\n"
    )


def gen_model_guide() -> str:
    """docs/model_guide.md — how to switch each step between Gemini and ChatGPT."""
    rows = "\n".join(
        f"| `{const}` | `{model}` | {_provider(model)} |"
        for const, model in (
            ("TRANSCRIBE_MODEL", TRANSCRIBE_MODEL),
            ("TRANSCRIBE_ENGLISH_MODEL", TRANSCRIBE_ENGLISH_MODEL),
            ("REWRITE_MODEL", REWRITE_MODEL),
            ("TRANSLATE_MODEL", TRANSLATE_MODEL),
        )
    )
    return (
        "# モデル・プロバイダの切り替え\n"
        "\n"
        "## 規約\n"
        "\n"
        "**モデル名がプロバイダを決めます。**\n"
        "`gpt-` で始まれば OpenAI、それ以外は Gemini。\n"
        "呼び分けは `pipeline/llm.py` が行い、各工程のコードは\n"
        "プロバイダのSDKを直接触りません。utimes プロジェクトと同じ規約です。\n"
        "\n"
        "## 現在の設定\n"
        "\n"
        "| 定数 | モデル | プロバイダ |\n"
        "|------|--------|-----------|\n"
        f"{rows}\n"
        "\n"
        "## 恒久的に変える\n"
        "\n"
        "`pipeline/config.py` の該当行を書き換えるだけです。\n"
        "\n"
        "```python\n"
        'TRANSCRIBE_MODEL = "gpt-transcribe"     # OpenAI\n'
        'TRANSCRIBE_MODEL = "gemini-2.5-flash"   # Gemini\n'
        "```\n"
        "\n"
        "## 一時的に変える（この実行だけ）\n"
        "\n"
        "```bash\n"
        "./run.sh --model-rewrite gpt-5.6-luna\n"
        "./run.sh --model-transcribe gemini-2.5-flash\n"
        "```\n"
        "\n"
        "## 確認する\n"
        "\n"
        "```bash\n"
        "./run_llm_check.sh            # 工程ごとのモデルとプロバイダ、キーの有無\n"
        "./run_llm_check.sh --live     # 実際に呼び出して疎通確認\n"
        "./run_llm_check.sh --models   # 利用可能なモデル一覧\n"
        "```\n"
        "\n"
        "## 文字起こしの注意\n"
        "\n"
        "`transcript/` は**常に英語**という約束ですが、実現方法が経路で違います。\n"
        "\n"
        "- **Gemini 経路** — マルチモーダルなので「英語で出せ」と直接指示でき、1回で終わります。\n"
        "- **OpenAI 経路** — `gpt-transcribe` は専用の音声認識モデルで、\n"
        "  **必ず話された言語のまま逐語で書き起こします**。\n"
        "  `prompt` でも `language=en` でも英語化できないことを実 API で確認済みです。\n"
        f"  そのため書き起こしの後に `{TRANSCRIBE_ENGLISH_MODEL}` で英語化を1回挟みます\n"
        "  （`TRANSCRIBE_ENGLISH_MODEL`）。英語音声なら実質そのまま返ります。\n"
        "\n"
        "OpenAI のアップロード上限は25MBです。超える音声は `pipeline/llm.py` が\n"
        "ffmpeg で時間分割して個別に送り、結果を連結します。\n"
        "\n"
        "## APIキー\n"
        "\n"
        "`.env`（git 管理外）に置きます。クライアントは遅延初期化なので、\n"
        "**実際に使う側のキーだけ**あれば動きます。\n"
        "\n"
        "```\n"
        "GEMINI_API_KEY=...\n"
        "OPENAI_API_KEY=...\n"
        "```\n"
        "\n"
        f"なお `tools/gen_notebooklm_prompt.py` だけは Google 検索グラウンディングを使うため\n"
        f"`NOTEBOOKLM_PROMPT_MODEL`（`{NOTEBOOKLM_PROMPT_MODEL}`）で Gemini 固定です。\n"
    )


# ── Registry & runner ─────────────────────────────────────────────────────────

# Map output filename → generator function
# To add a new doc: add an entry here.
DOCS_REGISTRY: dict[str, callable] = {
    "video_guide.md": gen_video_guide,
    "notebooklm_guide.md": gen_notebooklm_guide,
    "model_guide.md": gen_model_guide,
}


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    for filename, generator in DOCS_REGISTRY.items():
        out = DOCS / filename
        content = generator()
        current = out.read_text(encoding="utf-8") if out.exists() else ""
        if content != current:
            out.write_text(content, encoding="utf-8")
            print(f"[gen_docs] docs/{filename} updated")


if __name__ == "__main__":
    main()
