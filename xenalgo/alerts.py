from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Alert:
    kind: str
    message: str
    critical: bool = False


class InMemoryAlerter:
    def __init__(self) -> None:
        self.sent: list[Alert] = []

    def send(self, kind: str, message: str, critical: bool = False) -> None:
        self.sent.append(Alert(kind=kind, message=message, critical=critical))
