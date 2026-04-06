from __future__ import annotations

import json

from . import NotionClient, MyPlanNotionReader, load_env_config


def main() -> None:
    env = load_env_config()
    client = NotionClient(env)
    reader = MyPlanNotionReader(client)
    snapshot = reader.read_snapshot()

    out_dir = env.project_root / "notion_debug_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "my_plan_snapshot.json"
    out_path.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("Default timezone:", snapshot.default_timezone)
    print("Topics:", [x.title for x in snapshot.topics])
    print("Task count:", len(snapshot.tasks))
    print("Leave count:", len(snapshot.leave))
    print("Saved snapshot to:", out_path)

    print("\nTask preview:")
    for task in snapshot.tasks[:5]:
        print(
            json.dumps(
                {
                    "title": task.title,
                    "topic_titles": task.topic_titles,
                    "repeat_type": task.repeat_type,
                    "repeat_values": task.repeat_values,
                    "status": task.status,
                    "start_date": task.start_date.isoformat() if task.start_date else None,
                    "next_date": task.next_date.isoformat() if task.next_date else None,
                    "timezone": task.timezone,
                    "warnings": task.warnings,
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
