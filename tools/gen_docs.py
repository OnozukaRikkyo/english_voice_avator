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
    PRESETS,
    STEP_IO, NOTEBOOKLM_PROMPT_MODEL,
    TRANSCRIBE_MODEL, REWRITE_MODEL, TRANSLATE_MODEL,
)
from run_pipeline import ALL_STEPS  # active steps only — suspended ones are commented out there


def _provider(model: str) -> str:
    """モデル名がプロバイダを決める — pipeline/llm.py と同じ規約。"""
    return "OpenAI" if model.startswith("gpt-") else "Gemini"

# Steps that exist in STEP_IO but are not in ALL_STEPS are on hold.
SUSPENDED_STEPS = [s for s in STEP_IO if s not in ALL_STEPS]


# ── Document generators ────────────────────────────────────────────────────────

def gen_user_guide() -> str:
    """docs/user_guide.md — 全体の入口。何ができて、どれを読めばいいか。"""
    steps_list = " → ".join(ALL_STEPS)
    suspended = (
        f"\n`{'` / `'.join(SUSPENDED_STEPS)}` は保留中で実行されません"
        "（詳細は `video_guide.md`）。\n" if SUSPENDED_STEPS else "\n"
    )
    return (
        "# ユーザーガイド\n"
        "\n"
        "このプロジェクトでできることは2つです。目的から選んでください。\n"
        "\n"
        "| やりたいこと | コマンド | 詳細 |\n"
        "|---|---|---|\n"
        "| 音声ファイルから英語ナレーション台本と日本語訳を作る | `./run.sh` | `video_guide.md` |\n"
        "| 日本語資料から NotebookLM 用プロンプトを作る | `./gen_notebooklm_prompt.sh` | `notebooklm_guide.md` |\n"
        "\n"
        "使うAIモデルの変更方法は `model_guide.md` にまとめています。\n"
        "\n"
        "---\n"
        "\n"
        "## はじめに（初回のみ）\n"
        "\n"
        "### 1. APIキーを設定する\n"
        "\n"
        "`.env` に書きます（git 管理外）。**実際に使う側だけ**あれば動きます。\n"
        "\n"
        "```\n"
        "GEMINI_API_KEY=...\n"
        "OPENAI_API_KEY=...\n"
        "HEYGEN_API_KEY=...        # 動画生成を再開するときのみ\n"
        "```\n"
        "\n"
        "### 2. 設定を確認する\n"
        "\n"
        "```bash\n"
        "./run_llm_check.sh\n"
        "```\n"
        "\n"
        "工程ごとにどのモデル・どの提供元を使う設定か、必要なキーが揃っているかが出ます。\n"
        "`--live` を付けると実際に呼び出して疎通確認します。\n"
        "\n"
        "---\n"
        "\n"
        "## 使い方A: 音声 → 台本\n"
        "\n"
        "```bash\n"
        "./run_batch.sh path/to/audio.m4a     # 音声を指定して1本処理する\n"
        "```\n"
        "\n"
        "何本も続けて処理する場合はこれが一番手軽です。処理後は inbox から\n"
        "自動で片付けられるので、次のファイルを指定してまた実行するだけです。\n"
        "同名プロジェクトが既にある場合は上書きせずエラーで止まります。\n"
        "\n"
        "inbox に置いてから実行する従来の方法も使えます。\n"
        "\n"
        "```bash\n"
        "cp your_audio.m4a data/inbox/    # 1. 置く\n"
        "./run.sh                          # 2. 実行する\n"
        "```\n"
        "\n"
        f"`{steps_list}` が順に動きます。\n"
        "入力音声は英語である前提です。\n"
        f"{suspended}"
        "\n"
        "できあがるもの:\n"
        "\n"
        "```\n"
        "data/{プロジェクト名}/\n"
        "  narration/*_full.txt     ← 英語ナレーション台本（SSML）\n"
        "  translation/*_ja.txt     ← その日本語訳\n"
        "```\n"
        "\n"
        "プロジェクト名は音声ファイル名から自動で付きます。\n"
        "\n"
        "---\n"
        "\n"
        "## 使い方B: 資料 → NotebookLM プロンプト\n"
        "\n"
        "```bash\n"
        "cp your_doc.docx data/senario_jp/   # 1. 置く（.docx / .pdf）\n"
        "./gen_notebooklm_prompt.sh          # 2. 実行する\n"
        "```\n"
        "\n"
        "`data/senario_jp/prompts/*_prompt.txt` ができるので、\n"
        "中身をそのまま NotebookLM に貼り付けてください。\n"
        "\n"
        "---\n"
        "\n"
        "## よくある操作\n"
        "\n"
        "```bash\n"
        "./run.sh --steps transcribe            # 特定の工程だけ動かす\n"
        "./run.sh --force                       # 既存の出力を無視して作り直す\n"
        "./run.sh --provider openai             # 全工程を ChatGPT に切り替える\n"
        "./run.sh --project スラッグ名          # 特定プロジェクトだけ処理する\n"
        "python tools/clean_data.py             # 生成物を全部消してやり直す\n"
        "```\n"
        "\n"
        "工程ごとの個別実行用に `run_convert.sh` `run_transcribe.sh` `run_rewrite.sh`\n"
        "`run_concat_narration.sh` `run_translate.sh` も用意しています。\n"
        "\n"
        "---\n"
        "\n"
        "## 困ったとき\n"
        "\n"
        "| 症状 | 対処 |\n"
        "|---|---|\n"
        "| `GEMINI_API_KEY が未設定です` / `OPENAI_API_KEY が未設定です` | `.env` に該当キーを追加。`./run_llm_check.sh` で確認 |\n"
        "| 途中まで生成済みで先に進まない | 各工程は出力があるとスキップします。作り直すなら `--force` |\n"
        "| 出力が古い内容のまま | 同上。`--force` を付けるか `tools/clean_data.py` で消す |\n"
        "| モデルを変えたい | `./run.sh --provider openai`、または `pipeline/config.py` を編集（`model_guide.md`） |\n"
        "| 動画が作られない | `heygen` / `concat_video` は保留中です（`video_guide.md`） |\n"
        "| 生成物が消えた | `data/` は git 管理外です。元音声から作り直せます |\n"
        "\n"
        "---\n"
        "\n"
        "## 中身を知りたい人向け\n"
        "\n"
        "- `CLAUDE.md` — パイプラインの仕様（`pipeline/config.py` から自動生成）\n"
        "- `pipeline/config.py` — ステージ定義・モデル定数。**設定の単一の情報源**\n"
        "- `pipeline/llm.py` — Gemini / OpenAI の呼び分け\n"
        "- `docs/` は `tools/gen_docs.py` から自動生成されます。直接編集しないでください\n"
    )



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
        "入力音声は英語である前提です（逐語で書き起こします）。\n"
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
        f"`{NOTEBOOKLM_PROMPT_MODEL}`（{_provider(NOTEBOOKLM_PROMPT_MODEL)}）が資料を読んで\n"
        "ドメイン（戦争・政治・経済・技術など）を判定し、そのドメインに合わせて次の3つを書き起こします。\n"
        "Web検索ツールを有効にしているため、用語の英語表記は実際に検索して確認されます。\n"
        "モデルの切り替え方は `model_guide.md` を参照してください。\n"
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
        "## 変え方は4通り\n"
        "\n"
        "優先順位は **個別指定 > プリセット > .env > config.py の既定値** です。\n"
        "\n"
        "### 1. 全工程をまとめて（この実行だけ）\n"
        "\n"
        "```bash\n"
        f"{''.join(f'./run.sh --provider {n}{chr(10)}' for n in sorted(PRESETS))}"
        "```\n"
        "\n"
        "中身は `pipeline/config.py` の `PRESETS` です。\n"
        "\n"
        "### 2. 1工程だけ（この実行だけ）\n"
        "\n"
        "```bash\n"
        "./run.sh --model-rewrite gpt-5.6-luna\n"
        "./run.sh --model-transcribe gemini-2.5-flash\n"
        "./gen_notebooklm_prompt.sh --model-notebooklm gemini-2.5-flash\n"
        "```\n"
        "\n"
        "プリセットと併用でき、個別指定が勝ちます。\n"
        "\n"
        "```bash\n"
        "./run.sh --provider openai --model-rewrite gemini-3.5-flash\n"
        "  → rewrite だけ Gemini、他は OpenAI\n"
        "```\n"
        "\n"
        "### 3. 恒久的に変える（コード編集なし・おすすめ）\n"
        "\n"
        "`.env` に定数名と同じ名前で書くだけです。雛形がコメントで入っています。\n"
        "\n"
        "```\n"
        "REWRITE_MODEL=gemini-3.6-flash\n"
        "TRANSLATE_MODEL=gpt-5.6-luna\n"
        "```\n"
        "\n"
        "`./run_llm_check.sh` で反映を確認できます。\n"
        "\n"
        "### 4. 既定値そのものを変える\n"
        "\n"
        "`pipeline/config.py` の該当行を書き換えます。\n"
        "\n"
        "```python\n"
        'TRANSCRIBE_MODEL = _model("TRANSCRIBE_MODEL", "gpt-transcribe")     # OpenAI\n'
        'TRANSCRIBE_MODEL = _model("TRANSCRIBE_MODEL", "gemini-3.6-flash")   # Gemini\n'
        "```\n"
        "\n"
        "## 確認する\n"
        "\n"
        "```bash\n"
        "./run_llm_check.sh                    # 工程ごとのモデルとプロバイダ、キーの有無\n"
        "./run_llm_check.sh --provider openai  # プリセット適用後の姿を予習（変更はしない）\n"
        "./run_llm_check.sh --live             # 実際に呼び出して疎通確認\n"
        "./run_llm_check.sh --models           # 利用可能なモデル一覧\n"
        "```\n"
        "\n"
        "## 文字起こしについて\n"
        "\n"
        "入力音声は英語である前提です。書き起こしは逐語で行い、言語変換は挟みません\n"
        "（1音声につきAPI呼び出しは1回）。\n"
        "\n"
        "OpenAI のアップロード上限は25MBです。超える音声は `pipeline/llm.py` が\n"
        "ffmpeg で時間分割して個別に送り、結果を連結します。\n"
        "\n"
        "## モデル選定の考え方\n"
        "\n"
        "**作業の難易度で選びます。** 安いモデルで足りる工程だけ安くします。\n"
        "\n"
        "| 工程 | 難易度 | 理由 |\n"
        "|---|---|---|\n"
        "| rewrite | 最難 | 軍事用語の正確さ・行間の戦略的洞察・独自視点・SSML・意味単位での分割を同時に要求 |\n"
        "| transcribe | 高 | 固有名詞の聞き取り。誤ると後段すべてが誤った前提で動き、取り返しがつかない |\n"
        "| notebooklm | 中〜高 | 検索の使い分けと、一般読者が分からない語だけを選ぶ取捨選択 |\n"
        "| translate | 中 | 翻訳自体は機械的だが、NHK準拠の固有名詞表記と論調の維持が要る |\n"
        "\n"
        "translate を lite に落とすのは推奨しません。実測で `gemini-2.5-flash-lite` は\n"
        "改行構造が123行→8行に崩れ、固有名詞も落ちました。\n"
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
        "## Web検索を使う工程\n"
        "\n"
        f"`tools/gen_notebooklm_prompt.py` は用語の正式な英語表記を実際に調べさせるため、\n"
        f"Web検索ツールを有効にして呼びます（`NOTEBOOKLM_PROMPT_MODEL` = "
        f"`{NOTEBOOKLM_PROMPT_MODEL}` / {_provider(NOTEBOOKLM_PROMPT_MODEL)}）。\n"
        "これも同じ規約で切り替わります。\n"
        "\n"
        "- **OpenAI** — Responses API の `web_search` ツール\n"
        "- **Gemini** — Google 検索グラウンディング\n"
        "\n"
        "```bash\n"
        "./gen_notebooklm_prompt.sh                              # 既定モデル\n"
        "./gen_notebooklm_prompt.sh --model gemini-2.5-flash     # この実行だけ変更\n"
        "```\n"
    )


# ── Registry & runner ─────────────────────────────────────────────────────────

# Map output filename → generator function
# To add a new doc: add an entry here.
DOCS_REGISTRY: dict[str, callable] = {
    "user_guide.md": gen_user_guide,
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
