from __future__ import annotations

import datetime as dt

import pandas as pd

from xenalgo.broker.paper import PaperBroker
from xenalgo.broker.token import Token, TokenManager
from xenalgo.execution import Journal
from xenalgo.monolith import PaperDayRunner, PaperOrderPlan
from xenalgo.risk import RiskEngine


def test_full_simulated_paper_day_runs_unattended(tmp_journal):
    today = dt.date(2026, 7, 1)
    panel = {
        "close": pd.DataFrame({"RELIANCE": [1000.0]}, index=pd.to_datetime([today])),
        "volume": pd.DataFrame({"RELIANCE": [100_000]}, index=pd.to_datetime([today])),
    }
    broker = PaperBroker(cash=1_000_000.0, ltp={"RELIANCE": 1000.0})
    token_manager = TokenManager(
        tmp_journal,
        token_provider=lambda: Token(
            "paper-token",
            dt.datetime.now(dt.UTC) + dt.timedelta(hours=12),
        ),
    )
    risk = RiskEngine(
        {
            "max_order_notional_inr": 200_000,
            "max_pct_of_adv": 0.05,
            "price_collar_pct": 0.03,
            "max_position_pct": 0.10,
            "fee_buffer_pct": 0.001,
        }
    )
    runner = PaperDayRunner(
        broker=broker,
        journal=Journal(tmp_journal),
        token_manager=token_manager,
        risk_engine=risk,
    )

    result = runner.run(
        panel=panel,
        expected_trading_date=today,
        orders=[
            PaperOrderPlan(
                correlation_id="xa-20260701-std30-RELIANCE-BUY-1",
                sleeve="std30",
                symbol="RELIANCE",
                security_id="2885",
                side="BUY",
                qty=10,
                limit_price=1000.0,
            )
        ],
    )

    assert result.submitted == 1
    assert result.filled == 1
    assert result.reconciled is True
    assert result.alerts >= 3
    assert broker.holdings["RELIANCE"] == 10


def test_second_buy_respects_position_cap(tmp_journal):
    today = dt.date(2026, 7, 1)
    panel = {
        "close": pd.DataFrame({"RELIANCE": [1000.0]}, index=pd.to_datetime([today])),
        "volume": pd.DataFrame({"RELIANCE": [100_000]}, index=pd.to_datetime([today])),
    }
    broker = PaperBroker(cash=1_000_000.0, ltp={"RELIANCE": 1000.0})
    token_manager = TokenManager(
        tmp_journal,
        token_provider=lambda: Token(
            "paper-token",
            dt.datetime.now(dt.UTC) + dt.timedelta(hours=12),
        ),
    )
    risk = RiskEngine(
        {
            "max_order_notional_inr": 200_000,
            "max_pct_of_adv": 0.05,
            "price_collar_pct": 0.03,
            "max_position_pct": 0.10,
            "fee_buffer_pct": 0.001,
        }
    )
    runner = PaperDayRunner(
        broker=broker,
        journal=Journal(tmp_journal),
        token_manager=token_manager,
        risk_engine=risk,
    )

    result = runner.run(
        panel=panel,
        expected_trading_date=today,
        orders=[
            PaperOrderPlan(
                correlation_id="xa-20260701-std30-RELIANCE-BUY-1",
                sleeve="std30",
                symbol="RELIANCE",
                security_id="2885",
                side="BUY",
                qty=100,
                limit_price=1000.0,
            ),
            PaperOrderPlan(
                correlation_id="xa-20260701-alpha027-RELIANCE-BUY-1",
                sleeve="alpha_027",
                symbol="RELIANCE",
                security_id="2885",
                side="BUY",
                qty=100,
                limit_price=1000.0,
            ),
        ],
    )

    assert result.submitted == 1
    assert result.filled == 1
    assert broker.holdings["RELIANCE"] == 100
    events = Journal(tmp_journal).events()
    rejected = [event for event in events if event["state"] == "REJECTED"]
    assert rejected[-1]["reason"] == "position cap reached"
