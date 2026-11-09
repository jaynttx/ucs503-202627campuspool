"""Send sign-in and notification emails through SMTP or Brevo."""
import json
import logging
import os
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from .config import settings

log = logging.getLogger("campuspool")


class MailError(Exception):
    pass


def _send_smtp(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user or "no-reply@localhost"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user and settings.smtp_password:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except Exception as exc:
        log.error("SMTP delivery failed: %s", type(exc).__name__)
        raise MailError("Could not send the email. Try again in a moment.") from exc


def _send_brevo(to: str, subject: str, body: str) -> None:
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("MAIL_FROM_EMAIL")
    if not api_key or not sender_email:
        raise MailError("Email delivery is not configured on this server.")

    payload = {
        "sender": {
            "name": os.getenv("MAIL_FROM_NAME", "CampusPool"),
            "email": sender_email,
        },
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body,
    }
    request = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20):
            pass
    except urllib.error.HTTPError as exc:
        log.error("Brevo delivery failed with HTTP status %s", exc.code)
        raise MailError("Could not send the email. Check the email settings and try again.") from exc
    except Exception as exc:
        log.error("Brevo delivery failed: %s", type(exc).__name__)
        raise MailError("Could not send the email. Try again in a moment.") from exc


def _provider_configured() -> bool:
    return bool(
        settings.smtp_host
        or (os.getenv("BREVO_API_KEY") and os.getenv("MAIL_FROM_EMAIL"))
    )


def _send_configured(to: str, subject: str, body: str) -> None:
    if settings.smtp_host:
        _send_smtp(to, subject, body)
    else:
        _send_brevo(to, subject, body)


def deliver_otp(email: str, code: str) -> str:
    """Returns how the code was delivered: 'email' or 'console'."""
    subject = "Your CampusPool sign-in code"
    body = (
        f"Your CampusPool code is {code}.\n\n"
        f"It expires in {settings.otp_ttl_minutes} minutes. "
        "If you did not ask for it, you can ignore this email.\n"
    )

    if _provider_configured():
        _send_configured(email, subject, body)
        return "email"

    if settings.environment == "development":
        log.warning("DEVELOPMENT ONLY: sign-in code for %s is %s", email, code)
        return "console"

    raise MailError("Email delivery is not configured on this server.")


def send_notification_email(email: str, subject: str, body: str) -> str:
    """Send a reminder email using the configured provider."""
    if _provider_configured():
        _send_configured(email, subject, body)
        return "email"

    if settings.environment == "development":
        log.warning(
            "DEVELOPMENT ONLY: email to %s | %s | %s",
            email,
            subject,
            body.replace("\n", " "),
        )
        return "console"

    raise MailError("Email delivery is not configured on this server.")
