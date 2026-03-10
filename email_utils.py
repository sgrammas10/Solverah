# Send early access intake notification to info@solverah.com
def send_intake_notification(
    first_name: str,
    last_name: str,
    email: str,
    state: str,
    phone: str,
    linkedin_url: str,
    portfolio_url: str,
    object_key: str,
    mime: str,
    size: int,
) -> None:
    """Send an email to info@solverah.com with early access submission details."""
    if not RESEND_API_KEY:
        raise EmailConfigError("RESEND_API_KEY is not set")
    if not EMAIL_FROM:
        raise EmailConfigError("EMAIL_FROM is not set")

    html_content = f"""
    <div style='font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 32px; background: #0f172a; color: #e2e8f0; border-radius: 12px;'>
      <h2 style='color: #6ee7b7; margin-top: 0;'>New Early Access Submission</h2>
      <ul style='color: #e2e8f0; font-size: 15px;'>
        <li><b>First Name:</b> {first_name}</li>
        <li><b>Last Name:</b> {last_name}</li>
        <li><b>Email:</b> {email}</li>
        <li><b>State:</b> {state}</li>
        <li><b>Phone:</b> {phone or 'N/A'}</li>
        <li><b>LinkedIn:</b> {linkedin_url or 'N/A'}</li>
        <li><b>Portfolio:</b> {portfolio_url or 'N/A'}</li>
        <li><b>Resume Key:</b> {object_key}</li>
        <li><b>Resume MIME:</b> {mime}</li>
        <li><b>Resume Size:</b> {size} bytes</li>
      </ul>
    </div>
    """

    try:
        import resend as resend_lib
    except ImportError:
        raise EmailConfigError("resend package is not installed. Run: pip install resend")

    resend_lib.api_key = RESEND_API_KEY
    params = {
        "from": EMAIL_FROM,
        "to": ["info@solverah.com"],
        "subject": "New Early Access Submission",
        "html": html_content,
    }
    resend_lib.Emails.send(params)
import os

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "no-reply@solverah.com")


class EmailConfigError(RuntimeError):
    pass


def send_verification_email(to_email: str, code: str) -> None:
    """Send a 6-digit verification code email via Resend."""
    if not RESEND_API_KEY:
        raise EmailConfigError("RESEND_API_KEY is not set")
    if not EMAIL_FROM:
        raise EmailConfigError("EMAIL_FROM is not set")

    html_content = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 32px; background: #0f172a; color: #e2e8f0; border-radius: 12px;">
      <h2 style="color: #6ee7b7; margin-top: 0;">Verify your Solverah account</h2>
      <p>Enter this code to complete your registration:</p>
      <div style="font-size: 40px; font-weight: bold; letter-spacing: 10px; color: #ffffff; background: #1e293b; padding: 20px; border-radius: 8px; text-align: center; margin: 24px 0;">
        {code}
      </div>
      <p style="color: #94a3b8; font-size: 14px;">This code expires in 15 minutes. If you did not create this account, you can ignore this message.</p>
    </div>
    """

    try:
        import resend as resend_lib
    except ImportError:
        raise EmailConfigError("resend package is not installed. Run: pip install resend")

    resend_lib.api_key = RESEND_API_KEY
    params: resend_lib.Emails.SendParams = {
        "from": EMAIL_FROM,
        "to": [to_email],
        "subject": "Your Solverah verification code",
        "html": html_content,
    }
    resend_lib.Emails.send(params)


# Backward-compatible alias used by existing app.py imports
def send_confirmation_email(to_email: str, token: str) -> None:
    send_verification_email(to_email, token)
