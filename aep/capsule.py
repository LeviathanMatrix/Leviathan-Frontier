from __future__ import annotations

import copy
import time
from typing import Any

from .accountability import compute_json_digest
from .brand import SPEC_ID, producer_metadata
from .capsule_pricing import build_capsule_pricing_profile

CAPSULE_SCHEMA_VERSION = "aep.capital_capsule.v1"
CAPSULE_ACTIVE_STATUSES = {"ISSUED", "ARMED", "PARTIALLY_CONSUMED"}
CAPSULE_TERMINAL_STATUSES = {"EXHAUSTED", "EXPIRED", "REVOKED", "FINALIZED"}


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


def extract_requested_notional_usd(action_request: dict[str, Any]) -> float:
    action = action_request.get("action") if isinstance(action_request.get("action"), dict) else {}
    kind = str(action.get("kind") or "").strip().lower()
    if kind == "trade":
        trade = action.get("trade") if isinstance(action.get("trade"), dict) else {}
        return _round(max(0.0, _safe_float(trade.get("notional_usd"), 0.0)), 6)
    if kind == "payment":
        payment = action.get("payment") if isinstance(action.get("payment"), dict) else {}
        return _round(max(0.0, _safe_float(payment.get("amount_usd"), 0.0)), 6)
    if kind == "approve":
        approve = action.get("approve") if isinstance(action.get("approve"), dict) else {}
        return _round(max(0.0, _safe_float(approve.get("allowance_usd"), 0.0)), 6)
    if kind == "contract_call":
        contract_call = action.get("contract_call") if isinstance(action.get("contract_call"), dict) else {}
        return _round(max(0.0, _safe_float(contract_call.get("value_usd"), 0.0)), 6)
    if kind == "bridge":
        bridge = action.get("bridge") if isinstance(action.get("bridge"), dict) else {}
        return _round(max(0.0, _safe_float(bridge.get("amount_usd"), 0.0)), 6)
    return 0.0


def _execution_mode(action_request: dict[str, Any]) -> str:
    preferences = (
        action_request.get("execution_preferences")
        if isinstance(action_request.get("execution_preferences"), dict)
        else {}
    )
    return str(preferences.get("mode") or "paper").strip().lower() or "paper"


def _review_intensity(policy_output: dict[str, Any]) -> str:
    final_decision = str(policy_output.get("final_decision") or "").strip().upper()
    if final_decision in {"DENY", "ALLOW_WITH_HEAVY_BOND"}:
        return "strict"
    if final_decision == "ALLOW_WITH_STANDARD_BOND":
        return "enhanced"
    return "standard"


def create_capital_capsule(
    *,
    case_id: str,
    action_request: dict[str, Any],
    issuance: dict[str, Any],
    policy_output: dict[str, Any],
    risk_input: dict[str, Any],
    now_ts: int | None = None,
) -> dict[str, Any]:
    issued_at = _safe_int(now_ts, _now_ts())
    notional = extract_requested_notional_usd(action_request)

    pricing_input = {
        "open_risk_score": _safe_float(
            policy_output.get("derived_values", {}).get("risk_score_post_advisory")
            if isinstance(policy_output.get("derived_values"), dict)
            else 0.0,
            0.0,
        ),
        "uncertainty": _safe_float(risk_input.get("open_risk", {}).get("uncertainty") if isinstance(risk_input.get("open_risk"), dict) else 0.5, 0.5),
        "evidence_coverage": _safe_float(
            risk_input.get("open_risk", {}).get("evidence_coverage")
            if isinstance(risk_input.get("open_risk"), dict)
            else 0.5,
            0.5,
        ),
        "execution_mode": _execution_mode(action_request),
        "review_intensity": _review_intensity(policy_output),
    }
    pricing_profile = build_capsule_pricing_profile(risk_input=pricing_input)

    ttl_seconds = max(60, _safe_int(issuance.get("ttl_seconds"), 900))
    valid_until = issued_at + ttl_seconds
    capsule_id = f"capsule_{compute_json_digest({'case_id': case_id, 'issuance_id': issuance.get('issuance_id'), 'ts': issued_at})[:20]}"

    return {
        "schema_version": CAPSULE_SCHEMA_VERSION,
        "producer": producer_metadata("capital_capsule"),
        "spec_id": SPEC_ID,
        "capsule_id": capsule_id,
        "capsule_hash": "",
        "capsule_status": "ISSUED",
        "case_id": str(case_id or "").strip(),
        "issuance_id": str(issuance.get("issuance_id") or "").strip(),
        "capsule_bound_pass_id": None,
        "max_notional_usd": _round(notional, 6),
        "consumed_notional_usd": 0.0,
        "remaining_notional_usd": _round(notional, 6),
        "valid_from": issued_at,
        "valid_until": valid_until,
        "execution_mode": _execution_mode(action_request),
        "pricing_profile": pricing_profile,
        "status_history": [
            {
                "event": "issued",
                "at_ts": issued_at,
                "status": "ISSUED",
            }
        ],
    }


