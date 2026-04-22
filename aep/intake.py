from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from typing import Any

from .shared.assets import (
    DEFAULT_ASSET_REGISTRY_PATH,
    SOLANA_ADDRESS_RE,
    _coerce_document,
    _iter_asset_mentions,
    _load_asset_registry,
    _resolve_asset,
)
from .delegation import resolve_structured_delegation_for_intake
from .shared.parsing import (
    ACTION_REQUEST_API_VERSION,
    APPROVE_HINTS,
    BRIDGE_HINTS,
    CONTRACT_CALL_HINTS,
    BUY_HINTS,
    DEFAULT_NETWORK,
    DEFAULT_RUNTIME_TYPE,
    MONEY_RE,
    NUMBER_TOKEN_RE,
    PAYMENT_HINTS,
    SELL_HINTS,
    SUPPORTED_ACTION_KINDS,
    _detect_chain,
    _detect_requested_network,
    _extract_trade_quantity_candidate,
    parse_natural_language_approve_request,
    parse_natural_language_bridge_request,
    parse_natural_language_contract_call_request,
    parse_natural_language_payment_request,
    parse_natural_language_trade_request,
)

INTAKE_RESULT_SCHEMA_VERSION = "aep.intake_result.v1"
INTAKE_REQUEST_API_VERSION = "aep.intake_request.v1"

_SEQUENCE_MARKERS = (
    " then ",
    " and then ",
    " afterwards ",
    " after that ",
    "然后",
    "再",
    "接着",
    "同时",
    "并且",
)
_ADVANCED_TRADE_MARKERS = (
    "twap",
    "vwap",
    "iceberg",
    "delta-neutral",
    "delta neutral",
    "hedge",
    "hedging",
    "pair trade",
    "stat arb",
    "rebalance",
    "rebalancing",
    "grid",
    "dca",
    "对冲",
    "再平衡",
    "套利",
    "分批",
    "分片",
    "分次",
    "网格",
)
_ADVANCED_EXECUTION_PARAM_MARKERS = (
    "post-only",
    "post only",
    "maker only",
    "ioc",
    "fok",
    "fill-or-kill",
    "time in force",
    "tif",
    "take profit",
    "stop loss",
    "trailing stop",
    "限价",
    "止盈",
    "止损",
    "触发价",
)


def classify_boundary_action(
    text: str,
    *,
    asset_registry_path: Any = DEFAULT_ASSET_REGISTRY_PATH,
    default_network: str = DEFAULT_NETWORK,
) -> str:
    source_text = str(text or "").strip()
    if not source_text:
        return "unsupported"

    lowered = source_text.lower()
    if any(token in lowered for token in BRIDGE_HINTS):
        return "bridge"
    if any(token in lowered for token in APPROVE_HINTS):
        return "approve"
    if any(token in lowered for token in CONTRACT_CALL_HINTS):
        return "contract_call"
    if any(token in lowered for token in PAYMENT_HINTS) and not any(
        token in lowered for token in BUY_HINTS + SELL_HINTS
    ):
        return "payment"
    if any(token in lowered for token in BUY_HINTS + SELL_HINTS):
        return "trade"

    requested_chain = _detect_chain(source_text)
    requested_network = _detect_requested_network(source_text, default_network=default_network)
    registry = _load_asset_registry(asset_registry_path)
    mentioned_assets = _iter_asset_mentions(
        source_text,
        registry,
        chain=requested_chain,
        network=requested_network,
    )
    mentioned_non_usdc = [
        asset for asset in mentioned_assets if str(asset.get("symbol", "")).upper() != "USDC"
    ]
    has_money = MONEY_RE.search(source_text) is not None
    has_recipient = SOLANA_ADDRESS_RE.search(source_text) is not None
    if has_money and has_recipient and not mentioned_non_usdc:
        return "payment"
    if mentioned_non_usdc or has_money:
        return "trade"
    return "unsupported"


