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
from pipeline.config import STEP_IO


# ── Document generators ────────────────────────────────────────────────────────

def gen_video_guide() -> str:
    """docs/video_guide.md — how to create an avatar video from an audio file."""
    steps_list = " → ".join(STEP_IO.keys())
    return (
        "# 新規動画の作成手順\n"
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
        "### 2. パイプラインを実行する\n"
        "\n"
        "```bash\n"
        "python run_pipeline.py\n"
        "```\n"
        "\n"
        "これだけです。以下がすべて自動で実行されます：\n"
        "\n"
        f"1. `data/inbox/` をスキャンし、ファイル名からプロジェクトを自動作成\n"
        f"2. パイプライン実行: `{steps_list}`\n"
        "3. 動画・ナレーションの結合\n"
        "\n"
        "## トラブルシューティング\n"
        "\n"
        "### HeyGen API / アバターIDの確認\n"
        "\n"
        "```bash\n"
        "python heygen_check.py\n"
        "```\n"
    )


# ── Registry & runner ─────────────────────────────────────────────────────────

# Map output filename → generator function
# To add a new doc: add an entry here.
DOCS_REGISTRY: dict[str, callable] = {
    "video_guide.md": gen_video_guide,
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
