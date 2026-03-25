import os
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from langchain_core.tools import tool

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_TO      = os.getenv("ALERT_EMAIL_TO", "")

@tool
def send_slack_alert(message: str, severity: str, metric: str = "") -> dict:
    """Send a Slack alert. Call ONLY for critical severity events.
    Do NOT call for info or warn — those are stored silently.
    severity: 'warn' | 'critical'
    metric:   optional metric name e.g. 'disk_usage_pct'
    """
    if not SLACK_WEBHOOK:
        return {"status": "skipped", "reason": "SLACK_WEBHOOK_URL not configured"}

    color = {"warn": "#ff9800", "critical": "#e53935"}.get(severity, "#888")
    emoji = {"warn": ":warning:", "critical": ":rotating_light:"}.get(severity, ":information_source:")

    payload = {
        "attachments": [{
            "color": color,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{emoji} *SysWatcher {severity.upper()}*\n{message}"
                    }
                },
                {
                    "type": "context",
                    "elements": [{
                        "type": "mrkdwn",
                        "text": (
                            f"Severity: `{severity}`"
                            + (f" | Metric: `{metric}`" if metric else "")
                            + f" | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                    }]
                }
            ]
        }]
    }

    try:
        r = requests.post(SLACK_WEBHOOK, json=payload, timeout=5)
        return {"channel": "slack", "status": "sent" if r.status_code == 200 else "failed", "http_code": r.status_code}
    except Exception as e:
        return {"channel": "slack", "status": "error", "error": str(e)}

@tool
def send_email_alert(subject: str, body: str, severity: str) -> dict:
    """Send an email alert. Call ONLY for critical severity events.
    Do NOT call for info or warn.
    subject:  short description e.g. 'Disk at 96% on prod-01'
    body:     detailed message
    severity: 'critical' | 'warn'
    """
    if not all([SMTP_USER, SMTP_PASSWORD, EMAIL_TO]):
        return {"status": "skipped", "reason": "Email not configured in .env"}

    recipients = [r.strip() for r in EMAIL_TO.split(",")]
    prefix = {"critical": "[CRITICAL]", "warn": "[WARN]"}.get(severity, "[INFO]")
    full_subject = f"{prefix} SysWatcher: {subject}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = full_subject
    msg["From"]    = SMTP_USER
    msg["To"]      = ", ".join(recipients)

    text = f"SysWatcher Alert\n{'='*40}\nSeverity: {severity.upper()}\nTime: {datetime.now()}\n{'='*40}\n\n{body}"
    msg.attach(MIMEText(text, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.ehlo()
            s.starttls()
            s.login(SMTP_USER, SMTP_PASSWORD)
            s.sendmail(SMTP_USER, recipients, msg.as_string())
        return {"channel": "email", "status": "sent", "recipients": recipients}
    except Exception as e:
        return {"channel": "email", "status": "error", "error": str(e)}