def compile_text_intake(
    text: str,
    *,
    agent_id: str,
    authority_pubkey: str = "",
    runtime_type: str = DEFAULT_RUNTIME_TYPE,
    framework: str = "",
    session_id: str = "",
    asset_registry_path: Any = DEFAULT_ASSET_REGISTRY_PATH,
    default_network: str = DEFAULT_NETWORK,
) -> dict[str, Any]:
    source_text = str(text or "").strip()
    action_family = classify_boundary_action(
        source_text,
        asset_registry_path=asset_registry_path,
        default_network=default_network,
    )
    candidate_slots = _extract_candidate_slots(
        source_text,
        action_family=action_family,
        asset_registry_path=asset_registry_path,
        default_network=default_network,
    )

    if not source_text:
        return _needs_clarification_response(
            source_text=source_text,
            action_family=action_family,
            missing_fields=["source_text"],
            clarification_question="请提供要执行的价值动作。",
            suggested_examples=[
                "buy 5 USDC of SOL",
                "send 3 USDC to <recipient>",
            ],
            suggested_input_shape={"text": "buy 5 USDC of SOL"},
            candidate_slots=candidate_slots,
            reason_code="EMPTY_INPUT",
        )

    if action_family == "unsupported":
        return _unsupported_response(
            source_text=source_text,
            action_family=action_family,
            reason_code="UNSUPPORTED_BOUNDARY_ACTION",
            candidate_slots=candidate_slots,
        )

    if action_family == "trade":
        return _compile_trade_intake(
            source_text,
            agent_id=agent_id,
            authority_pubkey=authority_pubkey,
            runtime_type=runtime_type,
            framework=framework,
            session_id=session_id,
            asset_registry_path=asset_registry_path,
            default_network=default_network,
            candidate_slots=candidate_slots,
        )
    if action_family == "bridge":
        return _compile_bridge_intake(
            source_text,
            agent_id=agent_id,
            authority_pubkey=authority_pubkey,
            runtime_type=runtime_type,
            framework=framework,
            session_id=session_id,
            asset_registry_path=asset_registry_path,
            default_network=default_network,
            candidate_slots=candidate_slots,
        )
    if action_family == "payment":
        return _compile_payment_intake(
            source_text,
            agent_id=agent_id,
            authority_pubkey=authority_pubkey,
            runtime_type=runtime_type,
            framework=framework,
            session_id=session_id,
            asset_registry_path=asset_registry_path,
            default_network=default_network,
            candidate_slots=candidate_slots,
        )
    if action_family == "approve":
        return _compile_approve_intake(
            source_text,
            agent_id=agent_id,
            authority_pubkey=authority_pubkey,
            runtime_type=runtime_type,
            framework=framework,
            session_id=session_id,
            asset_registry_path=asset_registry_path,
            default_network=default_network,
            candidate_slots=candidate_slots,
        )
    if action_family == "contract_call":
        return _compile_contract_call_intake(
            source_text,
            agent_id=agent_id,
            authority_pubkey=authority_pubkey,
            runtime_type=runtime_type,
            framework=framework,
            session_id=session_id,
            default_network=default_network,
            candidate_slots=candidate_slots,
        )

    return _unsupported_response(
        source_text=source_text,
        action_family=action_family,
        reason_code="UNSUPPORTED_BOUNDARY_ACTION",
        candidate_slots=candidate_slots,
    )


def compile_request_intake(
    value: Any,
    *,
    default_network: str = DEFAULT_NETWORK,
    delegation_grants_path: Any = None,
) -> dict[str, Any]:
    doc = _coerce_document(value, "intake_request")
    api_version = str(doc.get("api_version") or "").strip()

    if api_version == ACTION_REQUEST_API_VERSION:
        return _compile_action_request_passthrough(doc)
    if api_version != INTAKE_REQUEST_API_VERSION:
        return _unsupported_structured_response(
            raw_input=doc,
            action_family="unsupported",
            reason_code="UNSUPPORTED_INTAKE_DOCUMENT",
            detail=(
                f"intake_request.api_version must be {INTAKE_REQUEST_API_VERSION} "
                f"or {ACTION_REQUEST_API_VERSION}"
            ),
        )

    return _compile_structured_intake_document(
        doc,
        default_network=default_network,
        delegation_grants_path=delegation_grants_path,
    )


def _extract_candidate_slots(
    source_text: str,
    *,
    action_family: str,
    asset_registry_path: Any,
    default_network: str,
) -> dict[str, Any]:
    requested_chain = _detect_chain(source_text)
    requested_network = _detect_requested_network(source_text, default_network=default_network)
    candidate_slots: dict[str, Any] = {
        "chain": requested_chain,
        "network": requested_network,
        "has_money_amount": MONEY_RE.search(source_text) is not None,
        "has_address": SOLANA_ADDRESS_RE.search(source_text) is not None,
    }
    if action_family in {"trade", "approve", "bridge"}:
        registry = _load_asset_registry(asset_registry_path)
        mentioned_assets = _iter_asset_mentions(
            source_text,
            registry,
            chain=requested_chain,
            network=requested_network,
        )
        candidate_slots["mentioned_assets"] = [
            {
                "symbol": str(asset.get("symbol", "")).upper(),
                "asset_ref": str(asset.get("resolution", {}).get("matched_ref") or asset.get("symbol") or "").upper(),
            }
            for asset in mentioned_assets
        ]
    return candidate_slots


def _compile_action_request_passthrough(doc: dict[str, Any]) -> dict[str, Any]:
    compiled_request = copy.deepcopy(doc)
    input_mode = str(compiled_request.get("input_mode") or "").strip()
    if input_mode == "structured_request":
        compiled_request["input_mode"] = "structured"
    raw_input = str(compiled_request.get("action", {}).get("source_text") or "").strip()
    action_family = str(compiled_request.get("action", {}).get("kind") or "").strip() or "unsupported"
    return _compiled_structured_response(
        raw_input=raw_input or "structured_request",
        action_family=action_family,
        action_request=compiled_request,
        candidate_slots=_candidate_slots_from_action_request(compiled_request),
        compiler_path="structured_request.action_request_passthrough",
    )


