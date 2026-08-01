#!/bin/bash
# 【ツール】設定中のアバターと音声を、短い文で1本だけ生成して確認する
# アバターIDや音声IDを変えたあとの見た目・声の確認用。消費は最小です。
# 出力: /tmp/heygen_test.mp4
#
#   ./tool_heygen_test.sh                    既定の短文で生成
#   ./tool_heygen_test.sh "好きな文章"        文章を指定して生成
cd "$(dirname "$0")"
source .venv/bin/activate
TEXT="${1:-}" python - <<'EOF'
import os
from pathlib import Path

from pipeline.config import HEYGEN_AVATAR_ID, HEYGEN_VOICE_ID
from pipeline.heygen import generate_video

# 短いほど消費が少ない。見た目・声・背景・字幕の有無はこれで分かる。
DEFAULT = ("Hello. This is a short test of the current avatar and voice setting. "
           "If you can see and hear this clearly, the configuration is working.")

text = os.environ.get("TEXT") or DEFAULT
out = Path("/tmp/heygen_test.mp4")

print(f"  アバターID: {HEYGEN_AVATAR_ID}")
print(f"  音声ID    : {HEYGEN_VOICE_ID}")
print(f"  本文      : {len(text)}字 ≒ {len(text) / 900 * 60:.0f}秒\n")

generate_video(text, out, title="avatar_test")
print(f"\n完了 → {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")
print("  確認: アバターの見た目 / 声 / 背景の緑 / 画面字幕が出ていないこと")
EOF
