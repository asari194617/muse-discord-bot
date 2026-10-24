#!/usr/bin/env bash
# Regenerate proxy.env from this session's environment (proxy credentials
# rotate between sessions) and restart the bot service.
set -euo pipefail
cd "$(dirname "$0")"
python3 - <<'PY'
import os
keys = ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'no_proxy', 'NO_PROXY']
lines = [f"{k}={os.environ[k]}" for k in keys if k in os.environ]
fd = os.open('proxy.env', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write('\n'.join(lines) + '\n')
os.chmod('proxy.env', 0o600)
print('proxy.env regenerated')
PY
sudo systemctl restart muse-discord-bot
echo "bot service restarted"
