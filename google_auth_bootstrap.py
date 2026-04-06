from __future__ import annotations

import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

PROJECT_ROOT = Path(__file__).resolve().parent
CLIENT_SECRET_FILE = PROJECT_ROOT / "credentials_google.json"
TOKEN_OUTPUT_FILE = PROJECT_ROOT / "google_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events.owned",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
]

def main() -> None:
    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRET_FILE),
        scopes=SCOPES,
    )
    creds = flow.run_local_server(port=0)

    payload = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or []),
    }

    TOKEN_OUTPUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Saved token to:", TOKEN_OUTPUT_FILE)
    print("refresh_token exists:", bool(creds.refresh_token))
    print("scopes:", creds.scopes)

if __name__ == "__main__":
    main()