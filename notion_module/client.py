from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from .config import NotionEnvConfig


class NotionClient:
    def __init__(self, env: NotionEnvConfig, timeout: int = 30) -> None:
        self.env = env
        self.timeout = timeout
        self.base_url = "https://api.notion.com/v1"

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.env.notion_token}",
            "Notion-Version": self.env.notion_version,
            "Content-Type": "application/json",
        }

    def retrieve_data_source(self, data_source_id: str) -> dict[str, Any]:
        resp = requests.get(
            f"{self.base_url}/data_sources/{data_source_id}",
            headers=self.headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def query_data_source(
        self,
        data_source_id: str,
        *,
        page_size: int = 100,
        start_cursor: Optional[str] = None,
        filter_obj: Optional[dict[str, Any]] = None,
        sorts: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"page_size": page_size}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        if filter_obj:
            payload["filter"] = filter_obj
        if sorts:
            payload["sorts"] = sorts

        resp = requests.post(
            f"{self.base_url}/data_sources/{data_source_id}/query",
            headers=self.headers,
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def query_all_rows(
        self,
        data_source_id: str,
        *,
        filter_obj: Optional[dict[str, Any]] = None,
        sorts: Optional[list[dict[str, Any]]] = None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor: Optional[str] = None

        while True:
            payload = self.query_data_source(
                data_source_id,
                start_cursor=cursor,
                filter_obj=filter_obj,
                sorts=sorts,
            )
            rows.extend(payload.get("results", []))
            if not payload.get("has_more"):
                break
            cursor = payload.get("next_cursor")
            if not cursor:
                break

        return rows

    def update_page(self, page_id: str, properties: dict[str, Any], archived: Optional[bool] = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"properties": properties}
        if archived is not None:
            payload["archived"] = archived

        resp = requests.patch(
            f"{self.base_url}/pages/{page_id}",
            headers=self.headers,
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        resp = requests.get(
            f"{self.base_url}/pages/{page_id}",
            headers=self.headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()
