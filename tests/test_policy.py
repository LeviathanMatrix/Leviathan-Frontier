from __future__ import annotations

import copy
from typing import Any

from aep.policy import evaluate_policy_decision


def _base_constitution() -> dict[str, Any]:
    return {
        "schema_version": "constitution.v1",
        "constitution_id": "const-test",
        "agent_id": "aep:solana:test-agent",
        "version": 1,
        "status": "active",
        "effective_at": 1774108800,
        "metadata_uri": "local://test",
        "hard_constraints": {
            "allowed_chains": ["solana"],
            "allowed_assets": ["USDC", "SOL"],
            "forbidden_assets": ["SCAM"],
            "enforce_asset_lists": False,
            "allowed_programs": ["paper.virtual.exchange"],
            "forbidden_programs": [],
            "allowed_counterparties": [],
            "forbidden_counterparties": [],
            "max_notional_per_tx_usd": 500,
            "max_daily_notional_usd": 10000,
            "max_slippage_bps": 150,
            "max_bridge_exposure_usd": 500,
            "max_leverage": 1,
            "require_counterparty_score_min": 50,
            "simulation_required": True,
        },
        "risk_parameters": {
            "base_bond_bps": 500,
            "risk_multiplier": 1,
            "base_bond_review_window_secs": 900,
            "evidence_min_score": 60,
            "decision_thresholds": {
                "allow_light_max": 35,
                "allow_standard_max": 65,
                "allow_heavy_max": 84.99,
                "deny_min": 85,
            },
            "advisory_mapping": {
                "allow_floor_score": 0,
                "review_floor_score": 50,
                "block_floor_score": 85,
            },
            "review_bond_bps": 200,
            "min_review_bond_usd": 20,
            "frivolous_penalty_ratio": 0.25,
        },
        "governance_parameters": {
            "upgrade_delay_secs": 86400,
            "emergency_guardian_enabled": True,
            "validator_quorum": 3,
            "allowed_upgraders": ["dao-multisig-01"],
            "guardian_accounts": ["guardian-01"],
        },
    }


def _base_intent() -> dict[str, Any]:
    return {
        "schema_version": "intent.v1",
        "intent_id": "intent-001",
        "agent_id": "aep:solana:test-agent",
        "intent_type": "swap",
        "chain": "solana",
        "assets_in": [{"asset": "USDC", "amount": "1000000", "decimals": 6, "usd_value": 1.0}],
        "assets_out_expectation": [
            {"asset": "SOL", "amount": "10000000", "decimals": 9, "usd_value": 1.0}
        ],
        "counterparties": [{"id": "paper-router", "kind": "service", "label": "Paper"}],
        "program_calls": [{"program_id": "paper.virtual.exchange", "method": "swap", "accounts": [], "data_hash": "0x01"}],
        "max_cost_usd": 0.1,
        "notional_usd": 1.0,
        "slippage_bps": 50,
        "expiry_ts": 1774110000,
        "requested_at": 1774109700,
        "reason": "test",
        "evidence_refs": [{"type": "hash", "ref": "0x1"}],
        "sim_result_hash": "0xsim",
        "policy_snapshot_root": "0xroot",
        "caller_session": "sess-1",
        "metadata": {},
    }


def _base_risk_input() -> dict[str, Any]:
    return {
        "schema_version": "risk_input.v1",
        "input_id": "risk-001",
        "agent_id": "aep:solana:test-agent",
        "intent_id": "intent-001",
        "generated_at": 1774109710,
        "source_systems": [{"name": "stub", "version": "1.0", "kind": "simulator"}],
        "mcp_scores": {
            "r1_control": 10,
            "r2_funding": 10,
            "r3_convergence": 10,
            "r4_terminal": 10,
            "r5_history": 10,
            "r6_lp_behavior": 10,
            "r7_anomaly": 10,
            "x_cross_signal": 10,
            "token_score": {
                "permission": 10,
                "rug": 10,
                "history": 10,
                "consistency_adjustment": 0,
                "weighted_score": 10,
            },
            "advisory_decision": "ALLOW",
            "decision_confidence": 0.9,
        },
        "aep_context": {
            "counterparty_risk": 10,
            "execution_complexity_risk": 10,
            "market_risk": 10,
            "anomaly_risk": 10,
            "evidence_gap_risk": 10,
            "governance_surface_risk": 10,
            "agent_reputation_bonus": 10,
            "treasury_health_bonus": 10,
        },
    }


def test_policy_allows_low_risk_case() -> None:
    output = evaluate_policy_decision(
        _base_constitution(),
        _base_intent(),
        _base_risk_input(),
    )
    assert output["output_version"] == "policy_output.v1"
    assert output["final_decision"].startswith("ALLOW_WITH_")


def test_policy_denies_block_advisory_case() -> None:
    constitution = _base_constitution()
    intent = _base_intent()
    risk_input = copy.deepcopy(_base_risk_input())
    risk_input["mcp_scores"].update(
        {
            "r1_control": 95,
            "r2_funding": 95,
            "r3_convergence": 95,
            "r4_terminal": 95,
            "r5_history": 95,
            "r6_lp_behavior": 95,
            "r7_anomaly": 95,
            "x_cross_signal": 95,
            "advisory_decision": "BLOCK",
        }
    )
    output = evaluate_policy_decision(constitution, intent, risk_input)
    assert output["final_decision"] == "DENY"
    assert "RISK_ADVISORY_BLOCK" in output["reason_codes"]
