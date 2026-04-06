from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .. import NextDateCalculator, NotionClient, MyPlanNotionReader, MyPlanNotionWriter, load_env_config
from ..google_calendar_client import GoogleCalendarClient, load_google_env_config
from ..services.google_sync_service import TaskGoogleSyncer


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
    print(f"Changed Next Date rows: {changed}")

    syncer = TaskGoogleSyncer(notion_reader, notion_writer, google_client)
    sync_results = syncer.sync_tasks(
        commit=args.commit,
        delete_inactive=args.delete_inactive,
        cleanup_orphans=args.cleanup_orphans,
    )

    sync_path = out_dir / "google_sync_results.json"
    sync_path.write_text(
        json.dumps([item.to_dict() for item in sync_results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for item in sync_results:
        print(f"[{item.action.upper():<20}] {item.title} | {item.reason}")

    print(f"\nGoogle sync results saved to: {sync_path}")
    if not args.commit:
        print("Dry run only. Use --commit to actually write changes.")


if __name__ == "__main__":
    main()
