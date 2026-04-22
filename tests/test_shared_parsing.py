from __future__ import annotations

from pathlib import Path

from aep.shared.assets import _load_asset_registry
from aep.shared.parsing import parse_natural_language_trade_request


def _fixtures_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures"


def test_load_asset_registry_has_usdc() -> None:
    registry = _load_asset_registry(_fixtures_root() / "paper_asset_registry.v1.json")
    assert "USDC" in registry["by_symbol"]


def test_parse_trade_request_returns_action_request() -> None:
    request = parse_natural_language_trade_request(
        "buy 2 USDC of SOL",
        agent_id="agent-demo",
        asset_registry_path=_fixtures_root() / "paper_asset_registry.v1.json",
    )
    assert request["api_version"] == "aep.action_request.v1"
    assert request["action"]["kind"] == "trade"
    assert request["action"]["trade"]["destination_asset"] == "SOL"
