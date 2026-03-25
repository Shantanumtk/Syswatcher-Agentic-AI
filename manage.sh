#!/bin/bash
set -e

CMD=${1:-help}

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }
info() { echo -e "  ${BLUE}→${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }

require_dir() {
  if [ ! -f "docker-compose.yml" ]; then
    echo "ERROR: Run manage.sh from inside the syswatcher/ directory"
    exit 1
  fi
}

# ── status ────────────────────────────────────────
cmd_status() {
  require_dir
  echo ""
  echo -e "${BOLD}SysWatcher service status${NC}"
  echo ""
  docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
  echo ""
  bash scripts/healthcheck.sh
}

# ── start / stop / restart ────────────────────────
cmd_start() {
  require_dir
  info "Starting SysWatcher..."
  docker compose up -d
  ok "Started"
}

cmd_stop() {
  require_dir
  info "Stopping SysWatcher..."
  docker compose down
  ok "Stopped"
}

cmd_restart() {
  require_dir
  local svc=${2:-""}
  if [ -n "$svc" ]; then
    info "Restarting $svc..."
    docker compose restart "$svc"
    ok "$svc restarted"
  else
    info "Restarting all services..."
    docker compose restart
    ok "All services restarted"
  fi
}

# ── logs ──────────────────────────────────────────
cmd_logs() {
  require_dir
  local svc=${2:-agent}
  docker compose logs -f --tail=100 "$svc"
}

# ── update ────────────────────────────────────────
cmd_update() {
  require_dir
  info "Pulling latest code..."
  git pull origin main
  info "Rebuilding images..."
  docker compose build --no-cache agent ui scheduler
  info "Restarting..."
  docker compose up -d
  ok "Update complete"
}

# ── add-server ────────────────────────────────────
cmd_add_server() {
  require_dir
  local NAME=$2 IP=$3 USER=$4 KEY=$5

  if [ -z "$NAME" ] || [ -z "$IP" ] || [ -z "$USER" ] || [ -z "$KEY" ]; then
    echo "Usage: ./manage.sh add-server <name> <ip> <ssh-user> <key-path>"
    echo "Example: ./manage.sh add-server prod-02 192.168.1.101 ubuntu ~/.ssh/id_rsa"
    exit 1
  fi

  echo ""
  info "Adding server: $NAME ($IP)"

  # Test SSH
  info "Testing SSH connection..."
  if ! ssh -i "$KEY" \
       -o StrictHostKeyChecking=no \
       -o ConnectTimeout=8 \
       -o BatchMode=yes \
       "$USER@$IP" "echo ok" &>/dev/null; then
    fail "Cannot SSH to $IP — check IP, user, and key"
    exit 1
  fi
  ok "SSH connection successful"

  # Install node_exporter
  info "Installing node_exporter on $NAME..."
  ssh -i "$KEY" \
      -o StrictHostKeyChecking=no \
      "$USER@$IP" "bash -s" < scripts/install_node_exporter.sh \
    && ok "node_exporter installed" \
    || { warn "node_exporter install failed — install manually on $NAME"; }

  # Add to syswatcher.conf
  if grep -q "^${NAME} *=" syswatcher.conf; then
    warn "$NAME already in syswatcher.conf — updating"
    python3 - << PYEOF
import re
with open('syswatcher.conf') as f:
    content = f.read()
content = re.sub(
    r'^${NAME}\s*=.*$',
    '${NAME} = ${IP}   ${USER}   ${KEY}',
    content, flags=re.MULTILINE
)
with open('syswatcher.conf', 'w') as f:
    f.write(content)
PYEOF
  else
    echo "${NAME} = ${IP}   ${USER}   ${KEY}" >> syswatcher.conf
    ok "Added $NAME to syswatcher.conf"
  fi

  # Regenerate configs
  info "Regenerating configs..."
  python3 scripts/generate_configs.py

  # Reload Prometheus (no restart needed)
  info "Reloading Prometheus scrape targets..."
  if curl -sf -X POST http://localhost:9090/-/reload &>/dev/null; then
    ok "Prometheus reloaded — $NAME now being scraped"
  else
    warn "Could not reload Prometheus — run: docker compose restart prometheus"
  fi

  # Register in agent DB
  info "Registering $NAME in agent database..."
  curl -sf -X POST http://localhost:8000/servers \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"${NAME}\",\"ip\":\"${IP}\",\"ssh_user\":\"${USER}\",\"ssh_key_path\":\"${KEY}\"}" \
    > /dev/null \
    && ok "$NAME registered in database" \
    || warn "Could not register in DB — agent may need restart"

  echo ""
  ok "$NAME is now being monitored"
  echo "  Metrics visible in Grafana server dropdown within 30 seconds"
  echo ""
}

# ── remove-server ─────────────────────────────────
cmd_remove_server() {
  require_dir
  local NAME=$2

  if [ -z "$NAME" ]; then
    echo "Usage: ./manage.sh remove-server <name>"
    exit 1
  fi

  warn "Removing $NAME from monitoring..."

  # Remove from syswatcher.conf
  python3 - << PYEOF
import re
with open('syswatcher.conf') as f:
    lines = f.readlines()
filtered = [l for l in lines if not l.strip().startswith('${NAME} =')]
with open('syswatcher.conf', 'w') as f:
    f.writelines(filtered)
print("  → Removed from syswatcher.conf")
PYEOF

  python3 scripts/generate_configs.py
  curl -sf -X POST http://localhost:9090/-/reload &>/dev/null || true
  ok "$NAME removed — will no longer be monitored"
}

# ── backup ────────────────────────────────────────
cmd_backup() {
  require_dir
  local TIMESTAMP
  TIMESTAMP=$(date +%Y%m%d_%H%M%S)
  local FILE="syswatcher_backup_${TIMESTAMP}.sql"

  info "Backing up Postgres to $FILE..."
  PG_USER=$(grep "^POSTGRES_USER=" .env | cut -d= -f2)
  PG_DB=$(grep "^POSTGRES_DB="   .env | cut -d= -f2)

  docker compose exec -T postgres \
    pg_dump -U "$PG_USER" "$PG_DB" > "$FILE"

  ok "Backup saved: $FILE ($(du -sh "$FILE" | cut -f1))"
}

# ── restore ───────────────────────────────────────
cmd_restore() {
  require_dir
  local FILE=$2
  if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
    echo "Usage: ./manage.sh restore <backup-file.sql>"
    exit 1
  fi
  warn "Restoring from $FILE — this will overwrite existing data"
  read -rp "  Type YES to confirm: " CONFIRM
  if [ "$CONFIRM" != "YES" ]; then
    echo "Aborted"
    exit 0
  fi

  PG_USER=$(grep "^POSTGRES_USER=" .env | cut -d= -f2)
  PG_DB=$(grep "^POSTGRES_DB="   .env | cut -d= -f2)
  docker compose exec -T postgres \
    psql -U "$PG_USER" "$PG_DB" < "$FILE"
  ok "Restore complete"
}

# ── sweep ─────────────────────────────────────────
cmd_sweep() {
  require_dir
  local SERVER=${2:-local}
  info "Running manual sweep on $SERVER..."
  RESULT=$(curl -sf -X POST http://localhost:8000/sweep \
    -H "Content-Type: application/json" \
    -d "{\"server_name\":\"${SERVER}\"}" 2>/dev/null || echo '{"error":"agent not responding"}')
  echo "$RESULT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print()
    print(f'  Severity: {d.get(\"severity\",\"unknown\")}')
    print()
    print('  Report:')
    for line in d.get('report','no report').split('\n'):
        print(f'  {line}')
except:
    print(sys.stdin.read())
"
}

# ── ask ───────────────────────────────────────────
cmd_ask() {
  require_dir
  local QUESTION="${*:2}"
  if [ -z "$QUESTION" ]; then
    echo "Usage: ./manage.sh ask <question>"
    echo "Example: ./manage.sh ask 'is everything ok?'"
    exit 1
  fi
  info "Asking: $QUESTION"
  RESULT=$(curl -sf -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" \
    -d "{\"question\":\"${QUESTION}\",\"server_name\":\"local\"}" \
    2>/dev/null || echo '{"error":"agent not responding"}')
  echo "$RESULT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print()
    sev = d.get('severity','')
    if sev == 'critical': print('  [CRITICAL]')
    elif sev == 'warn':   print('  [WARN]')
    for line in d.get('answer','no answer').split('\n'):
        print(f'  {line}')
except:
    print(sys.stdin.read())
" 2>/dev/null || echo "$RESULT"
  echo ""
}

# ── help ─────────────────────────────────────────
cmd_help() {
  echo ""
  echo -e "${BOLD}SysWatcher manage.sh${NC}"
  echo ""
  echo "  Service control:"
  echo "    ./manage.sh status                    — show service health"
  echo "    ./manage.sh start                     — start all services"
  echo "    ./manage.sh stop                      — stop all services"
  echo "    ./manage.sh restart [service]         — restart all or one service"
  echo "    ./manage.sh logs [service]            — tail logs (default: agent)"
  echo "    ./manage.sh update                    — pull latest + rebuild"
  echo ""
  echo "  Server management:"
  echo "    ./manage.sh add-server <n> <ip> <user> <key>  — add server"
  echo "    ./manage.sh remove-server <name>               — remove server"
  echo ""
  echo "  Data:"
  echo "    ./manage.sh backup                    — dump Postgres to .sql file"
  echo "    ./manage.sh restore <file.sql>        — restore from backup"
  echo ""
  echo "  Agent:"
  echo "    ./manage.sh sweep [server]            — run manual sweep"
  echo "    ./manage.sh ask <question>            — ask agent from CLI"
  echo ""
  echo "  Examples:"
  echo "    ./manage.sh add-server prod-02 192.168.1.101 ubuntu ~/.ssh/id_rsa"
  echo "    ./manage.sh ask 'did the backup cron run last night?'"
  echo "    ./manage.sh sweep prod-01"
  echo "    ./manage.sh logs scheduler"
  echo ""
}

# ── Router ────────────────────────────────────────
case "$CMD" in
  status)        cmd_status "$@" ;;
  start)         cmd_start "$@" ;;
  stop)          cmd_stop "$@" ;;
  restart)       cmd_restart "$@" ;;
  logs)          cmd_logs "$@" ;;
  update)        cmd_update "$@" ;;
  add-server)    cmd_add_server "$@" ;;
  remove-server) cmd_remove_server "$@" ;;
  backup)        cmd_backup "$@" ;;
  restore)       cmd_restore "$@" ;;
  sweep)         cmd_sweep "$@" ;;
  ask)           cmd_ask "$@" ;;
  help|--help|-h) cmd_help ;;
  *)
    fail "Unknown command: $CMD"
    cmd_help
    exit 1
    ;;
esac
