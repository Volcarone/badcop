"""Sending: a real SMTP mailer and a dry-run mailer that only records."""
from __future__ import annotations

import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from .config import Config


class SendError(RuntimeError):
    pass


@dataclass
class Message:
    to: str
    subject: str
    body: str
    headers: dict[str, str] = field(default_factory=dict)


def build_email(msg: Message, config: Config) -> EmailMessage:
    email = EmailMessage()
    email["From"] = formataddr((config.sender_name, config.sender_email))
    email["To"] = msg.to
    email["Reply-To"] = config.reply_to
    email["Subject"] = msg.subject
    email["Message-ID"] = make_msgid(domain=config.sender_email.rsplit("@", 1)[-1])
    email["X-Mailer"] = "BadCop"
    for k, v in msg.headers.items():
        email[k] = v
    email.set_content(msg.body)
    return email


class DryRunMailer:
    """Records what would be sent. Used by --dry-run, preview, and the tests."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, msg: Message, config: Config) -> str:
        email = build_email(msg, config)
        self.sent.append(email)
        return email["Message-ID"]


class SmtpMailer:
    def send(self, msg: Message, config: Config) -> str:
        email = build_email(msg, config)
        try:
            with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as smtp:
                if config.smtp_starttls:
                    smtp.starttls()
                if config.smtp_username:
                    password = config.smtp_password
                    if password is None:
                        raise SendError(f"SMTP password not found in environment variable {config.smtp_password_env}")
                    smtp.login(config.smtp_username, password)
                smtp.send_message(email)
        except (smtplib.SMTPException, OSError) as e:
            raise SendError(f"SMTP error sending to {msg.to}: {e}") from e
        return email["Message-ID"]
