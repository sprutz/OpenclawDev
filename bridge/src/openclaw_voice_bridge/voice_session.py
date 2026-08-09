"""Build Grok Voice session.update payloads from bridge settings + prompt files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Settings


def load_voice_instructions(settings: Settings) -> str:
    candidates = [
        Path(__file__).resolve().parents[3] / "grok-voice" / "prompts" / "system.md",
        Path("/opt/openclaw-voice-bridge/grok-voice/prompts/system.md"),
        Path("/grok-voice/prompts/system.md"),
    ]
    for prompt_path in candidates:
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
    return (
        f"You are the voice interface to the OpenClaw orchestrator for {settings.company_name}."
    )


def allowed_voice_tools(settings: Settings) -> list[str]:
    allowed = [
        "openclaw_voice_unlock",
        "openclaw_health",
        "openclaw_list_agents",
        "openclaw_get_status",
        "openclaw_get_summary",
        "openclaw_read_daily_report",
        "openclaw_list_second_brain",
        "openclaw_search_second_brain",
        "openclaw_read_second_brain",
    ]
    if settings.enable_write_tools:
        allowed.extend(["openclaw_assign_task", "openclaw_control_session"])
    return allowed


def build_session_update(settings: Settings) -> dict[str, Any]:
    mcp_url = settings.resolved_mcp_public_url or "REPLACE_WITH_PUBLIC_OR_TAILSCALE_MCP_URL/mcp"
    return {
        "type": "session.update",
        "session": {
            "instructions": load_voice_instructions(settings),
            "voice": "eve",
            "turn_detection": {
                "type": "server_vad",
                "silence_duration_ms": 700,
            },
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "transcription": {
                        "language_hint": "en-US",
                        "keyterms": [
                            "OpenClaw",
                            "QDS Systems",
                            "Second Brain",
                            "daily report",
                            "pursue",
                            "enthusiasm",
                            "pursuewithenthusiasm",
                        ],
                    },
                },
                "output": {"format": {"type": "audio/pcm", "rate": 24000}},
            },
            "tools": [
                {
                    "type": "mcp",
                    "server_url": mcp_url,
                    "server_label": "openclaw",
                    "server_description": "OpenClaw orchestrator control tools",
                    "authorization": settings.bridge_api_key,
                    "allowed_tools": allowed_voice_tools(settings),
                }
            ],
        },
    }
