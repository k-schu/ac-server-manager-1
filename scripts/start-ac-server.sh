#!/bin/bash
# Local copy (for repo) of the start wrapper used by cloud-init.
set -euo pipefail
LOGDIR=/var/log/ac-server
mkdir -p "$LOGDIR"
chown acserver:acserver "$LOGDIR" || true
cd /opt/ac-server || true
if [ -n "${AC_SERVER_START_CMD:-}" ]; then
  exec bash -lc "$AC_SERVER_START_CMD"
fi
if [ -x /opt/ac-server/server.sh ]; then
  exec /opt/ac-server/server.sh
fi
echo "$(date -u --rfc-3339=seconds) No AC_SERVER_START_CMD provided. Please set the start command in the systemd unit or env." >> "$LOGDIR/start.log"
sleep infinity
