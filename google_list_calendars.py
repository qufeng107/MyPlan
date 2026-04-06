from __future__ import annotations

import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parent
TOKEN_FILE = PROJECT_ROOT / "google_token.json"


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
    creds = load_creds()
    service = build("calendar", "v3", credentials=creds)

    result = service.calendarList().list().execute()
    items = result.get("items", [])

    for cal in items:
        print(
            f'{cal.get("summary")} | id={cal.get("id")} | '
            f'primary={cal.get("primary", False)} | accessRole={cal.get("accessRole")}'
        )


if __name__ == "__main__":
    main()