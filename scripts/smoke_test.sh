#!/usr/bin/env bash
set -euo pipefail

BRIDGE_URL="${BRIDGE_URL:-http://127.0.0.1:8787}"
BRIDGE_API_KEY="${BRIDGE_API_KEY:?Set BRIDGE_API_KEY}"

auth=(-H "Authorization: Bearer ${BRIDGE_API_KEY}" -H "Content-Type: application/json")

echo "== healthz =="
curl -fsS "${BRIDGE_URL}/healthz" | tee /tmp/voice-bridge-healthz.json
echo

echo "== tools =="
curl -fsS "${BRIDGE_URL}/v1/tools" "${auth[@]}" | tee /tmp/voice-bridge-tools.json
echo

echo "== openclaw_health =="
curl -fsS "${BRIDGE_URL}/v1/tools/invoke" "${auth[@]}" \
  -d '{"name":"openclaw_health","arguments":{}}' | tee /tmp/voice-bridge-openclaw-health.json
echo

echo "Smoke test completed."
