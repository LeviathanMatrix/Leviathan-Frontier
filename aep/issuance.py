from __future__ import annotations

import time
from typing import Any

from .accountability import compute_json_digest
from .brand import SPEC_ID, producer_metadata

ISSUANCE_OBJECT_SCHEMA_VERSION = "aep.issuance_object.v1"
EXECUTION_PASS_SCHEMA_VERSION = "aep.execution_pass.v1"
ISSUANCE_VALID_EXECUTION_STATUSES = {"ISSUED", "BOUND"}


def _now_ts() -> int:
    return int(time.time())


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _round(value: float, digits: int = 6) -> float:
    return round(float(value) + 1e-9, digits)


def _decision_to_pass_decision(final_decision: str) -> str:
    decision = str(final_decision or "").strip().upper()
    if decision in {"REVIEW", "ALLOW_WITH_HEAVY_BOND"}:
        return "NEEDS_REVIEW"
    if decision.startswith("ALLOW_WITH_") or decision == "ALLOW":
        return "ALLOW"
    return "DENY"


def _resolve_ttl_seconds(constitution: dict[str, Any], *, fallback: int = 900) -> int:
    issuance_cfg = constitution.get("issuance") if isinstance(constitution.get("issuance"), dict) else {}
    default_ttl = max(60, _safe_int(issuance_cfg.get("default_ttl_seconds"), fallback))
    max_ttl = max(60, _safe_int(issuance_cfg.get("max_ttl_seconds"), 3600))
    return min(default_ttl, max_ttl)


def _request_scope(action_request: dict[str, Any]) -> dict[str, Any]:
    action = action_request.get("action") if isinstance(action_request.get("action"), dict) else {}
    execution_preferences = (
        action_request.get("execution_preferences")
        if isinstance(action_request.get("execution_preferences"), dict)
        else {}
    )
    delegation = action_request.get("delegation") if isinstance(action_request.get("delegation"), dict) else {}
    return {
        "action_kind": str(action.get("kind") or "").strip().lower(),
        "mode": str(execution_preferences.get("mode") or "paper").strip().lower(),
        "chain": str(execution_preferences.get("chain") or "solana").strip().lower(),
        "network": str(execution_preferences.get("network") or "paper").strip().lower(),
        "venue": str(execution_preferences.get("venue") or "paper-virtual-orderbook").strip().lower(),
        "delegation_grant_id": str(delegation.get("grant_id") or "").strip() or None,
    }


def compute_issuance_capability_hash(
    *,
    case_id: str,
    action_request: dict[str, Any],
    policy_output: dict[str, Any],
) -> str:
    action = action_request.get("action") if isinstance(action_request.get("action"), dict) else {}
    delegation = action_request.get("delegation") if isinstance(action_request.get("delegation"), dict) else {}
    stable = {
        "case_id": str(case_id or "").strip(),
        "request_id": str(action_request.get("request_id") or "").strip(),
        "agent_id": str(action_request.get("agent", {}).get("agent_id") or "").strip()
        if isinstance(action_request.get("agent"), dict)
        else "",
        "action_kind": str(action.get("kind") or "").strip().lower(),
        "action_payload": action,
        "scope": _request_scope(action_request),
        "policy_final_decision": str(policy_output.get("final_decision") or "").strip().upper(),
        "policy_reason_codes": list(policy_output.get("reason_codes") or []),
        "delegation": {
            "principal_id": str(delegation.get("principal_id") or "").strip(),
            "delegate_id": str(delegation.get("delegate_id") or "").strip(),
            "role": str(delegation.get("role") or "").strip(),
            "grant_id": str(delegation.get("grant_id") or "").strip(),
        },
    }
    return compute_json_digest(stable)


