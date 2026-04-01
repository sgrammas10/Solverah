# Send early access modal notification (no resume)
def send_early_access_modal_notification(
    first_name: str,
    last_name: str,
    email: str,
    phone: str,
    preferred_contact: str,
    career_journey: str,
) -> None:
    """Send an email to info@solverah.com with early access modal submission details."""
    if not RESEND_API_KEY:
        raise EmailConfigError("RESEND_API_KEY is not set")
    if not EMAIL_FROM:
        raise EmailConfigError("EMAIL_FROM is not set")

    html_content = f"""
    <div style='font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 32px; background: #0f172a; color: #e2e8f0; border-radius: 12px;'>
      <h2 style='color: #6ee7b7; margin-top: 0;'>New Early Access Modal Submission</h2>
      <ul style='color: #e2e8f0; font-size: 15px;'>
        <li><b>First Name:</b> {first_name}</li>
        <li><b>Last Name:</b> {last_name}</li>
        <li><b>Email:</b> {email}</li>
        <li><b>Phone:</b> {phone or 'N/A'}</li>
        <li><b>Preferred Contact:</b> {preferred_contact or 'N/A'}</li>
        <li><b>Career Journey:</b> {career_journey or 'N/A'}</li>
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
        "subject": "New Early Access Modal Submission",
        "html": html_content,
    }
    resend_lib.Emails.send(params)
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
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 32px; background: #faf8f5; color: #1a1a18; border-radius: 12px; border: 1px solid #e8e4dd;">
      <p style="font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #6a8f72; margin: 0 0 8px 0;">Verify your email</p>
      <h2 style="margin: 0 0 16px 0; font-size: 24px; font-weight: 700; color: #1a1a18;">Confirm your Solverah account</h2>
      <p style="color: #4a4a44; font-size: 15px; margin: 0 0 24px 0;">Enter this code on the verification page to activate your account:</p>
      <div style="font-size: 40px; font-weight: 700; letter-spacing: 10px; color: #1a3d25; background: #ffffff; padding: 20px; border-radius: 8px; border: 1px solid #e8e4dd; text-align: center; margin: 0 0 24px 0;">
        {code}
      </div>
      <p style="color: #7a7a72; font-size: 13px; margin: 0;">This code expires in 15 minutes. If you didn't create a Solverah account, you can safely ignore this email.</p>
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
