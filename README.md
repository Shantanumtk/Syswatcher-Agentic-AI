# SysWatcher

AI-powered server health monitoring agent.
Ask it anything about your servers in plain English.

## Quick start

```bash
wget https://raw.githubusercontent.com/you/syswatcher/main/install.sh
chmod +x install.sh
./install.sh
```

That's it. Takes ~3 minutes.

## What it does

- Sweeps your servers every 5 minutes — silently stores everything
- You ask questions when you want: "is everything ok?", "did crons run?"
- Only notifies you for truly critical events (disk 95%+, OOM, etc.)
- Set up crons and alert rules via natural language
- Grafana dashboard pre-wired with CPU/memory/disk/network panels
- Works with multiple servers

## Daily use

Open **http://localhost:3001** and ask anything:

```
"is everything ok?"
"what's the CPU on prod-01?"
"did the backup cron run last night?"
"add an alert if /var disk goes above 80%"
"set up a cron to run /opt/backup.sh every day at 2am"
"show me what happened overnight"
```

## Manage

```bash
./manage.sh status                              # service health
./manage.sh add-server prod-02 1.2.3.4 ubuntu ~/.ssh/id_rsa
./manage.sh remove-server prod-02
./manage.sh sweep                               # manual sweep now
./manage.sh ask "is everything ok?"             # CLI query
./manage.sh logs agent                          # tail logs
./manage.sh backup                              # dump Postgres
./manage.sh stop / start / restart
```

## Access

| Service    | URL                        |
|------------|----------------------------|
| Chat UI    | http://localhost:3001       |
| Grafana    | http://localhost:3000       |
| Prometheus | http://localhost:9090       |
| API docs   | http://localhost:8000/docs  |

## Phases built

| Phase | What                        |
|-------|-----------------------------|
| 1     | Project skeleton            |
| 2     | Postgres schema + queries   |
| 3     | 30 @tool functions          |
| 4     | LangGraph agent             |
| 5     | FastAPI routes              |
| 6     | Scheduler (silent sweeps)   |
| 7     | Next.js chat UI             |
| 8     | Prometheus + Grafana        |
| 9     | install.sh + manage.sh      |
