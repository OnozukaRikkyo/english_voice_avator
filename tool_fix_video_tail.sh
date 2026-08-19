#!/bin/bash
# 【パイプライン外】既存の動画パートの末尾を点検し、台本が無音を指定している
# 区間に残った音を消す。直したら結合もやり直す。生成時は heygen が同じ検査をする。
#   ./tool_fix_video_tail.sh                  全プロジェクトを点検して直す
#   ./tool_fix_video_tail.sh --check          直さず報告だけ
#   ./tool_fix_video_tail.sh --project SLUG   1つだけ
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/fix_video_tail.py "$@"
