"""Daily assistant-upgrade recommendations (tools/skills) for voice approve → Cursor."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")

STATUSES = frozenset(
    {"pending", "approved", "building", "done", "rejected", "queued_no_api_key"}
)


def _root(path: str | Path) -> Path:
    root = Path(path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path_for(root: str | Path, suggestion_id: str) -> Path:
    sid = (suggestion_id or "").strip()
    if not _ID_RE.match(sid):
        raise ValueError("Invalid suggestion id")
    return _root(root) / f"{sid}.json"


def today_id(day: date | None = None) -> str:
    return (day or date.today()).isoformat()


def load_suggestion(root: str | Path, suggestion_id: str) -> dict[str, Any]:
    path = _path_for(root, suggestion_id)
    if not path.is_file():
        raise FileNotFoundError(f"No upgrade suggestion for id {suggestion_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Corrupt suggestion file")
    return data


def save_suggestion(root: str | Path, data: dict[str, Any]) -> dict[str, Any]:
    sid = str(data.get("id") or "").strip()
    if not _ID_RE.match(sid):
        raise ValueError("Suggestion requires a valid id")
    status = str(data.get("status") or "pending")
    if status not in STATUSES:
        raise ValueError(f"Invalid status: {status}")
    path = _path_for(root, sid)
    payload = dict(data)
    payload["id"] = sid
    payload["status"] = status
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Human-readable mirror next to JSON
    md_path = path.with_suffix(".md")
    md_path.write_text(_to_markdown(payload), encoding="utf-8")
    return payload


def list_suggestions(
    root: str | Path,
    *,
    status: str | None = None,
    limit: int = 14,
) -> list[dict[str, Any]]:
    base = _root(root)
    files = sorted(base.glob("*.json"), reverse=True)
    out: list[dict[str, Any]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if status and str(data.get("status")) != status:
            continue
        out.append(
            {
                "id": data.get("id") or path.stem,
                "date": data.get("date") or path.stem,
                "title": data.get("title") or "",
                "summary": data.get("summary") or "",
                "status": data.get("status") or "pending",
                "category": data.get("category") or "",
                "cursor_agent_url": data.get("cursor_agent_url"),
            }
        )
        if len(out) >= max(1, limit):
            break
    return out


def get_latest_pending(root: str | Path) -> dict[str, Any] | None:
    pending = list_suggestions(root, status="pending", limit=1)
    if pending:
        return load_suggestion(root, str(pending[0]["id"]))
    # Fall back to today's file even if not pending
    today = today_id()
    try:
        return load_suggestion(root, today)
    except FileNotFoundError:
        return None


def spoken_blurb(data: dict[str, Any]) -> str:
    title = str(data.get("title") or "Untitled").strip()
    summary = str(data.get("summary") or "").strip()
    status = str(data.get("status") or "pending")
    if summary:
        return f"{title}. {summary} Status: {status}."
    return f"{title}. Status: {status}."


def build_cursor_prompt(data: dict[str, Any]) -> str:
    custom = str(data.get("implementation_prompt") or "").strip()
    if custom:
        return custom
    title = data.get("title") or "OpenClaw upgrade"
    summary = data.get("summary") or ""
    rationale = data.get("rationale") or ""
    return (
        f"Implement this approved OpenClaw assistant upgrade for Stan / QDS Systems.\n\n"
        f"Title: {title}\n"
        f"Summary: {summary}\n"
        f"Rationale: {rationale}\n\n"
        "Requirements:\n"
        "- Implement in the OpenclawDev repo (bridge, grok-voice, scripts/vps, deploy docs as needed).\n"
        "- Add or update tests where practical; run them.\n"
        "- Deploy/sync to the Hostinger VPS using existing scripts/vps helpers when the change needs to be live.\n"
        "- Commit, push, and open/update a PR.\n"
        "- Do not ask Stan to paste console values or perform steps you can do yourself.\n"
    )


def _to_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"# {data.get('title') or data.get('id')}",
        "",
        f"- **id:** `{data.get('id')}`",
        f"- **date:** {data.get('date')}",
        f"- **status:** {data.get('status')}",
        f"- **category:** {data.get('category') or 'n/a'}",
        "",
        "## Summary",
        str(data.get("summary") or ""),
        "",
        "## Rationale",
        str(data.get("rationale") or ""),
        "",
        "## Implementation prompt",
        str(data.get("implementation_prompt") or ""),
        "",
    ]
    if data.get("cursor_agent_url"):
        lines.extend(["## Cursor agent", str(data["cursor_agent_url"]), ""])
    return "\n".join(lines)


def validate_date(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    if not _DATE_RE.match(text):
        raise ValueError("date must be YYYY-MM-DD")
    return text
