"""Email notification channel with pluggable backends.

Backends:
- console: prints the email to stdout (development/default)
- disabled: silently drops the email
- smtp: sends via configured SMTP server

No real email is sent when EMAIL_BACKEND is not "smtp" or when SMTP
configuration is incomplete.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

from app.config import get_settings


settings = get_settings()


@dataclass
class EmailResult:
    """Result of an email send attempt."""

    success: bool
    backend: str
    message_id: Optional[str] = None
    error: Optional[str] = None


class BaseEmailBackend:
    """Abstract email backend."""

    name: str = "base"

    async def send(
        self,
        *,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> EmailResult:
        raise NotImplementedError


class ConsoleEmailBackend(BaseEmailBackend):
    """Logs the email to stdout. Development-safe."""

    name = "console"

    async def send(
        self,
        *,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> EmailResult:
        sender = f"{from_name or settings.EMAIL_FROM_NAME} <{from_email or settings.EMAIL_FROM}>"
        print("=" * 60)
        print(f"[EMAIL - CONSOLE BACKEND]")
        print(f"From: {sender}")
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print("-" * 60)
        print(body_text)
        print("=" * 60)
        return EmailResult(success=True, backend=self.name, message_id="console")


class DisabledEmailBackend(BaseEmailBackend):
    """Silently drops the email."""

    name = "disabled"

    async def send(
        self,
        *,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> EmailResult:
        return EmailResult(success=False, backend=self.name, error="Notifications disabled")


class SmtpEmailBackend(BaseEmailBackend):
    """Sends email via SMTP when fully configured."""

    name = "smtp"

    async def send(
        self,
        *,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> EmailResult:
        if not settings.SMTP_HOST or not settings.SMTP_USER:
            return EmailResult(
                success=False,
                backend=self.name,
                error="SMTP not configured (missing host or user)",
            )

        sender = from_email or settings.EMAIL_FROM
        msg = EmailMessage()
        msg["From"] = f"{from_name or settings.EMAIL_FROM_NAME} <{sender}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body_text)
        if body_html:
            msg.add_alternative(body_html, subtype="html")

        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
            return EmailResult(success=True, backend=self.name, message_id=msg["Message-ID"])
        except Exception as exc:  # pragma: no cover - SMTP failures are environment-specific
            return EmailResult(success=False, backend=self.name, error=str(exc))


def _get_backend() -> BaseEmailBackend:
    """Return the configured email backend."""
    backend_name = (settings.EMAIL_BACKEND or "console").lower()
    if backend_name == "smtp":
        return SmtpEmailBackend()
    if backend_name == "disabled":
        return DisabledEmailBackend()
    return ConsoleEmailBackend()


async def send_email(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
) -> EmailResult:
    """Send an email using the configured backend."""
    backend = _get_backend()
    return await backend.send(
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        from_email=from_email,
        from_name=from_name,
    )
