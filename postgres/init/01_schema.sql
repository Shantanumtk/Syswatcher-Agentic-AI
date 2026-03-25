-- ═══════════════════════════════════════════════
-- SysWatcher — full Postgres schema
-- Runs automatically on first container start
-- ═══════════════════════════════════════════════

-- ── Servers ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS servers (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(100) UNIQUE NOT NULL,
    ip           VARCHAR(45)  NOT NULL,
    ssh_user     VARCHAR(100),
    ssh_key_path VARCHAR(500),
    active       BOOLEAN DEFAULT TRUE,
    added_at     TIMESTAMPTZ DEFAULT NOW()
);

-- ── Sweep runs ────────────────────────────────────
-- One row per full sweep execution
CREATE TABLE IF NOT EXISTS sweep_runs (
    id           SERIAL PRIMARY KEY,
    server_name  VARCHAR(100) NOT NULL,
    started_at   TIMESTAMPTZ DEFAULT NOW(),
    finished_at  TIMESTAMPTZ,
    duration_ms  INTEGER,
    overall      VARCHAR(20)  DEFAULT 'healthy',  -- healthy | warn | critical
    summary      TEXT,
    event_count  INTEGER DEFAULT 0
);

-- ── Events ───────────────────────────────────────
-- Every observation from every sweep
CREATE TABLE IF NOT EXISTS events (
    id           SERIAL PRIMARY KEY,
    server_name  VARCHAR(100) NOT NULL,
    sweep_id     INTEGER REFERENCES sweep_runs(id) ON DELETE SET NULL,
    timestamp    TIMESTAMPTZ  DEFAULT NOW(),
    severity     VARCHAR(20)  NOT NULL,           -- info | warn | critical
    category     VARCHAR(50)  NOT NULL,           -- system | cron | prometheus | logs | network
    metric       VARCHAR(200),                    -- e.g. cpu_usage_pct, disk_/var
    value        NUMERIC(10,2),                   -- numeric value if applicable
    message      TEXT         NOT NULL,
    raw          JSONB,                           -- full tool output
    notified     BOOLEAN      DEFAULT FALSE       -- true if Slack/email sent
);

-- ── Alert rules ───────────────────────────────────
-- Created via natural language: "alert me if disk > 80%"
CREATE TABLE IF NOT EXISTS alert_rules (
    id              SERIAL PRIMARY KEY,
    server_name     VARCHAR(100),                 -- NULL = applies to all servers
    metric          VARCHAR(200) NOT NULL,
    condition       VARCHAR(10)  NOT NULL,        -- gt | lt | eq
    threshold       NUMERIC(10,2) NOT NULL,
    severity        VARCHAR(20)  NOT NULL,        -- warn | critical
    notify_slack    BOOLEAN DEFAULT FALSE,
    notify_email    BOOLEAN DEFAULT FALSE,
    description     TEXT,
    active          BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    created_by      VARCHAR(100) DEFAULT 'user'
);

-- ── Cron registry ─────────────────────────────────
-- Crons SysWatcher knows about and monitors
CREATE TABLE IF NOT EXISTS cron_registry (
    id              SERIAL PRIMARY KEY,
    server_name     VARCHAR(100) NOT NULL,
    name            VARCHAR(200) NOT NULL,
    schedule        VARCHAR(100) NOT NULL,        -- cron expression: 0 2 * * *
    command         TEXT        NOT NULL,
    log_path        VARCHAR(500),
    active          BOOLEAN DEFAULT TRUE,
    last_run_at     TIMESTAMPTZ,
    last_exit_code  INTEGER,
    last_status     VARCHAR(20),                  -- ok | failed | missed
    fail_count      INTEGER DEFAULT 0,
    added_at        TIMESTAMPTZ DEFAULT NOW(),
    added_by        VARCHAR(100) DEFAULT 'user',  -- user | agent
    UNIQUE(server_name, name)
);

-- ── Notifications log ─────────────────────────────
-- Audit trail of every Slack/email sent
CREATE TABLE IF NOT EXISTS notifications (
    id           SERIAL PRIMARY KEY,
    server_name  VARCHAR(100),
    event_id     INTEGER REFERENCES events(id) ON DELETE SET NULL,
    channel      VARCHAR(50)  NOT NULL,           -- slack | email | pagerduty
    severity     VARCHAR(20)  NOT NULL,
    message      TEXT,
    sent_at      TIMESTAMPTZ  DEFAULT NOW(),
    success      BOOLEAN      DEFAULT TRUE,
    error        TEXT
);

-- ── Chat sessions ─────────────────────────────────
-- Conversation history per thread_id
CREATE TABLE IF NOT EXISTS chat_sessions (
    id           SERIAL PRIMARY KEY,
    thread_id    VARCHAR(200) UNIQUE NOT NULL,
    server_name  VARCHAR(100),
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    last_active  TIMESTAMPTZ DEFAULT NOW(),
    message_count INTEGER DEFAULT 0
);

-- ═══════════════════════════════════════════════
-- Indexes — for fast queries on large event tables
-- ═══════════════════════════════════════════════
CREATE INDEX IF NOT EXISTS idx_events_server     ON events(server_name);
CREATE INDEX IF NOT EXISTS idx_events_timestamp  ON events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_severity   ON events(severity);
CREATE INDEX IF NOT EXISTS idx_events_category   ON events(category);
CREATE INDEX IF NOT EXISTS idx_sweep_server      ON sweep_runs(server_name);
CREATE INDEX IF NOT EXISTS idx_sweep_started     ON sweep_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_cron_server       ON cron_registry(server_name);
CREATE INDEX IF NOT EXISTS idx_alert_server      ON alert_rules(server_name);

-- ═══════════════════════════════════════════════
-- Seed data — default alert rules
-- ═══════════════════════════════════════════════
INSERT INTO alert_rules (metric, condition, threshold, severity, notify_slack, notify_email, description)
VALUES
    ('cpu_usage_pct',    'gt', 98.0, 'critical', true,  true,  'CPU above 98% sustained'),
    ('memory_usage_pct', 'gt', 95.0, 'critical', true,  true,  'Memory above 95%'),
    ('disk_usage_pct',   'gt', 95.0, 'critical', true,  true,  'Disk above 95%'),
    ('disk_usage_pct',   'gt', 80.0, 'warn',     false, false, 'Disk above 80% - store only'),
    ('cpu_usage_pct',    'gt', 85.0, 'warn',     false, false, 'CPU above 85% - store only'),
    ('memory_usage_pct', 'gt', 85.0, 'warn',     false, false, 'Memory above 85% - store only')
ON CONFLICT DO NOTHING;

SELECT 'SysWatcher schema ready' AS status;
