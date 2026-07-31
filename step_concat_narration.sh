#!/bin/bash
# 【単一工程】concat_narration だけを全プロジェクトに対して実行する。全工程なら ./run.sh
# PIPELINE_DEBUG=1 ./step_concat_narration.sh  → first project only
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/concat_narration.py
