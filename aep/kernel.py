from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

from .accountability import record_accountability_event
from .brand import SPEC_ID, producer_metadata
from .capsule import (
    bind_capsule_to_execution_pass,
    consume_capsule_notional,
    create_capital_capsule,
    extract_requested_notional_usd,
    validate_capsule_for_execution,
)
from .execution import execute_action
from .intake import compile_request_intake, compile_text_intake
from .issuance import (
    build_issuance_object,
    compute_issuance_capability_hash,
    deny_issuance_object,
    refresh_issuance_execution_pass_fields,
    validate_issuance_for_execution,
)
from .policy import evaluate_policy_decision
from .review import build_counterfactual_review
from .risk_provider import RiskInputProvider, StaticRiskInputProvider

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE_ROOT = ROOT / "artifacts" / "cases"
DEFAULT_ACCOUNTABILITY_LOG_PATH = ROOT / "artifacts" / "accountability" / "events.jsonl"
DEFAULT_CONSTITUTION_PATH = ROOT / "fixtures" / "constitution.paper_trade.v1.json"
DEFAULT_ASSET_REGISTRY_PATH = ROOT / "fixtures" / "paper_asset_registry.v1.json"
DEFAULT_DELEGATION_GRANTS_PATH = ROOT / "fixtures" / "delegation_grants.v1.json"

ACTION_CASE_SCHEMA_VERSION = "aep.action_case.v1"
ACTION_REVIEW_SCHEMA_VERSION = "aep.action_review.v1"
EXECUTION_CLAIM_SCHEMA_VERSION = "aep.execution_claim.v1"


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


def _json_load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must decode to a JSON object")
    return payload


def _json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def _resolve_case_root(case_root: str | Path | None) -> Path:
    root = Path(case_root) if case_root is not None else DEFAULT_CASE_ROOT
    root = root.expanduser()
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _case_path(case_id: str, case_root: Path) -> Path:
    return case_root / f"{case_id}.json"


def _accountability_log_path(case_root: str | Path | None) -> Path:
    root = _resolve_case_root(case_root)
    return root.parent / "accountability" / "events.jsonl"


def load_case(case_id: str, *, case_root: str | Path | None = None) -> dict[str, Any]:
    root = _resolve_case_root(case_root)
    path = _case_path(str(case_id or "").strip(), root)
    if not path.exists():
        raise FileNotFoundError(f"case not found: {path}")
    return _json_load(path)


def _persist_case(case_doc: dict[str, Any], *, case_root: str | Path | None = None) -> Path:
    root = _resolve_case_root(case_root)
    case_id = str(case_doc.get("case_id") or "").strip()
    if not case_id:
        raise ValueError("case_doc.case_id is required")
    path = _case_path(case_id, root)
    _json_write(path, case_doc)
    return path


def _load_constitution(constitution: Any = None, constitution_path: Any = None) -> dict[str, Any]:
    if isinstance(constitution, dict):
        return copy.deepcopy(constitution)
    if constitution_path is None or (isinstance(constitution_path, str) and not constitution_path.strip()):
        path = DEFAULT_CONSTITUTION_PATH
    else:
        path = Path(str(constitution_path)).expanduser()
        if not path.is_absolute():
            path = (ROOT / path).resolve()
    return _json_load(path)


