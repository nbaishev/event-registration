from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.common.config import Settings
from app.notifications.contracts import MailMessage
from app.notifications.smtp import SmtpMailSender


def settings(**values):
    return Settings(_env_file=None, jwt_secret="x" * 32, **values)


@pytest.mark.parametrize("security", ["none", "starttls", "tls"])
def test_transport_timeout_tls_auth_and_mime(monkeypatch, security):
    connection = MagicMock()
    connection.__enter__.return_value.send_message.return_value = {}
    calls = []

    def connect(host, port, **kwargs):
        calls.append((host, port, kwargs))
        return connection

    monkeypatch.setattr("app.notifications.smtp.smtplib.SMTP", connect)
    monkeypatch.setattr("app.notifications.smtp.smtplib.SMTP_SSL", connect)
    config = settings(
        smtp_security=security,
        smtp_host="sink",
        smtp_port=1025,
        smtp_from="sender@example.com",
        smtp_timeout_seconds=4,
        smtp_username="user" if security != "none" else None,
        smtp_password="password" if security != "none" else None,
    )
    SmtpMailSender(config).send(MailMessage("guest@example.com", "Билет", "Текст"))
    assert calls[0][:2] == ("sink", 1025)
    assert calls[0][2]["timeout"] == 4
    transport = connection.__enter__.return_value
    assert transport.starttls.call_count == (1 if security == "starttls" else 0)
    assert transport.login.call_count == (0 if security == "none" else 1)
    if security == "starttls":
        names = [call[0] for call in transport.method_calls]
        assert (
            names.index("starttls") < names.index("login") < names.index("send_message")
        )
    mail = transport.send_message.call_args.args[0]
    assert mail["To"] == "guest@example.com"
    assert mail["From"] == "sender@example.com"
    assert mail["Subject"] == "Билет"
    assert mail.get_content_type() == "text/plain"
    assert mail.get_content().strip() == "Текст"


@pytest.mark.parametrize(
    "values",
    [
        {"smtp_username": "user"},
        {"smtp_password": "secret"},
        {"smtp_username": "user", "smtp_password": "secret", "smtp_security": "none"},
        {"smtp_timeout_seconds": 0},
        {"smtp_security": "invalid"},
        {"smtp_from": "a@example.com\r\nBcc: evil@example.com"},
    ],
)
def test_invalid_smtp_configuration_rejected(values):
    with pytest.raises(ValidationError) as error:
        settings(**values)
    assert "secret" not in str(error.value)


def test_smtp_failure_propagates(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value.send_message.side_effect = OSError("offline")
    monkeypatch.setattr(
        "app.notifications.smtp.smtplib.SMTP", lambda *a, **kw: connection
    )
    with pytest.raises(OSError):
        SmtpMailSender(settings()).send(MailMessage("a@example.com", "Ticket", "Body"))
