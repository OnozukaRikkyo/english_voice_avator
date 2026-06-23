#!/usr/bin/env python3
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY  = os.environ["HEYGEN_API_KEY"]
GROUP_ID = os.environ.get("HEYGEN_GROUP_ID", "c2bd6be301484056bd9274e6a905c816")

resp = requests.post(
    f"https://api.heygen.com/v3/avatars/{GROUP_ID}/consent",
    headers={"X-Api-Key": API_KEY, "Content-Type": "application/json"},
    json={},
    timeout=30,
)
print(f"HTTP {resp.status_code}")
print(resp.text)

if resp.ok:
    consent_url = resp.json().get("data", {}).get("consent_url")
    if consent_url:
        print(f"\nconsent_url: {consent_url}")
else:
    sys.exit(1)