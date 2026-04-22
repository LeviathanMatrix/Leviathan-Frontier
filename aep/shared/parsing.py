from __future__ import annotations

import re
import time
from typing import Any

from ..accountability import compute_json_digest
from .assets import (
    DEFAULT_ASSET_REGISTRY_PATH,
    DEFAULT_CHAIN,
    DEFAULT_NETWORK,
    SOLANA_ADDRESS_RE,
    _coerce_document,
    _iter_asset_mentions,
    _load_asset_registry,
    _resolve_asset,
)

ACTION_REQUEST_API_VERSION = "aep.action_request.v1"

DEFAULT_RUNTIME_TYPE = "generic-agent"
DEFAULT_SLIPPAGE_BPS = 50
DEFAULT_VENUE = "paper-virtual-orderbook"
DEFAULT_DEVNET_VENUE = "solana-devnet-requested"

PAPER_CONTRACT_CALL_PROGRAM_ID = "paper.virtual.contract_call"

SUPPORTED_ACTION_KINDS = {"trade", "payment", "approve", "contract_call", "bridge"}

BUY_HINTS = (
    "buy",
    "long",
    "swap",
    "purchase",
    "rebalance",
    "buy more",
    "买",
    "买入",
    "做多",
    "加仓",
    "增持",
    "补仓",
    "换成",
    "兑换",
)
SELL_HINTS = (
    "sell",
    "short",
    "exit",
    "reduce",
    "trim",
    "卖",
    "卖出",
    "减仓",
    "减持",
    "平仓",
    "清仓",
    "换回",
)
PAYMENT_HINTS = ("pay", "payment", "send", "transfer", "付款", "支付", "转账")
APPROVE_HINTS = ("approve", "allowance", "授权", "许可")
CONTRACT_CALL_HINTS = ("contract call", "call contract", "invoke", "调用合约", "调用")
BRIDGE_HINTS = ("bridge", "bridging", "cross-chain", "跨链", "桥接", "过桥")

MONEY_RE = re.compile(r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>usdc|usd|\$)", re.IGNORECASE)
NUMBER_TOKEN_RE = re.compile(r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<token>[A-Za-z][A-Za-z0-9_-]{1,15})")
NUMBER_RE = re.compile(r"(?P<amount>\d+(?:\.\d+)?)")
EVM_ADDRESS_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")


def _now_ts() -> int:
    return int(time.time())


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return default
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            return default
        if re.fullmatch(r"[-+]?\d+", text):
            return int(text)
        return int(float(text))
    except (TypeError, ValueError):
        return default


def _round(value: float, digits: int = 6) -> float:
    return round(float(value) + 1e-9, digits)


def _detect_chain(text: str) -> str:
    lowered = text.lower()
    if "solana" in lowered or re.search(r"\bsol\b", lowered):
        return "solana"
    return DEFAULT_CHAIN


