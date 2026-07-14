from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from xenalgo.alerts import HeartbeatEventAlerter, OperatorAlerter
from xenalgo.paper_daemon import (
    ProductionPaperDaemon,
    SafeAlertBus,
    build_paper_dependencies,
    run_host_preflight,
)
from xenalgo.scheduler import MarketCalendar


IST = ZoneInfo("Asia/Kolkata")
HISTORY_URL = "https://api-t1.fyers.in/data/history"


def latest_completed_trading_day(
    now: dt.datetime, calendar: MarketCalendar | None = None
) -> dt.date:
    calendar = calendar or MarketCalendar()
    local = now.astimezone(IST)
    candidate = local.date()
    if local.time() < dt.time(16, 0) or not calendar.is_trading_day(candidate):
        candidate -= dt.timedelta(days=1)
    while not calendar.is_trading_day(candidate):
        candidate -= dt.timedelta(days=1)
    return candidate


def fetch_validation_panel(
    *,
    app_id: str,
    access_token: str,
    expected_day: dt.date,
    get=requests.get,
) -> dict[str, pd.DataFrame]:
    response = get(
        HISTORY_URL,
        params={
            "symbol": "NSE:SBIN-EQ",
            "resolution": "D",
            "date_format": "1",
            "range_from": (expected_day - dt.timedelta(days=10)).isoformat(),
            "range_to": expected_day.isoformat(),
            "cont_flag": "1",
        },
        headers={
            "Authorization": f"{app_id}:{access_token}",
            "Accept": "application/json",
            "User-Agent": "XenAlgo/1.0",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("s") != "ok":
        raise RuntimeError("Fyers history preflight was rejected")
    candles = payload.get("candles") or []
    if len(candles) < 2:
        raise RuntimeError("Fyers history preflight returned fewer than two candles")
    index = pd.DatetimeIndex(
        [pd.Timestamp(dt.datetime.fromtimestamp(row[0], tz=dt.UTC).date()) for row in candles]
    )
    return {
        "close": pd.DataFrame({"SBIN": [float(row[4]) for row in candles]}, index=index),
        "volume": pd.DataFrame({"SBIN": [float(row[5]) for row in candles]}, index=index),
    }


def build_alert_adapter_from_env():
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if telegram_token and telegram_chat_id:
        return OperatorAlerter(
            telegram_token=telegram_token,
            telegram_chat_id=telegram_chat_id,
            pushover_token=os.environ.get("PUSHOVER_TOKEN", "").strip(),
            pushover_user_key=os.environ.get("PUSHOVER_USER_KEY", "").strip(),
        ), "telegram"
    heartbeat_url = os.environ.get("XENALGO_HEARTBEAT_URL", "").strip()
    return HeartbeatEventAlerter(heartbeat_url=heartbeat_url), "healthchecks"


def main() -> int:
    root = Path(os.environ.get("XENALGO_ROOT", "/app"))
    deps = build_paper_dependencies(root)
    alert_adapter, channel = build_alert_adapter_from_env()
    deps.alerts = SafeAlertBus(alert_adapter)
    token = deps.token_manager.ensure_valid()
    trading_day = latest_completed_trading_day(dt.datetime.now(dt.UTC), deps.calendar)
    panel = fetch_validation_panel(
        app_id=os.environ.get("FYERS_APP_ID", "").strip(),
        access_token=token.value,
        expected_day=trading_day,
    )
    report = run_host_preflight(
        ProductionPaperDaemon(deps, evidence_dir=root / "Diary" / "commissioning"),
        trading_date=trading_day,
        panel=panel,
    )
    print(
        json.dumps(
            {
                "passed": report.passed,
                "trading_date": trading_day.isoformat(),
                "alert_channel": channel,
                "checks": report.checks,
                "live_order_api_calls": 0,
            },
            sort_keys=True,
        )
    )
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
