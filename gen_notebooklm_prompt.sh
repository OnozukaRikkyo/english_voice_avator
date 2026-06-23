#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
python tools/gen_notebooklm_prompt.py "$@"
