"""
Executable specifications for the intraday QuotePoller and FyersQuoteFeed.

Covers SI-aligned behaviours: the quote rate never exceeds the governor cap,
corrupt ticks are rejected instead of stored, and a stale feed fails closed
(StaleDataError) rather than silently serving old prices. Mock-only: no test
touches the real Fyers API.
"""
from __future__ import annotations

import datetime as dt

import pytest

from xenalgo.broker.fyers import FyersQuoteFeed
from xenalgo.broker.governor import TokenBucket
from xenalgo.data import QuotePoller, StaleDataError


class FakeFeed:
    def __init__(self, prices: dict[str, float]) -> None:
        self.prices = dict(prices)
        self.calls = 0

    def quotes(self, symbols):
        self.calls += 1
        return {s: self.prices[s] for s in symbols if s in self.prices}


class FakeQuoteClient:
    def __init__(self, prices: dict[str, float]) -> None:
        self.prices = dict(prices)
        self.requests: list[str] = []

    def quotes(self, payload):
        self.requests.append(payload["symbols"])
        entries = []
        for fyers_symbol in payload["symbols"].split(","):
            plain = fyers_symbol.split(":")[-1].removesuffix("-EQ")
            if plain in self.prices:
                entries.append({"n": fyers_symbol, "s": "ok", "v": {"lp": self.prices[plain]}})
        return {"s": "ok", "d": entries}


def make_poller(feed, *, reference, clock=None, rate=1.0, bucket=None, sink=None):
    return QuotePoller(
        feed,
        list(reference),
        reference_close=reference,
        collar_pct=0.25,
        max_quotes_per_sec=rate,
        sink=sink,
        clock=clock,
        bucket=bucket,
    )


# ─────────────────────────── QuotePoller ────────────────────────────────


def test_poll_once_updates_sink_with_sane_prices(ist_clock):
    feed = FakeFeed({"SBIN": 812.0, "TCS": 4102.5})
    sink: dict[str, float] = {}
    poller = make_poller(feed, reference={"SBIN": 800.0, "TCS": 4000.0}, clock=ist_clock.now, sink=sink)

    result = poller.poll_once()

    assert not result.throttled
    assert result.updated == {"SBIN": 812.0, "TCS": 4102.5}
    assert sink == {"SBIN": 812.0, "TCS": 4102.5}
    assert poller.last_tick_at == ist_clock.now()


def test_poll_once_rejects_insane_price_and_keeps_last_good(ist_clock):
    feed = FakeFeed({"SBIN": 8120.0, "TCS": 4102.5})  # SBIN tick is 10x: corrupt
    sink: dict[str, float] = {}
    poller = make_poller(feed, reference={"SBIN": 800.0, "TCS": 4000.0}, clock=ist_clock.now, sink=sink)

    result = poller.poll_once()

    assert result.rejected == ("SBIN",)
    assert "SBIN" not in sink
    assert poller.last_good["SBIN"] == 800.0
    assert poller.rejected_total == 1


def test_poll_once_uses_last_good_as_moving_baseline(ist_clock):
    feed = FakeFeed({"SBIN": 900.0})
    poller = make_poller(feed, reference={"SBIN": 800.0}, clock=ist_clock.now)
    poller.poll_once()
    poller.bucket._tokens = 1.0  # refill for the second tick

    feed.prices["SBIN"] = 1100.0  # sane vs 900 (22%), insane vs 800 (37%)
    result = poller.poll_once()

    assert result.updated == {"SBIN": 1100.0}


def test_quote_rate_never_exceeds_governor_cap(ist_clock):
    """SI: quote traffic stays at or below governor.max_quotes_per_sec."""
    fake_time = {"t": 0.0}
    bucket = TokenBucket(rate_per_sec=1.0, clock=lambda: fake_time["t"])
    feed = FakeFeed({"SBIN": 810.0})
    poller = make_poller(feed, reference={"SBIN": 800.0}, clock=ist_clock.now, bucket=bucket)

    first = poller.poll_once()
    second = poller.poll_once()  # same instant: must throttle, not call the feed

    assert not first.throttled
    assert second.throttled
    assert feed.calls == 1

    fake_time["t"] = 1.0
    assert not poller.poll_once().throttled
    assert feed.calls == 2


