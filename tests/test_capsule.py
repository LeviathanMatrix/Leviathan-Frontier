from __future__ import annotations

import json
from pathlib import Path

import pytest

from aep.capsule import (
    bind_capsule_to_execution_pass,
    consume_capsule_notional,
    create_capital_capsule,
    finalize_capsule,
    validate_capsule_for_execution,
)
from aep.intake import compile_text_intake
from aep.issuance import build_issuance_object
from aep.risk_provider import StaticRiskInputProvider


def _fixtures_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures"


def _constitution() -> dict:
    return json.loads((_fixtures_root() / "constitution.paper_trade.v1.json").read_text(encoding="utf-8"))


def _issued_bundle() -> tuple[dict, dict, dict, dict]:
    action_request = compile_text_intake("buy 2 USDC of SOL", agent_id="agent-1")["action_request"]
    risk_input = StaticRiskInputProvider().build_risk_input(action_request)
    policy_output = {
        "final_decision": "ALLOW_WITH_LIGHT_BOND",
        "hard_constraints_passed": True,
        "reason_codes": [],
        "derived_values": {"risk_score_post_advisory": 15.0},
    }
    issuance = build_issuance_object(
        case_id="case-capsule",
        action_request=action_request,
        policy_output=policy_output,
        risk_input=risk_input,
        constitution=_constitution(),
    )
    capsule = create_capital_capsule(
        case_id="case-capsule",
        action_request=action_request,
        issuance=issuance,
        policy_output=policy_output,
        risk_input=risk_input,
    )
    return action_request, issuance, capsule, policy_output


def test_bind_and_consume_capsule() -> None:
    action_request, issuance, capsule, _ = _issued_bundle()
    assert capsule["producer"]["company"] == "LeviathanMatrix"
    assert capsule["spec_id"] == "leviathanmatrix.aep.open-core.v1"
    bound = bind_capsule_to_execution_pass(capsule, issuance)
    assert bound["capsule_status"] == "ARMED"
    check = validate_capsule_for_execution(bound, requested_notional_usd=1.0)
    assert check["ok"] is True
    consumed = consume_capsule_notional(bound, amount_usd=1.0)
    assert consumed["remaining_notional_usd"] >= 0.0


def test_reject_over_consumption() -> None:
    _, issuance, capsule, _ = _issued_bundle()
    bound = bind_capsule_to_execution_pass(capsule, issuance)
    with pytest.raises(ValueError):
        consume_capsule_notional(bound, amount_usd=bound["remaining_notional_usd"] + 1.0)


def test_finalized_capsule_cannot_execute() -> None:
    _, issuance, capsule, _ = _issued_bundle()
    bound = bind_capsule_to_execution_pass(capsule, issuance)
    finalized = finalize_capsule(bound)
    check = validate_capsule_for_execution(finalized, requested_notional_usd=0.1)
    assert check["ok"] is False
    assert check["reason"] == "capsule_status_finalized"
