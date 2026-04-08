from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from googleapiclient.errors import HttpError

from ..google_calendar_client import GoogleCalendarClient
from ..models import Task
from ..reader import MyPlanNotionReader
from ..writer import MyPlanNotionWriter

ACTIVE_STATUSES = {"Pending", "Ongoing"}
DELETE_STATUSES = {"Cancelled"}
KEEP_HISTORY_STATUSES = {"Finished"}
MANAGED_SOURCE = "MyPlan"
SYNC_STRATEGY = "rolling_single_event"
SYNC_HASH_VERSION = "v2"


@dataclass
class SyncResult:
    page_id: str
    title: str
    action: str
    google_event_id: Optional[str] = None
    reason: str = ""
    sync_hash: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskGoogleSyncer:
    def __init__(
        self,
        notion_reader: MyPlanNotionReader,
        notion_writer: MyPlanNotionWriter,
        google_client: GoogleCalendarClient,
    ):
        self.notion_reader = notion_reader
        self.notion_writer = notion_writer
        self.google_client = google_client

    @staticmethod
    def _effective_start(task: Task) -> Optional[datetime]:
        return task.next_date or task.start_date

    @staticmethod
    def _duration_minutes(task: Task) -> int:
        if task.duration_mins is None:
            return 30
        try:
            return max(int(task.duration_mins), 1)
        except Exception:
            return 30

    @staticmethod
    def _build_description(task: Task) -> str:
        parts: list[str] = []
        if task.description:
            parts.append(task.description.strip())
        if task.topic_titles:
            parts.append(f"Topics: {', '.join(task.topic_titles)}")
        if task.url:
            parts.append(f"Notion: {task.url}")
        return "\n\n".join(x for x in parts if x).strip()

    @staticmethod
    def _build_reminders(task: Task) -> dict[str, Any]:
        if task.reminder_min is None:
            return {"useDefault": True}

        try:
            reminder_min = max(int(task.reminder_min), 0)
        except Exception:
            reminder_min = 0

        return {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": reminder_min}],
        }

    def _compute_sync_hash(self, task: Task, start: datetime) -> str:
        payload = {
            "sync_hash_version": SYNC_HASH_VERSION,
            "title": task.title,
            "description": task.description,
            "topic_titles": task.topic_titles,
            "timezone": task.timezone,
            "start": start.isoformat(),
            "duration_mins": task.duration_mins,
            "repeat_type": task.repeat_type,
            "repeat_values": task.repeat_values,
            "status": task.status,
            "reminder_min": task.reminder_min,
            "reminders": self._build_reminders(task),
            "sync_to_google": task.sync_to_google,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _build_event_body(self, task: Task) -> dict[str, Any]:
        start = self._effective_start(task)
        if start is None:
            raise ValueError(f"Task {task.title} has no Start Date / Next Date")

        tz = task.timezone or self.notion_reader.get_default_timezone()
        end = start + timedelta(minutes=self._duration_minutes(task))
        sync_hash = self._compute_sync_hash(task, start)

        body: dict[str, Any] = {
            "summary": task.title,
            "description": self._build_description(task),
            "start": {
                "dateTime": start.isoformat(),
                "timeZone": tz,
            },
            "end": {
                "dateTime": end.isoformat(),
                "timeZone": tz,
            },
            "extendedProperties": {
                "private": {
                    "notion_page_id": task.page_id,
                    "sync_hash": sync_hash,
                    "source": MANAGED_SOURCE,
                    "sync_strategy": SYNC_STRATEGY,
                    "repeat_type": task.repeat_type or "Once",
                }
            },
            "reminders": self._build_reminders(task),
        }
        return body

    @staticmethod
    def _event_private_props(google_event: Optional[dict[str, Any]]) -> dict[str, str]:
        if not google_event:
            return {}
        return dict(
            google_event.get("extendedProperties", {}).get("private", {}) or {}
        )

    def _existing_sync_hash(self, google_event: Optional[dict[str, Any]]) -> Optional[str]:
        return self._event_private_props(google_event).get("sync_hash")

    @classmethod
    def _is_desired_task(cls, task: Task) -> tuple[bool, str]:
        if task.archived or task.in_trash:
            return False, "archived or in trash"
        if not task.sync_to_google:
            return False, "SyncToGoogle is false"
        if task.status in KEEP_HISTORY_STATUSES:
            return False, f"keep history status={task.status}"
        if task.status in DELETE_STATUSES:
            return False, f"delete status={task.status}"
        if task.status not in ACTIVE_STATUSES:
            return False, f"unsupported status={task.status}"
        if cls._effective_start(task) is None:
            return False, "missing Start Date / Next Date"
        return True, "eligible"

    @staticmethod
    def _select_best_existing_event(
        task: Task,
        direct_event: Optional[dict[str, Any]],
        page_events: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        if direct_event:
            return direct_event
        if task.google_event_id:
            for event in page_events:
                if event.get("id") == task.google_event_id:
                    return event
        if page_events:
            page_events = sorted(
                page_events,
                key=lambda x: (
                    x.get("start", {}).get("dateTime") or x.get("start", {}).get("date") or "",
                    x.get("updated") or "",
                ),
            )
            return page_events[0]
        return None

    def _delete_google_event_if_exists(self, event_id: str) -> None:
        try:
            self.google_client.delete_event(event_id)
        except HttpError as exc:
            if exc.resp.status != 404:
                raise

    def sync_tasks(
        self,
        *,
        commit: bool = False,
        delete_inactive: bool = True,
        cleanup_orphans: bool = True,
    ) -> list[SyncResult]:
        snapshot = self.notion_reader.read_snapshot()
        results: list[SyncResult] = []

        managed_events = self.google_client.list_managed_events()
        events_by_id: dict[str, dict[str, Any]] = {
            str(event.get("id")): event
            for event in managed_events
            if event.get("id")
        }
        events_by_page_id: dict[str, list[dict[str, Any]]] = {}
        for event in managed_events:
            page_id = self._event_private_props(event).get("notion_page_id")
            if not page_id:
                continue
            events_by_page_id.setdefault(page_id, []).append(event)

        desired_page_ids: set[str] = set()
        used_event_ids: set[str] = set()
        protected_history_page_ids: set[str] = set()

        for task in snapshot.tasks:
            desired, desired_reason = self._is_desired_task(task)
            direct_event = None
            if task.google_event_id:
                direct_event = events_by_id.get(task.google_event_id)
                if direct_event is None:
                    direct_event = self.google_client.get_event(task.google_event_id)
                    if direct_event and direct_event.get("id"):
                        events_by_id[str(direct_event.get("id"))] = direct_event
                        page_id = self._event_private_props(direct_event).get("notion_page_id")
                        if page_id:
                            events_by_page_id.setdefault(page_id, []).append(direct_event)

            page_events = list(events_by_page_id.get(task.page_id, []))
            existing_event = self._select_best_existing_event(task, direct_event, page_events)

            warnings = list(task.warnings)
            if len(page_events) > 1:
                warnings.append(
                    f"found {len(page_events)} managed Google events for the same Notion task"
                )

            if not desired:
                if desired_reason.startswith("keep history status="):
                    protected_history_page_ids.add(task.page_id)
                    if existing_event:
                        used_event_ids.add(existing_event["id"])
                        if commit and task.google_event_id != existing_event.get("id"):
                            self.notion_writer.update_task_sync_state(
                                task.page_id,
                                google_event_id=existing_event.get("id") or "",
                                last_synced_at=task.last_synced_at,
                            )
                        results.append(
                            SyncResult(
                                page_id=task.page_id,
                                title=task.title,
                                action="keep_history",
                                google_event_id=existing_event.get("id"),
                                reason="finished task kept in Google Calendar as history",
                                warnings=warnings,
                            )
                        )
                    else:
                        results.append(
                            SyncResult(
                                page_id=task.page_id,
                                title=task.title,
                                action="skip",
                                google_event_id=task.google_event_id or None,
                                reason="finished task has no Google event; nothing to preserve",
                                warnings=warnings,
                            )
                        )
                    continue

                if existing_event and (delete_inactive or desired_reason == "SyncToGoogle is false"):
                    if commit:
                        self._delete_google_event_if_exists(existing_event["id"])
                        self.notion_writer.update_task_sync_state(
                            task.page_id,
                            google_event_id="",
                            last_synced_at=datetime.now().astimezone(),
                        )
                    used_event_ids.add(existing_event["id"])
                    results.append(
                        SyncResult(
                            page_id=task.page_id,
                            title=task.title,
                            action="delete" if commit else "would_delete",
                            google_event_id=existing_event.get("id"),
                            reason=desired_reason,
                            warnings=warnings,
                        )
                    )
                elif task.google_event_id and commit:
                    self.notion_writer.update_task_sync_state(
                        task.page_id,
                        google_event_id="",
                        last_synced_at=datetime.now().astimezone(),
                    )
                    results.append(
                        SyncResult(
                            page_id=task.page_id,
                            title=task.title,
                            action="clear_state",
                            google_event_id=task.google_event_id,
                            reason=f"{desired_reason}; stale GoogleEventId cleared",
                            warnings=warnings,
                        )
                    )
                else:
                    results.append(
                        SyncResult(
                            page_id=task.page_id,
                            title=task.title,
                            action="skip",
                            google_event_id=(existing_event or {}).get("id")
                            if existing_event
                            else (task.google_event_id or None),
                            reason=desired_reason,
                            warnings=warnings,
                        )
                    )
                continue

            desired_page_ids.add(task.page_id)
            event_body = self._build_event_body(task)
            new_hash = self._existing_sync_hash(
                {"extendedProperties": event_body.get("extendedProperties", {})}
            )

            if existing_event:
                used_event_ids.add(existing_event["id"])
                old_hash = self._existing_sync_hash(existing_event)
                if old_hash == new_hash:
                    if commit and task.google_event_id != existing_event.get("id"):
                        self.notion_writer.update_task_sync_state(
                            task.page_id,
                            google_event_id=existing_event.get("id") or "",
                            last_synced_at=task.last_synced_at,
                        )
                    results.append(
                        SyncResult(
                            page_id=task.page_id,
                            title=task.title,
                            action="skip",
                            google_event_id=existing_event.get("id"),
                            reason="no effective event changes",
                            sync_hash=new_hash,
                            warnings=warnings,
                        )
                    )
                else:
                    if commit:
                        updated = self.google_client.patch_event(existing_event["id"], event_body)
                        self.notion_writer.update_task_sync_state(
                            task.page_id,
                            google_event_id=updated.get("id") or existing_event["id"],
                            last_synced_at=datetime.now().astimezone(),
                        )
                    results.append(
                        SyncResult(
                            page_id=task.page_id,
                            title=task.title,
                            action="update" if commit else "would_update",
                            google_event_id=existing_event.get("id"),
                            reason="rolling single event updated",
                            sync_hash=new_hash,
                            warnings=warnings,
                        )
                    )
                continue

            if commit:
                created = self.google_client.insert_event(event_body)
                created_id = created.get("id") or ""
                if created_id:
                    used_event_ids.add(created_id)
                self.notion_writer.update_task_sync_state(
                    task.page_id,
                    google_event_id=created_id,
                    last_synced_at=datetime.now().astimezone(),
                )
                results.append(
                    SyncResult(
                        page_id=task.page_id,
                        title=task.title,
                        action="create",
                        google_event_id=created_id,
                        reason="created rolling single event",
                        sync_hash=new_hash,
                        warnings=warnings,
                    )
                )
            else:
                results.append(
                    SyncResult(
                        page_id=task.page_id,
                        title=task.title,
                        action="would_create",
                        reason="would create rolling single event",
                        sync_hash=new_hash,
                        warnings=warnings,
                    )
                )

        if cleanup_orphans:
            for event in managed_events:
                event_id = event.get("id")
                if not event_id or event_id in used_event_ids:
                    continue
                page_id = self._event_private_props(event).get("notion_page_id")
                if page_id in protected_history_page_ids:
                    continue
                if page_id in desired_page_ids:
                    if commit:
                        self._delete_google_event_if_exists(event_id)
                    results.append(
                        SyncResult(
                            page_id=page_id or "",
                            title=event.get("summary") or "",
                            action="delete_duplicate" if commit else "would_delete_duplicate",
                            google_event_id=event_id,
                            reason="duplicate managed Google event for desired task",
                        )
                    )
                    continue

                if commit:
                    self._delete_google_event_if_exists(event_id)
                results.append(
                    SyncResult(
                        page_id=page_id or "",
                        title=event.get("summary") or "",
                        action="delete_orphan" if commit else "would_delete_orphan",
                        google_event_id=event_id,
                        reason="orphan managed Google event not present in desired Notion task set",
                    )
                )

        return results
