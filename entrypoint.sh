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
    if ! python3 -c "
import base64, os, sys
val = os.environ.get('RESUME_B64', '')
try:
    data = base64.b64decode(val)
    open('/app/resume.txt', 'wb').write(data)
except Exception as e:
    print('[entrypoint] ERROR: RESUME_B64 decode failed:', e)
    sys.exit(1)
"; then
        rm -f /app/resume.txt
        exit 1
    fi
fi

exec python main.py
