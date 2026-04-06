from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from . import NextDateCalculator, NotionClient, MyPlanNotionReader, MyPlanNotionWriter, load_env_config


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recalculate Next Date for Notion tasks")
    parser.add_argument("--commit", action="store_true", help="Actually write new Next Date values back to Notion")
    parser.add_argument("--now", help="Override current time, ISO format, e.g. 2026-04-05T21:00:00+01:00")
    parser.add_argument(
        "--holidays-json",
        help="Optional JSON file containing holiday dates as [\"YYYY-MM-DD\", ...] or dict of lists",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    env = load_env_config()
    client = NotionClient(env)
    reader = MyPlanNotionReader(client)
    writer = MyPlanNotionWriter(client)

    snapshot = reader.read_snapshot()
    holiday_dates = set()
    if args.holidays_json:
        holiday_payload = json.loads(Path(args.holidays_json).read_text(encoding="utf-8"))
        if isinstance(holiday_payload, list):
            holiday_dates = {datetime.fromisoformat(f"{item}T00:00:00").date() for item in holiday_payload}
        elif isinstance(holiday_payload, dict):
            for value in holiday_payload.values():
                if isinstance(value, list):
                    for item in value:
                        holiday_dates.add(datetime.fromisoformat(f"{item}T00:00:00").date())

    calc = NextDateCalculator(
        default_timezone=snapshot.default_timezone,
        holiday_dates=holiday_dates,
    )
    now = datetime.fromisoformat(args.now) if args.now else None
    results = calc.compute_snapshot_next_dates(
        snapshot.tasks,
        now=now,
        leave_entries=snapshot.leave,
    )

    out_dir = env.project_root / "notion_debug_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "next_date_results.json"
    out_path.write_text(
        json.dumps([item.to_dict() for item in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    changed = 0
    for item in results:
        old_value = item.old_next_date.isoformat() if item.old_next_date else None
        new_value = item.new_next_date.isoformat() if item.new_next_date else None
        is_changed = old_value != new_value
        if is_changed:
            changed += 1
        prefix = "[CHANGE]" if is_changed else "[KEEP]  "
        print(f"{prefix} {item.title}: {old_value} -> {new_value} | {item.reason}")
        for warning in item.warnings:
            print(f"         warning: {warning}")

    print(f"\nSaved detailed results to: {out_path}")
    print(f"Changed rows: {changed}")

    if args.commit:
        print("\nCommitting changed Next Date values back to Notion...")
        for item in results:
            old_value = item.old_next_date.isoformat() if item.old_next_date else None
            new_value = item.new_next_date.isoformat() if item.new_next_date else None
            if old_value == new_value:
                continue
            writer.update_task_next_date(item.page_id, item.new_next_date)
            print(f"  updated {item.title}")
    else:
        print("\nDry run only. Use --commit to write updates.")


if __name__ == "__main__":
    main()
