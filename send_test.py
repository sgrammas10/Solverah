import os, ssl, smtplib
from email.message import EmailMessage

SMTP_HOST = os.environ.get("SMTP_HOST", "in.smtp.sendamatic.net")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "26552679d3b55356bee4df15bf3bf306-737")  # set in environment
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "0468248b7eda4b83797fd09620b69334e9cb")  # set in environment
EMAIL_FROM = os.environ.get("EMAIL_FROM", "no-reply@solverah.google.com")  # must be a verified sender
TO = os.environ.get("TEST_TO", "will.gaca@gmail.com")

if not (SMTP_USER and SMTP_PASSWORD and EMAIL_FROM):
    raise SystemExit("Set SMTP_USER, SMTP_PASSWORD, and EMAIL_FROM in environment before running")

msg = EmailMessage()
msg["Subject"] = "SMTP test"
msg["From"] = EMAIL_FROM
msg["To"] = TO
msg.set_content("Test")
msg.add_alternative("<p>Test</p>", subtype="html")

ctx = ssl.create_default_context()
with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
    s.ehlo()
    s.starttls(context=ctx)
    s.ehlo()
    s.login(SMTP_USER, SMTP_PASSWORD)
    s.send_message(msg)
print("sent")