def _normalize_default_network(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized or DEFAULT_NETWORK


def _detect_requested_network(text: str, *, default_network: str = DEFAULT_NETWORK) -> str:
    lowered = text.lower()
    if "devnet" in lowered:
        return "devnet"
    if "mainnet" in lowered or "mainnet-beta" in lowered:
        return "mainnet-beta"
    if "paper" in lowered or "virtual" in lowered or "模拟盘" in lowered or "虚拟盘" in lowered:
        return "paper"
    return _normalize_default_network(default_network)


def _default_venue_for_network(network: str) -> str:
    if str(network).strip().lower() == "devnet":
        return DEFAULT_DEVNET_VENUE
    return DEFAULT_VENUE


def _detect_side(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in SELL_HINTS):
        return "sell"
    return "buy"


def _detect_action_kind(text: str) -> str:
    lowered = str(text or "").lower()
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
    return "trade"


def _detect_bridge_destination_chain(source_text: str) -> str:
    lowered = str(source_text or "").lower()
    chain_aliases = (
        ("base", "base"),
        ("ethereum", "ethereum"),
        ("eth", "ethereum"),
        ("arbitrum", "arbitrum"),
        ("optimism", "optimism"),
        ("polygon", "polygon"),
        ("bsc", "bsc"),
        ("bnb", "bsc"),
    )
    for alias, chain in chain_aliases:
        if alias in lowered:
            return chain
    return ""


def _bridge_destination_network_for_chain(destination_chain: str) -> str:
    if str(destination_chain or "").strip().lower() == "solana":
        return DEFAULT_NETWORK
    return "mainnet-beta"


def _extract_trade_quantity_candidate(
    source_text: str,
    *,
    mentioned_assets: list[dict[str, Any]],
    registry: dict[str, Any],
    requested_chain: str,
    requested_network: str,
) -> tuple[dict[str, Any], float] | None:
    token_matches = list(NUMBER_TOKEN_RE.finditer(source_text))
    for match in token_matches:
        token_candidate = match.group("token")
        asset = _resolve_asset(
            token_candidate,
            registry,
            chain=requested_chain,
            network=requested_network,
        )
        if str(asset.get("symbol")).upper() == "USDC":
            continue
        quantity = _safe_float(match.group("amount"))
        if quantity <= 0:
            continue
        return asset, quantity

    mentioned_non_usdc = [
        asset for asset in mentioned_assets if str(asset.get("symbol", "")).upper() != "USDC"
    ]
    if len(mentioned_non_usdc) != 1:
        return None

    numeric_values: list[float] = []
    for match in NUMBER_RE.finditer(source_text):
        quantity = _safe_float(match.group("amount"))
        if quantity > 0:
            numeric_values.append(quantity)
    if len(numeric_values) != 1:
        return None
    return mentioned_non_usdc[0], numeric_values[0]


def _base_natural_language_request(
    *,
    source_text: str,
    request_id: str,
    requested_at: int,
    agent_id: str,
    authority_pubkey: str,
    runtime_type: str,
    framework: str,
    session_id: str,
    action: dict[str, Any],
    requested_chain: str,
    requested_network: str,
) -> dict[str, Any]:
    return {
        "api_version": ACTION_REQUEST_API_VERSION,
        "request_id": request_id,
        "requested_at": requested_at,
        "agent": {
            "agent_id": agent_id,
            "authority_pubkey": str(authority_pubkey or "").strip(),
            "runtime_type": str(runtime_type or DEFAULT_RUNTIME_TYPE),
            "framework": str(framework or "").strip(),
            "session_id": str(session_id or "").strip() or f"session-{request_id[-8:]}",
        },
        "input_mode": "natural_language",
        "action": {"source_text": source_text, **action},
        "execution_preferences": {
            "mode": "devnet" if requested_network == "devnet" else "paper",
            "chain": requested_chain,
            "network": requested_network,
            "venue": _default_venue_for_network(requested_network),
            "auto_review": True,
        },
    }


def parse_natural_language_trade_request(
    text: str,
    *,
    agent_id: str,
    authority_pubkey: str = "",
    runtime_type: str = DEFAULT_RUNTIME_TYPE,
    framework: str = "",
    session_id: str = "",
    asset_registry_path: Any = DEFAULT_ASSET_REGISTRY_PATH,
    slippage_bps: int = DEFAULT_SLIPPAGE_BPS,
    default_network: str = DEFAULT_NETWORK,
) -> dict[str, Any]:
    source_text = str(text or "").strip()
    if not source_text:
        raise ValueError("text is required")

    requested_chain = _detect_chain(source_text)
    requested_network = _detect_requested_network(source_text, default_network=default_network)
    registry = _load_asset_registry(asset_registry_path)
    mentioned_assets = _iter_asset_mentions(
        source_text,
        registry,
        chain=requested_chain,
        network=requested_network,
    )
    side = _detect_side(source_text)
    money_match = MONEY_RE.search(source_text)

    request_trade: dict[str, Any]
    if money_match:
        notional_usd = _safe_float(money_match.group("amount"))
        if notional_usd <= 0:
            raise ValueError("notional amount must be > 0")
        destination_candidates = [
            asset for asset in mentioned_assets if str(asset.get("symbol", "")).upper() != "USDC"
        ]
        if not destination_candidates:
            raise ValueError("could not resolve destination asset from text")
        destination_asset = destination_candidates[0]
        destination_symbol = str(destination_asset.get("symbol", "")).upper()
        destination_ref = str(destination_asset.get("resolution", {}).get("matched_ref") or destination_symbol)
        expected_price_usd = _safe_float(destination_asset.get("price_usd"), 0.0)
        request_trade = {
            "side": side,
            "source_asset": "USDC" if side == "buy" else destination_symbol,
            "destination_asset": destination_symbol if side == "buy" else "USDC",
            "notional_usd": _round(notional_usd, 6),
            "expected_price_usd": _round(expected_price_usd, 8),
            "quantity_units": _round(notional_usd / max(expected_price_usd, 1e-9), 12)
            if expected_price_usd > 0
            else 0.0,
            "slippage_bps": int(slippage_bps),
            "source_asset_ref": "USDC",
            "destination_asset_ref": destination_ref if side == "buy" else "USDC",
        }
    else:
        resolved = _extract_trade_quantity_candidate(
            source_text,
            mentioned_assets=mentioned_assets,
            registry=registry,
            requested_chain=requested_chain,
            requested_network=requested_network,
        )
        if resolved is None:
            raise ValueError("could not resolve a tradable asset and quantity from text")
        asset, quantity_units = resolved
        notional_usd = quantity_units * _safe_float(asset.get("price_usd"), 0.0)
        request_trade = {
            "side": side,
            "source_asset": asset["symbol"] if side == "sell" else "USDC",
            "destination_asset": "USDC" if side == "sell" else asset["symbol"],
            "notional_usd": _round(notional_usd, 6),
            "expected_price_usd": _round(_safe_float(asset.get("price_usd")), 8),
            "quantity_units": _round(quantity_units, 12),
            "slippage_bps": int(slippage_bps),
            "source_asset_ref": str(asset.get("resolution", {}).get("matched_ref") or asset["symbol"])
            if side == "sell"
            else "USDC",
            "destination_asset_ref": "USDC"
            if side == "sell"
            else str(asset.get("resolution", {}).get("matched_ref") or asset["symbol"]),
        }

    if request_trade["notional_usd"] <= 0:
        raise ValueError("derived notional_usd must be > 0")

    request_id = f"req_{compute_json_digest({'text': source_text, 'agent_id': agent_id, 'ts': _now_ts()})[:16]}"
    requested_at = _now_ts()
    return {
        "api_version": ACTION_REQUEST_API_VERSION,
        "request_id": request_id,
        "requested_at": requested_at,
        "agent": {
            "agent_id": agent_id,
            "authority_pubkey": str(authority_pubkey or "").strip(),
            "runtime_type": str(runtime_type or DEFAULT_RUNTIME_TYPE),
            "framework": str(framework or "").strip(),
            "session_id": str(session_id or "").strip() or f"session-{request_id[-8:]}",
        },
        "input_mode": "natural_language",
        "action": {
            "kind": "trade",
            "source_text": source_text,
            "trade": request_trade,
        },
        "execution_preferences": {
            "mode": "devnet" if requested_network == "devnet" else "paper",
            "chain": requested_chain,
            "network": requested_network,
            "venue": _default_venue_for_network(requested_network),
            "auto_review": True,
        },
    }


def parse_natural_language_payment_request(
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
    requested_chain = _detect_chain(source_text)
    requested_network = _detect_requested_network(source_text, default_network=default_network)
    money_match = MONEY_RE.search(source_text)
    if money_match is None:
        raise ValueError("payment request must include USD/USDC amount")
    amount_usd = _round(_safe_float(money_match.group("amount")), 6)
    if amount_usd <= 0:
        raise ValueError("payment amount_usd must be > 0")

    recipient = "unknown-recipient"
    address_match = SOLANA_ADDRESS_RE.search(source_text)
    if address_match is not None:
        recipient = address_match.group(0)
    registry = _load_asset_registry(asset_registry_path)
    source_asset = _resolve_asset("USDC", registry, chain=requested_chain, network=requested_network)
    request_id = (
        f"req_{compute_json_digest({'text': source_text, 'agent_id': agent_id, 'kind': 'payment', 'ts': _now_ts()})[:16]}"
    )
    requested_at = _now_ts()
    return _base_natural_language_request(
        source_text=source_text,
        request_id=request_id,
        requested_at=requested_at,
        agent_id=agent_id,
        authority_pubkey=authority_pubkey,
        runtime_type=runtime_type,
        framework=framework,
        session_id=session_id,
        action={
            "kind": "payment",
            "payment": {
                "source_asset": str(source_asset.get("symbol") or "USDC"),
                "source_asset_ref": "USDC",
                "amount_usd": amount_usd,
                "recipient": recipient,
                "note": source_text,
            },
        },
        requested_chain=requested_chain,
        requested_network=requested_network,
    )


def parse_natural_language_approve_request(
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
    requested_chain = _detect_chain(source_text)
    requested_network = _detect_requested_network(source_text, default_network=default_network)
    registry = _load_asset_registry(asset_registry_path)
    mentioned_assets = _iter_asset_mentions(
        source_text,
        registry,
        chain=requested_chain,
        network=requested_network,
    )
    asset = (
        mentioned_assets[0]
        if mentioned_assets
        else _resolve_asset("USDC", registry, chain=requested_chain, network=requested_network)
    )
    money_match = MONEY_RE.search(source_text)
    allowance_usd = _round(_safe_float(money_match.group("amount")), 6) if money_match else 1.0
    if allowance_usd <= 0:
        raise ValueError("approve allowance_usd must be > 0")
    spender = "unknown-spender"
    address_match = SOLANA_ADDRESS_RE.search(source_text)
    if address_match is not None:
        spender = address_match.group(0)

    request_id = (
        f"req_{compute_json_digest({'text': source_text, 'agent_id': agent_id, 'kind': 'approve', 'ts': _now_ts()})[:16]}"
    )
    requested_at = _now_ts()
    return _base_natural_language_request(
        source_text=source_text,
        request_id=request_id,
        requested_at=requested_at,
        agent_id=agent_id,
        authority_pubkey=authority_pubkey,
        runtime_type=runtime_type,
        framework=framework,
        session_id=session_id,
        action={
            "kind": "approve",
            "approve": {
                "asset": str(asset.get("symbol") or "USDC"),
                "asset_ref": str(asset.get("resolution", {}).get("matched_ref") or asset.get("symbol") or "USDC"),
                "spender": spender,
                "allowance_usd": allowance_usd,
                "revoke_existing": False,
            },
        },
        requested_chain=requested_chain,
        requested_network=requested_network,
    )


def parse_natural_language_contract_call_request(
    text: str,
    *,
    agent_id: str,
    authority_pubkey: str = "",
    runtime_type: str = DEFAULT_RUNTIME_TYPE,
    framework: str = "",
    session_id: str = "",
    default_network: str = DEFAULT_NETWORK,
) -> dict[str, Any]:
    source_text = str(text or "").strip()
    requested_chain = _detect_chain(source_text)
    requested_network = _detect_requested_network(source_text, default_network=default_network)
    addresses = SOLANA_ADDRESS_RE.findall(source_text)
    program_id = addresses[0] if addresses else PAPER_CONTRACT_CALL_PROGRAM_ID
    accounts = addresses[1:] if len(addresses) > 1 else []
    money_match = MONEY_RE.search(source_text)
    value_usd = _round(_safe_float(money_match.group("amount")), 6) if money_match else 0.01
    if value_usd <= 0:
        value_usd = 0.01
    method_match = re.search(
        r"(?:method|函数|调用)\s*[:：]?\s*([A-Za-z_][A-Za-z0-9_]*)",
        source_text,
        re.IGNORECASE,
    )
    method = method_match.group(1) if method_match else "call"

    request_id = f"req_{compute_json_digest({'text': source_text, 'agent_id': agent_id, 'kind': 'contract_call', 'ts': _now_ts()})[:16]}"
    requested_at = _now_ts()
    return _base_natural_language_request(
        source_text=source_text,
        request_id=request_id,
        requested_at=requested_at,
        agent_id=agent_id,
        authority_pubkey=authority_pubkey,
        runtime_type=runtime_type,
        framework=framework,
        session_id=session_id,
        action={
            "kind": "contract_call",
            "contract_call": {
                "program_id": program_id,
                "method": method,
                "value_usd": value_usd,
                "source_asset": "USDC",
                "source_asset_ref": "USDC",
                "accounts": accounts,
                "data_hash": compute_json_digest(
                    {
                        "source_text": source_text,
                        "program_id": program_id,
                        "method": method,
                    }
                ),
            },
        },
        requested_chain=requested_chain,
        requested_network=requested_network,
    )


def parse_natural_language_bridge_request(
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
    if not source_text:
        raise ValueError("text is required")

    requested_chain = _detect_chain(source_text)
    requested_network = _detect_requested_network(source_text, default_network=default_network)
    lowered = source_text.lower()
    if requested_network == "devnet" and "devnet" not in lowered:
        requested_network = "paper"
    registry = _load_asset_registry(asset_registry_path)
    money_match = MONEY_RE.search(source_text)
    if money_match is None:
        raise ValueError("bridge request must include USD/USDC amount")
    amount_usd = _round(_safe_float(money_match.group("amount")), 6)
    if amount_usd <= 0:
        raise ValueError("bridge amount_usd must be > 0")

    mentioned_assets = _iter_asset_mentions(
        source_text,
        registry,
        chain=requested_chain,
        network=requested_network,
    )
    source_asset = (
        mentioned_assets[0]
        if mentioned_assets
        else _resolve_asset("USDC", registry, chain=requested_chain, network=requested_network)
    )
    destination_chain = _detect_bridge_destination_chain(source_text)
    if not destination_chain:
        raise ValueError("could not resolve destination chain from text")
    destination_network = _bridge_destination_network_for_chain(destination_chain)
    recipient = "same-agent-destination"
    evm_match = EVM_ADDRESS_RE.search(source_text)
    if evm_match is not None:
        recipient = evm_match.group(0)
    else:
        solana_match = SOLANA_ADDRESS_RE.search(source_text)
        if solana_match is not None:
            recipient = solana_match.group(0)
    bridge_protocol = "paper_bridge_router"
    if "wormhole" in source_text.lower():
        bridge_protocol = "wormhole"
    elif "across" in source_text.lower():
        bridge_protocol = "across"

    request_id = (
        f"req_{compute_json_digest({'text': source_text, 'agent_id': agent_id, 'kind': 'bridge', 'ts': _now_ts()})[:16]}"
    )
    requested_at = _now_ts()
    return _base_natural_language_request(
        source_text=source_text,
        request_id=request_id,
        requested_at=requested_at,
        agent_id=agent_id,
        authority_pubkey=authority_pubkey,
        runtime_type=runtime_type,
        framework=framework,
        session_id=session_id,
        action={
            "kind": "bridge",
            "bridge": {
                "source_asset": str(source_asset.get("symbol") or "USDC").upper(),
                "source_asset_ref": str(
                    source_asset.get("resolution", {}).get("matched_ref") or source_asset.get("symbol") or "USDC"
                ),
                "amount_usd": amount_usd,
                "destination_chain": destination_chain,
                "destination_network": destination_network,
                "destination_asset": str(source_asset.get("symbol") or "USDC").upper(),
                "destination_asset_ref": str(
                    source_asset.get("resolution", {}).get("matched_ref") or source_asset.get("symbol") or "USDC"
                ),
                "recipient": recipient,
                "bridge_protocol": bridge_protocol,
                "max_fee_usd": _round(max(amount_usd * 0.003, 0.05), 6),
            },
        },
        requested_chain=requested_chain,
        requested_network=requested_network,
    )


def parse_natural_language_action_request(
    text: str,
    *,
    agent_id: str,
    authority_pubkey: str = "",
    runtime_type: str = DEFAULT_RUNTIME_TYPE,
    framework: str = "",
    session_id: str = "",
    asset_registry_path: Any = DEFAULT_ASSET_REGISTRY_PATH,
    slippage_bps: int = DEFAULT_SLIPPAGE_BPS,
    default_network: str = DEFAULT_NETWORK,
) -> dict[str, Any]:
    action_kind = _detect_action_kind(text)
    if action_kind == "bridge":
        return parse_natural_language_bridge_request(
            text,
            agent_id=agent_id,
            authority_pubkey=authority_pubkey,
            runtime_type=runtime_type,
            framework=framework,
            session_id=session_id,
            asset_registry_path=asset_registry_path,
            default_network=default_network,
        )
    if action_kind == "payment":
        return parse_natural_language_payment_request(
            text,
            agent_id=agent_id,
            authority_pubkey=authority_pubkey,
            runtime_type=runtime_type,
            framework=framework,
            session_id=session_id,
            asset_registry_path=asset_registry_path,
            default_network=default_network,
        )
    if action_kind == "approve":
        return parse_natural_language_approve_request(
            text,
            agent_id=agent_id,
            authority_pubkey=authority_pubkey,
            runtime_type=runtime_type,
            framework=framework,
            session_id=session_id,
            asset_registry_path=asset_registry_path,
            default_network=default_network,
        )
    if action_kind == "contract_call":
        return parse_natural_language_contract_call_request(
            text,
            agent_id=agent_id,
            authority_pubkey=authority_pubkey,
            runtime_type=runtime_type,
            framework=framework,
            session_id=session_id,
            default_network=default_network,
        )
    return parse_natural_language_trade_request(
        text,
        agent_id=agent_id,
        authority_pubkey=authority_pubkey,
        runtime_type=runtime_type,
        framework=framework,
        session_id=session_id,
        asset_registry_path=asset_registry_path,
        slippage_bps=slippage_bps,
        default_network=default_network,
    )
