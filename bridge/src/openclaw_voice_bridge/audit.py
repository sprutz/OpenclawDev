from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("openclaw_voice_bridge.audit")


class AuditLogger:
    """Append-only JSONL audit trail for every tool call."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Fall back to cwd if /var/log is not writable in local/dev.
            self.path = Path("audit.jsonl")

    def log(
        self,
        *,
        tool: str,
        args: dict[str, Any],
        result: dict[str, Any] | None = None,
        error: str | None = None,
        confirmed: bool | None = None,
        actor: str = "grok-voice",
    ) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "tool": tool,
            "args": args,
            "confirmed": confirmed,
            "ok": error is None,
            "error": error,
            "result_summary": _summarize(result) if result is not None else None,
        }
        line = json.dumps(record, default=str)
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError as exc:
            logger.warning("Failed to write audit log: %s", exc)
        logger.info("tool=%s ok=%s error=%s", tool, error is None, error)


def _summarize(result: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(result, default=str)
    if len(text) <= 1200:
        return result
    return {"truncated": True, "preview": text[:1200]}
