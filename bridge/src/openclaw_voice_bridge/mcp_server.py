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
