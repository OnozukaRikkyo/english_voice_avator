#!/bin/bash
# 【単一工程】heygen だけを全プロジェクトに対して実行する。全工程なら ./run.sh
# PIPELINE_DEBUG=1 ./step_heygen.sh  → first project, 1 newly generated part only
cd "$(dirname "$0")"
source .venv/bin/activate
python -m pipeline.heygen
