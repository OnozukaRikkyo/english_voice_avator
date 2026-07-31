#!/bin/bash
# 【ツール】HeyGen 字幕の実証調査（実API + 画素解析）→ data/caption_investigation/
# Run caption investigation: empirical API tests + frame analysis
# Output: data/caption_investigation/report.md
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/investigate_caption.py
