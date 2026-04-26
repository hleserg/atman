# memoryHub — Deployment Guide

See `ARCHITECTURE.md §9 Deployment Diagram` for architecture overview.

## Quick Start (Development)

```bash
# 1. Clone and setup
git clone https://github.com/you/memoryhub
cd memoryhub
make setup               # Creates dirs, runs DB migrations

# 2. Configure
# Edit config/memoryhub.config.yaml
# Copy docker/.env.example to docker/.env

# 3. Run
make run                 # Local binary
# or
make docker-up           # Docker stack

# 4. Verify
curl http://localhost:3000/v1/health
```

## Production Deployment (mac-mini 192.168.1.51)

### Prerequisites
- Go 1.22+
- sqlite3
- Docker + Docker Compose (optional)

### Deploy with Docker

```bash
# 1. Build image
make docker-build

# 2. Configure
cp docker/.env.example docker/.env
# Fill in: DR keys, GitHub token, Telegram token

# 3. Start
make docker-up

# 4. Verify all components
curl http://192.168.1.51:3000/v1/status
```

### Deploy as systemd service

```bash
# 1. Build binary
make build-linux

# 2. Install
sudo cp bin/memoryhub-api-linux /usr/local/bin/memoryhub-api
sudo mkdir -p /etc/memoryhub /data/memoryhub
sudo cp config/memoryhub.config.yaml /etc/memoryhub/

# 3. Create systemd service
sudo tee /etc/systemd/system/memoryhub.service << 'EOF'
[Unit]
Description=memoryHub API Server
After=network.target
Wants=network.target

[Service]
Type=simple
User=memoryhub
Group=memoryhub
WorkingDirectory=/data/memoryhub
ExecStart=/usr/local/bin/memoryhub-api --config /etc/memoryhub/memoryhub.config.yaml
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/data/memoryhub

[Install]
WantedBy=multi-user.target
EOF

# 4. Enable and start
sudo systemctl daemon-reload
sudo systemctl enable memoryhub
sudo systemctl start memoryhub

# 5. Check status
sudo systemctl status memoryhub
curl http://localhost:3000/v1/health
```

### Backup timers (systemd)

```bash
# See ARCHITECTURE.md §4.9 Disaster Recovery schedule
sudo tee /etc/systemd/system/memoryhub-backup.timer << 'EOF'
[Unit]
Description=memoryHub incremental backup

[Timer]
OnCalendar=*-*-* 00/6:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl enable memoryhub-backup.timer
sudo systemctl start memoryhub-backup.timer
```

## Ports

| Port | Service | Description |
|------|---------|-------------|
| 3000 | API Hub | REST API — main entry point |
| 3100 | MCP Server | AI agent protocol (JSON-RPC 2.0) |
| 3200 | Health Dashboard | Monitoring UI |
| 6379 | Redis | Rate limiter state (optional) |

## Environment Variables

See `docker/.env.example` for the complete list.  
All secrets via ENV — never in config file.

| Variable | Required | Description |
|----------|----------|-------------|
| `MEMORYHUB_DR_ACCESS_KEY` | prod | Cloud storage access key |
| `MEMORYHUB_DR_SECRET_KEY` | prod | Cloud storage secret |
| `MEMORYHUB_DR_ENCRYPTION_KEY` | prod | AES-256 encryption key for backups |
| `MEMORYHUB_GITHUB_TOKEN` | prod | GitHub token for snapshots |
| `MEMORYHUB_TELEGRAM_TOKEN` | prod | Telegram bot token for alerts |
| `MEMORYHUB_ALERT_CHAT_ID` | prod | Telegram chat for alerts |

## Health Checks

```bash
# Liveness (for load balancers)
curl http://localhost:3000/v1/health

# Readiness (for orchestrators)
curl http://localhost:3000/v1/status | jq '.overall_health'

# Component details
curl http://localhost:3000/v1/status | jq '.components'

# Trust Pipeline queue depth
curl http://localhost:3000/v1/status | jq '.components.trust_pipeline.details.queue_depth'
```

## Operational Runbook

See `ARCHITECTURE.md Appendix B: Operational Runbook` for:
- Daily checks
- Trust Pipeline overflow response
- Integrity violation response
- Disk cleanup procedure

## Recovery

See `ARCHITECTURE.md §4.9` and `scripts/restore.sh`:
```bash
# List available snapshots
./scripts/restore.sh --list

# Restore to a specific point
./scripts/restore.sh --snapshot 2026-04-25T03:00:00Z

# Dry-run (test restore without overwriting)
./scripts/restore.sh --snapshot 2026-04-25T03:00:00Z --dry-run
```

**RTO:** < 15 minutes | **RPO:** < 6 hours
