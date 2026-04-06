"""Email delivery channel."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage


def send_email(
    payload: dict,
    *,
    smtp_host: str,
    smtp_port: int = 587,
    username: str | None = None,
    password: str | None = None,
    from_address: str,
    to: list[str],
) -> None:
    """Send an alert email via SMTP.

    The email subject falls back to a generic string when *payload* has no
    ``title`` key (e.g. when GitHub burst alerts arrive without one).
    """
    subject = payload.get("title") or "AI Infra Radar alert"
    body_lines = [f"Score: {payload.get('score', 'N/A')}"]
    if reason := payload.get("reason"):
        body_lines.append(f"Reason: {reason}")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_address
    msg["To"] = ", ".join(to)
    msg.set_content("\n".join(body_lines))

    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(msg)
