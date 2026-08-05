#!/bin/bash
# 【単一工程】factcheck だけを全プロジェクトに対して実行する。全工程なら ./run.sh
# PIPELINE_DEBUG=1 ./step_factcheck.sh  → first project only
cd "$(dirname "$0")"
source .venv/bin/activate
python -m pipeline.factcheck
