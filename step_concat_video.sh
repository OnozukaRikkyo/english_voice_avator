#!/bin/bash
# 【単一工程・保留中】concat_video。run.sh からは実行されない（字幕問題が未解決）
# PIPELINE_DEBUG=1 ./step_concat_video.sh  → first project only
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/concat_video.py
