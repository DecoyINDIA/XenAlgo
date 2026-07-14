from __future__ import annotations

import urllib.parse
import urllib.request
from collections.abc import Callable
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


class OperatorAlerter:
    """Synchronous host alert adapter; callers isolate failures via SafeAlertBus."""

    def __init__(
        self,
        *,
        telegram_token: str,
        telegram_chat_id: str,
        pushover_token: str = "",
        pushover_user_key: str = "",
        post: Callable[[str, dict[str, str], float], None] | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not telegram_token or not telegram_chat_id:
            raise ValueError("Telegram alert credentials are required")
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.pushover_token = pushover_token
        self.pushover_user_key = pushover_user_key
        self.post = post or self._post_form
        self.timeout_seconds = float(timeout_seconds)

    def send(self, kind: str, message: str, critical: bool = False) -> None:
        text = f"[{kind}] {message}"
        self.post(
            f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
            {"chat_id": self.telegram_chat_id, "text": text},
            self.timeout_seconds,
        )
        if critical:
            if not self.pushover_token or not self.pushover_user_key:
                raise RuntimeError("Pushover critical alert credentials are required")
            self.post(
                "https://api.pushover.net/1/messages.json",
                {"token": self.pushover_token, "user": self.pushover_user_key, "message": text},
                self.timeout_seconds,
            )

    @staticmethod
    def _post_form(url: str, payload: dict[str, str], timeout: float) -> None:
        request = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(payload).encode("utf-8"),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"alert delivery returned HTTP {response.status}")


class HeartbeatEventAlerter:
    """Post redacted application events to an existing Healthchecks channel."""

    def __init__(self, *, heartbeat_url: str, timeout_seconds: float = 10.0) -> None:
        if not heartbeat_url:
            raise ValueError("heartbeat URL is required")
        self.heartbeat_url = heartbeat_url
        self.timeout_seconds = float(timeout_seconds)

    def send(self, kind: str, message: str, critical: bool = False) -> None:
        body = f"[{kind}] {message}".encode("utf-8")
        request = urllib.request.Request(
            self.heartbeat_url,
            data=body,
            headers={"Content-Type": "text/plain; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"heartbeat event delivery returned HTTP {response.status}")
