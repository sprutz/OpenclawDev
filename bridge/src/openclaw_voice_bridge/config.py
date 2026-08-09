from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the Grok Voice ↔ OpenClaw bridge."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Bridge listener
    host: str = "127.0.0.1"
    port: int = 8787
    bridge_api_key: str = Field(
        ...,
        description="Bearer token required for HTTP/MCP callers (Grok Voice / operators).",
    )
    allow_origins: list[str] = Field(default_factory=lambda: ["*"])

    # OpenClaw gateway
    openclaw_base_url: str = "http://127.0.0.1:18789"
    openclaw_gateway_token: str = Field(
        ...,
        description="OPENCLAW_GATEWAY_TOKEN / gateway.auth.token shared secret.",
    )
    openclaw_timeout_seconds: float = 60.0
    openclaw_default_agent: str = "main"
    openclaw_session_key: str = "main"

    # Integration mode
    # gateway: admin-http-rpc + /tools/invoke + /v1/chat/completions
    # telegram: send text into Telegram bot API as a temporary bridge
    # hybrid: try gateway first, fall back to telegram for assign_task only
    backend_mode: Literal["gateway", "telegram", "hybrid"] = "gateway"

    # Write safety
    require_confirmation: bool = True
    enable_write_tools: bool = False
    rate_limit_per_minute: int = 60
    audit_log_path: str = "/var/log/openclaw-voice-bridge/audit.jsonl"

    # Optional Telegram bridge (path C)
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    # Branding / spoken context
    company_name: str = "QDS Systems"
    voice_agent_name: str = "OpenClaw Voice Control"

    # Public hostname(s) for MCP DNS-rebinding protection (Tailscale Funnel / MagicDNS).
    # Comma-separated MagicDNS hostnames, no scheme/path. Keep as str so env parsing
    # does not require JSON list encoding.
    mcp_public_hosts: str = ""

    # Second Brain (OpenClaw workspace knowledge store) — read-only for voice.
    second_brain_root: str = "/home/stan/clawd/second-brain"

    # Spoken voice unlock. Empty = gate disabled. Prefer a short phrase that STT hears reliably.
    voice_spoken_password: str = ""
    # How long the bridge stays unlocked after a correct spoken passphrase (seconds).
    voice_unlock_ttl_seconds: int = 8 * 60 * 60

    @field_validator("allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            # Support JSON list or comma-separated values.
            stripped = value.strip()
            if stripped.startswith("["):
                return value
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @property
    def mcp_public_host_list(self) -> list[str]:
        raw = self.mcp_public_hosts.strip()
        if not raw:
            return []
        if raw.startswith("["):
            import json

            parsed = json.loads(raw)
            return [str(x).strip() for x in parsed if str(x).strip()]
        return [part.strip() for part in raw.split(",") if part.strip()]

    @property
    def openclaw_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.openclaw_gateway_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
