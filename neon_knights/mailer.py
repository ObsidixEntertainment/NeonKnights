from __future__ import annotations

import os
import re
import smtplib
import time
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path


@dataclass(frozen=True)
class MailResult:
    recipient: str
    subject: str
    sent: bool
    detail: str
    code: str | None = None
    purpose: str | None = None


def send_mail(recipient: str, subject: str, body: str) -> MailResult:
    recipient = recipient.strip().lower()
    host = os.environ.get("NEON_KNIGHTS_SMTP_HOST", "").strip()
    sender = os.environ.get("NEON_KNIGHTS_MAIL_FROM", "Neon Knights <no-reply@neonknights.local>").strip()

    if host:
        return send_smtp(recipient, sender, subject, body, host)
    return write_outbox(recipient, sender, subject, body)


def send_smtp(recipient: str, sender: str, subject: str, body: str, host: str) -> MailResult:
    port = int(os.environ.get("NEON_KNIGHTS_SMTP_PORT", "587"))
    username = os.environ.get("NEON_KNIGHTS_SMTP_USERNAME", "").strip()
    password = os.environ.get("NEON_KNIGHTS_SMTP_PASSWORD", "")
    use_tls = os.environ.get("NEON_KNIGHTS_SMTP_TLS", "1") != "0"

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(host, port, timeout=20) as smtp:
        if use_tls:
            smtp.starttls()
        if username:
            smtp.login(username, password)
        smtp.send_message(message)

    return MailResult(recipient, subject, True, f"Sent to {recipient}.")


def write_outbox(recipient: str, sender: str, subject: str, body: str) -> MailResult:
    outbox = Path(os.environ.get("NEON_KNIGHTS_MAIL_OUTBOX", "mail_outbox"))
    outbox.mkdir(parents=True, exist_ok=True)
    safe_recipient = re.sub(r"[^a-zA-Z0-9_.@-]+", "_", recipient)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    filename = outbox / f"{stamp}-{safe_recipient}.eml"

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    filename.write_text(message.as_string(), encoding="utf-8")

    return MailResult(
        recipient,
        subject,
        False,
        f"SMTP is not configured; wrote email to {filename}.",
    )