def test_assert_fresh_fails_closed_when_stale(ist_clock):
    feed = FakeFeed({"SBIN": 810.0})
    poller = make_poller(feed, reference={"SBIN": 800.0}, clock=ist_clock.now)

    with pytest.raises(StaleDataError):
        poller.assert_fresh(dt.timedelta(seconds=5))  # no tick yet

    poller.poll_once()
    poller.assert_fresh(dt.timedelta(seconds=5))

    ist_clock.advance(seconds=10)
    with pytest.raises(StaleDataError):
        poller.assert_fresh(dt.timedelta(seconds=5))


def test_run_until_polls_at_cap_interval(ist_clock):
    fake_time = {"t": 0.0}
    bucket = TokenBucket(rate_per_sec=1.0, clock=lambda: fake_time["t"])
    feed = FakeFeed({"SBIN": 810.0})
    poller = make_poller(feed, reference={"SBIN": 800.0}, clock=ist_clock.now, bucket=bucket)

    sleeps: list[float] = []

    def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        fake_time["t"] += seconds

    ticks = poller.run_until(lambda: feed.calls >= 3, sleeper=sleeper)

    assert ticks == 3
    assert all(s >= 1.0 for s in sleeps)  # never faster than 1 req/sec


def test_min_interval_respects_rate_floor():
    feed = FakeFeed({})
    poller = make_poller(feed, reference={}, rate=2.0)
    assert poller.min_interval_seconds == pytest.approx(0.5)
    with pytest.raises(ValueError):
        make_poller(feed, reference={}, rate=0.0)


# ─────────────────────────── FyersQuoteFeed ─────────────────────────────


def test_quote_feed_parses_last_price():
    client = FakeQuoteClient({"SBIN": 812.0, "TCS": 4102.5})
    feed = FyersQuoteFeed(client)

    prices = feed.quotes(["SBIN", "TCS", "UNKNOWN"])

    assert prices == {"SBIN": 812.0, "TCS": 4102.5}
    assert client.requests == ["NSE:SBIN-EQ,NSE:TCS-EQ,NSE:UNKNOWN-EQ"]


def test_quote_feed_batches_fifty_symbols_per_request():
    symbols = [f"SYM{i}" for i in range(120)]
    client = FakeQuoteClient({s: 100.0 for s in symbols})
    feed = FyersQuoteFeed(client)

    prices = feed.quotes(symbols)

    assert len(prices) == 120
    assert len(client.requests) == 3
    assert all(len(req.split(",")) <= 50 for req in client.requests)


def test_quote_feed_skips_malformed_entries():
    class BadClient:
        def quotes(self, payload):
            return {
                "s": "ok",
                "d": [
                    {"n": "NSE:SBIN-EQ", "v": {"lp": "not-a-number"}},
                    {"n": "NSE:TCS-EQ", "v": {"lp": 4102.5}},
                    "garbage",
                ],
            }

    prices = FyersQuoteFeed(BadClient()).quotes(["SBIN", "TCS"])
    assert prices == {"TCS": 4102.5}


# ─────────────────────────── composition ────────────────────────────────


def test_build_quote_poller_wires_config_caps():
    pd = pytest.importorskip("pandas")
    from xenalgo.session_composition import build_quote_poller

    class Cfg:
        data = {
            "governor": {"max_quotes_per_sec": 1},
            "risk": {"data_sanity_move_pct": 0.25},
        }

    index = pd.DatetimeIndex([pd.Timestamp("2026-07-15")])
    panel = {"close": pd.DataFrame({"SBIN": [800.0]}, index=index)}
    client = FakeQuoteClient({"SBIN": 810.0})
    sink: dict[str, float] = {}

    poller = build_quote_poller(Cfg(), client, ["SBIN"], panel, sink=sink)
    result = poller.poll_once()

    assert poller.min_interval_seconds == pytest.approx(1.0)
    assert result.updated == {"SBIN": 810.0}
    assert sink == {"SBIN": 810.0}
