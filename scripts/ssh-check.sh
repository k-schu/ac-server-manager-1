#!/bin/bash
# Usage: ./ssh-check.sh <USER>@<HOST> [-i /path/to/key]
set -euo pipefail
if [ $# -lt 1 ]; then
  echo "Usage: $0 <user@host> [-i keyfile]"
  exit 2
fi
TARGET="$1"
shift
SSH_OPTS=("$@")
echo "Testing SSH connection to $TARGET ..."
ssh -o BatchMode=yes -o ConnectTimeout=10 "${SSH_OPTS[@]}" "$TARGET" 'echo "SSH_OK"' && echo "SSH OK" || echo "SSH failed"
HOST=$(echo "$TARGET" | awk -F@ '{print $2}')
echo "Checking TCP 8081..."
timeout 3 bash -c "cat < /dev/null > /dev/tcp/$HOST/8081" && echo "8081 reachable (TCP)" || echo "8081 not reachable (TCP)"
echo "Checking TCP 9600..."
timeout 3 bash -c "cat < /dev/null > /dev/tcp/$HOST/9600" && echo "9600 reachable (TCP)" || echo "9600 not reachable (TCP)"
echo "UDP test: cannot fully verify without server; use nmap -sU $HOST -p 9600 from a machine with appropriate tools."
