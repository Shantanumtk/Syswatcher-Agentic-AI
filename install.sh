#!/bin/bash
set -e

REPO_URL="https://github.com/Shantanumtk/Syswatcher-Agentic-AI"   # update with real URL
SYSWATCHER_DIR="syswatcher"

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

banner() {
  echo ""
  echo -e "${BOLD}╔══════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║          SysWatcher Installer                ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"
  echo ""
}

# ── Check OS ─────────────────────────────────────
detect_os() {
  if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "mac"
  elif [ -f /etc/debian_version ]; then
    echo "debian"
  elif [ -f /etc/redhat-release ]; then
    echo "redhat"
  else
    echo "unknown"
  fi
}

# ── Install Docker ────────────────────────────────
install_docker() {
  local os=$1
  if command -v docker &>/dev/null; then
    ok "Docker $(docker --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"
    return
  fi

  info "Installing Docker..."
  case $os in
    debian)
      curl -fsSL https://get.docker.com | sudo sh
      sudo usermod -aG docker "$USER"
      ok "Docker installed (re-login may be required)"
      ;;
    redhat)
      sudo yum install -y docker
      sudo systemctl start docker
      sudo systemctl enable docker
      sudo usermod -aG docker "$USER"
      ok "Docker installed"
      ;;
    mac)
      fail "Please install Docker Desktop: https://docs.docker.com/desktop/mac/install/"
      exit 1
      ;;
    *)
      fail "Unsupported OS — install Docker manually: https://docs.docker.com/engine/install/"
      exit 1
      ;;
  esac
}

# ── Install Docker Compose ────────────────────────
install_compose() {
  if docker compose version &>/dev/null; then
    ok "Docker Compose $(docker compose version --short)"
    return
  fi
  info "Installing Docker Compose plugin..."
  local os=$1
  case $os in
    debian)
      sudo apt-get install -y docker-compose-plugin 2>/dev/null \
        || sudo apt-get install -y docker-compose 2>/dev/null
      ;;
    redhat)
      sudo yum install -y docker-compose-plugin 2>/dev/null \
        || sudo yum install -y docker-compose 2>/dev/null
      ;;
    *)
      fail "Install Docker Compose manually: https://docs.docker.com/compose/install/"
      exit 1
      ;;
  esac
  ok "Docker Compose installed"
}

# ── Validate config ───────────────────────────────
validate_conf() {
  local conf="syswatcher.conf"
  local errors=0

  # OpenAI key
  local key
  key=$(grep "^OPENAI_API_KEY" "$conf" | cut -d= -f2 | tr -d ' ')
  if [ -z "$key" ] || [ "$key" = "YOUR_OPENAI_API_KEY_HERE" ]; then
    fail "OPENAI_API_KEY not set in $conf"
    errors=$((errors+1))
  else
    ok "OpenAI API key set"
  fi

  # Postgres password
  local pg_pass
  pg_pass=$(grep "^POSTGRES_PASSWORD" "$conf" | cut -d= -f2 | tr -d ' ')
  if [ -z "$pg_pass" ]; then
    fail "POSTGRES_PASSWORD not set in $conf"
    errors=$((errors+1))
  else
    ok "Postgres password set"
  fi

  return $errors
}

# ── Test SSH connection ───────────────────────────
test_ssh() {
  local name=$1 ip=$2 user=$3 key=$4
  if ssh -i "$key" \
       -o StrictHostKeyChecking=no \
       -o ConnectTimeout=8 \
       -o BatchMode=yes \
       "$user@$ip" "echo ok" &>/dev/null; then
    ok "SSH to $name ($ip)"
    return 0
  else
    warn "Cannot SSH to $name ($ip) — skipping node_exporter install"
    return 1
  fi
}

# ── Install node_exporter on remote server ────────
install_node_exporter_remote() {
  local name=$1 ip=$2 user=$3 key=$4
  info "Installing node_exporter on $name ($ip)..."
  ssh -i "$key" \
      -o StrictHostKeyChecking=no \
      -o ConnectTimeout=15 \
      "$user@$ip" "bash -s" < scripts/install_node_exporter.sh \
    && ok "node_exporter installed on $name" \
    || warn "node_exporter install failed on $name — install manually"
}

# ── Parse servers from conf ───────────────────────
get_servers() {
  grep -E "^[a-zA-Z0-9_-]+ *= *[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+" \
    syswatcher.conf 2>/dev/null | while read -r line; do
    name=$(echo "$line" | cut -d= -f1 | tr -d ' ')
    rest=$(echo "$line" | cut -d= -f2 | tr -d ' ')
    ip=$(echo "$rest"   | awk '{print $1}')
    user=$(echo "$rest" | awk '{print $2}')
    key=$(echo "$rest"  | awk '{print $3}')
    echo "$name|$ip|$user|$key"
  done
}

# ══════════════════════════════════════════════════
banner

OS=$(detect_os)
info "Detected OS: $OS"
echo ""

# ── Dependencies ─────────────────────────────────
echo -e "${BOLD}[1/6] Checking dependencies${NC}"
install_docker "$OS"
install_compose "$OS"

if ! command -v git &>/dev/null; then
  info "Installing git..."
  case $OS in
    debian) sudo apt-get install -y git ;;
    redhat) sudo yum install -y git ;;
  esac
