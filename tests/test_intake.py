from __future__ import annotations

from pathlib import Path

from aep.intake import compile_request_intake, compile_text_intake


def _fixtures_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures"


def test_compile_text_trade_compiled() -> None:
    result = compile_text_intake(
        "buy 1 USDC of SOL",
        agent_id="demo-agent",
    )
    assert result["status"] == "compiled"
    assert result["action_family"] == "trade"
    assert result["action_request"]["action"]["kind"] == "trade"


def test_compile_text_empty_needs_clarification() -> None:
    result = compile_text_intake("", agent_id="demo-agent")
    assert result["status"] == "needs_clarification"
    assert result["reason_code"] == "EMPTY_INPUT"


def test_compile_structured_request_merges_delegation_grant() -> None:
    fixtures = _fixtures_root()
    intake_request = {
        "api_version": "aep.intake_request.v1",
        "requested_action_family": "trade",
        "actor_context": {
            "agent_id": "aep:solana:agent-alpha",
            "runtime_type": "generic-agent",
        },
        "action": {
            "kind": "trade",
            "trade": {
                "side": "buy",
                "source_asset": "USDC",
                "destination_asset": "SOL",
                "notional_usd": 5.0,
                "expected_price_usd": 120.0,
            },
        },
        "execution_preferences": {
            "mode": "paper",
            "chain": "solana",
            "network": "paper",
            "venue": "paper-virtual-orderbook",
        },
        "delegation_ref": "grant-public-api-shell-alpha",
    }
    result = compile_request_intake(
        intake_request,
        delegation_grants_path=fixtures / "delegation_grants.v1.json",
    )
    assert result["status"] == "compiled"
    delegation = result["action_request"].get("delegation")
    assert delegation is not None
    assert delegation["grant_id"] == "grant-public-api-shell-alpha"
    assert delegation["delegate_id"] == "aep:solana:agent-alpha"
