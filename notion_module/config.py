from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class NotionEnvConfig:
    notion_token: str
    notion_version: str
    config_data_source_id: str
    topics_data_source_id: str
    tasks_data_source_id: str
    leave_data_source_id: str
    project_root: Path


def _load_local_env() -> Optional[Path]:
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for path in candidates:
        if path.exists():
            load_dotenv(path)
            return path
    return None


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_env_config() -> NotionEnvConfig:
    env_path = _load_local_env()
    project_root = env_path.parent if env_path else Path.cwd()

    return NotionEnvConfig(
        notion_token=_required_env("NOTION_TOKEN"),
        notion_version=os.getenv("NOTION_VERSION", "2025-09-03"),
        config_data_source_id=_required_env("NOTION_CONFIG_DATA_SOURCE_ID"),
        topics_data_source_id=_required_env("NOTION_TOPICS_DATA_SOURCE_ID"),
        tasks_data_source_id=_required_env("NOTION_TASKS_DATA_SOURCE_ID"),
        leave_data_source_id=_required_env("NOTION_LEAVE_DATA_SOURCE_ID"),
        project_root=project_root,
    )
