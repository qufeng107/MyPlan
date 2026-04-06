from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


@dataclass(frozen=True)
class GoogleCalendarEnvConfig:
    calendar_id: str
    project_root: Path
    token_file: Path



def _load_local_env() -> Optional[Path]:
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for path in candidates:
        if path.exists():
            load_dotenv(path)
            return path
    return None



def load_google_env_config() -> GoogleCalendarEnvConfig:
    env_path = _load_local_env()
    project_root = env_path.parent if env_path else Path.cwd()
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID")
    if not calendar_id:
        raise RuntimeError("Missing GOOGLE_CALENDAR_ID in .env or environment variables")

    token_file = project_root / "google_token.json"
    token_json = os.getenv("GOOGLE_TOKEN_JSON")
    if token_json and not token_file.exists():
        token_file.write_text(token_json, encoding="utf-8")

    if not token_file.exists():
        raise RuntimeError(
            f"Missing token file: {token_file}. Provide google_token.json or GOOGLE_TOKEN_JSON"
        )
    return GoogleCalendarEnvConfig(
        calendar_id=calendar_id,
        project_root=project_root,
        token_file=token_file,
    )


class GoogleCalendarClient:
    def __init__(self, env: GoogleCalendarEnvConfig) -> None:
        self.env = env
        self._creds: Optional[Credentials] = None
        self._service = None

    def _load_creds(self) -> Credentials:
        data = json.loads(self.env.token_file.read_text(encoding="utf-8"))
        creds = Credentials(
            token=data["token"],
            refresh_token=data.get("refresh_token"),
            token_uri=data["token_uri"],
            client_id=data["client_id"],
            client_secret=data["client_secret"],
            scopes=data["scopes"],
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self._save_creds(creds)
        return creds

    def _save_creds(self, creds: Credentials) -> None:
        payload = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes or []),
        }
        self.env.token_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @property
    def creds(self) -> Credentials:
        if self._creds is None:
            self._creds = self._load_creds()
        return self._creds

    @property
    def service(self):
        if self._service is None:
            self._service = build("calendar", "v3", credentials=self.creds)
        return self._service

    def get_event(self, event_id: str) -> Optional[dict[str, Any]]:
        try:
            return self.service.events().get(calendarId=self.env.calendar_id, eventId=event_id).execute()
        except HttpError as exc:
            if exc.resp.status == 404:
                return None
            raise

    def list_events(
        self,
        *,
        private_extended_properties: Optional[list[str]] = None,
        show_deleted: bool = False,
        single_events: bool = True,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        page_token: Optional[str] = None
        items: list[dict[str, Any]] = []

        while True:
            request = self.service.events().list(
                calendarId=self.env.calendar_id,
                privateExtendedProperty=private_extended_properties,
                showDeleted=show_deleted,
                singleEvents=single_events,
                timeMin=time_min,
                timeMax=time_max,
                pageToken=page_token,
                maxResults=2500,
            )
            payload = request.execute()
            items.extend(payload.get("items", []))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return items

    def list_managed_events(self) -> list[dict[str, Any]]:
        return self.list_events(private_extended_properties=["source=MyPlan"])

    def insert_event(self, event_body: dict[str, Any]) -> dict[str, Any]:
        return (
            self.service.events()
            .insert(calendarId=self.env.calendar_id, body=event_body, sendUpdates="none")
            .execute()
        )

    def patch_event(self, event_id: str, event_body: dict[str, Any]) -> dict[str, Any]:
        return (
            self.service.events()
            .patch(calendarId=self.env.calendar_id, eventId=event_id, body=event_body, sendUpdates="none")
            .execute()
        )

    def delete_event(self, event_id: str) -> None:
        self.service.events().delete(calendarId=self.env.calendar_id, eventId=event_id, sendUpdates="none").execute()
