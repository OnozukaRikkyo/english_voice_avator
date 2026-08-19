#!/bin/bash
# 【パイプライン外】指定した動画パートだけを作り直し、その後に結合をやり直す。
# 全部作り直す --force と違い、指定した本数ぶんしか課金されない。
#   ./tool_regen_video_parts.sh part01
#   ./tool_regen_video_parts.sh part01 part04 --project SLUG
#   ./tool_regen_video_parts.sh 01 --dry-run
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/regen_video_parts.py "$@"
