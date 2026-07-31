#!/bin/bash
# 【ツール】HeyGen 字幕の挙動テスト（v3 API）
# Test HeyGen caption behavior. Set CAPTION_MODE to switch test case:
#   CAPTION_MODE=false       ./tool_test_caption.sh   (default)
#   CAPTION_MODE=enable_off  ./tool_test_caption.sh
#   CAPTION_MODE=omit        ./tool_test_caption.sh
#   CAPTION_MODE=obj         ./tool_test_caption.sh
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/test_caption.py