fi
ok "git $(git --version | awk '{print $3}')"

if ! command -v python3 &>/dev/null; then
  info "Installing python3..."
  case $OS in
    debian) sudo apt-get install -y python3 ;;
    redhat) sudo yum install -y python3 ;;
  esac
fi
ok "python3 $(python3 --version | awk '{print $2}')"
echo ""

# ── Clone repo ────────────────────────────────────
echo -e "${BOLD}[2/6] Getting SysWatcher${NC}"
if [ -d "$SYSWATCHER_DIR" ]; then
  warn "Directory $SYSWATCHER_DIR already exists — pulling latest"
  cd "$SYSWATCHER_DIR"
  git pull origin main 2>/dev/null || true
else
  info "Cloning from $REPO_URL..."
  git clone "$REPO_URL" "$SYSWATCHER_DIR"
  cd "$SYSWATCHER_DIR"
fi
ok "SysWatcher source ready"
echo ""

# ── Config ───────────────────────────────────────
echo -e "${BOLD}[3/6] Configuration${NC}"
echo ""
echo "  Opening syswatcher.conf — fill in your details:"
echo "    • OPENAI_API_KEY — your OpenAI key (required)"
echo "    • Server IPs + SSH info (optional)"
echo "    • Notification settings (optional)"
echo ""
echo "  Press Enter to open the editor..."
read -r
"${EDITOR:-nano}" syswatcher.conf

echo ""
info "Validating config..."
if ! validate_conf; then
  echo ""
  fail "Fix the errors above in syswatcher.conf, then re-run install.sh"
  exit 1
fi
echo ""

# ── Generate configs ─────────────────────────────
echo -e "${BOLD}[4/6] Generating config files${NC}"
python3 scripts/generate_configs.py
ok ".env generated"
ok "prometheus.yml generated"
echo ""

# ── Setup remote servers ──────────────────────────
echo -e "${BOLD}[5/6] Setting up remote servers${NC}"
SERVER_COUNT=0
while IFS='|' read -r name ip user key; do
  SERVER_COUNT=$((SERVER_COUNT+1))
  info "Server: $name ($ip)"
  if test_ssh "$name" "$ip" "$user" "$key"; then
    install_node_exporter_remote "$name" "$ip" "$user" "$key"
  fi
done < <(get_servers)

if [ "$SERVER_COUNT" -eq 0 ]; then
  ok "No remote servers configured — monitoring local only"
fi
echo ""

# ── Start services ────────────────────────────────
echo -e "${BOLD}[6/6] Starting SysWatcher${NC}"

info "Pulling Docker images (this may take a few minutes)..."
docker compose pull --quiet
ok "Images pulled"

info "Starting services..."
docker compose up -d
echo ""

info "Waiting for services to become healthy..."
WAIT=0
MAX_WAIT=120
while [ $WAIT -lt $MAX_WAIT ]; do
  AGENT_UP=$(curl -sf http://localhost:8000/health 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('database','no'))" \
    2>/dev/null || echo "no")
  if [ "$AGENT_UP" = "ok" ]; then
    break
  fi
  sleep 5
  WAIT=$((WAIT+5))
  echo -ne "  Waited ${WAIT}s...\r"
done

if [ "$AGENT_UP" != "ok" ]; then
  warn "Services taking longer than expected"
  warn "Check: docker compose logs agent"
else
  ok "All services healthy"
fi

# ── Init Grafana token ────────────────────────────
info "Initialising Grafana service account..."
GRAFANA_URL=http://localhost:3000 \
GRAFANA_ADMIN_PASSWORD="$(grep GRAFANA_ADMIN_PASSWORD .env | cut -d= -f2)" \
python3 scripts/grafana_init.py 2>/dev/null \
  && ok "Grafana token created" \
  || warn "Grafana init failed — run: python3 scripts/grafana_init.py"

# Restart agent to pick up token
docker compose restart agent scheduler &>/dev/null
ok "Agent restarted with Grafana token"

# ── Service check ─────────────────────────────────
echo ""
bash scripts/healthcheck.sh

# ── Done ─────────────────────────────────────────
GRAFANA_PASS=$(grep GRAFANA_ADMIN_PASSWORD .env | cut -d= -f2)
API_PORT=$(grep "^API_PORT=" .env | cut -d= -f2 || echo "8000")
UI_PORT=$(grep "^UI_PORT="  .env | cut -d= -f2 || echo "3001")

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  SysWatcher is ready!${NC}"
echo ""
echo -e "  ${GREEN}Chat UI${NC}    →  http://localhost:${UI_PORT}"
echo -e "  ${YELLOW}Grafana${NC}    →  http://localhost:3000  (admin / ${GRAFANA_PASS})"
echo -e "  ${BLUE}Prometheus${NC} →  http://localhost:9090"
echo -e "  ${BLUE}API docs${NC}   →  http://localhost:${API_PORT}/docs"
echo ""
echo "  Manage your installation:"
echo "    ./manage.sh status          — check all services"
echo "    ./manage.sh add-server ...  — add a new server"
echo "    ./manage.sh logs agent      — tail agent logs"
echo "    ./manage.sh backup          — backup Postgres"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
