from __future__ import annotations

from xenalgo.web.state import ConsoleStore


class TelegramCommandRouter:
    """Dependency-free command handler for Phase 2 Telegram operator actions."""

    def __init__(self, store: ConsoleStore, allowed_chat_ids: list[str] | set[str] | None = None) -> None:
        self.store = store
        if allowed_chat_ids is None:
            import os
            raw = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
            self.allowed_chat_ids = {c.strip() for c in raw.split(",") if c.strip()} if raw else set()
        else:
            self.allowed_chat_ids = {str(c).strip() for c in allowed_chat_ids if str(c).strip()}

    def handle(self, text: str, *, chat_id: str | int | None = None, actor: str = "telegram") -> str:
        cid = str(chat_id).strip() if chat_id is not None else ""
        if not self.allowed_chat_ids or cid not in self.allowed_chat_ids:
            return "Unauthorized sender."

        parts = (text or "").strip().split()
        if not parts:
            return "Unknown command. Supported: /status, /positions, /kill, /rearm <breaker>."
        command, *args = parts
        command = command.lower()
        if command == "/status":
            return self._status()
        if command == "/positions":
            return self._positions()
        if command == "/kill":
            self.store.activate_kill(source="telegram", actor=actor)
            return "Kill switch active. New order submission is blocked."
        if command == "/rearm":
            if not args:
                return "Usage: /rearm <breaker>"
            breaker = args[0]
            self.store.rearm(breaker, actor=actor, reason="telegram")
            return f"Re-armed {breaker}."
        return "Unknown command. Supported: /status, /positions, /kill, /rearm <breaker>."

    def _status(self) -> str:
        snapshot = self.store.snapshot()
        summary = snapshot["summary"]
        return (
            f"XenAlgo status: {summary['open_orders']} open orders, "
            f"{summary['positions']} positions, {summary['active_breakers']} active breakers."
        )

    def _positions(self) -> str:
        positions = self.store.snapshot()["positions"]
        if not positions:
            return "No open positions."
        lines = [
            f"{position['symbol']}: {position['qty']} @ {position['avg_price']}"
            for position in positions
        ]
        return "\n".join(lines)
