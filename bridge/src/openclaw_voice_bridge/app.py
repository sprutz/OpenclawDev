from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .audit import AuditLogger
from .auth import RateLimiter, extract_bearer, require_bridge_auth
from .config import Settings, get_settings
from .mcp_server import build_mcp
from .openclaw_client import OpenClawClient, TelegramBridge
from .tools import VoiceTools, tool_specs
from .voice_session import build_session_update

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

    # Build MCP ASGI app first so we can wire its session_manager into our lifespan.
    # Nested Starlette mounts do NOT run child lifespans automatically.
    from mcp.server.transport_security import TransportSecuritySettings

    allowed_hosts = [
        "127.0.0.1:*",
        "localhost:*",
        "[::1]:*",
    ]
    for host in settings.mcp_public_host_list:
        host = host.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
        if not host:
            continue
        allowed_hosts.append(host)
        allowed_hosts.append(f"{host}:*")

    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=["*"],
    )

    # host != localhost so the SDK does not force localhost-only Host checks.
    # stateless_http fits xAI remote MCP (each call from their cloud).
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        transport_security=transport_security,
        host="0.0.0.0",
    )
    session_manager = mcp._lowlevel_server._session_manager  # noqa: SLF001

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        logger.info(
            "Starting %s on %s:%s (backend=%s write_tools=%s mcp_hosts=%s)",
            settings.voice_agent_name,
            settings.host,
            settings.port,
            settings.backend_mode,
            settings.enable_write_tools,
            settings.mcp_public_host_list,
        )
        async with session_manager.run():
            try:
                yield
            finally:
                await openclaw.aclose()
                await telegram.aclose()

    app = FastAPI(
        title="OpenClaw Grok Voice Bridge",
        version="0.1.0",
        lifespan=lifespan,
        # Avoid /mcp -> /mcp/ 307 redirects that break some MCP clients (incl. xAI).
        redirect_slashes=False,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    class NormalizeMcpPathMiddleware:
        """Rewrite /mcp -> /mcp/ before routing.

        With redirect_slashes=False, Mount('/mcp') does not serve exact /mcp in
        this FastAPI/Starlette stack (clients get a root 404). xAI uses /mcp.
        """

        def __init__(self, app):  # noqa: ANN001
            self.app = app

        async def __call__(self, scope, receive, send):  # noqa: ANN001
            if scope["type"] == "http" and scope.get("path") == "/mcp":
                scope = dict(scope)
                scope["path"] = "/mcp/"
                if scope.get("raw_path") == b"/mcp":
                    scope["raw_path"] = b"/mcp/"
            await self.app(scope, receive, send)

    # Pure ASGI middleware (not BaseHTTPMiddleware) so scope mutation is reliable.
    app.add_middleware(NormalizeMcpPathMiddleware)

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

    async def mint_client_secret() -> JSONResponse | dict[str, Any]:
        if not settings.xai_api_key.strip():
            return JSONResponse(
                status_code=503,
                content={"ok": False, "error": "XAI_API_KEY not configured on bridge"},
            )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.x.ai/v1/realtime/client_secrets",
                    headers={
                        "Authorization": f"Bearer {settings.xai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"expires_after": {"seconds": 300}},
                )
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                status_code=502,
                content={"ok": False, "error": f"xAI client_secrets request failed: {exc}"},
            )
        if resp.status_code >= 400:
            return JSONResponse(
                status_code=502,
                content={
                    "ok": False,
                    "error": "xAI client_secrets rejected request",
                    "status": resp.status_code,
                    "body": resp.text[:500],
                },
            )
        return resp.json()

    @app.get("/v1/voice-agent/session")
    async def voice_session_config(_: str = Depends(bridge_auth)) -> dict[str, Any]:
        """Ready-to-use Grok Voice session.update fragment."""
        return build_session_update(settings)

    @app.post("/v1/voice-agent/client-secret")
    async def voice_client_secret(_: str = Depends(bridge_auth)) -> JSONResponse:
        """Mint a short-lived xAI realtime client secret (server holds XAI_API_KEY)."""
        result = await mint_client_secret()
        if isinstance(result, JSONResponse):
            return result
        return JSONResponse(status_code=200, content={"ok": True, "data": result})

    @app.post("/v1/voice-agent/bootstrap")
    async def voice_bootstrap(_: str = Depends(bridge_auth)) -> JSONResponse:
        """One-shot bootstrap for the bridge-hosted voice UI."""
        secret = await mint_client_secret()
        if isinstance(secret, JSONResponse):
            return secret
        return JSONResponse(
            status_code=200,
            content={
                "ok": True,
                "client_secret": secret,
                "session_update": build_session_update(settings),
                "realtime_url": "wss://api.x.ai/v1/realtime?model=grok-voice-latest",
            },
        )

    voice_static = Path(__file__).resolve().parent / "static" / "voice"

    @app.get("/voice")
    @app.get("/voice/")
    async def voice_ui() -> FileResponse:
        index = voice_static / "index.html"
        if not index.exists():
            return JSONResponse(status_code=404, content={"error": "voice UI missing"})
        return FileResponse(index)

    class EnsureMcpRootPath:
        """Mount('/mcp') leaves path='' for exact /mcp; StreamableHTTP expects '/'."""

        def __init__(self, inner):  # noqa: ANN001
            self.inner = inner

        async def __call__(self, scope, receive, send):  # noqa: ANN001
            if scope["type"] == "http" and scope.get("path") in ("",):
                scope = dict(scope)
                scope["path"] = "/"
                scope["raw_path"] = b"/"
            await self.inner(scope, receive, send)

    class McpAuthMiddleware:
        """Bearer/X-API-Key gate in front of the MCP ASGI app."""

        def __init__(self, inner):  # noqa: ANN001
            self.inner = inner

        async def __call__(self, scope, receive, send):  # noqa: ANN001
            if scope["type"] != "http":
                await self.inner(scope, receive, send)
                return

            # xAI (and similar) probe with GET. Passing GET into StreamableHTTP opens
            # an SSE stream that never ends and fails their "Couldn't reach" check.
            # Answer GET immediately; real MCP traffic uses POST.
            if scope.get("method") == "GET":
                body = (
                    b'{"ok":true,"service":"openclaw-voice-bridge",'
                    b'"transport":"streamable-http","mcp":true}'
                )
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode("ascii")),
                            (b"cache-control", b"no-store"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
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

    # Mount once; clients may use /mcp or /mcp/ (no redirect).
    app.mount("/mcp", McpAuthMiddleware(EnsureMcpRootPath(mcp_app)))
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
