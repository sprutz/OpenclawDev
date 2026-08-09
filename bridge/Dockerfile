FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8787 \
    AUDIT_LOG_PATH=/var/log/openclaw-voice-bridge/audit.jsonl \
    PYTHONPATH=/app/src

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /var/log/openclaw-voice-bridge /grok-voice

COPY bridge/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY bridge/src /app/src
COPY bridge/README.md /app/README.md
COPY bridge/pyproject.toml /app/pyproject.toml
COPY grok-voice /grok-voice

EXPOSE 8787

CMD ["python", "-m", "uvicorn", "openclaw_voice_bridge.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8787"]
