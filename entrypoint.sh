#!/bin/sh
set -e

# Generate config.yaml from env vars if not already volume-mounted
if [ ! -f /app/config.yaml ]; then
    echo "[entrypoint] Generating config.yaml from environment variables..."
    python /app/generate_config.py
fi

# Decode resume from base64 env var if not already volume-mounted
if [ ! -f /app/resume.txt ]; then
    if [ -z "$RESUME_B64" ]; then
        echo "[entrypoint] ERROR: resume.txt not found and RESUME_B64 env var is not set."
        exit 1
    fi
    echo "[entrypoint] Decoding resume from RESUME_B64..."
    echo "$RESUME_B64" | base64 -d > /app/resume.txt
fi

exec python main.py
