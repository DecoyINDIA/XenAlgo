from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


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
    ) -> None:
        self.store = str(store)
        self.token_provider = token_provider
        self.clock = clock or (lambda: dt.datetime.now(dt.UTC))
        self._init()

    def _connect(self):
        return sqlite3.connect(self.store)

    def _init(self) -> None:
        with self._connect() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS tokens "
                "(name TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at TEXT NOT NULL)"
            )

    def refresh(self) -> Token:
        if self.token_provider is None:
            raise TradingBlocked("no token provider configured")
        token = self.token_provider()
        if token.expires_at <= self.clock():
            raise TradingBlocked("token provider returned expired token")
        with self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO tokens(name, value, expires_at) VALUES (?, ?, ?)",
                ("dhan", token.value, token.expires_at.isoformat()),
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
                "SELECT value, expires_at FROM tokens WHERE name='dhan'"
            ).fetchone()
        if row is None:
            return None
        expires_at = dt.datetime.fromisoformat(row[1])
        return Token(row[0], expires_at)
