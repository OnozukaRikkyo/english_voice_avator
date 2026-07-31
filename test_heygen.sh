#!/bin/bash
# Generate one short test video to verify caption setting.
# Output: /tmp/heygen_test.mp4
cd "$(dirname "$0")"
source .venv/bin/activate
python - <<'EOF'
from pathlib import Path
from pipeline.heygen import generate_video

out = Path("/tmp/heygen_test.mp4")
text = "This is a test video to verify that on-screen captions are disabled. If you can see subtitle text overlaid on the video, captions are still enabled."
print(f"Sending {len(text)} chars to HeyGen...")
generate_video(text, out, title="caption_test")
print(f"Done → {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")
EOF
