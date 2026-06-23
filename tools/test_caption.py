#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY   = os.environ["HEYGEN_API_KEY"]
AVATAR_ID = os.environ["HEYGEN_AVATAR_ID"]
VOICE_ID  = os.environ["HEYGEN_VOICE_ID"]
BASE_URL  = "https://api.heygen.com"
HEADERS   = {"X-Api-Key": API_KEY, "Content-Type": "application/json"}
OUTPUT    = Path(__file__).parent.parent / "data" / "caption_test" / "heygen_caption_test.mp4"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
TEXT      = "Hello and welcome. This is a short test video to check whether captions appear on screen."

# payload = {
#     "title": "caption_test",
#     "video_inputs": [{
#         "character": {"type": "avatar", "avatar_id": AVATAR_ID, "avatar_style": "normal"},
#         "voice": {"type": "text", "voice_id": VOICE_ID, "input_text": TEXT},
#     }],
#     "aspect_ratio": "16:9"
# }
# ▼ ここが V3 用の正しいペイロード（入れ子をなくし、シンプルになっています）
payload = {
    "type": "avatar",
    "avatar_id": AVATAR_ID,
    "script": TEXT,
    "voice_id": VOICE_ID,
    "aspect_ratio": "16:9"
    # caption 関連のパラメータは「何も書かない」のがV3の焼き付けオフの正解です
}
# resp = requests.post(f"{BASE_URL}/v2/video/generate", headers=HEADERS, json=payload, timeout=60)
resp = requests.post(f"{BASE_URL}/v3/videos", headers=HEADERS, json=payload, timeout=60)
print(f"HTTP {resp.status_code}: {resp.text}")
resp.raise_for_status()

video_id = resp.json()["data"]["video_id"]
print(f"\npolling {video_id} ...")

while True:
    r = requests.get(f"{BASE_URL}/v1/video_status.get",
                     headers={"X-Api-Key": API_KEY}, params={"video_id": video_id}, timeout=30)
    data = r.json()["data"]
    print(f"  {data['status']}")
    if data["status"] == "completed":
        print(json.dumps(data, indent=2))
        with open(OUTPUT, "wb") as f:
            for chunk in requests.get(data["video_url"], stream=True, timeout=300).iter_content(1 << 20):
                f.write(chunk)
        print(f"saved → {OUTPUT}")
        break
    if data["status"] == "failed":
        print(data.get("error")); sys.exit(1)
    time.sleep(1)
