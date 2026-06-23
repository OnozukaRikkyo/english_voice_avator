#!/bin/bash
# PIPELINE_DEBUG=1 ./run_heygen.sh  → first project, 1 newly generated part only
cd "$(dirname "$0")"
source .venv/bin/activate
python -m pipeline.heygen
