from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from .client import NotionClient
from .models import ConfigEntry, LeaveEntry, MyPlanSnapshot, Task, Topic


WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class MyPlanNotionReader:
    def __init__(self, client: NotionClient, fallback_timezone: str = "Europe/London") -> None:
        self.client = client
        self.fallback_timezone = fallback_timezone

    @staticmethod
    def _parse_datetime(value: Optional[dict[str, Any]]) -> Optional[datetime]:
        if not value:
            return None
        start = value.get("start")
        if not start:
            return None
        return datetime.fromisoformat(start)

    @staticmethod
    def _parse_date_part(value: Optional[dict[str, Any]], key: str) -> Optional[datetime]:
        if not value:
            return None
        raw_value = value.get(key)
        if not raw_value:
            return None
        return datetime.fromisoformat(raw_value)

    @staticmethod
    def _date_part_has_explicit_time(value: Optional[dict[str, Any]], key: str) -> bool:
        if not value:
            return False
        raw_value = value.get(key)
        if not isinstance(raw_value, str):
            return False
        return "T" in raw_value

    @staticmethod
    def _parse_property(prop: dict[str, Any]) -> Any:
        prop_type = prop.get("type")

        if prop_type == "title":
            return "".join(x.get("plain_text", "") for x in prop.get("title", []))
        if prop_type == "rich_text":
            return "".join(x.get("plain_text", "") for x in prop.get("rich_text", []))
        if prop_type == "number":
            return prop.get("number")
        if prop_type == "checkbox":
            return prop.get("checkbox")
        if prop_type == "select":
            obj = prop.get("select")
            return obj.get("name") if obj else None
        if prop_type == "status":
            obj = prop.get("status")
            return obj.get("name") if obj else None
        if prop_type == "multi_select":
            return [x.get("name") for x in prop.get("multi_select", [])]
        if prop_type == "date":
            return prop.get("date")
        if prop_type == "relation":
            return [x.get("id") for x in prop.get("relation", [])]
        if prop_type == "url":
            return prop.get("url")
        if prop_type == "email":
            return prop.get("email")
        if prop_type == "phone_number":
            return prop.get("phone_number")
        return prop.get(prop_type)

    def _simplify_page(self, page: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {
            "page_id": page.get("id"),
            "url": page.get("url"),
            "archived": page.get("archived", False),
            "in_trash": page.get("in_trash", False),
        }
        props = page.get("properties", {})
        for name, prop in props.items():
            out[name] = self._parse_property(prop)
        return out

    def read_config_entries(self) -> list[ConfigEntry]:
        rows = self.client.query_all_rows(self.client.env.config_data_source_id)
        entries: list[ConfigEntry] = []
        for row in rows:
            data = self._simplify_page(row)
            entries.append(
                ConfigEntry(
                    page_id=data["page_id"],
                    key=str(data.get("Key") or ""),
                    value=str(data.get("Value") or ""),
                    url=data.get("url"),
                )
            )
        return entries

    def read_topics(self) -> list[Topic]:
        rows = self.client.query_all_rows(self.client.env.topics_data_source_id)
        topics: list[Topic] = []
        for row in rows:
            data = self._simplify_page(row)
            topics.append(
                Topic(
                    page_id=data["page_id"],
                    title=str(data.get("Title") or ""),
                    url=data.get("url"),
                )
            )
        return topics

    def read_leave(self) -> list[LeaveEntry]:
        rows = self.client.query_all_rows(self.client.env.leave_data_source_id)
        leave_rows: list[LeaveEntry] = []
        for row in rows:
            data = self._simplify_page(row)
            leave_rows.append(
                LeaveEntry(
                    page_id=data["page_id"],
                    title=str(data.get("Title") or ""),
                    start_date=self._parse_datetime(data.get("Start Date")),
                    end_date=self._parse_datetime(data.get("End Date")),
                    leave_type=data.get("Type"),
                    affects_scheduling=bool(data.get("AffectsScheduling", False)),
                    notes=str(data.get("Notes") or ""),
                    url=data.get("url"),
                )
            )
        return leave_rows

    def read_tasks(self) -> list[Task]:
        rows = self.client.query_all_rows(self.client.env.tasks_data_source_id)
        topic_map = {t.page_id: t.title for t in self.read_topics()}

        tasks: list[Task] = []
        for row in rows:
            data = self._simplify_page(row)
            topic_ids = list(data.get("Topic") or [])
            repeat_type_raw = list(data.get("Repeat Type") or [])
            warnings: list[str] = []

            repeat_type: Optional[str] = None
            if len(repeat_type_raw) > 1:
                warnings.append(
                    f"Repeat Type has multiple values: {repeat_type_raw}. Only the first value will be used."
                )
            if repeat_type_raw:
                repeat_type = repeat_type_raw[0]

            repeat_values = list(data.get("Repeat") or [])
            ordered_repeat_values = sorted(
                repeat_values,
                key=lambda x: WEEKDAY_ORDER.index(x) if x in WEEKDAY_ORDER else 999,
            )

            start_date_value = data.get("Start Date")
            task = Task(
                page_id=data["page_id"],
                title=str(data.get("Title") or ""),
                topic_ids=topic_ids,
                topic_titles=[topic_map[x] for x in topic_ids if x in topic_map],
                description=str(data.get("Description") or ""),
                records=str(data.get("Records") or ""),
                google_event_id=str(data.get("GoogleEventId") or ""),
                status=data.get("Status"),
                reminder_min=data.get("ReminderMin"),
                start_date=self._parse_datetime(start_date_value),
                start_date_end=self._parse_date_part(start_date_value, "end"),
                start_date_end_has_time=self._date_part_has_explicit_time(start_date_value, "end"),
                next_date=self._parse_datetime(data.get("Next Date")),
                last_synced_at=self._parse_datetime(data.get("LastSyncedAt")),
                timezone=data.get("Timezone") or None,
                sync_to_google=bool(data.get("SyncToGoogle", False)),
                repeat_type=repeat_type,
                repeat_type_raw=repeat_type_raw,
                repeat_values=ordered_repeat_values,
                duration_mins=data.get("Duration (mins)"),
                archived=bool(data.get("archived", False)),
                in_trash=bool(data.get("in_trash", False)),
                url=data.get("url"),
                warnings=warnings,
            )
            tasks.append(task)
        return tasks

    def get_default_timezone(self) -> str:
        config_entries = self.read_config_entries()
        for entry in config_entries:
            if entry.key.strip().lower() == "timezone" and entry.value.strip():
                return entry.value.strip()
        return self.fallback_timezone

    def read_snapshot(self) -> MyPlanSnapshot:
        config_entries = self.read_config_entries()
        topics = self.read_topics()
        tasks = self.read_tasks()
        leave_entries = self.read_leave()
        default_timezone = self.fallback_timezone
        for entry in config_entries:
            if entry.key.strip().lower() == "timezone" and entry.value.strip():
                default_timezone = entry.value.strip()
                break
        return MyPlanSnapshot(
            default_timezone=default_timezone,
            config=config_entries,
            topics=topics,
            tasks=tasks,
            leave=leave_entries,
        )
