from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MailMessage:
    recipient: str
    subject: str
    body: str


class MailSender(Protocol):
    def send(self, message: MailMessage) -> None: ...