def _compile_structured_intake_document(
    doc: dict[str, Any],
    *,
    default_network: str,
    delegation_grants_path: Any,
) -> dict[str, Any]:
    actor_context = doc.get("actor_context") if isinstance(doc.get("actor_context"), dict) else {}
    action = doc.get("action") if isinstance(doc.get("action"), dict) else {}
    execution_preferences = (
        doc.get("execution_preferences") if isinstance(doc.get("execution_preferences"), dict) else {}
    )
    delegation = _resolve_structured_delegation(
        doc,
        actor_context=actor_context,
        delegation_grants_path=delegation_grants_path,
    )
    requested_action_family = str(doc.get("requested_action_family") or "").strip()
    action_kind = str(action.get("kind") or requested_action_family or "").strip()
    raw_input = str(doc.get("raw_input") or action.get("source_text") or "").strip()

    missing_fields = _structured_missing_fields(
        actor_context=actor_context,
        action_kind=action_kind,
        action=action,
        execution_preferences=execution_preferences,
        delegation=delegation,
    )
    candidate_slots = _structured_candidate_slots(
        action_kind=action_kind,
        action=action,
        execution_preferences=execution_preferences,
        delegation=delegation,
    )

    if missing_fields:
        return _needs_clarification_structured_response(
            raw_input=raw_input or "structured_intake",
            action_family=action_kind or requested_action_family or "unsupported",
            missing_fields=missing_fields,
            clarification_question=_clarification_question_for_structured_fields(missing_fields),
            suggested_examples=[],
            suggested_input_shape={"api_version": INTAKE_REQUEST_API_VERSION, "requested_action_family": "trade"},
            candidate_slots=candidate_slots,
            reason_code="STRUCTURED_FIELDS_MISSING",
        )

    if action_kind not in SUPPORTED_ACTION_KINDS:
        return _unsupported_structured_response(
            raw_input=doc,
            action_family=action_kind or "unsupported",
            reason_code="UNSUPPORTED_BOUNDARY_ACTION",
            detail="structured intake action kind is outside the supported AEP boundary",
            candidate_slots=candidate_slots,
        )

    compiled_request = {
        "api_version": ACTION_REQUEST_API_VERSION,
        "request_id": str(doc.get("request_id") or _generate_structured_request_id(doc)),
        "requested_at": int(doc.get("requested_at") or time.time()),
        "agent": {
            "agent_id": str(actor_context.get("agent_id") or "").strip(),
            "authority_pubkey": str(actor_context.get("authority_pubkey") or "").strip(),
            "runtime_type": str(actor_context.get("runtime_type") or DEFAULT_RUNTIME_TYPE).strip(),
            "framework": str(actor_context.get("framework") or "").strip(),
            "session_id": str(actor_context.get("session_id") or _generate_session_id(doc)).strip(),
        },
        "input_mode": "structured",
        "action": copy.deepcopy(action),
        "execution_preferences": _normalized_execution_preferences(
            execution_preferences,
            default_network=default_network,
        ),
    }
    if raw_input and not str(compiled_request["action"].get("source_text") or "").strip():
        compiled_request["action"]["source_text"] = raw_input
    if delegation is not None:
        compiled_request["delegation"] = copy.deepcopy(delegation)

    return _compiled_structured_response(
        raw_input=raw_input or "structured_intake",
        action_family=action_kind,
        action_request=compiled_request,
        candidate_slots=candidate_slots,
        compiler_path="structured_intake.document_v1",
    )


def _structured_missing_fields(
    *,
    actor_context: dict[str, Any],
    action_kind: str,
    action: dict[str, Any],
    execution_preferences: dict[str, Any],
    delegation: dict[str, Any] | None,
) -> list[str]:
    missing_fields: list[str] = []
    if not str(actor_context.get("agent_id") or "").strip():
        missing_fields.append("actor_context.agent_id")
    if not action_kind:
        missing_fields.append("requested_action_family")
    if not execution_preferences:
        missing_fields.append("execution_preferences")
    else:
        for field in ("mode", "chain", "venue"):
            if not str(execution_preferences.get(field) or "").strip():
                missing_fields.append(f"execution_preferences.{field}")

    if action_kind == "trade":
        trade = action.get("trade") if isinstance(action.get("trade"), dict) else {}
        if not str(action.get("kind") or "").strip():
            missing_fields.append("action.kind")
        for field in ("side", "source_asset", "destination_asset", "notional_usd", "expected_price_usd"):
            if trade.get(field) in (None, ""):
                missing_fields.append(f"action.trade.{field}")
    elif action_kind == "payment":
        payment = action.get("payment") if isinstance(action.get("payment"), dict) else {}
        if not str(action.get("kind") or "").strip():
            missing_fields.append("action.kind")
        for field in ("source_asset", "amount_usd", "recipient"):
            if payment.get(field) in (None, ""):
                missing_fields.append(f"action.payment.{field}")
    elif action_kind == "approve":
        approve = action.get("approve") if isinstance(action.get("approve"), dict) else {}
        if not str(action.get("kind") or "").strip():
            missing_fields.append("action.kind")
        for field in ("asset", "spender", "allowance_usd"):
            if approve.get(field) in (None, ""):
                missing_fields.append(f"action.approve.{field}")
    elif action_kind == "contract_call":
        contract_call = action.get("contract_call") if isinstance(action.get("contract_call"), dict) else {}
        if not str(action.get("kind") or "").strip():
            missing_fields.append("action.kind")
        for field in ("program_id", "method"):
            if contract_call.get(field) in (None, ""):
                missing_fields.append(f"action.contract_call.{field}")
    elif action_kind == "bridge":
        bridge = action.get("bridge") if isinstance(action.get("bridge"), dict) else {}
        if not str(action.get("kind") or "").strip():
            missing_fields.append("action.kind")
        for field in ("source_asset", "amount_usd", "destination_chain"):
            if bridge.get(field) in (None, ""):
                missing_fields.append(f"action.bridge.{field}")

    if delegation is not None:
        for field in ("principal_id", "delegate_id", "role"):
            if not str(delegation.get(field) or "").strip():
                missing_fields.append(f"delegation.{field}")

    return missing_fields


