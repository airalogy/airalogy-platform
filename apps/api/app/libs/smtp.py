"""Deliver a plain-text message using the deployment SMTP configuration."""

import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlparse
from uuid import UUID

from app.config import config


def send_smtp_message(
    *,
    delivery_id: UUID,
    recipient: str,
    subject: str,
    body: str,
) -> None:
    message = EmailMessage()
    message["From"] = config.SMTP_FROM_ADDRESS
    message["To"] = recipient
    message["Subject"] = subject
    hostname = urlparse(config.SITE_URL).hostname or "localhost"
    message["Message-ID"] = f"<{delivery_id}@{hostname}>"
    message.set_content(body)

    context = ssl.create_default_context()
    if config.SMTP_SECURITY == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            config.SMTP_HOST,
            config.SMTP_PORT,
            timeout=config.SMTP_TIMEOUT_SECONDS,
            context=context,
        )
    else:
        client = smtplib.SMTP(
            config.SMTP_HOST,
            config.SMTP_PORT,
            timeout=config.SMTP_TIMEOUT_SECONDS,
        )
    with client:
        client.ehlo()
        if config.SMTP_SECURITY == "starttls":
            client.starttls(context=context)
            client.ehlo()
        if config.SMTP_USERNAME:
            client.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        client.send_message(message)
