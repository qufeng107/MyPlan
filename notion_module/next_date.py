from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable, Optional, Set
from zoneinfo import ZoneInfo

from .models import LeaveEntry, NextDateResult, Task


WEEKDAY_TO_INT = {
    "Mon": 0,
    "Tue": 1,
    "Wed": 2,
    "Thu": 3,
    "Fri": 4,
    "Sat": 5,
    "Sun": 6,
}

ACTIVE_STATUSES = {"Pending", "Ongoing"}
STOPPED_STATUSES = {"Finished", "Cancelled"}


def load_holiday_dates_from_json(path: str | Path) -> Set[date]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    out: Set[date] = set()
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                out.add(date.fromisoformat(item))
    elif isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        out.add(date.fromisoformat(item))
    return out


@dataclass
class LeaveWindow:
    start: datetime
    end: datetime
    title: str


class NextDateCalculator:
    def __init__(
        self,
        *,
        default_timezone: str = "Europe/London",
        holiday_dates: Optional[Iterable[date]] = None,
    ) -> None:
        self.default_timezone = default_timezone
        self.holiday_dates: Set[date] = set(holiday_dates or [])

    def _task_zone(self, task: Task) -> ZoneInfo:
        tz_name = task.timezone or self.default_timezone
        return ZoneInfo(tz_name)

    def _normalize_now(self, now: Optional[datetime], zone: ZoneInfo) -> datetime:
        if now is None:
            return datetime.now(zone)
        if now.tzinfo is None:
            return now.replace(tzinfo=zone)
        return now.astimezone(zone)

    def _task_start_in_zone(self, task: Task, zone: ZoneInfo) -> Optional[datetime]:
        if task.start_date is None:
            return None
        if task.start_date.tzinfo is None:
            return task.start_date.replace(tzinfo=zone)
        return task.start_date.astimezone(zone)

    def _build_leave_windows(self, leave_entries: Iterable[LeaveEntry], zone: ZoneInfo) -> list[LeaveWindow]:
        windows: list[LeaveWindow] = []
        for entry in leave_entries:
            if not entry.affects_scheduling or not entry.start_date:
                continue
            start = entry.start_date.astimezone(zone) if entry.start_date.tzinfo else entry.start_date.replace(tzinfo=zone)
            raw_end = entry.end_date or entry.start_date
            end = raw_end.astimezone(zone) if raw_end.tzinfo else raw_end.replace(tzinfo=zone)
            if end < start:
                end = start
            if entry.end_date and end.time() == time(0, 0):
                end = end + timedelta(days=1) - timedelta(seconds=1)
            windows.append(LeaveWindow(start=start, end=end, title=entry.title))
        return windows

    @staticmethod
    def _same_time(dt: datetime, base: datetime) -> datetime:
        return dt.replace(hour=base.hour, minute=base.minute, second=base.second, microsecond=base.microsecond)

    @staticmethod
    def _last_day_of_month(year: int, month: int) -> int:
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        return (next_month - timedelta(days=1)).day

    def _advance_month(self, current: datetime, anchor_day: int) -> datetime:
        year = current.year
        month = current.month + 1
        if month == 13:
            year += 1
            month = 1
        day = min(anchor_day, self._last_day_of_month(year, month))
        return current.replace(year=year, month=month, day=day)

    def _is_blocked_by_leave(self, candidate: datetime, duration_mins: int, leave_windows: list[LeaveWindow]) -> bool:
        end_candidate = candidate + timedelta(minutes=max(duration_mins, 1))
        for window in leave_windows:
            if candidate <= window.end and end_candidate >= window.start:
                return True
        return False

    def _next_daily(self, start_dt: datetime, now: datetime) -> datetime:
        candidate = start_dt
        while candidate < now:
            candidate = candidate + timedelta(days=1)
        return candidate

    def _next_weekly(self, start_dt: datetime, now: datetime, weekdays: list[int]) -> datetime:
        if not weekdays:
            weekdays = [start_dt.weekday()]
        candidate_date = now.date()
        for offset in range(0, 370):
            d = candidate_date + timedelta(days=offset)
            candidate = datetime.combine(d, start_dt.timetz()).replace(tzinfo=start_dt.tzinfo)
            if d.weekday() in weekdays and candidate >= start_dt and candidate >= now:
                return candidate
        raise RuntimeError("Unable to compute weekly next date within search window")

    def _next_monthly(self, start_dt: datetime, now: datetime) -> datetime:
        anchor_day = start_dt.day
        candidate = start_dt
        while candidate < now:
            candidate = self._advance_month(candidate, anchor_day)
        return candidate

    def _next_holiday(self, start_dt: datetime, now: datetime) -> Optional[datetime]:
        for holiday_date in sorted(self.holiday_dates):
            candidate = datetime.combine(holiday_date, start_dt.timetz()).replace(tzinfo=start_dt.tzinfo)
            if candidate >= start_dt and candidate >= now:
                return candidate
        return None

    def _compute_base_candidate(self, task: Task, now: datetime) -> tuple[Optional[datetime], str, Optional[date]]:
        start_dt = self._task_start_in_zone(task, now.tzinfo)  # type: ignore[arg-type]
        if start_dt is None:
            return None, "missing Start Date", None

        repeat_type = task.repeat_type or "Once"
        if repeat_type == "Once":
            return start_dt, "single occurrence uses Start Date", None
        if repeat_type == "Daily":
            return self._next_daily(start_dt, now), "daily recurrence", None
        if repeat_type == "Weekly":
            weekdays = [WEEKDAY_TO_INT[x] for x in task.repeat_values if x in WEEKDAY_TO_INT]
            return self._next_weekly(start_dt, now, weekdays), "weekly recurrence", None
        if repeat_type == "Weekdays":
            return self._next_weekly(start_dt, now, [0, 1, 2, 3, 4]), "weekday recurrence", None
        if repeat_type == "Monthly":
            return self._next_monthly(start_dt, now), "monthly recurrence", None
        if repeat_type == "Holidays":
            holiday_dt = self._next_holiday(start_dt, now)
            if holiday_dt is None:
                return None, "no upcoming holiday found", None
            return holiday_dt, "holiday recurrence", holiday_dt.date()
        return start_dt, f"unknown repeat type {repeat_type!r}; falling back to Start Date", None

    def compute_task_next_date(
        self,
        task: Task,
        *,
        now: Optional[datetime] = None,
        leave_entries: Optional[Iterable[LeaveEntry]] = None,
        skip_leave_conflicts: bool = True,
    ) -> NextDateResult:
        zone = self._task_zone(task)
        now_dt = self._normalize_now(now, zone)
        leave_windows = self._build_leave_windows(leave_entries or [], zone)
        warnings = list(task.warnings)

        if task.archived or task.in_trash:
            return NextDateResult(
                page_id=task.page_id,
                title=task.title,
                old_next_date=task.next_date,
                new_next_date=None,
                effective_repeat_type=task.repeat_type,
                reason="archived or in trash",
                warnings=warnings,
            )

        if task.status in STOPPED_STATUSES:
            return NextDateResult(
                page_id=task.page_id,
                title=task.title,
                old_next_date=task.next_date,
                new_next_date=None,
                effective_repeat_type=task.repeat_type,
                reason=f"status={task.status} stops scheduling",
                warnings=warnings,
            )

        if task.status not in ACTIVE_STATUSES and task.status is not None:
            warnings.append(f"Unhandled status {task.status!r}; treating as active")

        candidate, reason, holiday_date = self._compute_base_candidate(task, now_dt)
        if candidate is None:
            return NextDateResult(
                page_id=task.page_id,
                title=task.title,
                old_next_date=task.next_date,
                new_next_date=None,
                effective_repeat_type=task.repeat_type,
                reason=reason,
                warnings=warnings,
                used_holiday_date=holiday_date,
            )

        duration_mins = int(task.duration_mins or 0)
        blocked = False
        if skip_leave_conflicts and leave_windows:
            safety = 0
            while self._is_blocked_by_leave(candidate, duration_mins, leave_windows):
                blocked = True
                safety += 1
                if safety > 366:
                    warnings.append("leave conflict search exceeded 366 iterations")
                    break
                temp_task = Task(
                    page_id=task.page_id,
                    title=task.title,
                    start_date=candidate,
                    repeat_type=task.repeat_type,
                    repeat_values=task.repeat_values,
                    timezone=task.timezone,
                    duration_mins=task.duration_mins,
                )
                candidate, _, holiday_date = self._compute_base_candidate(
                    temp_task,
                    candidate + timedelta(seconds=1),
                )
                if candidate is None:
                    break

        return NextDateResult(
            page_id=task.page_id,
            title=task.title,
            old_next_date=task.next_date,
            new_next_date=candidate,
            effective_repeat_type=task.repeat_type,
            reason=reason + ("; advanced past leave conflict" if blocked else ""),
            warnings=warnings,
            blocked_by_leave=blocked,
            used_holiday_date=holiday_date,
        )

    def compute_snapshot_next_dates(
        self,
        tasks: Iterable[Task],
        *,
        now: Optional[datetime] = None,
        leave_entries: Optional[Iterable[LeaveEntry]] = None,
        skip_leave_conflicts: bool = True,
    ) -> list[NextDateResult]:
        return [
            self.compute_task_next_date(
                task,
                now=now,
                leave_entries=leave_entries,
                skip_leave_conflicts=skip_leave_conflicts,
            )
            for task in tasks
        ]
