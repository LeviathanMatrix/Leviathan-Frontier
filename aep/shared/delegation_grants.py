from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .assets import _coerce_optional_document

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DELEGATION_GRANTS_PATH = ROOT / "fixtures" / "delegation_grants.v1.json"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return default
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            return default
        return int(float(text))
    except (TypeError, ValueError):
        return default


def _normalize_scope_values(value: Any) -> list[str]:
    if isinstance(value, list):
        rows = value
    elif isinstance(value, str):
        rows = [value]
    else:
        rows = []
    out: list[str] = []
    for row in rows:
        text = str(row or "").strip().lower()
        if text and text not in out:
            out.append(text)
    return out


def _normalize_asset_scope_mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"all", "any", "open"}:
        return "all"
    return "allowlist"


def _resolve_asset_scope_mode(payload: dict[str, Any] | None) -> str:
    payload = payload if isinstance(payload, dict) else {}
    if bool(payload.get("asset_scope_all", False)):
        return "all"
    return _normalize_asset_scope_mode(payload.get("asset_scope_mode"))


def _load_delegation_grants(grants_path: Any = DEFAULT_DELEGATION_GRANTS_PATH) -> dict[str, Any]:
    doc = _coerce_optional_document(grants_path, "delegation_grants_path")
    if doc is None:
        return {
            "document": None,
            "grants": [],
            "by_grant_id": {},
            "by_delegate_id": {},
            "by_tuple": {},
        }
    grants = doc.get("grants")
    if not isinstance(grants, list):
        raise ValueError("delegation grants document must contain grants array")

    active_grants: list[dict[str, Any]] = []
    by_grant_id: dict[str, dict[str, Any]] = {}
    by_delegate_id: dict[str, list[dict[str, Any]]] = {}
    by_tuple: dict[str, list[dict[str, Any]]] = {}
    for row in grants:
        if not isinstance(row, dict):
            continue
        if not bool(row.get("active", True)):
            continue
        if _safe_int(row.get("revoked_at"), 0) > 0:
            continue
        grant = copy.deepcopy(row)
        grant_id = str(grant.get("grant_id") or "").strip()
        principal_id = str(grant.get("principal_id") or "").strip()
        delegate_id = str(grant.get("delegate_id") or "").strip()
        role = str(grant.get("role") or "").strip()
        if not principal_id or not delegate_id or not role:
            continue
        active_grants.append(grant)
        if grant_id:
            by_grant_id[grant_id] = grant
        by_delegate_id.setdefault(delegate_id, []).append(grant)
        tuple_key = f"{principal_id}|{delegate_id}|{role}"
        by_tuple.setdefault(tuple_key, []).append(grant)

    return {
        "document": doc,
        "grants": active_grants,
        "by_grant_id": by_grant_id,
        "by_delegate_id": by_delegate_id,
        "by_tuple": by_tuple,
    }


def _merge_delegation_claim_with_grant(
    claim: dict[str, Any] | None,
    grant: dict[str, Any] | None,
) -> dict[str, Any]:
    claim = claim if isinstance(claim, dict) else {}
    grant = grant if isinstance(grant, dict) else {}
    asset_scope_mode = _resolve_asset_scope_mode(grant if grant else claim)
    return {
        "principal_id": str(grant.get("principal_id") or claim.get("principal_id") or "").strip(),
        "delegate_id": str(grant.get("delegate_id") or claim.get("delegate_id") or "").strip(),
        "role": str(grant.get("role") or claim.get("role") or "").strip(),
        "grant_id": str(grant.get("grant_id") or claim.get("grant_id") or "").strip() or None,
        "allowed_actions": grant.get("allowed_actions")
        if isinstance(grant.get("allowed_actions"), list)
        else claim.get("allowed_actions"),
        "asset_scope_mode": asset_scope_mode,
        "asset_scope": grant.get("asset_scope")
        if isinstance(grant.get("asset_scope"), list)
        else claim.get("asset_scope"),
        "program_scope": grant.get("program_scope")
        if isinstance(grant.get("program_scope"), list)
        else claim.get("program_scope"),
        "notional_limits": grant.get("notional_limits")
        if isinstance(grant.get("notional_limits"), dict)
        else (claim.get("notional_limits") if isinstance(claim.get("notional_limits"), dict) else {}),
        "required_policy_level": str(
            grant.get("required_policy_level") or claim.get("required_policy_level") or ""
        ).strip()
        or None,
        "required_risk_band": str(
            grant.get("required_risk_band") or claim.get("required_risk_band") or ""
        ).strip()
        or None,
        "valid_from": _safe_int(
            grant.get("valid_from", claim.get("valid_from")),
            0,
        ),
        "valid_until": _safe_int(
            grant.get("valid_until", claim.get("valid_until")),
            0,
        ),
    }
