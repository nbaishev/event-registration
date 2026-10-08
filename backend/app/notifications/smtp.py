import smtplib
import ssl
from email.message import EmailMessage

from app.common.config import Settings
from app.notifications.contracts import MailMessage


class SmtpMailSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, message: MailMessage) -> None:
        config = self.settings
        mail = EmailMessage()
        mail["From"] = str(config.smtp_from)
        mail["To"] = message.recipient
        mail["Subject"] = message.subject
        mail.set_content(message.body)
        connection: smtplib.SMTP
        if config.smtp_security == "tls":
            connection = smtplib.SMTP_SSL(
                config.smtp_host,
                config.smtp_port,
                timeout=config.smtp_timeout_seconds,
                context=ssl.create_default_context(),
            )
        else:
            connection = smtplib.SMTP(
                config.smtp_host,
                config.smtp_port,
                timeout=config.smtp_timeout_seconds,
            )
        with connection as transport:
            if config.smtp_security == "starttls":
                transport.ehlo()
                transport.starttls(context=ssl.create_default_context())
                transport.ehlo()
            if config.smtp_username is not None and config.smtp_password is not None:
                transport.login(
                    config.smtp_username, config.smtp_password.get_secret_value()
                )
            refused = transport.send_message(mail)
            if refused:
                # Do not propagate SMTP response data containing recipient addresses.
                raise RuntimeError("SMTP recipient refused")
