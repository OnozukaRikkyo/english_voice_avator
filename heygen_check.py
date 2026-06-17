#!/usr/bin/env python3
"""HeyGen API utility — check avatars, voices, account, and configured IDs.

Usage:
  python heygen_check.py             # Check configured IDs (default)
  python heygen_check.py avatars     # List all avatars
  python heygen_check.py voices      # List English voices
  python heygen_check.py account     # Account / credit info
  python heygen_check.py all         # Run all checks
"""
import json
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

from pipeline.config import HEYGEN_API_KEY, HEYGEN_BASE_URL, HEYGEN_AVATAR_ID, HEYGEN_VOICE_ID

HEADERS = {
    "X-Api-Key": HEYGEN_API_KEY,
    "Accept": "application/json",
}


def _get(path: str, params: dict | None = None) -> dict:
    resp = requests.get(f"{HEYGEN_BASE_URL}{path}", headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def check_configured() -> None:
    """Verify that the avatar/voice IDs set in .env are valid."""
    print("\n=== Configured IDs (.env) ===")
    print(f"  HEYGEN_AVATAR_ID : {HEYGEN_AVATAR_ID or '(not set)'}")
    print(f"  HEYGEN_VOICE_ID  : {HEYGEN_VOICE_ID or '(not set)'}")

    # Avatar
    if HEYGEN_AVATAR_ID:
        data = _get("/v2/avatars")
        avatars = data.get("data", {}).get("avatars", [])
        match = next((a for a in avatars if a.get("avatar_id") == HEYGEN_AVATAR_ID), None)
        if match:
            print(f"  ✓ Avatar found : {match.get('avatar_name')} (gender={match.get('gender', '-')})")
        else:
            print(f"  ? Avatar not in public list (may be a custom/personal avatar)")

    # Voice
    if HEYGEN_VOICE_ID:
        data = _get("/v2/voices")
        voices = data.get("data", {}).get("voices", [])
        match = next((v for v in voices if v.get("voice_id") == HEYGEN_VOICE_ID), None)
        if match:
            name = match.get("display_name") or match.get("name") or match.get("voice_id")
            print(f"  ✓ Voice found  : {name} (lang={match.get('language', '-')}, gender={match.get('gender', '-')})")
        else:
            print(f"  ✗ Voice ID not found in voice list")


def check_avatars() -> None:
    print("\n=== Avatars ===")
    data = _get("/v2/avatars")
    avatars = data.get("data", {}).get("avatars", [])
    print(f"Total: {len(avatars)}")
    for a in avatars:
        print(f"  id={a.get('avatar_id')}  name={a.get('avatar_name')}  gender={a.get('gender', '-')}")


def check_voices(lang_filter: str = "en") -> None:
    print(f"\n=== Voices (filter: '{lang_filter}') ===")
    data = _get("/v2/voices")
    voices = data.get("data", {}).get("voices", [])
    print(f"Total: {len(voices)}")
    for v in voices:
        lang = v.get("language", "")
        if lang_filter.lower() in lang.lower():
            name = v.get("display_name") or v.get("name") or "-"
            print(f"  id={v.get('voice_id')}  name={name}  lang={lang}  gender={v.get('gender', '-')}")


def check_account() -> None:
    print("\n=== Account ===")
    # Try v2 credits endpoint
    for path in ("/v2/user/credits", "/v2/user/quota", "/v1/user.info"):
        try:
            data = _get(path)
            print(f"  Endpoint: {path}")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return
        except requests.HTTPError as e:
            print(f"  {path} → {e.response.status_code}")
    print("  Could not retrieve account info (all endpoints returned errors)")


def main() -> None:
    if not HEYGEN_API_KEY:
        print("ERROR: HEYGEN_API_KEY is not set in .env")
        sys.exit(1)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "configured"

    if cmd in ("configured", "all"):
        check_configured()
    if cmd in ("avatars", "all"):
        check_avatars()
    if cmd in ("voices", "all"):
        check_voices()
    if cmd in ("account", "all"):
        check_account()


if __name__ == "__main__":
    main()
