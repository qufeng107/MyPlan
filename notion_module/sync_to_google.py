from __future__ import annotations

import argparse
import json

from . import MyPlanNotionReader, MyPlanNotionWriter, NotionClient, load_env_config
from .cli.sync_pipeline import _auto_finish_tasks_by_start_date_end
from .google_calendar_client import GoogleCalendarClient, load_google_env_config
from .services.google_sync_service import TaskGoogleSyncer


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Notion Tasks to Google Calendar")
    parser.add_argument("--commit", action="store_true", help="Write changes to Google Calendar and Notion")
    parser.add_argument("--delete-inactive", action="store_true", default=True, help="Delete Google events for inactive or unsynced tasks")
    parser.add_argument("--no-delete-inactive", action="store_false", dest="delete_inactive", help="Do not delete Google events for inactive or unsynced tasks")
    parser.add_argument("--cleanup-orphans", action="store_true", default=True, help="Delete orphan or duplicate managed Google events")
    parser.add_argument("--no-cleanup-orphans", action="store_false", dest="cleanup_orphans", help="Do not delete orphan or duplicate managed Google events")
    args = parser.parse_args()

    notion_env = load_env_config()
    google_env = load_google_env_config()

    notion_client = NotionClient(notion_env)
    notion_reader = MyPlanNotionReader(notion_client)
    notion_writer = MyPlanNotionWriter(notion_client)
    google_client = GoogleCalendarClient(google_env)

    snapshot = notion_reader.read_snapshot()
    auto_finished_count = _auto_finish_tasks_by_start_date_end(
        tasks=snapshot.tasks,
        default_timezone=snapshot.default_timezone,
        notion_writer=notion_writer,
        commit=args.commit,
        now=None,
    )
    print(f"Auto-finished rows by Start Date end: {auto_finished_count}")

    syncer = TaskGoogleSyncer(notion_reader, notion_writer, google_client)
    results = syncer.sync_tasks(
        commit=args.commit,
        delete_inactive=args.delete_inactive,
        cleanup_orphans=args.cleanup_orphans,
    )

    output_dir = notion_env.project_root / "notion_debug_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "google_sync_results.json"
    output_path.write_text(
        json.dumps([x.to_dict() for x in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for item in results:
        print(f"[{item.action.upper():<20}] {item.title} | {item.reason}")

    print(f"\nSaved results to: {output_path}")
    if not args.commit:
        print("Dry run only. Use --commit to actually sync.")


if __name__ == "__main__":
    main()
