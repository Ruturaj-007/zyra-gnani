"""Create a Vapi tool from a JSON definition file.

Usage (from the repo root):
    python vapi\\create_tool.py vapi\\submit-answer.tool.json

Reads VAPI_PRIVATE_API_KEY from backend/.env, so the key never appears in commands.
"""
import json
import os
import sys
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv(os.path.join("backend", ".env"))
key = os.getenv("VAPI_PRIVATE_API_KEY", "").strip()
if not key:
    sys.exit("VAPI_PRIVATE_API_KEY is empty. Add it to backend/.env and run from the repo root.")
if len(sys.argv) != 2:
    sys.exit("Usage: python vapi\\create_tool.py <tool-json-file>")

with open(sys.argv[1], "rb") as f:
    payload = f.read()

req = urllib.request.Request(
    "https://api.vapi.ai/tool",
    data=payload,
    method="POST",
    headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "User-Agent": "zyra-setup/1.0",
    },
)

try:
    with urllib.request.urlopen(req, timeout=30) as res:
        body = json.loads(res.read())
        print("OK, status", res.status)
        print("tool id:", body.get("id"))
        print("name:", body.get("name") or body.get("function", {}).get("name"))
except urllib.error.HTTPError as e:
    print("FAILED, status", e.code)
    print(e.read().decode())