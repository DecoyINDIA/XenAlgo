from __future__ import annotations

import json
import logging
from io import StringIO
from pathlib import Path

import pytest
import xenalgo
from xenalgo.config import load_config
from xenalgo.logging_setup import configure_logging


ROOT = Path(__file__).resolve().parents[1]


def test_promoted_research_packages_import_cleanly():
    import Brain.alpha_engine  # noqa: F401
    import Brain.backtest_engine  # noqa: F401
    import Strategies.alpha_027  # noqa: F401
    import Strategies.alpha_062  # noqa: F401
    import Strategies.std30  # noqa: F401

    assert xenalgo.__version__ == "0.0.0"


def test_promoted_research_packages_match_source_bytes():
    source_root = ROOT / "_source"
    if not source_root.exists() or not (source_root / "Brain").exists():
        pytest.skip("_source research snapshot is optional outside the operator checkout")

    for relative in [
        Path("Brain/alpha_engine.py"),
        Path("Brain/backtest_engine.py"),
        Path("Brain/data_manager.py"),
        Path("Strategies/alpha_027.py"),
        Path("Strategies/alpha_062.py"),
        Path("Strategies/std30.py"),
    ]:
        assert (ROOT / relative).read_bytes() == (ROOT / "_source" / relative).read_bytes()


def test_phase1_modules_import_cleanly():
    import xenalgo.broker.governor  # noqa: F401
    import xenalgo.execution  # noqa: F401
    import xenalgo.risk  # noqa: F401


def test_phase2_modules_import_cleanly():
    import xenalgo.web  # noqa: F401
    import xenalgo.web.app  # noqa: F401
    import xenalgo.web.state  # noqa: F401
    import xenalgo.web.telegram  # noqa: F401


def test_config_profiles_load_and_enforce_phase0_safety_defaults():
    research = load_config("research", ROOT)
    live = load_config("live", ROOT)

    assert research.profile == "research"
    assert live.profile == "live"
    assert len(research.checksum) == 64
    assert len(live.checksum) == 64
    assert live.section("live_trading")["enabled"] is False
    assert live.section("live_trading")["mode"] == "paper"
    assert live.section("broker")["order_api_enabled"] is False
    assert live.section("broker")["dhan_sdk_version"] == "2.0.2"
    assert live.section("governor")["max_orders_per_sec"] == 2


def test_structured_logging_includes_run_id():
    stream = StringIO()
    run_id = configure_logging(run_id="phase0-test", stream=stream)

    logging.getLogger("XenAlgo.Phase0").info("scaffold ready")
    payload = json.loads(stream.getvalue())

    assert run_id == "phase0-test"
    assert payload["run_id"] == "phase0-test"
    assert payload["logger"] == "XenAlgo.Phase0"
    assert payload["message"] == "scaffold ready"
