from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parent
TOKEN_FILE = PROJECT_ROOT / "google_token.json"

load_dotenv(PROJECT_ROOT / ".env")


def load_creds() -> Credentials:
    data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    return Credentials(
        token=data["token"],
        refresh_token=data.get("refresh_token"),
        token_uri=data["token_uri"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=data["scopes"],
    )


def main() -> None:
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID")
    if not calendar_id:
        raise RuntimeError("Missing GOOGLE_CALENDAR_ID in .env")

    creds = load_creds()
    service = build("calendar", "v3", credentials=creds)

    event = {
        "summary": "MyPlan test event",
        "description": "Created by MyPlan sync test",
        "start": {
            "dateTime": "2026-04-06T20:00:00+01:00",
            "timeZone": "Europe/London",
        },
        "end": {
            "dateTime": "2026-04-06T20:30:00+01:00",
            "timeZone": "Europe/London",
        },
    }

    created = service.events().insert(calendarId=calendar_id, body=event).execute()
    print("Created event:")
    print("id =", created.get("id"))
    print("htmlLink =", created.get("htmlLink"))


if __name__ == "__main__":
    main()