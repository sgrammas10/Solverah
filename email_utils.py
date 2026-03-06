import os
from datetime import datetime
import ssl
import smtplib
from email.message import EmailMessage

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
EMAIL_FROM = os.environ.get("EMAIL_FROM")

# Prefer SendGrid if available, otherwise fall back to SMTP (Sendamatic)
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "0") or 0)
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")


class EmailConfigError(RuntimeError):
    pass


def _build_confirm_url(token: str) -> str:
    return f"{FRONTEND_URL.rstrip('/')}/confirm-email?token={token}"


def _ensure_sendgrid_config():
    if not SENDGRID_API_KEY:
        raise EmailConfigError("SENDGRID_API_KEY is not set")
    if not EMAIL_FROM:
        raise EmailConfigError("EMAIL_FROM is not set")


def _ensure_smtp_config():
    if not (SMTP_HOST and SMTP_PORT and SMTP_USER and SMTP_PASSWORD and EMAIL_FROM):
        raise EmailConfigError("Missing SMTP configuration. Require SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM")


def _send_via_smtp(to_email: str, subject: str, html_content: str, plain_text: str = None) -> None:
    _ensure_smtp_config()

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email
    msg.set_content(plain_text or "Please view this message in an HTML-capable client.")
    msg.add_alternative(html_content, subtype="html")

    # Choose SSL or STARTTLS based on port heuristic (465 => SSL)
    try:
        if SMTP_PORT == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
    except Exception as e:
        raise RuntimeError(f"SMTP send failed: {e}")


def _send_via_sendgrid(to_email: str, subject: str, html_content: str) -> None:
    # lazy import to avoid requiring sendgrid in SMTP-only deployments
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
    except Exception as e:
        raise EmailConfigError("sendgrid package not available")

    if not SENDGRID_API_KEY or not EMAIL_FROM:
        raise EmailConfigError("SENDGRID_API_KEY or EMAIL_FROM missing")

    message = Mail(from_email=EMAIL_FROM, to_emails=to_email, subject=subject, html_content=html_content)
    sg = SendGridAPIClient(SENDGRID_API_KEY)
    resp = sg.send(message)
    if not (200 <= resp.status_code < 300):
        raise RuntimeError(f"SendGrid failed with status {resp.status_code}")


def send_confirmation_email(to_email: str, token: str) -> None:
    """Send a confirmation email. Uses SendGrid when `SENDGRID_API_KEY` is set; otherwise falls back to SMTP.

    Provide either SendGrid credentials (`SENDGRID_API_KEY`) or SMTP settings
    (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`) plus `EMAIL_FROM`.
    """
    confirm_url = _build_confirm_url(token)
    subject = "Confirm your Solverah account"
    html_content = f"""
    <p>Welcome to Solverah!</p>
    <p>To complete your registration, please confirm your email address by clicking the link below:</p>
    <p><a href=\"{confirm_url}\">Confirm your email</a></p>
    <p>This link will expire in 48 hours.</p>
    <p>If you did not create this account, you can ignore this message.</p>
    """
    plain_text = f"Visit {confirm_url} to confirm your email (link expires in 48 hours)."

    # Prefer SendGrid when configured
    if SENDGRID_API_KEY:
        _send_via_sendgrid(to_email, subject, html_content)
        return

    # Fallback to SMTP (Sendamatic)
    _send_via_smtp(to_email, subject, html_content, plain_text)
