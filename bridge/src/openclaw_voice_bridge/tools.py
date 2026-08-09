from __future__ import annotations

import re
import secrets
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from .audit import AuditLogger
from .config import Settings
from .openclaw_client import OpenClawClient, OpenClawError, TelegramBridge
from . import second_brain as sb

Priority = Literal["low", "normal", "high", "urgent"]
SessionAction = Literal["start", "pause", "resume", "stop"]


def normalize_passphrase(value: str) -> str:
    """Normalize spoken passphrases for reliable STT matching."""
    cleaned = re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


class ToolResult(BaseModel):
    ok: bool
    tool: str
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    needs_confirmation: bool = False
    spoken_hint: str | None = None


class VoiceTools:
    """Maps Grok Voice tool calls onto OpenClaw (and optional Telegram)."""

    WRITE_TOOLS = {"openclaw_assign_task", "openclaw_control_session"}
    UNLOCK_TOOL = "openclaw_voice_unlock"

    def __init__(
        self,
        settings: Settings,
        openclaw: OpenClawClient,
        telegram: TelegramBridge,
        audit: AuditLogger,
    ) -> None:
        self.settings = settings
        self.openclaw = openclaw
        self.telegram = telegram
        self.audit = audit
        self._unlocked_until = 0.0

    @property
    def voice_gate_enabled(self) -> bool:
        return bool(normalize_passphrase(self.settings.voice_spoken_password))

    @property
    def is_unlocked(self) -> bool:
        if not self.voice_gate_enabled:
            return True
        return time.time() < self._unlocked_until

    async def dispatch(self, name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        args = arguments or {}
        handlers = {
            "openclaw_voice_unlock": self.voice_unlock,
            "openclaw_list_agents": self.list_agents,
            "openclaw_get_status": self.get_status,
            "openclaw_assign_task": self.assign_task,
            "openclaw_control_session": self.control_session,
            "openclaw_get_summary": self.get_summary,
            "openclaw_health": self.health,
            "openclaw_read_daily_report": self.read_daily_report,
            "openclaw_list_second_brain": self.list_second_brain,
            "openclaw_search_second_brain": self.search_second_brain,
            "openclaw_read_second_brain": self.read_second_brain,
        }
        handler = handlers.get(name)
        if handler is None:
            result = ToolResult(ok=False, tool=name, error=f"Unknown tool: {name}")
            self.audit.log(tool=name, args=args, error=result.error)
            return result

        if name != self.UNLOCK_TOOL:
            gate = self._gate_voice_unlock(name)
            if gate:
                self.audit.log(tool=name, args=args, error=gate.error)
                return gate

        try:
            result = await handler(**args)
        except TypeError as exc:
            result = ToolResult(ok=False, tool=name, error=f"Invalid arguments: {exc}")
        except OpenClawError as exc:
            result = ToolResult(ok=False, tool=name, error=str(exc), data={"payload": exc.payload})
        except Exception as exc:  # noqa: BLE001 - surface unexpected failures to voice layer
            result = ToolResult(ok=False, tool=name, error=f"Unexpected error: {exc}")
        # Never log the raw passphrase.
        audit_args = dict(args)
        if name == self.UNLOCK_TOOL and "passphrase" in audit_args:
            audit_args["passphrase"] = "***"
        self.audit.log(
            tool=name,
            args=audit_args,
            result=result.model_dump(),
            error=result.error,
            confirmed=args.get("confirmed"),
        )
        return result

    def _gate_voice_unlock(self, tool: str) -> ToolResult | None:
        if self.is_unlocked:
            return None
        return ToolResult(
            ok=False,
            tool=tool,
            error="Voice session is locked. Speak the access passphrase first.",
            spoken_hint="Voice control is locked. Please say the access passphrase.",
            data={"locked": True},
        )

    def _gate_write(self, tool: str, confirmed: bool | None) -> ToolResult | None:
        if not self.settings.enable_write_tools:
            return ToolResult(
                ok=False,
                tool=tool,
                error=(
                    "Write tools are disabled. Set ENABLE_WRITE_TOOLS=true after validating "
                    "read-only voice control."
                ),
                spoken_hint="Write actions are currently locked. I can still check status.",
            )
        if self.settings.require_confirmation and not confirmed:
            return ToolResult(
                ok=False,
                tool=tool,
                needs_confirmation=True,
                error="Confirmation required before changing OpenClaw state.",
                spoken_hint="Please confirm before I make that change.",
            )
        return None

    async def voice_unlock(self, passphrase: str) -> ToolResult:
        if not self.voice_gate_enabled:
            return ToolResult(
                ok=True,
                tool=self.UNLOCK_TOOL,
                data={"unlocked": True, "gate_enabled": False},
                spoken_hint="Voice unlock is not required right now.",
            )
        expected = normalize_passphrase(self.settings.voice_spoken_password)
        provided = normalize_passphrase(passphrase)
        if not provided or not secrets.compare_digest(provided, expected):
            self._unlocked_until = 0.0
            return ToolResult(
                ok=False,
                tool=self.UNLOCK_TOOL,
                error="Incorrect passphrase.",
                spoken_hint="Access denied. Voice control remains locked.",
                data={"unlocked": False},
            )
        self._unlocked_until = time.time() + max(60, int(self.settings.voice_unlock_ttl_seconds))
        return ToolResult(
            ok=True,
            tool=self.UNLOCK_TOOL,
            data={
                "unlocked": True,
                "ttl_seconds": int(self.settings.voice_unlock_ttl_seconds),
            },
            spoken_hint="Unlocked. How can I help?",
        )

    async def health(self) -> ToolResult:
        data = await self.openclaw.health()
        return ToolResult(
            ok=bool(data.get("ok")),
            tool="openclaw_health",
            data=data,
            spoken_hint="Gateway is healthy." if data.get("ok") else "Gateway health check failed.",
        )

    async def list_agents(self) -> ToolResult:
        data = await self.openclaw.list_agents()
        return ToolResult(
            ok=True,
            tool="openclaw_list_agents",
            data=data,
            spoken_hint="Here are the active OpenClaw agents.",
        )

    async def get_status(self, target: str) -> ToolResult:
        target = (target or "").strip()
        if not target:
            raise OpenClawError("target is required")

        bundle: dict[str, Any] = {"target": target}
        # Always include gateway status context.
        bundle["gateway"] = await self.openclaw.gateway_status()

        lowered = target.lower()
        if lowered in {"gateway", "openclaw", "orchestrator", "system"}:
            return ToolResult(
                ok=True,
                tool="openclaw_get_status",
                data=bundle,
                spoken_hint="Gateway status retrieved.",
            )

        # Try task lookup when it looks like an id; otherwise inspect sessions + agent chat.
        if _looks_like_id(target):
            try:
                bundle["task"] = await self.openclaw.get_task(target)
            except OpenClawError as exc:
                bundle["task_error"] = str(exc)

        try:
            bundle["sessions"] = await self.openclaw.list_sessions()
        except OpenClawError as exc:
            bundle["sessions_error"] = str(exc)

        try:
            reply = await self.openclaw.chat_completions(
                f"Voice control status check for: {target}. "
                "Reply with a concise operational status only.",
                agent=target if not _looks_like_id(target) else None,
            )
            bundle["agent_report"] = reply
        except OpenClawError as exc:
            bundle["agent_report_error"] = str(exc)

        return ToolResult(
            ok=True,
            tool="openclaw_get_status",
            data=bundle,
            spoken_hint=f"Status for {target} retrieved.",
        )

    async def get_summary(self, target: str | None = None) -> ToolResult:
        focus = target or "all active agents and tasks"
        gateway = await self.openclaw.gateway_status()
        agents = await self.openclaw.list_agents()
        sessions = None
        sessions_error = None
        try:
            sessions = await self.openclaw.list_sessions()
        except OpenClawError as exc:
            sessions_error = str(exc)
        try:
            narrative = await self.openclaw.chat_completions(
                f"Voice control summary request covering: {focus}. "
                "Give a short spoken-friendly operations summary.",
            )
        except OpenClawError as exc:
            narrative = None
            narrative_error = str(exc)
        else:
            narrative_error = None

        return ToolResult(
            ok=True,
            tool="openclaw_get_summary",
            data={
                "focus": focus,
                "gateway": gateway,
                "agents": agents,
                "sessions": sessions,
                "sessions_error": sessions_error,
                "summary": narrative,
                "summary_error": narrative_error,
            },
            spoken_hint="Summary ready.",
        )

    async def read_daily_report(self, date: str | None = None) -> ToolResult:
        """Read Second Brain daily journal (YYYY-MM-DD). Defaults to today, else latest."""
        try:
            data = sb.read_daily_report(self.settings.second_brain_root, date)
        except (FileNotFoundError, ValueError) as exc:
            return ToolResult(
                ok=False,
                tool="openclaw_read_daily_report",
                error=str(exc),
                spoken_hint="I could not find a daily report in Second Brain.",
            )
        day = data["date"]
        fallback = data.get("fallback_to_latest")
        hint = f"Daily report for {day}."
        if fallback:
            hint = f"No report for the requested day; reading the latest report from {day}."
        return ToolResult(
            ok=True,
            tool="openclaw_read_daily_report",
            data=data,
            spoken_hint=hint,
        )

    async def list_second_brain(
        self,
        kind: str = "both",
        limit: int = 20,
    ) -> ToolResult:
        """List Second Brain journals and/or docs."""
        kind_n = (kind or "both").strip().lower()
        if kind_n not in {"journal", "docs", "both"}:
            return ToolResult(
                ok=False,
                tool="openclaw_list_second_brain",
                error="kind must be journal, docs, or both",
                spoken_hint="I can list journals, docs, or both.",
            )
        try:
            data: dict[str, Any] = {"root": self.settings.second_brain_root, "kind": kind_n}
            if kind_n in {"journal", "both"}:
                data["journals"] = sb.list_journals(self.settings.second_brain_root, limit=limit)
            if kind_n in {"docs", "both"}:
                data["docs"] = sb.list_docs(self.settings.second_brain_root, limit=limit)
        except (FileNotFoundError, ValueError) as exc:
            return ToolResult(
                ok=False,
                tool="openclaw_list_second_brain",
                error=str(exc),
                spoken_hint="Second Brain is not available right now.",
            )
        return ToolResult(
            ok=True,
            tool="openclaw_list_second_brain",
            data=data,
            spoken_hint="Second Brain listing ready.",
        )

    async def search_second_brain(self, query: str, limit: int = 8) -> ToolResult:
        try:
            hits = sb.search_second_brain(self.settings.second_brain_root, query, limit=limit)
        except (FileNotFoundError, ValueError) as exc:
            return ToolResult(
                ok=False,
                tool="openclaw_search_second_brain",
                error=str(exc),
                spoken_hint="I could not search Second Brain.",
            )
        return ToolResult(
            ok=True,
            tool="openclaw_search_second_brain",
            data={"query": query, "hits": hits, "count": len(hits)},
            spoken_hint=f"Found {len(hits)} Second Brain matches." if hits else "No Second Brain matches.",
        )

    async def read_second_brain(self, path: str) -> ToolResult:
        try:
            data = sb.read_doc(self.settings.second_brain_root, path)
        except (FileNotFoundError, ValueError) as exc:
            return ToolResult(
                ok=False,
                tool="openclaw_read_second_brain",
                error=str(exc),
                spoken_hint="I could not open that Second Brain document.",
            )
        return ToolResult(
            ok=True,
            tool="openclaw_read_second_brain",
            data=data,
            spoken_hint="Document ready.",
        )

    async def assign_task(
        self,
        description: str,
        agent: str | None = None,
        priority: Priority = "normal",
        confirmed: bool = False,
    ) -> ToolResult:
        gate = self._gate_write("openclaw_assign_task", confirmed)
        if gate:
            return gate
        if not description or not description.strip():
            raise OpenClawError("description is required")

        mode = self.settings.backend_mode
        if mode in {"gateway", "hybrid"}:
            try:
                data = await self.openclaw.assign_task(
                    description.strip(),
                    agent=agent,
                    priority=priority,
                )
                data["transport"] = "gateway"
                return ToolResult(
                    ok=True,
                    tool="openclaw_assign_task",
                    data=data,
                    spoken_hint="Task assigned.",
                )
            except OpenClawError:
                if mode != "hybrid":
                    raise

        message = (
            f"[Grok Voice → OpenClaw]\n"
            f"Priority: {priority}\n"
            f"Agent: {agent or self.settings.openclaw_default_agent}\n"
            f"Task: {description.strip()}"
        )
        data = await self.telegram.send_message(message)
        return ToolResult(
            ok=True,
            tool="openclaw_assign_task",
            data={**data, "priority": priority, "agent": agent, "description": description},
            spoken_hint="Task sent through Telegram.",
        )

    async def control_session(
        self,
        action: SessionAction,
        target: str | None = None,
        confirmed: bool = False,
    ) -> ToolResult:
        gate = self._gate_write("openclaw_control_session", confirmed)
        if gate:
            return gate
        data = await self.openclaw.control_session(action, target)
        return ToolResult(
            ok=True,
            tool="openclaw_control_session",
            data=data,
            spoken_hint=f"Session {action} completed.",
        )


def tool_specs(*, include_write_tools: bool = True) -> list[dict[str, Any]]:
    """Grok Voice / OpenAI-style function tool definitions."""
    tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "name": "openclaw_voice_unlock",
            "description": (
                "Unlock the voice session after the user speaks the access passphrase. "
                "Call this before any other tool when the session is locked."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "passphrase": {
                        "type": "string",
                        "description": "The spoken access passphrase exactly as heard",
                    }
                },
                "required": ["passphrase"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "openclaw_health",
            "description": "Check OpenClaw gateway health and connectivity",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "type": "function",
            "name": "openclaw_list_agents",
            "description": "List all configured OpenClaw agents and related model aliases",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "type": "function",
            "name": "openclaw_get_status",
            "description": "Get detailed status of a gateway, agent, task, or project",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Agent name, task ID, project name, or 'gateway'",
                    }
                },
                "required": ["target"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "openclaw_get_summary",
            "description": "Get a concise operational summary across agents/tasks",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Optional focus area (agent, project, or omit for all)",
                    }
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "openclaw_read_daily_report",
            "description": (
                "Read the Second Brain daily journal/report for a date (YYYY-MM-DD). "
                "Omit date for today; falls back to the latest available report. "
                "Use spoken_text / content to read the report aloud while driving."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Optional journal date YYYY-MM-DD",
                    }
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "openclaw_list_second_brain",
            "description": "List Second Brain daily journals and/or knowledge docs",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["journal", "docs", "both"],
                        "description": "What to list",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max items per section",
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "openclaw_search_second_brain",
            "description": "Search Second Brain journals and docs by keyword",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text"},
                    "limit": {"type": "integer", "description": "Max hits"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "openclaw_read_second_brain",
            "description": (
                "Read a Second Brain document by relative path "
                "(e.g. docs/qds-terafab-opportunity.md or journal/2026-04-18.md)"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path under the Second Brain root",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    ]
    if include_write_tools:
        tools.extend(
            [
                {
                    "type": "function",
                    "name": "openclaw_assign_task",
                    "description": (
                        "Assign a new task to an OpenClaw agent or the orchestrator. "
                        "Requires confirmed=true after explicit user confirmation."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "agent": {
                                "type": "string",
                                "description": "Optional agent id/name. Defaults to orchestrator/main.",
                            },
                            "description": {
                                "type": "string",
                                "description": "Clear task description to execute",
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "normal", "high", "urgent"],
                                "description": "Task priority",
                            },
                            "confirmed": {
                                "type": "boolean",
                                "description": "Must be true after the user explicitly confirms",
                            },
                        },
                        "required": ["description"],
                        "additionalProperties": False,
                    },
                },
                {
                    "type": "function",
                    "name": "openclaw_control_session",
                    "description": (
                        "Start, pause, resume, or stop an agent/task session. "
                        "Requires confirmed=true after explicit user confirmation."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["start", "pause", "resume", "stop"],
                            },
                            "target": {
                                "type": "string",
                                "description": "Agent name or task ID",
                            },
                            "confirmed": {
                                "type": "boolean",
                                "description": "Must be true after the user explicitly confirms",
                            },
                        },
                        "required": ["action"],
                        "additionalProperties": False,
                    },
                },
            ]
        )
    return tools


def _looks_like_id(value: str) -> bool:
    cleaned = value.strip()
    if len(cleaned) < 6:
        return False
    return all(ch.isalnum() or ch in "-_" for ch in cleaned)
