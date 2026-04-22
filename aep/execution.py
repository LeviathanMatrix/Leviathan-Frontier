from __future__ import annotations

import time
from typing import Any

from .accountability import compute_json_digest
from .brand import SPEC_ID, producer_metadata
from .capsule import extract_requested_notional_usd


def _now_ts() -> int:
    return int(time.time())


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _round(value: float, digits: int = 6) -> float:
    return round(float(value) + 1e-9, digits)


def _program_id_for_action(action: dict[str, Any]) -> str:
    kind = str(action.get("kind") or "").strip().lower()
    if kind == "trade":
        return "paper.virtual.exchange"
    if kind == "payment":
        return "paper.virtual.payment"
    if kind == "approve":
        return "paper.virtual.approve"
    if kind == "bridge":
        return "paper.virtual.bridge"
    if kind == "contract_call":
        call = action.get("contract_call") if isinstance(action.get("contract_call"), dict) else {}
        return str(call.get("program_id") or "paper.virtual.contract_call").strip()
    return "paper.virtual.unknown"


def execute_action(
    action_request: dict[str, Any],
    *,
    simulate: bool = False,
    now_ts: int | None = None,
) -> dict[str, Any]:
    ts = _safe_int(now_ts, _now_ts())
    action = action_request.get("action") if isinstance(action_request.get("action"), dict) else {}
    execution_preferences = (
        action_request.get("execution_preferences")
        if isinstance(action_request.get("execution_preferences"), dict)
        else {}
    )
    mode = str(execution_preferences.get("mode") or "paper").strip().lower() or "paper"
    kind = str(action.get("kind") or "").strip().lower() or "unknown"
    notional = extract_requested_notional_usd(action_request)

    execution_id = f"exec_{compute_json_digest({'request_id': action_request.get('request_id'), 'simulate': simulate, 'ts': ts})[:18]}"
    tx_prefix = "sim" if simulate else "tx"
    tx_id = f"{tx_prefix}_{compute_json_digest({'execution_id': execution_id, 'mode': mode})[:22]}"

    if notional <= 0:
        return {
            "ok": False,
            "producer": producer_metadata("execution"),
            "spec_id": SPEC_ID,
            "status": "FAILED",
            "simulated": bool(simulate),
            "execution_id": execution_id,
            "mode": mode,
            "kind": kind,
            "program_id": _program_id_for_action(action),
            "tx_id": "",
            "executed_notional_usd": 0.0,
            "executed_at": ts,
            "error": "requested_notional_usd_invalid",
            "receipt_ingest": {
                "ok": False,
                "receipt": {
                    "status": "FAILED",
                    "reason": "requested_notional_usd_invalid",
                },
            },
        }

    result_status = "SIMULATED" if simulate else "EXECUTED"
    return {
        "ok": True,
        "producer": producer_metadata("execution"),
        "spec_id": SPEC_ID,
        "status": result_status,
        "simulated": bool(simulate),
        "execution_id": execution_id,
        "mode": mode,
        "kind": kind,
        "program_id": _program_id_for_action(action),
        "tx_id": tx_id,
        "executed_notional_usd": _round(notional, 6),
        "executed_at": ts,
        "error": "",
        "receipt_ingest": {
            "ok": True,
            "receipt": {
                "status": result_status,
                "tx_id": tx_id,
                "executed_notional_usd": _round(notional, 6),
                "executed_at": ts,
            },
        },
    }
