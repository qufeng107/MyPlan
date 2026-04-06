from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
LOCAL_ENV_PATH = PROJECT_ROOT / ".env"

# 本地调试时：优先从项目根目录 .env 读取。
# GitHub Actions 时：通常不会有 .env，直接读取 workflow 注入的环境变量 / secrets。
if LOCAL_ENV_PATH.exists():
    load_dotenv(dotenv_path=LOCAL_ENV_PATH, override=False)
else:
    load_dotenv(override=False)

BASE_URL = "https://api.notion.com/v1"
DEFAULT_NOTION_VERSION = os.getenv("NOTION_VERSION", "2025-09-03")


def _build_output_dir() -> Path:
    raw = os.getenv("NOTION_DEBUG_OUTPUT_DIR", "notion_debug_output")
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


OUTPUT_DIR = _build_output_dir()

ENV_TARGETS: List[Tuple[str, str]] = [
    ("CONFIG", "NOTION_CONFIG_DATA_SOURCE_ID"),
    ("TOPICS", "NOTION_TOPICS_DATA_SOURCE_ID"),
    ("TASKS", "NOTION_TASKS_DATA_SOURCE_ID"),
    ("LEAVE", "NOTION_LEAVE_DATA_SOURCE_ID"),
]


class NotionConfigError(RuntimeError):
    pass


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise NotionConfigError(
            f"Missing required environment variable: {name}\n"
            f"- Local run: create {LOCAL_ENV_PATH}\n"
            f"- GitHub Actions: add the same name to repository secrets and map it into env"
        )
    return value


NOTION_TOKEN = require_env("NOTION_TOKEN")


def notion_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": DEFAULT_NOTION_VERSION,
        "Content-Type": "application/json",
    }


def notion_get(path: str) -> Dict[str, Any]:
    url = f"{BASE_URL}{path}"
    resp = requests.get(url, headers=notion_headers(), timeout=30)
    _raise_helpful(resp)
    return resp.json()


def notion_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{BASE_URL}{path}"
    resp = requests.post(url, headers=notion_headers(), json=payload, timeout=30)
    _raise_helpful(resp)
    return resp.json()


def _raise_helpful(resp: requests.Response) -> None:
    if resp.ok:
        return

    try:
        detail = json.dumps(resp.json(), ensure_ascii=False, indent=2)
    except Exception:
        detail = resp.text

    hint = ""
    if resp.status_code == 404:
        hint = (
            "\nHint: check the data source ID, Notion-Version, and whether the integration "
            "has been added to this page/data source."
        )
    elif resp.status_code == 401:
        hint = "\nHint: check NOTION_TOKEN."
    elif resp.status_code == 429:
        hint = "\nHint: rate limited by Notion; wait a moment and retry."

    raise RuntimeError(
        f"Notion API request failed: {resp.status_code} {resp.reason}\n{detail}{hint}"
    )


def retrieve_data_source(data_source_id: str) -> Dict[str, Any]:
    return notion_get(f"/data_sources/{data_source_id}")


def query_data_source(
    data_source_id: str,
    *,
    page_size: int = 100,
    start_cursor: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"page_size": page_size}
    if start_cursor:
        payload["start_cursor"] = start_cursor
    return notion_post(f"/data_sources/{data_source_id}/query", payload)


def query_all_rows(data_source_id: str, *, page_size: int = 100) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start_cursor: Optional[str] = None

    while True:
        data = query_data_source(data_source_id, page_size=page_size, start_cursor=start_cursor)
        rows.extend(data.get("results", []))

        if not data.get("has_more"):
            break
        start_cursor = data.get("next_cursor")
        if not start_cursor:
            break

    return rows


def parse_rich_text(items: List[Dict[str, Any]]) -> str:
    return "".join(item.get("plain_text", "") for item in items)


