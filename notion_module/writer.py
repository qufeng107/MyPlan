from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from .client import NotionClient


_UNSET = object()


class MyPlanNotionWriter:
    def __init__(self, client: NotionClient) -> None:
        self.client = client

    @staticmethod
    def _title(value: str) -> dict[str, Any]:
        return {"title": [{"type": "text", "text": {"content": value}}]}

    @staticmethod
    def _rich_text(value: str) -> dict[str, Any]:
        if value:
            return {"rich_text": [{"type": "text", "text": {"content": value}}]}
        return {"rich_text": []}

    @staticmethod
    def _number(value: Optional[float]) -> dict[str, Any]:
        return {"number": value}

    @staticmethod
    def _checkbox(value: bool) -> dict[str, Any]:
        return {"checkbox": value}

    @staticmethod
    def _select(value: Optional[str]) -> dict[str, Any]:
        return {"select": {"name": value} if value else None}

    @staticmethod
    def _status(value: Optional[str]) -> dict[str, Any]:
        return {"status": {"name": value} if value else None}

    @staticmethod
    def _multi_select(values: list[str]) -> dict[str, Any]:
        return {"multi_select": [{"name": x} for x in values]}

    @staticmethod
    def _date(value: Optional[datetime]) -> dict[str, Any]:
        return {"date": {"start": value.isoformat()} if value else None}

    @staticmethod
    def _relation(page_ids: list[str]) -> dict[str, Any]:
        return {"relation": [{"id": x} for x in page_ids]}

    def update_page_properties(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        if not properties:
            raise ValueError("No properties provided for update")
        return self.client.update_page(page_id, properties)

    def update_task_next_date(self, page_id: str, next_date: Optional[datetime]) -> dict[str, Any]:
        return self.update_page_properties(page_id, {"Next Date": self._date(next_date)})

    def update_task_sync_state(
        self,
        page_id: str,
        *,
        sync_to_google: Any = _UNSET,
        google_event_id: Any = _UNSET,
        last_synced_at: Any = _UNSET,
        reminder_min: Any = _UNSET,
    ) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        if sync_to_google is not _UNSET:
            properties["SyncToGoogle"] = self._checkbox(bool(sync_to_google))
        if google_event_id is not _UNSET:
            properties["GoogleEventId"] = self._rich_text(google_event_id or "")
        if last_synced_at is not _UNSET:
            properties["LastSyncedAt"] = self._date(last_synced_at)
        if reminder_min is not _UNSET:
            properties["ReminderMin"] = self._number(reminder_min)
        return self.update_page_properties(page_id, properties)

    def update_task_timezone(self, page_id: str, timezone: Optional[str]) -> dict[str, Any]:
        return self.update_page_properties(page_id, {"Timezone": self._select(timezone)})

    def update_task_status(self, page_id: str, status: str) -> dict[str, Any]:
        return self.update_page_properties(page_id, {"Status": self._status(status)})

    def update_task_record_text(self, page_id: str, text: str) -> dict[str, Any]:
        return self.update_page_properties(page_id, {"Records": self._rich_text(text)})

    def update_task_core_fields(
        self,
        page_id: str,
        *,
        title: Any = _UNSET,
        topic_page_ids: Any = _UNSET,
        description: Any = _UNSET,
        start_date: Any = _UNSET,
        next_date: Any = _UNSET,
        duration_mins: Any = _UNSET,
        repeat_type: Any = _UNSET,
        repeat_values: Any = _UNSET,
        status: Any = _UNSET,
        records: Any = _UNSET,
        timezone: Any = _UNSET,
    ) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        if title is not _UNSET:
            properties["Title"] = self._title(title or "")
        if topic_page_ids is not _UNSET:
            properties["Topic"] = self._relation(topic_page_ids or [])
        if description is not _UNSET:
            properties["Description"] = self._rich_text(description or "")
        if start_date is not _UNSET:
            properties["Start Date"] = self._date(start_date)
        if next_date is not _UNSET:
            properties["Next Date"] = self._date(next_date)
        if duration_mins is not _UNSET:
            properties["Duration (mins)"] = self._number(duration_mins)
        if repeat_type is not _UNSET:
            properties["Repeat Type"] = self._multi_select(repeat_type or [])
        if repeat_values is not _UNSET:
            properties["Repeat"] = self._multi_select(repeat_values or [])
        if status is not _UNSET:
            properties["Status"] = self._status(status)
        if records is not _UNSET:
            properties["Records"] = self._rich_text(records or "")
        if timezone is not _UNSET:
            properties["Timezone"] = self._select(timezone)

        return self.update_page_properties(page_id, properties)

    def update_config_timezone(self, page_id: str, timezone: str) -> dict[str, Any]:
        return self.update_page_properties(page_id, {"Value": self._rich_text(timezone)})
