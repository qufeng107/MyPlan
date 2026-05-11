from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import HTTPError, ReadTimeout

from .config import NotionEnvConfig


class NotionClient:
    def __init__(
        self,
        env: NotionEnvConfig,
        timeout: int | tuple[int, int] = (10, 60),
        max_retries: int = 4,
        retry_backoff_seconds: float = 1.5,
    ) -> None:
        self.env = env
        self.timeout = timeout
        self.max_retries = max(int(max_retries), 1)
        self.retry_backoff_seconds = max(float(retry_backoff_seconds), 0.0)
        self.base_url = "https://api.notion.com/v1"
        self.session = requests.Session()

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.env.notion_token}",
            "Notion-Version": self.env.notion_version,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _should_retry_http_error(exc: HTTPError) -> bool:
        response = getattr(exc, "response", None)
        if response is None:
            return False
        return response.status_code in {408, 409, 429, 500, 502, 503, 504}

    def _sleep_before_retry(self, attempt: int, response: Optional[requests.Response] = None) -> None:
        retry_after = None
        if response is not None:
            retry_after = response.headers.get("Retry-After")

        if retry_after:
            try:
                seconds = max(float(retry_after), 0.0)
            except Exception:
                seconds = self.retry_backoff_seconds * (2 ** (attempt - 1))
        else:
            seconds = self.retry_backoff_seconds * (2 ** (attempt - 1))

        if seconds > 0:
            time.sleep(seconds)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=json_payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                return resp.json()
            except (ReadTimeout, RequestsConnectionError) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise
                print(
                    f"[NOTION_RETRY] {method.upper()} {path} | attempt {attempt}/{self.max_retries} | "
                    f"reason={exc.__class__.__name__}: {exc}"
                )
                self._sleep_before_retry(attempt)
            except HTTPError as exc:
                last_exc = exc
                if not self._should_retry_http_error(exc) or attempt >= self.max_retries:
                    raise
                response = getattr(exc, "response", None)
                status_code = response.status_code if response is not None else "unknown"
                print(
                    f"[NOTION_RETRY] {method.upper()} {path} | attempt {attempt}/{self.max_retries} | "
                    f"status={status_code} | reason={exc}"
                )
                self._sleep_before_retry(attempt, response=response)

        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"Unexpected request failure without exception for {method} {path}")

    def retrieve_data_source(self, data_source_id: str) -> dict[str, Any]:
        return self._request("GET", f"/data_sources/{data_source_id}")

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

        return self._request("POST", f"/data_sources/{data_source_id}/query", json_payload=payload)

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

        return self._request("PATCH", f"/pages/{page_id}", json_payload=payload)

    def retrieve_page(self, page_id: str) -> dict[str, Any]:
        return self._request("GET", f"/pages/{page_id}")
