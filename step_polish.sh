#!/bin/bash
# 【単一工程】台本を全文で点検して直す（A検出→Bパッチ→C検証）。全工程なら ./run.sh
# PIPELINE_DEBUG=1 ./step_polish.sh  → first project only
cd "$(dirname "$0")"
source .venv/bin/activate
python -m pipeline.polish
