from __future__ import annotations

import json
from pathlib import Path

from aep.intake import compile_text_intake
from aep.issuance import build_issuance_object, compute_issuance_capability_hash, validate_issuance_for_execution
from aep.risk_provider import StaticRiskInputProvider


def _fixtures_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures"


def _constitution() -> dict:
    return json.loads((_fixtures_root() / "constitution.paper_trade.v1.json").read_text(encoding="utf-8"))


def _action_request() -> dict:
    intake = compile_text_intake("buy 1 USDC of SOL", agent_id="agent-1")
    return intake["action_request"]


def test_issue_and_validate_execution_pass() -> None:
    action_request = _action_request()
    risk_input = StaticRiskInputProvider().build_risk_input(action_request)
    policy_output = {
        "final_decision": "ALLOW_WITH_LIGHT_BOND",
        "hard_constraints_passed": True,
        "reason_codes": [],
        "derived_values": {"risk_score_post_advisory": 12.5},
    }
    issuance = build_issuance_object(
        case_id="case-1",
        action_request=action_request,
        policy_output=policy_output,
        risk_input=risk_input,
        constitution=_constitution(),
    )
    assert issuance["status"] == "ISSUED"
    assert issuance["producer"]["company"] == "LeviathanMatrix"
    assert issuance["spec_id"] == "leviathanmatrix.aep.open-core.v1"
    assert issuance["execution_pass"]["producer"]["project"] == "LeviathanMatrix AEP Open Core"
    verify = validate_issuance_for_execution(issuance)
    assert verify["ok"] is True


def test_deny_issuance_not_valid_for_execution() -> None:
    action_request = _action_request()
    risk_input = StaticRiskInputProvider().build_risk_input(action_request)
    policy_output = {
        "final_decision": "DENY",
        "hard_constraints_passed": False,
        "reason_codes": ["HC_NOTIONAL_EXCEEDED"],
        "derived_values": {"risk_score_post_advisory": 90.0},
    }
    issuance = build_issuance_object(
        case_id="case-2",
        action_request=action_request,
        policy_output=policy_output,
        risk_input=risk_input,
        constitution=_constitution(),
    )
    assert issuance["status"] == "DENIED"
    verify = validate_issuance_for_execution(issuance)
    assert verify["ok"] is False


def test_heavy_bond_maps_to_needs_review() -> None:
    action_request = _action_request()
    risk_input = StaticRiskInputProvider().build_risk_input(action_request)
    policy_output = {
        "final_decision": "ALLOW_WITH_HEAVY_BOND",
        "hard_constraints_passed": True,
        "reason_codes": ["RISK_SCORE_HEAVY_BOND"],
        "derived_values": {"risk_score_post_advisory": 80.0},
    }
    issuance = build_issuance_object(
        case_id="case-heavy-bond",
        action_request=action_request,
        policy_output=policy_output,
        risk_input=risk_input,
        constitution=_constitution(),
    )
    assert issuance["decision"] == "NEEDS_REVIEW"
    assert issuance["status"] == "DENIED"


def test_capability_hash_changes_when_scope_changes() -> None:
    action_request = _action_request()
    policy_output = {"final_decision": "ALLOW_WITH_LIGHT_BOND", "reason_codes": []}
    cap1 = compute_issuance_capability_hash(
        case_id="case-3",
        action_request=action_request,
        policy_output=policy_output,
    )
    mutated = dict(action_request)
    mutated_action = dict(mutated.get("action") or {})
    trade = dict(mutated_action.get("trade") or {})
    trade["notional_usd"] = float(trade.get("notional_usd", 1.0)) + 1.0
    mutated_action["trade"] = trade
    mutated["action"] = mutated_action
    cap2 = compute_issuance_capability_hash(
        case_id="case-3",
        action_request=mutated,
        policy_output=policy_output,
    )
    assert cap1 != cap2
