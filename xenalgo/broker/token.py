from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol


class TradingBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class Token:
    value: str
    expires_at: dt.datetime


class TokenManager:
    def __init__(
        self,
        store: str | Path,
        token_provider: Callable[[], Token] | None = None,
        clock: Callable[[], dt.datetime] | None = None,
        token_name: str = "fyers",
    ) -> None:
        self.store = str(store)
        self.token_provider = token_provider
        self.clock = clock or (lambda: dt.datetime.now(dt.UTC))
        self.token_name = token_name
        self._init()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.store)
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _init(self) -> None:
        with self._connect() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS tokens "
                "(name TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at TEXT NOT NULL)"
            )
        self._restrict_store_permissions()

    def refresh(self) -> Token:
        if self.token_provider is None:
            raise TradingBlocked("no token provider configured")
        token = self.token_provider()
        if token.expires_at <= self.clock():
            raise TradingBlocked("token provider returned expired token")
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO tokens(name, value, expires_at) VALUES (?, ?, ?)",
                (self.token_name, token.value, token.expires_at.isoformat()),
            )
        return token

    def ensure_valid(self, min_ttl: dt.timedelta = dt.timedelta(minutes=5)) -> Token:
        token = self._load()
        if token is not None and token.expires_at - self.clock() >= min_ttl:
            return token
        try:
            return self.refresh()
        except Exception as exc:
            raise TradingBlocked(str(exc)) from exc

    def _load(self) -> Token | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT value, expires_at FROM tokens WHERE name=?", (self.token_name,)
            ).fetchone()
        if row is None:
            return None
        expires_at = dt.datetime.fromisoformat(row[1])
        return Token(row[0], expires_at)

    def _restrict_store_permissions(self) -> None:
        if os.name == "posix":
            os.chmod(self.store, 0o600)


class FyersSession(Protocol):
    def set_token(self, auth_code: str) -> None: ...
    def generate_token(self) -> dict: ...


class FyersAuthCodeSession:
    """Exchange a documented Fyers OAuth auth code without importing the SDK."""

    TOKEN_URL = "https://api-t1.fyers.in/api/v3/validate-authcode"

    def __init__(
        self,
        app_id: str,
        secret_key: str,
        *,
        post: Callable[[str, dict, float], dict] | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.app_id = app_id
        self.secret_key = secret_key
        self.post = post or self._post_json
        self.timeout_seconds = float(timeout_seconds)
        self.auth_code = ""

    def set_token(self, auth_code: str) -> None:
        self.auth_code = auth_code

    def generate_token(self) -> dict:
        if not self.auth_code:
            raise TradingBlocked("Fyers auth code is missing")
        app_id_hash = hashlib.sha256(f"{self.app_id}:{self.secret_key}".encode()).hexdigest()
        return self.post(
            self.TOKEN_URL,
            {
                "grant_type": "authorization_code",
                "appIdHash": app_id_hash,
                "code": self.auth_code,
            },
            self.timeout_seconds,
        )

    @staticmethod
    def _post_json(url: str, payload: dict, timeout: float) -> dict:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not isinstance(result, dict):
            raise TradingBlocked("Fyers token exchange returned an invalid response")
        return result


class FyersOAuthProvider:
    """Mockable Fyers OAuth2 auth-code provider for daily access tokens."""

    def __init__(
        self,
        *,
        auth_code_provider: Callable[[], str],
        session_factory: Callable[[], FyersSession],
        clock: Callable[[], dt.datetime] | None = None,
        token_ttl: dt.timedelta = dt.timedelta(hours=24),
        timeout_seconds: float = 120.0,
    ) -> None:
        self.auth_code_provider = auth_code_provider
        self.session_factory = session_factory
        self.clock = clock or (lambda: dt.datetime.now(dt.UTC))
        self.token_ttl = token_ttl
        self.timeout_seconds = float(timeout_seconds)

    def __call__(self) -> Token:
        try:
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="fyers-auth") as pool:
                auth_code = pool.submit(self.auth_code_provider).result(timeout=self.timeout_seconds)
        except FutureTimeout as exc:
            raise TradingBlocked("Fyers daily authentication timed out") from exc
        if not auth_code:
            raise TradingBlocked("Fyers auth-code provider returned no auth code")
        session = self.session_factory()
        session.set_token(auth_code)
        response = session.generate_token()
        value = response.get("access_token") or response.get("accessToken")
        if not value:
            raise TradingBlocked("Fyers token exchange failed")
        return Token(str(value), self.clock() + self.token_ttl)


def token_store_excluded_from_backup(token_store: str | Path, backup_roots: list[str | Path]) -> bool:
    token_path = Path(token_store).resolve()
    for root in backup_roots:
        root_path = Path(root).resolve()
        if token_path == root_path or root_path in token_path.parents:
            return False
    return True
