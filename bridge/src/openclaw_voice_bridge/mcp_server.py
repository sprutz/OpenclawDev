from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from .tools import VoiceTools


def build_mcp(tools: VoiceTools) -> MCPServer:
    """Build an MCP server exposing OpenClaw voice tools for Grok Voice."""

    mcp = MCPServer(
        name="openclaw-voice",
        instructions=(
            "MCP bridge for controlling an OpenClaw orchestrator from Grok Voice. "
            "Prefer read-only tools first. Write tools require confirmed=true."
        ),
    )

    @mcp.tool(name="openclaw_voice_unlock")
    async def openclaw_voice_unlock(passphrase: str) -> dict[str, Any]:
        """Unlock voice tools after the user speaks the access passphrase."""
        return (
            await tools.dispatch("openclaw_voice_unlock", {"passphrase": passphrase})
        ).model_dump()

    @mcp.tool(name="openclaw_health")
    async def openclaw_health() -> dict[str, Any]:
        """Check OpenClaw gateway health and connectivity."""
        return (await tools.dispatch("openclaw_health")).model_dump()

    @mcp.tool(name="openclaw_list_agents")
    async def openclaw_list_agents() -> dict[str, Any]:
        """List all configured OpenClaw agents and related model aliases."""
        return (await tools.dispatch("openclaw_list_agents")).model_dump()

    @mcp.tool(name="openclaw_get_status")
    async def openclaw_get_status(target: str) -> dict[str, Any]:
        """Get detailed status of a gateway, agent, task, or project."""
        return (await tools.dispatch("openclaw_get_status", {"target": target})).model_dump()

    @mcp.tool(name="openclaw_get_summary")
    async def openclaw_get_summary(target: str | None = None) -> dict[str, Any]:
        """Get a concise operational summary across agents/tasks."""
        args: dict[str, Any] = {}
        if target:
            args["target"] = target
        return (await tools.dispatch("openclaw_get_summary", args)).model_dump()

    @mcp.tool(name="openclaw_read_daily_report")
    async def openclaw_read_daily_report(date: str | None = None) -> dict[str, Any]:
        """Read the Second Brain daily journal/report. Omit date for today/latest."""
        args: dict[str, Any] = {}
        if date:
            args["date"] = date
        return (await tools.dispatch("openclaw_read_daily_report", args)).model_dump()

    @mcp.tool(name="openclaw_list_second_brain")
    async def openclaw_list_second_brain(
        kind: str = "both",
        limit: int = 20,
    ) -> dict[str, Any]:
        """List Second Brain journals and/or docs."""
        return (
            await tools.dispatch(
                "openclaw_list_second_brain",
                {"kind": kind, "limit": limit},
            )
        ).model_dump()

    @mcp.tool(name="openclaw_search_second_brain")
    async def openclaw_search_second_brain(query: str, limit: int = 8) -> dict[str, Any]:
        """Search Second Brain journals and docs."""
        return (
            await tools.dispatch(
                "openclaw_search_second_brain",
                {"query": query, "limit": limit},
            )
        ).model_dump()

    @mcp.tool(name="openclaw_read_second_brain")
    async def openclaw_read_second_brain(path: str) -> dict[str, Any]:
        """Read a Second Brain document by relative path."""
        return (await tools.dispatch("openclaw_read_second_brain", {"path": path})).model_dump()

    @mcp.tool(name="openclaw_list_upgrades")
    async def openclaw_list_upgrades(
        status: str | None = None,
        limit: int = 7,
    ) -> dict[str, Any]:
        """List daily tool/skill upgrade suggestions."""
        args: dict[str, Any] = {"limit": limit}
        if status:
            args["status"] = status
        return (await tools.dispatch("openclaw_list_upgrades", args)).model_dump()

    @mcp.tool(name="openclaw_get_upgrade")
    async def openclaw_get_upgrade(
        id: str | None = None,
        date: str | None = None,
    ) -> dict[str, Any]:
        """Get today's or a specific upgrade suggestion for spoken readout."""
        args: dict[str, Any] = {}
        if id:
            args["id"] = id
        if date:
            args["date"] = date
        return (await tools.dispatch("openclaw_get_upgrade", args)).model_dump()

    @mcp.tool(name="openclaw_approve_upgrade")
    async def openclaw_approve_upgrade(
        id: str | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """Approve suggestion and launch Cursor cloud agent. Requires confirmed=true."""
        args: dict[str, Any] = {"confirmed": confirmed}
        if id:
            args["id"] = id
        return (await tools.dispatch("openclaw_approve_upgrade", args)).model_dump()

    @mcp.tool(name="openclaw_reject_upgrade")
    async def openclaw_reject_upgrade(
        id: str | None = None,
        reason: str | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """Reject an upgrade suggestion. Requires confirmed=true."""
        args: dict[str, Any] = {"confirmed": confirmed}
        if id:
            args["id"] = id
        if reason:
            args["reason"] = reason
        return (await tools.dispatch("openclaw_reject_upgrade", args)).model_dump()

    @mcp.tool(name="openclaw_assign_task")
    async def openclaw_assign_task(
        description: str,
        agent: str | None = None,
        priority: str = "normal",
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """Assign a new task. Requires confirmed=true after explicit user confirmation."""
        return (
            await tools.dispatch(
                "openclaw_assign_task",
                {
                    "description": description,
                    "agent": agent,
                    "priority": priority,
                    "confirmed": confirmed,
                },
            )
        ).model_dump()

    @mcp.tool(name="openclaw_control_session")
    async def openclaw_control_session(
        action: str,
        target: str | None = None,
        confirmed: bool = False,
    ) -> dict[str, Any]:
        """Start, pause, resume, or stop a session. Requires confirmed=true."""
        return (
            await tools.dispatch(
                "openclaw_control_session",
                {"action": action, "target": target, "confirmed": confirmed},
            )
        ).model_dump()

    return mcp
