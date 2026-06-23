"""Send a test event to the local orchestration API.

Reads JSON payloads from requests/events/ and posts them to POST /events/.
Reads ORCHESTRATION_API_KEY from app/.env (or environment) for auth.

Usage:
    # Send a sample customer_care event (no API key needed for local quick test)
    python requests/send_event.py

    # Send a specific event file
    python requests/send_event.py refund.json

Prerequisites:
    - API running on http://localhost:8080
    - ORCHESTRATION_API_KEY set in app/.env (or exported in the shell)
"""

import json
import os
import sys
from pathlib import Path

import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent
_APP_ENV = _REPO_ROOT / "app" / ".env"

BASE_URL = "http://localhost:8080/events/"
EVENTS_DIR = _REPO_ROOT / "requests" / "events"


def _load_api_key() -> str | None:
    """Read ORCHESTRATION_API_KEY from environment or app/.env."""
    key = os.environ.get("ORCHESTRATION_API_KEY")
    if key:
        return key
    if _APP_ENV.exists():
        for line in _APP_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ORCHESTRATION_API_KEY="):
                value = line.split("=", 1)[1].strip()
                if value:
                    return value
    return None


def load_event(event_file: str) -> dict:
    """Load event data from JSON file in requests/events/."""
    path = EVENTS_DIR / event_file
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def send_event(event_file: str) -> None:
    """Post an event file to the API and print the result."""
    payload = load_event(event_file)
    api_key = _load_api_key()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    response = requests.post(BASE_URL, json=payload, headers=headers)

    print(f"Event file : {event_file}")
    print(f"Status     : {response.status_code}")
    print(f"Response   : {response.text}")

    if response.status_code == 401:
        print("\nHint: set ORCHESTRATION_API_KEY in app/.env or export it in your shell.")
    elif response.status_code != 202:
        print("\nExpected 202 Accepted.")


if __name__ == "__main__":
    file = sys.argv[1] if len(sys.argv) > 1 else "product.json"
    send_event(event_file=file)