def _resolve_structured_delegation(
    doc: dict[str, Any],
    *,
    actor_context: dict[str, Any],
    delegation_grants_path: Any,
) -> dict[str, Any] | None:
    return resolve_structured_delegation_for_intake(
        doc,
        actor_context=actor_context,
        delegation_grants_path=delegation_grants_path,
    )


def _structured_candidate_slots(
    *,
    action_kind: str,
    action: dict[str, Any],
    execution_preferences: dict[str, Any],
    delegation: dict[str, Any] | None,
) -> dict[str, Any]:
    candidate_slots: dict[str, Any] = {
        "chain": str(execution_preferences.get("chain") or "").strip(),
        "network": str(execution_preferences.get("network") or "").strip(),
        "mode": str(execution_preferences.get("mode") or "").strip(),
        "action_kind": action_kind,
        "has_delegation": delegation is not None,
    }
    if action_kind == "trade":
        trade = action.get("trade") if isinstance(action.get("trade"), dict) else {}
        candidate_slots.update(
            {
                "source_asset": str(trade.get("source_asset") or "").upper(),
                "destination_asset": str(trade.get("destination_asset") or "").upper(),
                "notional_usd": trade.get("notional_usd"),
            }
        )
    elif action_kind == "payment":
        payment = action.get("payment") if isinstance(action.get("payment"), dict) else {}
        candidate_slots.update(
            {
                "source_asset": str(payment.get("source_asset") or "").upper(),
                "amount_usd": payment.get("amount_usd"),
                "recipient": str(payment.get("recipient") or "").strip(),
            }
        )
    elif action_kind == "approve":
        approve = action.get("approve") if isinstance(action.get("approve"), dict) else {}
        candidate_slots.update(
            {
                "asset": str(approve.get("asset") or "").upper(),
                "allowance_usd": approve.get("allowance_usd"),
                "spender": str(approve.get("spender") or "").strip(),
            }
        )
    elif action_kind == "contract_call":
        contract_call = action.get("contract_call") if isinstance(action.get("contract_call"), dict) else {}
        candidate_slots.update(
            {
                "program_id": str(contract_call.get("program_id") or "").strip(),
                "method": str(contract_call.get("method") or "").strip(),
            }
        )
    elif action_kind == "bridge":
        bridge = action.get("bridge") if isinstance(action.get("bridge"), dict) else {}
        candidate_slots.update(
            {
                "source_asset": str(bridge.get("source_asset") or "").upper(),
                "amount_usd": bridge.get("amount_usd"),
                "destination_chain": str(bridge.get("destination_chain") or "").strip().lower(),
                "destination_network": str(bridge.get("destination_network") or "").strip().lower(),
                "destination_asset": str(bridge.get("destination_asset") or "").upper(),
            }
        )
    if delegation is not None:
        candidate_slots["delegation"] = {
            "principal_id": str(delegation.get("principal_id") or "").strip(),
            "delegate_id": str(delegation.get("delegate_id") or "").strip(),
            "role": str(delegation.get("role") or "").strip(),
        }
    return candidate_slots


def _candidate_slots_from_action_request(action_request: dict[str, Any]) -> dict[str, Any]:
    action = action_request.get("action") if isinstance(action_request.get("action"), dict) else {}
    execution_preferences = (
        action_request.get("execution_preferences")
        if isinstance(action_request.get("execution_preferences"), dict)
        else {}
    )
    delegation = action_request.get("delegation") if isinstance(action_request.get("delegation"), dict) else None
    action_kind = str(action.get("kind") or "").strip()
    return _structured_candidate_slots(
        action_kind=action_kind,
        action=action,
        execution_preferences=execution_preferences,
        delegation=delegation,
    )