def _update_hash(capsule: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(capsule)
    stable = copy.deepcopy(updated)
    stable.pop("capsule_hash", None)
    updated["capsule_hash"] = compute_json_digest(stable)
    return updated


def bind_capsule_to_execution_pass(
    capsule: dict[str, Any],
    issuance: dict[str, Any],
    *,
    now_ts: int | None = None,
) -> dict[str, Any]:
    ts = _safe_int(now_ts, _now_ts())
    updated = copy.deepcopy(capsule)
    execution_pass = issuance.get("execution_pass") if isinstance(issuance.get("execution_pass"), dict) else {}
    pass_id = str(execution_pass.get("pass_id") or "").strip()
    if not pass_id:
        raise ValueError("issuance.execution_pass.pass_id is required")
    updated["capsule_bound_pass_id"] = pass_id
    if str(updated.get("capsule_status") or "").strip().upper() == "ISSUED":
        updated["capsule_status"] = "ARMED"
    history = updated.get("status_history") if isinstance(updated.get("status_history"), list) else []
    history.append({"event": "bound", "at_ts": ts, "status": str(updated.get("capsule_status") or "")})
    updated["status_history"] = history
    return _update_hash(updated)


def consume_capsule_notional(
    capsule: dict[str, Any],
    *,
    amount_usd: float,
    now_ts: int | None = None,
    ticket_id: str = "",
) -> dict[str, Any]:
    ts = _safe_int(now_ts, _now_ts())
    consume = max(0.0, _safe_float(amount_usd, 0.0))
    if consume <= 0.0:
        raise ValueError("amount_usd must be > 0")

    status = str(capsule.get("capsule_status") or "").strip().upper()
    if status not in {"ARMED", "PARTIALLY_CONSUMED"}:
        raise ValueError(f"capsule status {status or 'unknown'} cannot consume")

    remaining = _safe_float(capsule.get("remaining_notional_usd"), 0.0)
    if consume > remaining + 1e-9:
        raise ValueError("capsule remaining notional exceeded")

    updated = copy.deepcopy(capsule)
    updated["consumed_notional_usd"] = _round(_safe_float(updated.get("consumed_notional_usd"), 0.0) + consume, 6)
    updated["remaining_notional_usd"] = _round(max(0.0, remaining - consume), 6)
    if updated["remaining_notional_usd"] <= 1e-9:
        updated["capsule_status"] = "EXHAUSTED"
    else:
        updated["capsule_status"] = "PARTIALLY_CONSUMED"
    history = updated.get("status_history") if isinstance(updated.get("status_history"), list) else []
    history.append(
        {
            "event": "consumed",
            "at_ts": ts,
            "status": updated["capsule_status"],
            "amount_usd": _round(consume, 6),
            "ticket_id": str(ticket_id or "").strip(),
        }
    )
    updated["status_history"] = history
    return _update_hash(updated)


def revoke_capsule(capsule: dict[str, Any], *, reason: str = "", now_ts: int | None = None) -> dict[str, Any]:
    ts = _safe_int(now_ts, _now_ts())
    updated = copy.deepcopy(capsule)
    updated["capsule_status"] = "REVOKED"
    history = updated.get("status_history") if isinstance(updated.get("status_history"), list) else []
    history.append({"event": "revoked", "at_ts": ts, "status": "REVOKED", "reason": str(reason or "").strip()})
    updated["status_history"] = history
    return _update_hash(updated)


def expire_capsule(capsule: dict[str, Any], *, now_ts: int | None = None) -> dict[str, Any]:
    ts = _safe_int(now_ts, _now_ts())
    updated = copy.deepcopy(capsule)
    updated["capsule_status"] = "EXPIRED"
    history = updated.get("status_history") if isinstance(updated.get("status_history"), list) else []
    history.append({"event": "expired", "at_ts": ts, "status": "EXPIRED"})
    updated["status_history"] = history
    return _update_hash(updated)


def finalize_capsule(capsule: dict[str, Any], *, now_ts: int | None = None) -> dict[str, Any]:
    ts = _safe_int(now_ts, _now_ts())
    updated = copy.deepcopy(capsule)
    updated["capsule_status"] = "FINALIZED"
    history = updated.get("status_history") if isinstance(updated.get("status_history"), list) else []
    history.append({"event": "finalized", "at_ts": ts, "status": "FINALIZED"})
    updated["status_history"] = history
    return _update_hash(updated)


def validate_capsule_for_execution(
    capsule: dict[str, Any],
    *,
    requested_notional_usd: float,
    at_ts: int | None = None,
) -> dict[str, Any]:
    now_ts = _safe_int(at_ts, _now_ts())
    status = str(capsule.get("capsule_status") or "").strip().upper()
    if status in CAPSULE_TERMINAL_STATUSES:
        return {"ok": False, "reason": f"capsule_status_{status.lower()}"}
    if status not in CAPSULE_ACTIVE_STATUSES:
        return {"ok": False, "reason": f"capsule_status_{status.lower() or 'unknown'}"}

    valid_until = _safe_int(capsule.get("valid_until"), 0)
    if valid_until > 0 and now_ts > valid_until:
        return {"ok": False, "reason": "capsule_expired"}

    remaining = _safe_float(capsule.get("remaining_notional_usd"), 0.0)
    requested = max(0.0, _safe_float(requested_notional_usd, 0.0))
    if requested <= 0.0:
        return {"ok": False, "reason": "requested_notional_invalid"}
    if requested > remaining + 1e-9:
        return {"ok": False, "reason": "capsule_remaining_exceeded", "remaining_notional_usd": _round(remaining, 6)}

    return {
        "ok": True,
        "reason": "ok",
        "status": status,
        "remaining_notional_usd": _round(remaining, 6),
    }
