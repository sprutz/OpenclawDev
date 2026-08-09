"""Launch Cursor Cloud Agents via the public Cloud Agents API."""

from __future__ import annotations

from typing import Any

import httpx

from .config import Settings


class CursorApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


async def launch_cloud_agent(
    settings: Settings,
    *,
    prompt: str,
    name: str | None = None,
) -> dict[str, Any]:
    key = settings.cursor_api_key.strip()
    if not key:
        raise CursorApiError("CURSOR_API_KEY is not configured on the bridge")

    body: dict[str, Any] = {
        "prompt": {"text": prompt},
        "repos": [
            {
                "url": settings.cursor_repo_url,
                "startingRef": settings.cursor_starting_ref,
            }
        ],
        "autoCreatePR": settings.cursor_auto_create_pr,
    }
    if name:
        body["name"] = name[:100]
    if settings.cursor_model_id.strip():
        body["model"] = {"id": settings.cursor_model_id.strip()}

    auth = (key, "")
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.cursor_api_base.rstrip('/')}/v1/agents",
            auth=auth,
            headers={"Content-Type": "application/json"},
            json=body,
        )
    if resp.status_code >= 400:
        try:
            payload = resp.json()
        except Exception:  # noqa: BLE001
            payload = resp.text
        raise CursorApiError(
            f"Cursor API create agent failed ({resp.status_code})",
            status=resp.status_code,
            payload=payload,
        )
    return resp.json()