def _normalized_execution_preferences(
    execution_preferences: dict[str, Any],
    *,
    default_network: str,
) -> dict[str, Any]:
    normalized = copy.deepcopy(execution_preferences)
    if not str(normalized.get("network") or "").strip():
        normalized["network"] = default_network
    if not str(normalized.get("mode") or "").strip():
        normalized["mode"] = "paper" if normalized["network"] == "paper" else "devnet"
    if not str(normalized.get("chain") or "").strip():
        normalized["chain"] = "solana"
    if "auto_review" not in normalized:
        normalized["auto_review"] = True
    return normalized


def _generate_structured_request_id(doc: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(doc, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()
    return f"req_{digest[:16]}"


def _generate_session_id(doc: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(doc.get("actor_context") or {}, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    return f"intake-session-{digest[:12]}"


def _compile_trade_intake(
    source_text: str,
    *,
    agent_id: str,
    authority_pubkey: str,
    runtime_type: str,
    framework: str,
    session_id: str,
    asset_registry_path: Any,
    default_network: str,
    candidate_slots: dict[str, Any],
) -> dict[str, Any]:
    missing_fields = _trade_missing_fields(
        source_text,
        asset_registry_path=asset_registry_path,
        default_network=default_network,
    )
    if missing_fields:
        question = "你想交易哪个资产？"
        examples = ["buy 5 USDC of SOL", "sell 2 SOL"]
        suggested_shape: dict[str, Any] = {"text": "buy 5 USDC of SOL"}
        if missing_fields == ["notional_usd_or_quantity"]:
            question = "要交易多少 USDC，或者卖出多少目标资产？"
        elif missing_fields == ["destination_asset"]:
            question = "你想交易哪个资产？"
        else:
            question = "请补充要交易的资产，以及交易金额或数量。"
        return _needs_clarification_response(
            source_text=source_text,
            action_family="trade",
            missing_fields=missing_fields,
            clarification_question=question,
            suggested_examples=examples,
            suggested_input_shape=suggested_shape,
            candidate_slots=candidate_slots,
            reason_code="TRADE_FIELDS_MISSING",
        )

    semantic_issues = _trade_semantic_fidelity_issues(source_text)
    if semantic_issues:
        candidate_slots["semantic_fidelity_guard"] = semantic_issues
        return _needs_clarification_response(
            source_text=source_text,
            action_family="trade",
            missing_fields=["execution_plan"],
            clarification_question=(
                "该请求包含多腿/时序/高级执行语义。请提供结构化 execution_plan，"
                "避免系统把复杂策略降级成单笔交易。"
            ),
            suggested_examples=[
                "buy 5 USDC of SOL",
                "只执行单笔：buy 20 USDC of SOL",
            ],
            suggested_input_shape={
                "request": {
                    "api_version": "aep.intake_request.v1",
                    "requested_action_family": "trade",
                    "action": {"kind": "trade", "trade": {"notional_usd": 5.0}},
                }
            },
            candidate_slots=candidate_slots,
            reason_code="TRADE_SEMANTIC_FIDELITY_GUARD",
        )

    try:
        action_request = parse_natural_language_trade_request(
            source_text,
            agent_id=agent_id,
            authority_pubkey=authority_pubkey,
            runtime_type=runtime_type,
            framework=framework,
            session_id=session_id,
            asset_registry_path=asset_registry_path,
            default_network=default_network,
        )
    except ValueError as exc:
        return _unsupported_response(
            source_text=source_text,
            action_family="trade",
            reason_code="TRADE_PARSE_FAILED",
            candidate_slots=candidate_slots,
            detail=str(exc),
        )
    return _compiled_response(
        source_text=source_text,
        action_family="trade",
        action_request=action_request,
        candidate_slots=candidate_slots,
        compiler_path="quick_parser.trade",
    )


def _compile_bridge_intake(
    source_text: str,
    *,
    agent_id: str,
    authority_pubkey: str,
    runtime_type: str,
    framework: str,
    session_id: str,
    asset_registry_path: Any,
    default_network: str,
    candidate_slots: dict[str, Any],
) -> dict[str, Any]:
    if _bridge_has_multistep_intent(source_text):
        candidate_slots["semantic_fidelity_guard"] = {
            "reason_codes": ["bridge_multistep_sequence_detected"],
            "requires_structured_plan": True,
        }
        return _needs_clarification_response(
            source_text=source_text,
            action_family="bridge",
            missing_fields=["execution_plan"],
            clarification_question=(
                "检测到跨链后续联动动作（例如 then buy/swap）。"
                "请改为结构化多步执行计划，避免只执行第一步桥接。"
            ),
            suggested_examples=[
                "bridge 10 USDC to base",
                "只执行桥接：bridge 25 USDC to ethereum",
            ],
            suggested_input_shape={
                "request": {
                    "api_version": "aep.intake_request.v1",
                    "requested_action_family": "bridge",
                    "action": {"kind": "bridge", "bridge": {"amount_usd": 10.0, "destination_chain": "base"}},
                }
            },
            candidate_slots=candidate_slots,
            reason_code="BRIDGE_MULTISTEP_NOT_SUPPORTED",
        )

    missing_fields: list[str] = []
    if MONEY_RE.search(source_text) is None:
        missing_fields.append("amount_usd")
    if not any(
        alias in source_text.lower()
        for alias in ("base", "ethereum", "eth", "arbitrum", "optimism", "polygon", "bsc", "bnb")
    ):
        missing_fields.append("destination_chain")
    if missing_fields:
        return _needs_clarification_response(
            source_text=source_text,
            action_family="bridge",
            missing_fields=missing_fields,
            clarification_question=_clarification_question_for_bridge(missing_fields),
            suggested_examples=[
                "bridge 10 USDC to base",
                "把 25 USDC 跨链到 ethereum",
            ],
            suggested_input_shape={"text": "bridge 10 USDC to base"},
            candidate_slots=candidate_slots,
            reason_code="BRIDGE_FIELDS_MISSING",
        )
    try:
        action_request = parse_natural_language_bridge_request(
            source_text,
            agent_id=agent_id,
            authority_pubkey=authority_pubkey,
            runtime_type=runtime_type,
            framework=framework,
            session_id=session_id,
            asset_registry_path=asset_registry_path,
            default_network=default_network,
        )
    except ValueError as exc:
        return _unsupported_response(
            source_text=source_text,
            action_family="bridge",
            reason_code="BRIDGE_PARSE_FAILED",
            candidate_slots=candidate_slots,
            detail=str(exc),
        )
    return _compiled_response(
        source_text=source_text,
        action_family="bridge",
        action_request=action_request,
        candidate_slots=candidate_slots,
        compiler_path="quick_parser.bridge",
    )


def _compile_payment_intake(
    source_text: str,
    *,
    agent_id: str,
    authority_pubkey: str,
    runtime_type: str,
    framework: str,
    session_id: str,
    asset_registry_path: Any,
    default_network: str,
    candidate_slots: dict[str, Any],
) -> dict[str, Any]:
    missing_fields: list[str] = []
    if MONEY_RE.search(source_text) is None:
        missing_fields.append("amount_usd")
    if SOLANA_ADDRESS_RE.search(source_text) is None:
        missing_fields.append("recipient")
    if missing_fields:
        return _needs_clarification_response(
            source_text=source_text,
            action_family="payment",
            missing_fields=missing_fields,
            clarification_question=_clarification_question_for_payment(missing_fields),
            suggested_examples=[
                "send 3 USDC to 9M51Vh1XU9yrtXs8xZjhwrzbBMVinWP85oT7DWSJEDEY",
                "支付 5 USDC 给 <recipient>",
            ],
            suggested_input_shape={"text": "send 3 USDC to <recipient>"},
            candidate_slots=candidate_slots,
            reason_code="PAYMENT_FIELDS_MISSING",
        )
    try:
        action_request = parse_natural_language_payment_request(
            source_text,
            agent_id=agent_id,
            authority_pubkey=authority_pubkey,
            runtime_type=runtime_type,
            framework=framework,
            session_id=session_id,
            asset_registry_path=asset_registry_path,
            default_network=default_network,
        )
    except ValueError as exc:
        return _unsupported_response(
            source_text=source_text,
            action_family="payment",
            reason_code="PAYMENT_PARSE_FAILED",
            candidate_slots=candidate_slots,
            detail=str(exc),
        )
    return _compiled_response(
        source_text=source_text,
        action_family="payment",
        action_request=action_request,
        candidate_slots=candidate_slots,
        compiler_path="quick_parser.payment",
    )


def _compile_approve_intake(
    source_text: str,
    *,
    agent_id: str,
    authority_pubkey: str,
    runtime_type: str,
    framework: str,
    session_id: str,
    asset_registry_path: Any,
    default_network: str,
    candidate_slots: dict[str, Any],
) -> dict[str, Any]:
    missing_fields: list[str] = []
    if MONEY_RE.search(source_text) is None:
        missing_fields.append("allowance_usd")
    if SOLANA_ADDRESS_RE.search(source_text) is None:
        missing_fields.append("spender")
    if missing_fields:
        return _needs_clarification_response(
            source_text=source_text,
            action_family="approve",
            missing_fields=missing_fields,
            clarification_question=_clarification_question_for_approve(missing_fields),
            suggested_examples=[
                "approve 5 USDC for 9M51Vh1XU9yrtXs8xZjhwrzbBMVinWP85oT7DWSJEDEY",
                "授权 10 USDC 给 <spender>",
            ],
            suggested_input_shape={"text": "approve 5 USDC for <spender>"},
            candidate_slots=candidate_slots,
            reason_code="APPROVE_FIELDS_MISSING",
        )
    try:
        action_request = parse_natural_language_approve_request(
            source_text,
            agent_id=agent_id,
            authority_pubkey=authority_pubkey,
            runtime_type=runtime_type,
            framework=framework,
            session_id=session_id,
            asset_registry_path=asset_registry_path,
            default_network=default_network,
        )
    except ValueError as exc:
        return _unsupported_response(
            source_text=source_text,
            action_family="approve",
            reason_code="APPROVE_PARSE_FAILED",
            candidate_slots=candidate_slots,
            detail=str(exc),
        )
    return _compiled_response(
        source_text=source_text,
        action_family="approve",
        action_request=action_request,
        candidate_slots=candidate_slots,
        compiler_path="quick_parser.approve",
    )


def _compile_contract_call_intake(
    source_text: str,
    *,
    agent_id: str,
    authority_pubkey: str,
    runtime_type: str,
    framework: str,
    session_id: str,
    default_network: str,
    candidate_slots: dict[str, Any],
) -> dict[str, Any]:
    try:
        action_request = parse_natural_language_contract_call_request(
            source_text,
            agent_id=agent_id,
            authority_pubkey=authority_pubkey,
            runtime_type=runtime_type,
            framework=framework,
            session_id=session_id,
            default_network=default_network,
        )
    except ValueError as exc:
        return _unsupported_response(
            source_text=source_text,
            action_family="contract_call",
            reason_code="CONTRACT_CALL_PARSE_FAILED",
            candidate_slots=candidate_slots,
            detail=str(exc),
        )
    return _compiled_response(
        source_text=source_text,
        action_family="contract_call",
        action_request=action_request,
        candidate_slots=candidate_slots,
        compiler_path="quick_parser.contract_call",
    )


def _trade_missing_fields(
    source_text: str,
    *,
    asset_registry_path: Any,
    default_network: str,
) -> list[str]:
    requested_chain = _detect_chain(source_text)
    requested_network = _detect_requested_network(source_text, default_network=default_network)
    registry = _load_asset_registry(asset_registry_path)
    mentioned_assets = _iter_asset_mentions(
        source_text,
        registry,
        chain=requested_chain,
        network=requested_network,
    )
    mentioned_non_usdc = [
        asset for asset in mentioned_assets if str(asset.get("symbol", "")).upper() != "USDC"
    ]
    has_money = MONEY_RE.search(source_text) is not None
    has_quantity_asset = (
        _extract_trade_quantity_candidate(
            source_text,
            mentioned_assets=mentioned_assets,
            registry=registry,
            requested_chain=requested_chain,
            requested_network=requested_network,
        )
        is not None
    )

    missing_fields: list[str] = []
    if not mentioned_non_usdc and not has_quantity_asset:
        missing_fields.append("destination_asset")
    if not has_money and not has_quantity_asset:
        missing_fields.append("notional_usd_or_quantity")
    return missing_fields


def _trade_semantic_fidelity_issues(source_text: str) -> list[str]:
    lowered = f" {str(source_text or '').lower()} "
    reasons: list[str] = []

    if any(token in lowered for token in _ADVANCED_TRADE_MARKERS):
        reasons.append("advanced_trade_strategy_marker_detected")
    if any(token in lowered for token in _ADVANCED_EXECUTION_PARAM_MARKERS):
        reasons.append("advanced_execution_parameter_marker_detected")
    if re.search(r"\b\d+(?:\.\d+)?\s*(?:bps|bp|basis point|basis points)\b", lowered):
        reasons.append("explicit_bps_parameter_detected")
    if re.search(r"\b\d{1,3}\s*/\s*\d{1,3}\b", lowered):
        reasons.append("portfolio_ratio_marker_detected")
    if re.search(r"\bover\s+\d+\s*(?:minute|minutes|hour|hours|day|days)\b", lowered):
        reasons.append("time_window_execution_marker_detected")
    if re.search(r"\d+\s*(?:分钟|小时|天)", source_text):
        reasons.append("time_window_execution_marker_detected_cn")
    if any(marker in lowered for marker in _SEQUENCE_MARKERS):
        reasons.append("sequenced_execution_marker_detected")

    deduped: list[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return deduped


def _bridge_has_multistep_intent(source_text: str) -> bool:
    lowered = f" {str(source_text or '').lower()} "
    has_sequence = any(marker in lowered for marker in _SEQUENCE_MARKERS)
    if not has_sequence:
        return False
    secondary_action_markers = BUY_HINTS + SELL_HINTS + PAYMENT_HINTS + APPROVE_HINTS + CONTRACT_CALL_HINTS
    return any(token in lowered for token in secondary_action_markers)


def _compiled_response(
    *,
    source_text: str,
    action_family: str,
    action_request: dict[str, Any],
    candidate_slots: dict[str, Any],
    compiler_path: str,
) -> dict[str, Any]:
    return {
        "schema_version": INTAKE_RESULT_SCHEMA_VERSION,
        "status": "compiled",
        "input_source": "natural_language",
        "raw_input": source_text,
        "action_family": action_family,
        "compiler_path": compiler_path,
        "candidate_slots": candidate_slots,
        "missing_fields": [],
        "clarification_question": "",
        "suggested_examples": [],
        "suggested_input_shape": {},
        "reenter_mode": "merge_into_pending_intake",
        "action_request": action_request,
    }


def _compiled_structured_response(
    *,
    raw_input: str,
    action_family: str,
    action_request: dict[str, Any],
    candidate_slots: dict[str, Any],
    compiler_path: str,
) -> dict[str, Any]:
    return {
        "schema_version": INTAKE_RESULT_SCHEMA_VERSION,
        "status": "compiled",
        "input_source": "structured_request",
        "raw_input": raw_input,
        "action_family": action_family,
        "compiler_path": compiler_path,
        "candidate_slots": candidate_slots,
        "missing_fields": [],
        "clarification_question": "",
        "suggested_examples": [],
        "suggested_input_shape": {},
        "reenter_mode": "merge_into_pending_intake",
        "action_request": action_request,
    }


def _needs_clarification_response(
    *,
    source_text: str,
    action_family: str,
    missing_fields: list[str],
    clarification_question: str,
    suggested_examples: list[str],
    suggested_input_shape: dict[str, Any],
    candidate_slots: dict[str, Any],
    reason_code: str,
) -> dict[str, Any]:
    return {
        "schema_version": INTAKE_RESULT_SCHEMA_VERSION,
        "status": "needs_clarification",
        "input_source": "natural_language",
        "raw_input": source_text,
        "action_family": action_family,
        "reason_code": reason_code,
        "candidate_slots": candidate_slots,
        "missing_fields": missing_fields,
        "clarification_question": clarification_question,
        "suggested_examples": suggested_examples,
        "suggested_input_shape": suggested_input_shape,
        "reenter_mode": "merge_into_pending_intake",
        "action_request": None,
    }


def _needs_clarification_structured_response(
    *,
    raw_input: str,
    action_family: str,
    missing_fields: list[str],
    clarification_question: str,
    suggested_examples: list[str],
    suggested_input_shape: dict[str, Any],
    candidate_slots: dict[str, Any],
    reason_code: str,
) -> dict[str, Any]:
    return {
        "schema_version": INTAKE_RESULT_SCHEMA_VERSION,
        "status": "needs_clarification",
        "input_source": "structured_request",
        "raw_input": raw_input,
        "action_family": action_family,
        "reason_code": reason_code,
        "candidate_slots": candidate_slots,
        "missing_fields": missing_fields,
        "clarification_question": clarification_question,
        "suggested_examples": suggested_examples,
        "suggested_input_shape": suggested_input_shape,
        "reenter_mode": "merge_into_pending_intake",
        "action_request": None,
    }


def _unsupported_response(
    *,
    source_text: str,
    action_family: str,
    reason_code: str,
    candidate_slots: dict[str, Any],
    detail: str = "",
) -> dict[str, Any]:
    return {
        "schema_version": INTAKE_RESULT_SCHEMA_VERSION,
        "status": "unsupported",
        "input_source": "natural_language",
        "raw_input": source_text,
        "action_family": action_family,
        "reason_code": reason_code,
        "detail": detail,
        "candidate_slots": candidate_slots,
        "missing_fields": [],
        "clarification_question": "",
        "suggested_examples": [],
        "suggested_input_shape": {},
        "reenter_mode": "merge_into_pending_intake",
        "action_request": None,
    }


def _unsupported_structured_response(
    *,
    raw_input: Any,
    action_family: str,
    reason_code: str,
    detail: str = "",
    candidate_slots: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": INTAKE_RESULT_SCHEMA_VERSION,
        "status": "unsupported",
        "input_source": "structured_request",
        "raw_input": raw_input,
        "action_family": action_family,
        "reason_code": reason_code,
        "detail": detail,
        "candidate_slots": candidate_slots or {},
        "missing_fields": [],
        "clarification_question": "",
        "suggested_examples": [],
        "suggested_input_shape": {},
        "reenter_mode": "merge_into_pending_intake",
        "action_request": None,
    }


def _clarification_question_for_payment(missing_fields: list[str]) -> str:
    if missing_fields == ["amount_usd"]:
        return "要支付多少 USDC？"
    if missing_fields == ["recipient"]:
        return "要支付给谁？请提供收款地址。"
    return "请补充支付金额和收款地址。"


def _clarification_question_for_approve(missing_fields: list[str]) -> str:
    if missing_fields == ["allowance_usd"]:
        return "要授权多少 USDC？"
    if missing_fields == ["spender"]:
        return "要授权给哪个 spender？请提供地址。"
    return "请补充授权额度和 spender 地址。"


def _clarification_question_for_bridge(missing_fields: list[str]) -> str:
    if missing_fields == ["amount_usd"]:
        return "要桥接多少 USDC？"
    if missing_fields == ["destination_chain"]:
        return "要桥接到哪条目标链？"
    return "请补充桥接金额和目标链。"


def _clarification_question_for_structured_fields(missing_fields: list[str]) -> str:
    if not missing_fields:
        return "请补充缺失字段。"
    if missing_fields == ["actor_context.agent_id"]:
        return "请提供 actor_context.agent_id。"
    if missing_fields == ["requested_action_family"] or missing_fields == ["action.kind"]:
        return "请提供要执行的动作类型。"
    if missing_fields == ["action.trade.notional_usd"]:
        return "请补充交易金额 action.trade.notional_usd。"
    if missing_fields == ["delegation.role"]:
        return "请补充 delegation.role。"
    return "请补充缺失字段：" + ", ".join(missing_fields)