def _intake_to_action_request(
    *,
    text: str,
    request: Any,
    agent_id: str,
    authority_pubkey: str,
    runtime_type: str,
    framework: str,
    session_id: str,
    asset_registry_path: Any,
    delegation_grants_path: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if request is None:
        result = compile_text_intake(
            text,
            agent_id=agent_id,
            authority_pubkey=authority_pubkey,
            runtime_type=runtime_type,
            framework=framework,
            session_id=session_id,
            asset_registry_path=asset_registry_path,
        )
    else:
        result = compile_request_intake(
            request,
            delegation_grants_path=delegation_grants_path,
        )

    status = str(result.get("status") or "").strip().lower()
    action_request = result.get("action_request") if isinstance(result.get("action_request"), dict) else None
    if status != "compiled" or action_request is None:
        reason = str(result.get("reason_code") or status or "intake_failed").strip()
        detail = str(result.get("detail") or result.get("clarification_question") or "").strip()
        raise ValueError(f"intake_not_compiled:{reason}:{detail}")
    return result, action_request


def _program_call_from_action(action: dict[str, Any]) -> tuple[str, str, list[str], str]:
    kind = str(action.get("kind") or "").strip().lower()
    if kind == "trade":
        trade = action.get("trade") if isinstance(action.get("trade"), dict) else {}
        return "paper.virtual.exchange", str(trade.get("side") or "swap"), [], ""
    if kind == "payment":
        return "paper.virtual.payment", "transfer", [], ""
    if kind == "approve":
        return "paper.virtual.approve", "approve", [], ""
    if kind == "bridge":
        return "paper.virtual.bridge", "bridge", [], ""
    if kind == "contract_call":
        call = action.get("contract_call") if isinstance(action.get("contract_call"), dict) else {}
        return (
            str(call.get("program_id") or "paper.virtual.contract_call").strip(),
            str(call.get("method") or "call").strip(),
            [str(x) for x in (call.get("accounts") or []) if str(x)],
            str(call.get("data_hash") or "").strip(),
        )
    return "paper.virtual.unknown", "unknown", [], ""


def _intent_type_from_action(kind: str) -> str:
    normalized = str(kind or "").strip().lower()
    if normalized == "trade":
        return "swap"
    if normalized == "payment":
        return "payment"
    if normalized == "approve":
        return "approve"
    if normalized == "contract_call":
        return "contract_call"
    if normalized == "bridge":
        return "bridge"
    return "swap"


def _build_intent_from_action_request(action_request: dict[str, Any], constitution: dict[str, Any]) -> dict[str, Any]:
    request_id = str(action_request.get("request_id") or "").strip()
    agent = action_request.get("agent") if isinstance(action_request.get("agent"), dict) else {}
    action = action_request.get("action") if isinstance(action_request.get("action"), dict) else {}
    kind = str(action.get("kind") or "trade").strip().lower()
    preferences = (
        action_request.get("execution_preferences")
        if isinstance(action_request.get("execution_preferences"), dict)
        else {}
    )

    notional = extract_requested_notional_usd(action_request)
    source_asset = "USDC"
    destination_asset = "USDC"
    slippage_bps = 0
    if kind == "trade":
        trade = action.get("trade") if isinstance(action.get("trade"), dict) else {}
        source_asset = str(trade.get("source_asset") or "USDC").strip().upper() or "USDC"
        destination_asset = str(trade.get("destination_asset") or "USDC").strip().upper() or "USDC"
        slippage_bps = _safe_int(trade.get("slippage_bps"), 0)
    elif kind == "payment":
        payment = action.get("payment") if isinstance(action.get("payment"), dict) else {}
        source_asset = str(payment.get("source_asset") or "USDC").strip().upper() or "USDC"
        destination_asset = source_asset
    elif kind == "approve":
        approve = action.get("approve") if isinstance(action.get("approve"), dict) else {}
        source_asset = str(approve.get("asset") or "USDC").strip().upper() or "USDC"
        destination_asset = source_asset
    elif kind == "contract_call":
        call = action.get("contract_call") if isinstance(action.get("contract_call"), dict) else {}
        source_asset = str(call.get("source_asset") or "USDC").strip().upper() or "USDC"
        destination_asset = source_asset
    elif kind == "bridge":
        bridge = action.get("bridge") if isinstance(action.get("bridge"), dict) else {}
        source_asset = str(bridge.get("source_asset") or "USDC").strip().upper() or "USDC"
        destination_asset = str(bridge.get("destination_asset") or source_asset).strip().upper() or source_asset

    program_id, method, accounts, data_hash = _program_call_from_action(action)
    now_ts = _now_ts()
    amount_micro = str(int(max(0.0, notional) * 1_000_000))
    policy_snapshot_root = str(constitution.get("metadata_uri") or "local://aep/constitution/open-core/v1").strip()

    return {
        "schema_version": "intent.v1",
        "intent_id": request_id or f"intent-{now_ts}",
        "agent_id": str(agent.get("agent_id") or "").strip() or "unknown-agent",
        "intent_type": _intent_type_from_action(kind),
        "chain": str(preferences.get("chain") or "solana").strip().lower() or "solana",
        "assets_in": [
            {
                "asset": source_asset,
                "amount": amount_micro,
                "decimals": 6,
                "usd_value": _round(notional, 6),
            }
        ],
        "assets_out_expectation": [
            {
                "asset": destination_asset,
                "amount": amount_micro,
                "decimals": 6,
                "usd_value": _round(notional, 6),
            }
        ],
        "counterparties": [
            {
                "id": str(preferences.get("venue") or "paper-virtual-orderbook").strip() or "paper-virtual-orderbook",
                "kind": "service",
                "label": "AEP Open Core Venue",
            }
        ],
        "program_calls": [
            {
                "program_id": program_id,
                "method": method or "call",
                "accounts": accounts,
                "data_hash": data_hash or f"0x{compute_issuance_capability_hash(case_id=request_id, action_request=action_request, policy_output={'final_decision': 'ALLOW'})[:16]}",
            }
        ],
        "max_cost_usd": _round(max(0.01, notional * 0.01), 6),
        "notional_usd": _round(notional, 6),
        "slippage_bps": max(0, slippage_bps),
        "expiry_ts": now_ts + 900,
        "requested_at": _safe_int(action_request.get("requested_at"), now_ts),
        "reason": str(action.get("source_text") or f"{kind} requested via open core").strip() or "open core request",
        "evidence_refs": [{"type": "hash", "ref": f"0x{request_id or 'intent'}"}],
        "sim_result_hash": f"0xsim-{request_id or now_ts}",
        "policy_snapshot_root": policy_snapshot_root,
        "caller_session": str(agent.get("session_id") or "").strip(),
        "metadata": {
            "network": str(preferences.get("network") or "paper").strip().lower() or "paper",
            "mode": str(preferences.get("mode") or "paper").strip().lower() or "paper",
        },
    }


def authorize_action(
    *,
    text: str = "",
    request: Any | None = None,
    agent_id: str = "",
    authority_pubkey: str = "",
    runtime_type: str = "generic-agent",
    framework: str = "",
    session_id: str = "",
    constitution: Any = None,
    constitution_path: Any = None,
    risk_provider: RiskInputProvider | None = None,
    case_root: str | Path | None = None,
    asset_registry_path: Any = DEFAULT_ASSET_REGISTRY_PATH,
    delegation_grants_path: Any = DEFAULT_DELEGATION_GRANTS_PATH,
    now_ts: int | None = None,
) -> dict[str, Any]:
    ts = _safe_int(now_ts, _now_ts())
    intake_result, action_request = _intake_to_action_request(
        text=text,
        request=request,
        agent_id=agent_id,
        authority_pubkey=authority_pubkey,
        runtime_type=runtime_type,
        framework=framework,
        session_id=session_id,
        asset_registry_path=asset_registry_path,
        delegation_grants_path=delegation_grants_path,
    )

    constitution_doc = _load_constitution(constitution, constitution_path)
    provider = risk_provider if isinstance(risk_provider, RiskInputProvider) else StaticRiskInputProvider()
    risk_input = provider.build_risk_input(action_request)
    intent = _build_intent_from_action_request(action_request, constitution_doc)
    policy_output = evaluate_policy_decision(
        constitution_doc,
        intent,
        risk_input,
        validate_schema=False,
    )

    case_id = f"case_{action_request.get('request_id') or ts}"
    final_decision = str(policy_output.get("final_decision") or "").strip().upper()
    if final_decision.startswith("ALLOW_WITH_") or final_decision == "ALLOW":
        issuance = build_issuance_object(
            case_id=case_id,
            action_request=action_request,
            policy_output=policy_output,
            risk_input=risk_input,
            constitution=constitution_doc,
            now_ts=ts,
        )
        issuance = refresh_issuance_execution_pass_fields(issuance)
        capsule = create_capital_capsule(
            case_id=case_id,
            action_request=action_request,
            issuance=issuance,
            policy_output=policy_output,
            risk_input=risk_input,
            now_ts=ts,
        )
        capsule = bind_capsule_to_execution_pass(capsule, issuance, now_ts=ts)
        authorization_status = "AUTHORIZED"
    else:
        issuance = deny_issuance_object(
            case_id=case_id,
            action_request=action_request,
            policy_output=policy_output,
            risk_input=risk_input,
            constitution=constitution_doc,
            now_ts=ts,
        )
        capsule = None
        authorization_status = "DENIED"

    decision_confidence = _safe_float(
        risk_input.get("mcp_scores", {}).get("decision_confidence")
        if isinstance(risk_input.get("mcp_scores"), dict)
        else 0.0,
        0.0,
    )
    risk_score = _safe_float(
        policy_output.get("derived_values", {}).get("risk_score_post_advisory")
        if isinstance(policy_output.get("derived_values"), dict)
        else 0.0,
        0.0,
    )

    case_doc = {
        "schema_version": ACTION_CASE_SCHEMA_VERSION,
        "producer": producer_metadata("action_case"),
        "spec_id": SPEC_ID,
        "case_id": case_id,
        "created_at": ts,
        "status": authorization_status,
        "request": action_request,
        "intake": intake_result,
        "intent": intent,
        "risk_input": risk_input,
        "policy_output": policy_output,
        "authorization": {
            "status": authorization_status,
            "issuance": issuance,
            "decision": {
                "capital_capsule": capsule,
            },
            "summary": {
                "risk_score": _round(risk_score, 2),
                "decision_confidence": _round(decision_confidence, 6),
                "reason_codes": list(policy_output.get("reason_codes") or []),
            },
        },
        "execution": {},
        "receipt": {},
        "review": {},
    }

    accountability_log = _accountability_log_path(case_root)
    record_accountability_event(stage="intake", payload={"case_id": case_id, "request_id": action_request.get("request_id")}, log_path=accountability_log)
    record_accountability_event(stage="policy", payload={"case_id": case_id, "final_decision": final_decision}, log_path=accountability_log)
    record_accountability_event(stage="authorization", payload={"case_id": case_id, "status": authorization_status, "issuance_id": issuance.get("issuance_id")}, log_path=accountability_log)

    _persist_case(case_doc, case_root=case_root)
    return case_doc


def execute_case(
    case_doc: dict[str, Any],
    *,
    simulate: bool = False,
    now_ts: int | None = None,
    case_root: str | Path | None = None,
) -> dict[str, Any]:
    ts = _safe_int(now_ts, _now_ts())
    updated = copy.deepcopy(case_doc)
    case_id = str(updated.get("case_id") or "").strip()
    authorization = updated.get("authorization") if isinstance(updated.get("authorization"), dict) else {}
    action_request = updated.get("request") if isinstance(updated.get("request"), dict) else {}

    if str(authorization.get("status") or "").strip().upper() != "AUTHORIZED":
        execution = {
            "ok": False,
            "status": "BLOCKED",
            "simulated": bool(simulate),
            "executed_at": ts,
            "error": "authorization_denied",
        }
        updated["execution"] = execution
        updated["status"] = "BLOCKED"
        _persist_case(updated, case_root=case_root)
        return updated

    issuance = authorization.get("issuance") if isinstance(authorization.get("issuance"), dict) else {}
    expected_cap_hash = compute_issuance_capability_hash(
        case_id=case_id,
        action_request=action_request,
        policy_output=updated.get("policy_output") if isinstance(updated.get("policy_output"), dict) else {},
    )
    issuance_check = validate_issuance_for_execution(issuance, at_ts=ts, expected_capability_hash=expected_cap_hash)
    if not bool(issuance_check.get("ok", False)):
        execution = {
            "ok": False,
            "status": "BLOCKED",
            "simulated": bool(simulate),
            "executed_at": ts,
            "error": str(issuance_check.get("reason") or "issuance_invalid"),
        }
        updated["execution"] = execution
        updated["status"] = "BLOCKED"
        _persist_case(updated, case_root=case_root)
        return updated

    decision = authorization.get("decision") if isinstance(authorization.get("decision"), dict) else {}
    capsule = decision.get("capital_capsule") if isinstance(decision.get("capital_capsule"), dict) else {}
    notional = extract_requested_notional_usd(action_request)
    capsule_check = validate_capsule_for_execution(capsule, requested_notional_usd=notional, at_ts=ts)
    if not bool(capsule_check.get("ok", False)):
        execution = {
            "ok": False,
            "status": "BLOCKED",
            "simulated": bool(simulate),
            "executed_at": ts,
            "error": str(capsule_check.get("reason") or "capsule_invalid"),
        }
        updated["execution"] = execution
        updated["status"] = "BLOCKED"
        _persist_case(updated, case_root=case_root)
        return updated

    execution = execute_action(action_request, simulate=simulate, now_ts=ts)
    updated["execution"] = execution

    receipt = {}
    receipt_ingest = execution.get("receipt_ingest") if isinstance(execution.get("receipt_ingest"), dict) else {}
    receipt_doc = receipt_ingest.get("receipt") if isinstance(receipt_ingest.get("receipt"), dict) else {}
    if receipt_doc:
        receipt = {
            "status": str(receipt_doc.get("status") or "").strip().upper(),
            "tx_id": str(receipt_doc.get("tx_id") or "").strip(),
            "executed_notional_usd": _safe_float(receipt_doc.get("executed_notional_usd"), 0.0),
            "executed_at": _safe_int(receipt_doc.get("executed_at"), ts),
        }
    updated["receipt"] = receipt

    if execution.get("ok", False) and not bool(execution.get("simulated", False)):
        consumed = consume_capsule_notional(
            capsule,
            amount_usd=notional,
            now_ts=ts,
            ticket_id=str(execution.get("execution_id") or ""),
        )
        decision["capital_capsule"] = consumed
        authorization["decision"] = decision
        updated["authorization"] = authorization

    updated["status"] = str(execution.get("status") or "").strip().upper() or "EXECUTED"
    record_accountability_event(
        stage="execution",
        payload={
            "case_id": case_id,
            "execution_status": updated["status"],
            "execution_id": execution.get("execution_id"),
        },
        log_path=_accountability_log_path(case_root),
    )
    _persist_case(updated, case_root=case_root)
    return updated


def simulate_case(
    case_doc: dict[str, Any],
    *,
    now_ts: int | None = None,
    case_root: str | Path | None = None,
) -> dict[str, Any]:
    return execute_case(case_doc, simulate=True, now_ts=now_ts, case_root=case_root)


def review_case(
    case_doc: dict[str, Any],
    *,
    now_ts: int | None = None,
    case_root: str | Path | None = None,
) -> dict[str, Any]:
    ts = _safe_int(now_ts, _now_ts())
    updated = copy.deepcopy(case_doc)
    authorization = updated.get("authorization") if isinstance(updated.get("authorization"), dict) else {}
    summary = authorization.get("summary") if isinstance(authorization.get("summary"), dict) else {}
    execution = updated.get("execution") if isinstance(updated.get("execution"), dict) else {}

    review_payload = build_counterfactual_review(
        {
            "risk_score": _safe_float(summary.get("risk_score"), 100.0),
            "decision_confidence": _safe_float(summary.get("decision_confidence"), 0.0),
        }
    )
    passed = bool(execution.get("ok", False)) and str(authorization.get("status") or "").strip().upper() == "AUTHORIZED"

    review_doc = {
        "schema_version": ACTION_REVIEW_SCHEMA_VERSION,
        "producer": producer_metadata("review"),
        "spec_id": SPEC_ID,
        "reviewed_at": ts,
        "passed": passed,
        "status": "PASSED" if passed else "FAILED",
        "counterfactual": review_payload,
    }
    updated["review"] = review_doc
    if passed:
        updated["status"] = str(updated.get("status") or "").strip().upper() or "EXECUTED"
    else:
        updated["status"] = "REVIEW_FAILED"

    record_accountability_event(
        stage="review",
        payload={"case_id": str(updated.get("case_id") or ""), "review_status": review_doc["status"]},
        log_path=_accountability_log_path(case_root),
    )
    _persist_case(updated, case_root=case_root)
    return updated


def export_execution_claim(case_doc: dict[str, Any]) -> dict[str, Any]:
    authorization = case_doc.get("authorization") if isinstance(case_doc.get("authorization"), dict) else {}
    issuance = authorization.get("issuance") if isinstance(authorization.get("issuance"), dict) else {}
    decision = authorization.get("decision") if isinstance(authorization.get("decision"), dict) else {}
    capsule = decision.get("capital_capsule") if isinstance(decision.get("capital_capsule"), dict) else {}
    execution = case_doc.get("execution") if isinstance(case_doc.get("execution"), dict) else {}
    receipt = case_doc.get("receipt") if isinstance(case_doc.get("receipt"), dict) else {}
    review = case_doc.get("review") if isinstance(case_doc.get("review"), dict) else {}
    request = case_doc.get("request") if isinstance(case_doc.get("request"), dict) else {}
    agent = request.get("agent") if isinstance(request.get("agent"), dict) else {}

    execution_claim = {
        "schema_version": EXECUTION_CLAIM_SCHEMA_VERSION,
        "producer": producer_metadata("execution_claim"),
        "spec_id": SPEC_ID,
        "case_id": str(case_doc.get("case_id") or "").strip(),
        "request_id": str(request.get("request_id") or "").strip(),
        "agent_id": str(agent.get("agent_id") or "").strip(),
        "authorization": {
            "status": str(authorization.get("status") or "").strip().upper(),
            "issuance_id": str(issuance.get("issuance_id") or "").strip(),
            "pass_id": str(issuance.get("execution_pass", {}).get("pass_id") or "").strip()
            if isinstance(issuance.get("execution_pass"), dict)
            else "",
            "capsule_id": str(capsule.get("capsule_id") or "").strip(),
        },
        "execution": {
            "status": str(execution.get("status") or "").strip().upper(),
            "execution_id": str(execution.get("execution_id") or "").strip(),
            "tx_id": str(execution.get("tx_id") or "").strip(),
            "mode": str(execution.get("mode") or "").strip().lower(),
            "executed_notional_usd": _round(_safe_float(execution.get("executed_notional_usd"), 0.0), 6),
        },
        "receipt": {
            "status": str(receipt.get("status") or "").strip().upper(),
        },
        "review": {
            "status": str(review.get("status") or "").strip().upper(),
            "passed": bool(review.get("passed", False)),
        },
        "timestamps": {
            "created_at": _safe_int(case_doc.get("created_at"), 0),
        },
    }
    return execution_claim


def run_text(
    *,
    text: str,
    agent_id: str,
    authority_pubkey: str = "",
    runtime_type: str = "generic-agent",
    framework: str = "",
    session_id: str = "",
    constitution: Any = None,
    constitution_path: Any = None,
    risk_provider: RiskInputProvider | None = None,
    case_root: str | Path | None = None,
    asset_registry_path: Any = DEFAULT_ASSET_REGISTRY_PATH,
    delegation_grants_path: Any = DEFAULT_DELEGATION_GRANTS_PATH,
) -> dict[str, Any]:
    case_doc = authorize_action(
        text=text,
        request=None,
        agent_id=agent_id,
        authority_pubkey=authority_pubkey,
        runtime_type=runtime_type,
        framework=framework,
        session_id=session_id,
        constitution=constitution,
        constitution_path=constitution_path,
        risk_provider=risk_provider,
        case_root=case_root,
        asset_registry_path=asset_registry_path,
        delegation_grants_path=delegation_grants_path,
    )
    case_doc = execute_case(case_doc, case_root=case_root)
    case_doc = review_case(case_doc, case_root=case_root)

    authorization = case_doc.get("authorization") if isinstance(case_doc.get("authorization"), dict) else {}
    issuance = authorization.get("issuance") if isinstance(authorization.get("issuance"), dict) else {}
    decision = authorization.get("decision") if isinstance(authorization.get("decision"), dict) else {}
    capsule = decision.get("capital_capsule") if isinstance(decision.get("capital_capsule"), dict) else {}
    execution = case_doc.get("execution") if isinstance(case_doc.get("execution"), dict) else {}
    receipt = case_doc.get("receipt") if isinstance(case_doc.get("receipt"), dict) else {}
    review = case_doc.get("review") if isinstance(case_doc.get("review"), dict) else {}

    ok = bool(execution.get("ok", False)) and str(review.get("status") or "").strip().upper() == "PASSED"
    return {
        "ok": ok,
        "producer": producer_metadata("cli_summary"),
        "spec_id": SPEC_ID,
        "case_id": str(case_doc.get("case_id") or "").strip(),
        "authorization": {
            "status": str(authorization.get("status") or "").strip().upper(),
            "issuance_id": str(issuance.get("issuance_id") or "").strip(),
            "capsule_id": str(capsule.get("capsule_id") or "").strip(),
        },
        "execution": {
            "status": str(execution.get("status") or "").strip().upper(),
            "execution_id": str(execution.get("execution_id") or "").strip(),
            "tx_id": str(execution.get("tx_id") or "").strip(),
        },
        "receipt": {
            "status": str(receipt.get("status") or "").strip().upper(),
        },
        "review": {
            "status": str(review.get("status") or "").strip().upper(),
        },
    }
