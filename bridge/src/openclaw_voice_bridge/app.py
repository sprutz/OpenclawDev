from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .audit import AuditLogger
from .auth import RateLimiter, extract_bearer, require_bridge_auth
from .config import Settings, get_settings
from .mcp_server import build_mcp
from .openclaw_client import OpenClawClient, TelegramBridge
from .tools import VoiceTools, tool_specs

logger = logging.getLogger("openclaw_voice_bridge")


class InvokeRequest(BaseModel):
    name: str = Field(..., description="Tool name")
    arguments: dict[str, Any] = Field(default_factory=dict)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    audit = AuditLogger(settings.audit_log_path)
    rate_limiter = RateLimiter(settings.rate_limit_per_minute)

    openclaw = OpenClawClient(settings)
    telegram = TelegramBridge(settings)
    tools = VoiceTools(settings, openclaw, telegram, audit)
    mcp = build_mcp(tools)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        logger.info(
            "Starting %s on %s:%s (backend=%s write_tools=%s)",
            settings.voice_agent_name,
            settings.host,
            settings.port,
            settings.backend_mode,
            settings.enable_write_tools,
        )
        try:
            yield
        finally:
            await openclaw.aclose()
            await telegram.aclose()

    app = FastAPI(
        title="OpenClaw Grok Voice Bridge",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    async def bridge_auth(
        request: Request,
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> str:
        return require_bridge_auth(
            settings,
            rate_limiter,
            request,
            authorization=authorization,
            x_api_key=x_api_key,
        )

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "openclaw-voice-bridge",
            "company": settings.company_name,
            "write_tools_enabled": settings.enable_write_tools,
            "backend_mode": settings.backend_mode,
        }

    @app.get("/v1/tools")
    async def list_tools(_: str = Depends(bridge_auth)) -> dict[str, Any]:
        return {
            "tools": tool_specs(include_write_tools=True),
            "write_tools_enabled": settings.enable_write_tools,
            "require_confirmation": settings.require_confirmation,
        }

    @app.post("/v1/tools/invoke")
    async def invoke_tool(body: InvokeRequest, _: str = Depends(bridge_auth)) -> JSONResponse:
        result = await tools.dispatch(body.name, body.arguments)
        status = 200 if result.ok or result.needs_confirmation else 400
        return JSONResponse(status_code=status, content=result.model_dump())

    @app.post("/v1/tools/{tool_name}")
    async def invoke_named_tool(
        tool_name: str,
        request: Request,
        _: str = Depends(bridge_auth),
    ) -> JSONResponse:
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        result = await tools.dispatch(tool_name, payload)
        status = 200 if result.ok or result.needs_confirmation else 400
        return JSONResponse(status_code=status, content=result.model_dump())

    @app.get("/v1/voice-agent/session")
    async def voice_session_config(_: str = Depends(bridge_auth)) -> dict[str, Any]:
        """Ready-to-use Grok Voice session.update fragment."""
        candidates = [
            Path(__file__).resolve().parents[3] / "grok-voice" / "prompts" / "system.md",
            Path("/grok-voice/prompts/system.md"),
        ]
        instructions = None
        for prompt_path in candidates:
            if prompt_path.exists():
                instructions = prompt_path.read_text(encoding="utf-8")
                break
        if instructions is None:
            instructions = (
                f"You are the voice interface to the OpenClaw orchestrator for {settings.company_name}."
            )
        allowed = [
            "openclaw_health",
            "openclaw_list_agents",
            "openclaw_get_status",
            "openclaw_get_summary",
        ]
        if settings.enable_write_tools:
            allowed.extend(["openclaw_assign_task", "openclaw_control_session"])
        return {
            "type": "session.update",
            "session": {
                "instructions": instructions,
                "voice": "eve",
                "turn_detection": {"type": "server_vad"},
                "tools": [
                    {
                        "type": "mcp",
                        "server_url": "REPLACE_WITH_PUBLIC_OR_TAILSCALE_MCP_URL/mcp",
                        "server_label": "openclaw",
                        "server_description": "OpenClaw orchestrator control tools",
                        "authorization": settings.bridge_api_key,
                        "allowed_tools": allowed,
                    }
                ],
            },
        }

    # Mount MCP streamable HTTP at /mcp (xAI Remote MCP transport).
    mcp_app = mcp.streamable_http_app(streamable_http_path="/", host=settings.host)

    class McpAuthMiddleware:
        def __init__(self, inner):  # noqa: ANN001
            self.inner = inner

        async def __call__(self, scope, receive, send):  # noqa: ANN001
            if scope["type"] != "http":
                await self.inner(scope, receive, send)
                return
            headers = {
                k.decode("latin1").lower(): v.decode("latin1")
                for k, v in scope.get("headers", [])
            }
            token = extract_bearer(headers.get("authorization")) or (
                headers.get("x-api-key", "").strip() or None
            )
            if not token or not secrets.compare_digest(token, settings.bridge_api_key):
                body = b'{"error":"unauthorized"}'
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode("ascii")),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
            await self.inner(scope, receive, send)

    app.mount("/mcp", McpAuthMiddleware(mcp_app))
    app.state.settings = settings
    app.state.tools = tools
    return app


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "openclaw_voice_bridge.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
