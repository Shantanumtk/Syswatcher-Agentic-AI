from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # LLM — OpenAI
    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # Postgres
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "syswatcher"
    postgres_password: str = "syswatcher123"
    postgres_db: str = "syswatcher"
    database_url: str = ""

    # Observability
    prometheus_url: str = "http://prometheus:9090"
    grafana_url: str = "http://grafana:3000"
    grafana_token: str = ""

    # Notifications
    slack_webhook_url: str = ""
    alert_email_to: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # Sweep
    sweep_interval_min: int = 5

    # Thresholds
    critical_cpu_pct: float = 98.0
    critical_memory_pct: float = 95.0
    critical_disk_pct: float = 95.0
    critical_cron_fails: int = 3

    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
