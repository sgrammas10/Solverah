import os
from datetime import datetime

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
EMAIL_FROM = os.environ.get("EMAIL_FROM")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")


class EmailConfigError(RuntimeError):
    pass


def _ensure_config():
    if not EMAIL_FROM:
        raise EmailConfigError("EMAIL_FROM is not set")
    if not SENDGRID_API_KEY:
        raise EmailConfigError("SENDGRID_API_KEY is not set")


def send_confirmation_email(to_email: str, token: str) -> None:
    """Send a confirmation email with a link containing the token.

    The frontend should handle GET /confirm-email?token=... and POST that token to the backend.
    """
    _ensure_config()

    confirm_url = f"{FRONTEND_URL.rstrip('/')}/confirm-email?token={token}"

    subject = "Confirm your Solverah account"
    html_content = f"""
    <p>Welcome to Solverah!</p>
    <p>To complete your registration, please confirm your email address by clicking the link below:</p>
    <p><a href=\"{confirm_url}\">Confirm your email</a></p>
    <p>This link will expire in 48 hours.</p>
    <p>If you did not create this account, you can ignore this message.</p>
    """

    message = Mail(from_email=EMAIL_FROM, to_emails=to_email, subject=subject, html_content=html_content)

    sg = SendGridAPIClient(SENDGRID_API_KEY)
    resp = sg.send(message)

    # simple check: 2xx success from SendGrid
    if not (200 <= resp.status_code < 300):
        raise RuntimeError(f"SendGrid failed with status {resp.status_code}")
