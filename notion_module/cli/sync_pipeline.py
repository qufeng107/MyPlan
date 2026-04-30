from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from .. import NextDateCalculator, NotionClient, MyPlanNotionReader, MyPlanNotionWriter, Task, load_env_config
from ..google_calendar_client import GoogleCalendarClient, load_google_env_config
from ..services.google_sync_service import TaskGoogleSyncer


AUTO_FINISH_SOURCE_STATUSES = {"Pending", "Ongoing"}


def _load_holiday_dates(path: str | None) -> set:
    if not path:
        return set()
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    out = set()
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                out.add(datetime.fromisoformat(f"{item}T00:00:00").date())
    elif isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        out.add(datetime.fromisoformat(f"{item}T00:00:00").date())
    return out


def _task_zone(task: Task, default_timezone: str) -> ZoneInfo:
    return ZoneInfo(task.timezone or default_timezone)


def _normalize_datetime_for_zone(value: Optional[datetime], zone: ZoneInfo) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


def _normalize_now_for_task(now: Optional[datetime], task: Task, default_timezone: str) -> datetime:
    zone = _task_zone(task, default_timezone)
    if now is None:
        return datetime.now(zone)
    if now.tzinfo is None:
        return now.replace(tzinfo=zone)
    return now.astimezone(zone)


def _task_start_date_end_cutoff(task: Task, default_timezone: str) -> Optional[datetime]:
    zone = _task_zone(task, default_timezone)
    end_dt = _normalize_datetime_for_zone(task.start_date_end, zone)
    if end_dt is None:
        return None
    if not task.start_date_end_has_time:
        return end_dt + timedelta(days=1)
    return end_dt


def _format_end_for_log(task: Task, default_timezone: str) -> str:
    zone = _task_zone(task, default_timezone)
    end_dt = _normalize_datetime_for_zone(task.start_date_end, zone)
    if end_dt is None:
        return "None"
    if task.start_date_end_has_time:
        return end_dt.isoformat()
    return end_dt.date().isoformat()


def _auto_finish_tasks_by_start_date_end(
    *,
    tasks: Iterable[Task],
    default_timezone: str,
    notion_writer: MyPlanNotionWriter,
    commit: bool,
    now: Optional[datetime],
) -> int:
    changed = 0
    for task in tasks:
        if task.status not in AUTO_FINISH_SOURCE_STATUSES:
            continue

        cutoff = _task_start_date_end_cutoff(task, default_timezone)
        if cutoff is None:
            continue

        now_dt = _normalize_now_for_task(now, task, default_timezone)
        if now_dt < cutoff:
            continue

        old_status = task.status
        old_next_date = task.next_date
        end_for_log = _format_end_for_log(task, default_timezone)

        if commit:
            try:
                notion_writer.update_task_core_fields(
                    task.page_id,
                    status="Finished",
                    next_date=None,
                )
            except Exception as exc:
                print(
                    f"[AUTO_FINISH_ERROR] {task.title}: failed to update Notion | "
                    f"target=Finished | Start Date end reached ({end_for_log}) | error={exc}"
                )
                task.status = old_status
                task.next_date = old_next_date
                continue

        task.status = "Finished"
        task.next_date = None
        changed += 1

        print(
            f"[AUTO_FINISH] {task.title}: {old_status} -> Finished | "
            f"Start Date end reached ({end_for_log})"
        )
    return changed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MyPlan next-date recalculation and Google sync in one pipeline")
    parser.add_argument("--commit", action="store_true", help="Write changes to Notion and Google Calendar")
    parser.add_argument("--now", help="Override current time, ISO format, e.g. 2026-04-06T05:00:00+01:00")
    parser.add_argument("--holidays-json", help="Optional holiday JSON file")
    parser.add_argument("--delete-inactive", action="store_true", default=True, help="Delete Google events for inactive / unsynced tasks")
    parser.add_argument("--no-delete-inactive", action="store_false", dest="delete_inactive", help="Do not delete inactive / unsynced Google events")
    parser.add_argument("--cleanup-orphans", action="store_true", default=True, help="Delete orphan / duplicate managed Google events")
    parser.add_argument("--no-cleanup-orphans", action="store_false", dest="cleanup_orphans", help="Do not delete orphan / duplicate managed Google events")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    notion_env = load_env_config()
    google_env = load_google_env_config()

    notion_client = NotionClient(notion_env)
    notion_reader = MyPlanNotionReader(notion_client)
    notion_writer = MyPlanNotionWriter(notion_client)
    google_client = GoogleCalendarClient(google_env)

    snapshot = notion_reader.read_snapshot()
    holiday_dates = _load_holiday_dates(args.holidays_json)
    calc = NextDateCalculator(
        default_timezone=snapshot.default_timezone,
        holiday_dates=holiday_dates,
    )
    now = datetime.fromisoformat(args.now) if args.now else None

    auto_finished_count = _auto_finish_tasks_by_start_date_end(
        tasks=snapshot.tasks,
        default_timezone=snapshot.default_timezone,
        notion_writer=notion_writer,
        commit=args.commit,
        now=now,
    )

    next_date_results = calc.compute_snapshot_next_dates(
        snapshot.tasks,
        now=now,
        leave_entries=snapshot.leave,
    )

    out_dir = notion_env.project_root / "notion_debug_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    next_date_path = out_dir / "next_date_results.json"
    next_date_path.write_text(
        json.dumps([item.to_dict() for item in next_date_results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    changed = 0
    for item in next_date_results:
        old_value = item.old_next_date.isoformat() if item.old_next_date else None
        new_value = item.new_next_date.isoformat() if item.new_next_date else None
        is_changed = old_value != new_value
        if is_changed:
            changed += 1
        prefix = "[CHANGE]" if is_changed else "[KEEP]  "
        print(f"{prefix} next-date | {item.title}: {old_value} -> {new_value} | {item.reason}")
        if args.commit and is_changed:
            notion_writer.update_task_next_date(item.page_id, item.new_next_date)

    print(f"\nNext-date results saved to: {next_date_path}")
    print(f"Auto-finished rows by Start Date end: {auto_finished_count}")
    print(f"Changed Next Date rows: {changed}")

    syncer = TaskGoogleSyncer(notion_reader, notion_writer, google_client)
    google_results = syncer.sync_tasks(
        commit=args.commit,
        delete_inactive=args.delete_inactive,
        cleanup_orphans=args.cleanup_orphans,
    )

    google_sync_path = out_dir / "google_sync_results.json"
    google_sync_path.write_text(
        json.dumps([item.to_dict() for item in google_results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nGoogle sync results saved to: {google_sync_path}")
    for item in google_results:
        print(f"[{item.action.upper():<20}] {item.title} | {item.reason}")

    if not args.commit:
        print("\nDry run only. Use --commit to actually sync.")


if __name__ == "__main__":
    main()
