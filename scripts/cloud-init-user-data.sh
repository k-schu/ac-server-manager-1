#cloud-config
package_update: true
package_upgrade: true
packages:
  - ufw
  - wget
  - curl
  - ca-certificates
  - net-tools
  - iproute2
  - jq
  - openssh-server

runcmd:
  # Ensure we have a dedicated user
  - [ bash, -lc, "id -u acserver || useradd -m -s /bin/bash acserver" ]

  # Create directory for server files
  - [ bash, -lc, "mkdir -p /opt/ac-server && chown acserver:acserver /opt/ac-server" ]

  # Ensure sshd is enabled and started (Ubuntu images usually have it already)
  - [ bash, -lc, "mkdir -p /var/run/sshd" ]
  - [ bash, -lc, "systemctl enable ssh || true" ]
  - [ bash, -lc, "systemctl start ssh || true" ]

  # Install default firewall rules and allow required ports
  - [ bash, -lc, "ufw allow ssh || true" ]
  - [ bash, -lc, "ufw allow 8081/tcp || true" ]
  - [ bash, -lc, "ufw allow 9600/tcp || true" ]
  - [ bash, -lc, "ufw allow 9600/udp || true" ]
  - [ bash, -lc, "ufw --force enable || true" ]

  # Create start script used by the systemd unit (placeholder)
  - [ bash, -lc, "cat > /usr/local/bin/start-ac-server.sh <<'EOF'\n#!/bin/bash\nset -euo pipefail\nLOGDIR=/var/log/ac-server\nmkdir -p \"$LOGDIR\"\nchown acserver:acserver \"$LOGDIR\" || true\ncd /opt/ac-server || true\n# If the environment variable AC_SERVER_START_CMD is set, execute it.\nif [ -n \"${AC_SERVER_START_CMD:-}\" ]; then\n  exec bash -lc \"$AC_SERVER_START_CMD\"\nfi\n# Otherwise try a default executable path; adjust this to your real server binary.\nif [ -x /opt/ac-server/server.sh ]; then\n  exec /opt/ac-server/server.sh\nfi\n# No command available: log and sleep to allow troubleshooting\necho \"No AC server start command found. Check /usr/local/bin/start-ac-server.sh or set AC_SERVER_START_CMD.\" >> \"$LOGDIR/start.log\"\nsleep infinity\nEOF" ]

  - [ bash, -lc, "chmod +x /usr/local/bin/start-ac-server.sh" ]

  # Create systemd unit for the server
  - [ bash, -lc, "cat > /etc/systemd/system/ac-server.service <<'EOF'\n[Unit]\nDescription=AC Game Server\nAfter=network.target\n\n[Service]\nType=simple\nUser=acserver\nGroup=acserver\nEnvironment=AC_SERVER_START_CMD=\"/usr/local/bin/start-ac-server.sh\"\nExecStart=/usr/local/bin/start-ac-server.sh\nRestart=on-failure\nRestartSec=5\nStandardOutput=syslog\nStandardError=syslog\nSyslogIdentifier=ac-server\n\n[Install]\nWantedBy=multi-user.target\nEOF" ]

  - [ bash, -lc, "systemctl daemon-reload" ]
  - [ bash, -lc, "systemctl enable ac-server.service || true" ]

  # Start the service and capture early failures to logs
  - [ bash, -lc, "systemctl start ac-server.service || (journalctl -u ac-server.service --no-pager > /var/log/ac-server/boot-failure.log && exit 1)" ]

final_message: "Cloud-init finished. Replace the placeholder start command or set AC_SERVER_START_CMD to run your real game server."
