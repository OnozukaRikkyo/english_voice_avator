#!/bin/bash
# 【単一工程・保留中】heygen。run.sh からは実行されない（字幕問題が未解決）
# PIPELINE_DEBUG=1 ./step_heygen.sh  → first project, 1 newly generated part only
cd "$(dirname "$0")"
source .venv/bin/activate
python -m pipeline.heygen
