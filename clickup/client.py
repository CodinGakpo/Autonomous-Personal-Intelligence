"""Typed ClickUp client. All ClickUp API access MUST go through this module (ADR-0001)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

CLICKUP_BASE = "https://api.clickup.com/api/v2"
TIMEOUT_S = 30


@dataclass(frozen=True)
class TaskRef:
    id: str
    url: str


class ClickUpClient:
    def __init__(self, token: str | None = None) -> None:
        self._token = token or os.environ["CLICKUP_TOKEN"]

    def _headers(self) -> dict[str, str]:
        return {"Authorization": self._token, "Content-Type": "application/json"}

    def create_task(self, list_id: str, name: str, description: str) -> TaskRef:
        response = requests.post(
            f"{CLICKUP_BASE}/list/{list_id}/task",
            headers=self._headers(),
            json={"name": name, "markdown_description": description},
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()
        data = response.json()
        return TaskRef(id=data["id"], url=data["url"])

    def add_comment(self, task_id: str, text: str) -> None:
        response = requests.post(
            f"{CLICKUP_BASE}/task/{task_id}/comment",
            headers=self._headers(),
            json={"comment_text": text},
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()

    def list_tasks(self, list_id: str) -> list[dict[str, Any]]:
        """Read the tasks in a ClickUp list (for pulling them into the brain)."""
        response = requests.get(
            f"{CLICKUP_BASE}/list/{list_id}/task",
            headers=self._headers(),
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()
        return response.json().get("tasks", [])