def build_issuance_object(
    *,
    case_id: str,
    action_request: dict[str, Any],
    policy_output: dict[str, Any],
    risk_input: dict[str, Any],
    constitution: dict[str, Any],
    now_ts: int | None = None,
    ttl_seconds: int | None = None,
) -> dict[str, Any]:
    ts = _safe_int(now_ts, _now_ts())
    resolved_ttl = max(60, _safe_int(ttl_seconds, _resolve_ttl_seconds(constitution)))
    valid_until = ts + resolved_ttl

    final_decision = str(policy_output.get("final_decision") or "").strip().upper()
    pass_decision = _decision_to_pass_decision(final_decision)
    status = "ISSUED" if pass_decision == "ALLOW" else "DENIED"

    capability_hash = compute_issuance_capability_hash(
        case_id=case_id,
        action_request=action_request,
        policy_output=policy_output,
    )
    issuance_id = f"iss_{compute_json_digest({'case_id': case_id, 'request_id': action_request.get('request_id'), 'ts': ts})[:20]}"
    execution_pass_id = f"pass_{compute_json_digest({'issuance_id': issuance_id, 'capability_hash': capability_hash})[:20]}"

    risk_score = _safe_float(
        policy_output.get("derived_values", {}).get("risk_score_post_advisory")
        if isinstance(policy_output.get("derived_values"), dict)
        else None,
        0.0,
    )
    decision_confidence = _safe_float(
        risk_input.get("mcp_scores", {}).get("decision_confidence")
        if isinstance(risk_input.get("mcp_scores"), dict)
        else None,
        0.0,
    )

    return {
        "schema_version": ISSUANCE_OBJECT_SCHEMA_VERSION,
        "producer": producer_metadata("issuance"),
        "spec_id": SPEC_ID,
        "issuance_id": issuance_id,
        "status": status,
        "issued_at": ts,
        "valid_from": ts,
        "valid_until": valid_until,
        "ttl_seconds": resolved_ttl,
        "capability_hash": capability_hash,
        "decision": pass_decision,
        "decision_basis": {
            "policy_final_decision": final_decision,
            "hard_constraints_passed": bool(policy_output.get("hard_constraints_passed", False)),
            "reason_codes": list(policy_output.get("reason_codes") or []),
            "risk_score_post_advisory": _round(risk_score, 2),
            "decision_confidence": _round(decision_confidence, 6),
        },
        "execution_pass": {
            "schema_version": EXECUTION_PASS_SCHEMA_VERSION,
            "producer": producer_metadata("execution_pass"),
            "spec_id": SPEC_ID,
            "pass_id": execution_pass_id,
            "issuance_id": issuance_id,
            "status": status,
            "capability_hash": capability_hash,
            "issued_at": ts,
            "expires_at": valid_until,
            "scope": _request_scope(action_request),
        },
    }


def deny_issuance_object(
    *,
    case_id: str,
    action_request: dict[str, Any],
    policy_output: dict[str, Any],
    risk_input: dict[str, Any],
    constitution: dict[str, Any],
    now_ts: int | None = None,
) -> dict[str, Any]:
    issuance = build_issuance_object(
        case_id=case_id,
        action_request=action_request,
        policy_output=policy_output,
        risk_input=risk_input,
        constitution=constitution,
        now_ts=now_ts,
        ttl_seconds=60,
    )
    issuance["status"] = "DENIED"
    issuance["decision"] = "DENY"
    issuance_pass = issuance.get("execution_pass") if isinstance(issuance.get("execution_pass"), dict) else {}
    issuance_pass["status"] = "DENIED"
    issuance["execution_pass"] = issuance_pass
    return issuance


def refresh_issuance_execution_pass_fields(issuance: dict[str, Any]) -> dict[str, Any]:
    updated = dict(issuance)
    execution_pass = dict(updated.get("execution_pass") or {})
    execution_pass.setdefault("schema_version", EXECUTION_PASS_SCHEMA_VERSION)
    execution_pass.setdefault("producer", producer_metadata("execution_pass"))
    execution_pass.setdefault("spec_id", SPEC_ID)
    execution_pass["issuance_id"] = str(updated.get("issuance_id") or "")
    execution_pass["status"] = str(updated.get("status") or "").strip().upper()
    execution_pass["capability_hash"] = str(updated.get("capability_hash") or "")
    execution_pass["issued_at"] = _safe_int(updated.get("issued_at"), 0)
    execution_pass["expires_at"] = _safe_int(updated.get("valid_until"), 0)
    updated["execution_pass"] = execution_pass
    return updated


def validate_issuance_for_execution(
    issuance: dict[str, Any],
    *,
    at_ts: int | None = None,
    expected_capability_hash: str = "",
) -> dict[str, Any]:
    now_ts = _safe_int(at_ts, _now_ts())
    status = str(issuance.get("status") or "").strip().upper()
    if status not in ISSUANCE_VALID_EXECUTION_STATUSES:
        return {"ok": False, "reason": f"issuance_status_{status or 'unknown'}"}

    valid_until = _safe_int(issuance.get("valid_until"), 0)
    if valid_until > 0 and now_ts > valid_until:
        return {"ok": False, "reason": "issuance_expired"}

    if expected_capability_hash:
        cap_hash = str(issuance.get("capability_hash") or "").strip()
        if cap_hash != str(expected_capability_hash).strip():
            return {"ok": False, "reason": "capability_hash_mismatch"}

    return {
        "ok": True,
        "reason": "ok",
        "status": status,
        "valid_until": valid_until,
        "capability_hash": str(issuance.get("capability_hash") or "").strip(),
    }