def parse_property_value(prop: Dict[str, Any]) -> Any:
    prop_type = prop.get("type")

    if prop_type == "title":
        return parse_rich_text(prop.get("title", []))
    if prop_type == "rich_text":
        return parse_rich_text(prop.get("rich_text", []))
    if prop_type == "number":
        return prop.get("number")
    if prop_type == "checkbox":
        return prop.get("checkbox")
    if prop_type == "select":
        obj = prop.get("select")
        return obj.get("name") if obj else None
    if prop_type == "multi_select":
        return [item.get("name") for item in prop.get("multi_select", [])]
    if prop_type == "status":
        obj = prop.get("status")
        return obj.get("name") if obj else None
    if prop_type == "date":
        obj = prop.get("date")
        if not obj:
            return None
        return {
            "start": obj.get("start"),
            "end": obj.get("end"),
            "time_zone": obj.get("time_zone"),
        }
    if prop_type == "relation":
        return [item.get("id") for item in prop.get("relation", [])]
    if prop_type == "url":
        return prop.get("url")
    if prop_type == "email":
        return prop.get("email")
    if prop_type == "phone_number":
        return prop.get("phone_number")
    if prop_type == "people":
        return [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "type": item.get("type"),
            }
            for item in prop.get("people", [])
        ]
    if prop_type == "files":
        return [item.get("name") for item in prop.get("files", [])]
    if prop_type == "created_time":
        return prop.get("created_time")
    if prop_type == "last_edited_time":
        return prop.get("last_edited_time")
    if prop_type == "created_by":
        obj = prop.get("created_by") or {}
        return {"id": obj.get("id"), "name": obj.get("name")}
    if prop_type == "last_edited_by":
        obj = prop.get("last_edited_by") or {}
        return {"id": obj.get("id"), "name": obj.get("name")}
    if prop_type == "formula":
        formula = prop.get("formula") or {}
        formula_type = formula.get("type")
        return formula.get(formula_type)
    if prop_type == "rollup":
        rollup = prop.get("rollup") or {}
        rollup_type = rollup.get("type")
        return rollup.get(rollup_type)
    if prop_type == "unique_id":
        obj = prop.get("unique_id") or {}
        return {"prefix": obj.get("prefix"), "number": obj.get("number")}

    return prop.get(prop_type)


def simplify_page(page: Dict[str, Any]) -> Dict[str, Any]:
    properties = page.get("properties", {})
    simplified: Dict[str, Any] = {
        "page_id": page.get("id"),
        "url": page.get("url"),
        "archived": page.get("archived"),
        "in_trash": page.get("in_trash"),
    }

    for prop_name, prop_value in properties.items():
        simplified[prop_name] = parse_property_value(prop_value)

    return simplified


def schema_summary(data_source: Dict[str, Any]) -> Dict[str, Any]:
    properties = data_source.get("properties", {})
    summary: Dict[str, Any] = {}

    for name, prop in properties.items():
        item: Dict[str, Any] = {"type": prop.get("type")}

        if prop.get("type") == "select":
            item["options"] = [opt.get("name") for opt in prop.get("select", {}).get("options", [])]
        elif prop.get("type") == "multi_select":
            item["options"] = [opt.get("name") for opt in prop.get("multi_select", {}).get("options", [])]
        elif prop.get("type") == "status":
            item["options"] = [opt.get("name") for opt in prop.get("status", {}).get("options", [])]

        summary[name] = item

    return summary


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def inspect_data_source(label: str, data_source_id: str) -> None:
    print(f"\n===== {label} =====")
    ds = retrieve_data_source(data_source_id)
    rows = query_all_rows(data_source_id)
    simple_rows = [simplify_page(row) for row in rows]

    ds_title = parse_rich_text(ds.get("title", [])) if isinstance(ds.get("title"), list) else ds.get("title")
    print(f"Data source ID: {ds.get('id')}")
    print(f"Title: {ds_title}")
    print(f"Row count fetched: {len(simple_rows)}")

    schema = schema_summary(ds)
    print("Schema:")
    print(json.dumps(schema, ensure_ascii=False, indent=2))

    preview = simple_rows[:5]
    print("Rows preview:")
    print(json.dumps(preview, ensure_ascii=False, indent=2))

    prefix = label.lower()
    save_json(OUTPUT_DIR / f"{prefix}_schema.json", schema)
    save_json(OUTPUT_DIR / f"{prefix}_rows.json", simple_rows)


def print_runtime_info() -> None:
    print("Using local .env:" if LOCAL_ENV_PATH.exists() else "No local .env found; using process environment only.")
    if LOCAL_ENV_PATH.exists():
        print(f"  {LOCAL_ENV_PATH}")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Using Notion-Version: {DEFAULT_NOTION_VERSION}")
    print(f"Output directory: {OUTPUT_DIR.resolve()}")


def main() -> None:
    print_runtime_info()

    for label, env_name in ENV_TARGETS:
        ds_id = os.getenv(env_name)
        if not ds_id:
            print(f"\nSkip {label}: missing {env_name}")
            continue
        inspect_data_source(label, ds_id)

    print("\nDone. JSON files saved to:")
    print(OUTPUT_DIR.resolve())


if __name__ == "__main__":
    main()
