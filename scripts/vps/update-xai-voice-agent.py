#!/usr/bin/env python3
"""Update the saved xAI Voice Agent (prompt + MCP) via API when available.

Uses XAI_API_KEY. Exits 0 on success, 3 if the Agents API is not enabled for
the team (Voice Agent Builder saved agents cannot be mutated without it), 2 on
other configuration errors.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = os.environ.get("XAI_API_BASE", "https://api.x.ai").rstrip("/")


def die(code: int, msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def req(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        die(2, "Missing XAI_API_KEY")
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as resp:
            raw = resp.read().decode() or "{}"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode() if exc.fp else ""
        try:
            payload = json.loads(raw) if raw else {"error": raw}
        except json.JSONDecodeError:
            payload = {"error": raw}
        return exc.code, payload


def load_instructions() -> str:
    path = ROOT / "grok-voice" / "prompts" / "system.md"
    return path.read_text(encoding="utf-8")


def load_mcp_tool() -> dict:
    cfg = json.loads((ROOT / "grok-voice" / "configs" / "voice-agent-mcp.json").read_text())
    tools = cfg.get("session", {}).get("session", {}).get("tools") or cfg.get("tools") or []
    mcp = next((t for t in tools if t.get("type") == "mcp"), None)
    if not mcp:
        die(2, "No mcp tool in voice-agent-mcp.json")

    host = os.environ.get("MCP_PUBLIC_HOSTS", "").split(",")[0].strip()
    if not host:
        # Prefer ready artifact URL if present
        artifact = Path("/opt/cursor/artifacts/voice-bridge-mcp-url.txt")
        if artifact.exists():
            for line in artifact.read_text().splitlines():
                if "MCP URL:" in line:
                    url = line.split("MCP URL:", 1)[1].strip()
                    mcp = {**mcp, "server_url": url}
                    break
    else:
        mcp = {**mcp, "server_url": f"https://{host}/mcp"}

    auth = os.environ.get("BRIDGE_API_KEY", "").strip()
    if not auth:
        # Pull from VPS-synced ready artifact if local secret missing
        ready = Path("/opt/cursor/artifacts/voice-agent-mcp.ready.json")
        if ready.exists():
            ready_cfg = json.loads(ready.read_text())
            ready_tools = ready_cfg.get("session", {}).get("session", {}).get("tools") or []
            ready_mcp = next((t for t in ready_tools if t.get("type") == "mcp"), None)
            if ready_mcp and ready_mcp.get("authorization"):
                auth = str(ready_mcp["authorization"])
                if not host and ready_mcp.get("server_url"):
                    mcp["server_url"] = ready_mcp["server_url"]
    if auth:
        mcp["authorization"] = auth
    return mcp


def desired_agent_payload() -> dict:
    mcp = load_mcp_tool()
    return {
        "name": "OpenClaw Voice Control",
        "voice": "eve",
        "instructions": load_instructions(),
        "tools": [mcp],
    }


def main() -> None:
    desired = desired_agent_payload()
    status, listing = req("GET", "/v1/agents")
    if status == 403:
        err = listing if isinstance(listing, dict) else {"error": listing}
        die(
            3,
            "xAI Agents API is not enabled for this team "
            f"({err.get('error') or err}). Cannot update the saved Voice Agent "
            "Builder agent until that endpoint is enabled.",
        )
    if status >= 400:
        die(2, f"GET /v1/agents failed ({status}): {listing}")

    agents = []
    if isinstance(listing, dict):
        agents = listing.get("data") or listing.get("agents") or []
    elif isinstance(listing, list):
        agents = listing

    target = None
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        name = str(agent.get("name") or "")
        if name.lower() in {"openclaw voice control", "openclaw"}:
            target = agent
            break

    if target and target.get("id"):
        agent_id = target["id"]
        status, updated = req("PATCH", f"/v1/agents/{agent_id}", desired)
        if status == 404:
            status, updated = req("PUT", f"/v1/agents/{agent_id}", desired)
        if status >= 400:
            die(2, f"Update agent {agent_id} failed ({status}): {updated}")
        print(json.dumps({"ok": True, "action": "updated", "id": agent_id, "result": updated}, indent=2))
        return

    status, created = req("POST", "/v1/agents", desired)
    if status >= 400:
        die(2, f"Create agent failed ({status}): {created}")
    print(json.dumps({"ok": True, "action": "created", "result": created}, indent=2))


if __name__ == "__main__":
    main()
