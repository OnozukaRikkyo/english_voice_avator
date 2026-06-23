#!/bin/bash
# PIPELINE_DEBUG=1 ./run_convert.sh  → first project only
cd "$(dirname "$0")"
source .venv/bin/activate
python -m pipeline.convert
