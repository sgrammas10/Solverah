"""Manual SMTP smoke test — run by hand, not part of the pytest suite.

Every credential is read from the environment with no fallback on purpose.
This script previously carried live Sendamatic credentials as
``os.environ.get(...)`` defaults, which committed them to git history; the
literals are gone and the values below must come from your shell or ``.env``.

    SMTP_USER=... SMTP_PASSWORD=... EMAIL_FROM=... TEST_TO=... python send_test.py
"""

import os, ssl, smtplib
from email.message import EmailMessage

# Non-secret connection defaults; override via environment if the host changes.
SMTP_HOST = os.environ.get("SMTP_HOST", "in.smtp.sendamatic.net")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))

SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
EMAIL_FROM = os.environ.get("EMAIL_FROM")  # must be a verified sender
TO = os.environ.get("TEST_TO")

_missing = [
    name
    for name, value in (
        ("SMTP_USER", SMTP_USER),
        ("SMTP_PASSWORD", SMTP_PASSWORD),
        ("EMAIL_FROM", EMAIL_FROM),
        ("TEST_TO", TO),
    )
    if not value
]
if _missing:
    raise SystemExit(
        "Set %s in the environment before running" % ", ".join(_missing)
    )

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
