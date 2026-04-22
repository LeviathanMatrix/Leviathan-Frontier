from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from ..accountability import compute_json_digest

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ASSET_REGISTRY_PATH = ROOT / "fixtures" / "paper_asset_registry.v1.json"
DEFAULT_CHAIN = "solana"
DEFAULT_NETWORK = "paper"
DEFAULT_SLIPPAGE_BPS = 50

SOLANA_ADDRESS_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _json_load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must decode to a JSON object")
    return payload


def _coerce_document(value: Any, field_name: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    if isinstance(value, (str, Path)):
        stripped = str(value).strip()
        if not stripped:
            raise ValueError(f"{field_name} must not be empty")
        if stripped.startswith("{"):
            parsed = json.loads(stripped)
            if not isinstance(parsed, dict):
                raise ValueError(f"{field_name} must decode to a JSON object")
            return parsed
        path = Path(stripped).expanduser()
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        else:
            path = path.resolve()
        return _json_load(path)
    raise ValueError(f"{field_name} must be a dict, JSON string, or file path")


def _coerce_optional_document(value: Any, field_name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return _coerce_document(value, field_name)


def _normalize_identifier_key(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _load_asset_registry(asset_registry_path: Any = DEFAULT_ASSET_REGISTRY_PATH) -> dict[str, Any]:
    doc = _coerce_document(asset_registry_path, "asset_registry_path")
    assets = doc.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("paper asset registry must contain a non-empty assets array")

    by_symbol: dict[str, dict[str, Any]] = {}
    by_alias: dict[str, str] = {}
    by_identifier: dict[str, str] = {}
    for row in assets:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        item = copy.deepcopy(row)
        item.setdefault("aliases", [])
        item.setdefault("decimals", 6)
        item.setdefault("price_usd", 0.0)
        item.setdefault("expected_slippage_bps", DEFAULT_SLIPPAGE_BPS)
        item.setdefault("paper_depth_usd", 10000.0)
        item.setdefault("risk_profile", {})
        item.setdefault("identifiers", {})
        by_symbol[symbol] = item
        by_alias[symbol.lower()] = symbol

        for alias in item.get("aliases", []):
            alias_text = str(alias).strip().lower()
            if alias_text:
                by_alias[alias_text] = symbol

        identifiers = item.get("identifiers") if isinstance(item.get("identifiers"), dict) else {}
        solana_ids = identifiers.get("solana") if isinstance(identifiers.get("solana"), dict) else {}
        for network_key, values in solana_ids.items():
            if not isinstance(values, list):
                continue
            normalized_network_key = _normalize_identifier_key(str(network_key))
            for raw_value in values:
                identifier = str(raw_value or "").strip().lower()
                if not identifier:
                    continue
                by_identifier[f"solana:{normalized_network_key}:{identifier}"] = symbol
                by_identifier[f"solana:*:{identifier}"] = symbol
    return {"document": doc, "by_symbol": by_symbol, "by_alias": by_alias, "by_identifier": by_identifier}


def _unknown_asset_profile(asset_text: str, *, chain: str, network: str) -> dict[str, Any]:
    raw = str(asset_text or "").strip()
    short = compute_json_digest({"asset_text": raw})[:8].upper()
    return {
        "symbol": f"UNK{short}",
        "aliases": [raw],
        "decimals": 6,
        "price_usd": 0.0,
        "expected_slippage_bps": 250,
        "paper_depth_usd": 1000.0,
        "identifiers": {chain: {network: [raw]}},
        "risk_profile": {
            "control_risk": 92,
            "funding_risk": 90,
            "history_risk": 88,
            "governance_surface_risk": 91,
            "volatility_risk": 89,
            "anomaly_risk": 90,
            "liquidity_score": 12,
            "permission_risk": 90,
            "rug_risk": 95,
            "confidence": 0.18,
            "grade": "Rug",
            "drift_state": "outlier",
        },
        "resolution": {
            "matched": False,
            "matched_ref": raw,
            "chain": chain,
            "network": network,
            "kind": "unknown_identifier",
        },
    }


def _resolve_asset(
    asset_text: str,
    registry: dict[str, Any],
    *,
    chain: str = DEFAULT_CHAIN,
    network: str = DEFAULT_NETWORK,
) -> dict[str, Any]:
    alias = str(asset_text or "").strip().lower()
    if not alias:
        raise ValueError("asset text is required")
    symbol = registry["by_alias"].get(alias)
    matched_kind = "alias"
    if symbol is None:
        normalized_chain = _normalize_identifier_key(chain)
        normalized_network = _normalize_identifier_key(network)
        symbol = registry.get("by_identifier", {}).get(f"{normalized_chain}:{normalized_network}:{alias}")
        if symbol is None:
            symbol = registry.get("by_identifier", {}).get(f"{normalized_chain}:*:{alias}")
        matched_kind = "identifier"
    if symbol is None:
        return _unknown_asset_profile(asset_text, chain=chain, network=network)
    asset = copy.deepcopy(registry["by_symbol"][symbol])
    asset["resolution"] = {
        "matched": True,
        "matched_ref": str(asset_text).strip(),
        "chain": chain,
        "network": network,
        "kind": matched_kind,
    }
    return asset


def _iter_asset_mentions(
    text: str,
    registry: dict[str, Any],
    *,
    chain: str = DEFAULT_CHAIN,
    network: str = DEFAULT_NETWORK,
) -> list[dict[str, Any]]:
    lowered = text.lower()
    seen: set[str] = set()
    resolved: list[dict[str, Any]] = []
    for match in SOLANA_ADDRESS_RE.finditer(text):
        candidate = match.group(0)
        asset = _resolve_asset(candidate, registry, chain=chain, network=network)
        unique_key = str(asset.get("resolution", {}).get("matched_ref") or candidate).lower()
        if unique_key in seen:
            continue
        seen.add(unique_key)
        resolved.append(asset)
    alias_items = sorted(registry["by_alias"].items(), key=lambda item: len(item[0]), reverse=True)
    for alias, symbol in alias_items:
        if not alias:
            continue
        pattern = r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])"
        if not re.search(pattern, lowered):
            continue
        unique_key = symbol.lower()
        if unique_key in seen:
            continue
        seen.add(unique_key)
        resolved.append(_resolve_asset(symbol, registry, chain=chain, network=network))
    return resolved
