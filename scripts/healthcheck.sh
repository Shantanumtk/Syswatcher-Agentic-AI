#!/bin/bash
# Check all SysWatcher services

check() {
  local name=$1
  local url=$2
  if curl -sf "$url" > /dev/null 2>&1; then
    echo "  ✓ $name"
    return 0
  else
    echo "  ✗ $name — not responding at $url"
    return 1
  fi
}

echo ""
echo "SysWatcher service health:"
check "Agent API"        "http://localhost:8000/health"
check "Prometheus"       "http://localhost:9090/-/healthy"
check "Grafana"          "http://localhost:3000/api/health"
check "Node Exporter"    "http://localhost:9100/metrics"
check "Chat UI"          "http://localhost:3001"
echo ""

# Postgres via agent health endpoint
AGENT_HEALTH=$(curl -sf http://localhost:8000/health 2>/dev/null || echo '{}')
DB_STATUS=$(echo "$AGENT_HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('database','unknown'))" 2>/dev/null || echo "unknown")
if [ "$DB_STATUS" = "ok" ]; then
  echo "  ✓ Postgres (via agent health)"
else
  echo "  ✗ Postgres — agent reports: $DB_STATUS"
fi

# Prometheus targets
echo ""
echo "Prometheus scrape targets:"
curl -sf "http://localhost:9090/api/v1/targets" 2>/dev/null \
  | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    targets = d.get('data', {}).get('activeTargets', [])
    for t in targets:
        state  = t.get('health', '?')
        labels = t.get('labels', {})
        job    = labels.get('job', '?')
        inst   = labels.get('instance', '?')
        icon   = '✓' if state == 'up' else '✗'
        print(f'  {icon} {job} ({inst}) — {state}')
except Exception as e:
    print(f'  could not parse targets: {e}')
" 2>/dev/null || echo "  could not reach Prometheus"

echo ""
echo "Access:"
echo "  Chat UI    →  http://localhost:3001"
echo "  Grafana    →  http://localhost:3000  (admin / \$(grep GRAFANA_ADMIN_PASSWORD .env | cut -d= -f2))"
echo "  Prometheus →  http://localhost:9090"
echo "  API docs   →  http://localhost:8000/docs"
echo ""
