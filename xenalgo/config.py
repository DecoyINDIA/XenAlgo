from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


VALID_PROFILES = {"research", "live"}


@dataclass(frozen=True)
class RuntimeConfig:
    profile: str
    path: Path
    data: dict[str, Any]
    checksum: str

    def section(self, name: str) -> dict[str, Any]:
        value = self.data.get(name)
        if not isinstance(value, dict):
            raise KeyError(f"missing config section: {name}")
        return value


def load_config(profile: str = "live", root: str | Path | None = None) -> RuntimeConfig:
    if profile not in VALID_PROFILES:
        raise ValueError(f"unknown config profile: {profile}")

    base = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    path = base / "config" / f"config.{profile}.yaml"
    raw = path.read_bytes()
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config must be a mapping: {path}")
    if data.get("profile") != profile:
        raise ValueError(f"config profile mismatch in {path}")

    _validate(profile, data)
    return RuntimeConfig(
        profile=profile,
        path=path,
        data=data,
        checksum=hashlib.sha256(raw).hexdigest(),
    )


def _validate(profile: str, data: dict[str, Any]) -> None:
    if profile == "research":
        _require(data, "dhan", "database", "universe", "backtest", "portfolio", "costs", "logging")
        return

    _require(
        data,
        "live_trading",
        "sleeves",
        "risk",
        "execution",
        "governor",
        "broker",
        "storage",
        "scheduler",
        "alerts",
        "web",
        "logging",
    )
    live_trading = data["live_trading"]
    if live_trading.get("enabled") is not False:
        raise ValueError("Phase 0 live config must keep live_trading.enabled=false")
    if live_trading.get("mode") not in {"paper", "live"}:
        raise ValueError("live_trading.mode must be paper or live")

    sleeves = data["sleeves"]
    total_fraction = sum(float(v.get("capital_fraction", 0)) for v in sleeves.values())
    if abs(total_fraction - 1.0) > 0.001:
        raise ValueError("sleeve capital fractions must sum to 1.0")

    governor = data["governor"]
    max_orders_per_sec = float(governor.get("max_orders_per_sec", 0))
    if max_orders_per_sec <= 0 or max_orders_per_sec > 2 or max_orders_per_sec >= 10:
        raise ValueError("governor.max_orders_per_sec must stay at or below 2")

    broker = data["broker"]
    if str(broker.get("dhan_sdk_version")) != "2.0.2":
        raise ValueError("dhan SDK must remain pinned to 2.0.2")
    if broker.get("order_api_enabled") is not False:
        raise ValueError("Phase 0 config must not enable broker order APIs")


def _require(data: dict[str, Any], *sections: str) -> None:
    missing = [section for section in sections if section not in data]
    if missing:
        raise ValueError(f"missing config section(s): {', '.join(missing)}")
