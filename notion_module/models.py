from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Optional


@dataclass
class ConfigEntry:
    page_id: str
    key: str
    value: str
    url: Optional[str] = None


@dataclass
class Topic:
    page_id: str
    title: str
    url: Optional[str] = None


@dataclass
class Task:
    page_id: str
    title: str
    topic_ids: list[str] = field(default_factory=list)
    topic_titles: list[str] = field(default_factory=list)
    description: str = ""
    records: str = ""
    google_event_id: str = ""
    status: Optional[str] = None
    reminder_min: Optional[float] = None
    start_date: Optional[datetime] = None
    next_date: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    timezone: Optional[str] = None
    sync_to_google: bool = False
    repeat_type: Optional[str] = None
    repeat_type_raw: list[str] = field(default_factory=list)
    repeat_values: list[str] = field(default_factory=list)
    duration_mins: Optional[float] = None
    archived: bool = False
    in_trash: bool = False
    url: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LeaveEntry:
    page_id: str
    title: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    leave_type: Optional[str] = None
    affects_scheduling: bool = False
    notes: str = ""
    url: Optional[str] = None


@dataclass
class MyPlanSnapshot:
    default_timezone: str
    config: list[ConfigEntry]
    topics: list[Topic]
    tasks: list[Task]
    leave: list[LeaveEntry]

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_timezone": self.default_timezone,
            "config": [asdict(x) for x in self.config],
            "topics": [asdict(x) for x in self.topics],
            "tasks": [x.to_dict() for x in self.tasks],
            "leave": [asdict(x) for x in self.leave],
        }


@dataclass
class NextDateResult:
    page_id: str
    title: str
    old_next_date: Optional[datetime]
    new_next_date: Optional[datetime]
    effective_repeat_type: Optional[str]
    reason: str
    warnings: list[str] = field(default_factory=list)
    blocked_by_leave: bool = False
    blocked_by_holiday: bool = False
    used_holiday_date: Optional[date] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_id": self.page_id,
            "title": self.title,
            "old_next_date": self.old_next_date.isoformat() if self.old_next_date else None,
            "new_next_date": self.new_next_date.isoformat() if self.new_next_date else None,
            "effective_repeat_type": self.effective_repeat_type,
            "reason": self.reason,
            "warnings": list(self.warnings),
            "blocked_by_leave": self.blocked_by_leave,
            "blocked_by_holiday": self.blocked_by_holiday,
            "used_holiday_date": self.used_holiday_date.isoformat() if self.used_holiday_date else None,
        }
