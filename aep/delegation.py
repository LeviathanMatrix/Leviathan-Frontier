from __future__ import annotations

import copy
from typing import Any

from .shared.delegation_grants import _load_delegation_grants, _merge_delegation_claim_with_grant


def _single_grant_or_none(rows: Any) -> dict[str, Any] | None:
    candidates = [row for row in (rows or []) if isinstance(row, dict)]
    if len(candidates) == 1:
        return copy.deepcopy(candidates[0])
    return None


def _resolve_delegation_grant_for_intake(
    claim: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any] | None:
    by_grant_id = registry.get("by_grant_id") if isinstance(registry.get("by_grant_id"), dict) else {}
    by_tuple = registry.get("by_tuple") if isinstance(registry.get("by_tuple"), dict) else {}
    by_delegate_id = registry.get("by_delegate_id") if isinstance(registry.get("by_delegate_id"), dict) else {}

    grant_id = str(claim.get("grant_id") or "").strip()
    if grant_id:
        grant = by_grant_id.get(grant_id)
        if isinstance(grant, dict):
            return grant

    principal_id = str(claim.get("principal_id") or "").strip()
    delegate_id = str(claim.get("delegate_id") or "").strip()
    role = str(claim.get("role") or "").strip()
    if principal_id and delegate_id and role:
        grant = _single_grant_or_none(by_tuple.get(f"{principal_id}|{delegate_id}|{role}"))
        if isinstance(grant, dict):
            return grant

    if delegate_id:
        candidates = by_delegate_id.get(delegate_id)
        if principal_id:
            candidates = [
                row for row in (candidates or []) if str(row.get("principal_id") or "").strip() == principal_id
            ]
        if role:
            candidates = [row for row in (candidates or []) if str(row.get("role") or "").strip() == role]
        grant = _single_grant_or_none(candidates)
        if isinstance(grant, dict):
            return grant
    return None


def resolve_structured_delegation_for_intake(
    doc: dict[str, Any],
    *,
    actor_context: dict[str, Any],
    delegation_grants_path: Any,
) -> dict[str, Any] | None:
    direct_delegation = doc.get("delegation") if isinstance(doc.get("delegation"), dict) else None
    raw_delegate_id = str(doc.get("delegate_id") or "").strip()
    top_level_claim = {
        "principal_id": str(doc.get("principal_id") or "").strip(),
        "delegate_id": raw_delegate_id or str(actor_context.get("agent_id") or "").strip(),
        "role": str(doc.get("role") or "").strip(),
        "grant_id": str(doc.get("grant_id") or "").strip(),
    }
    delegation_ref = str(doc.get("delegation_ref") or "").strip()

    has_direct = isinstance(direct_delegation, dict) and bool(direct_delegation)
    has_top_level = any(
        bool(value)
        for value in (
            top_level_claim["principal_id"],
            top_level_claim["role"],
            top_level_claim["grant_id"],
            delegation_ref,
            raw_delegate_id,
        )
    )
    if not has_direct and not has_top_level:
        return None

    claim = copy.deepcopy(direct_delegation) if has_direct else {}
    if top_level_claim["principal_id"] and not str(claim.get("principal_id") or "").strip():
        claim["principal_id"] = top_level_claim["principal_id"]
    if top_level_claim["delegate_id"] and not str(claim.get("delegate_id") or "").strip():
        claim["delegate_id"] = top_level_claim["delegate_id"]
    if top_level_claim["role"] and not str(claim.get("role") or "").strip():
        claim["role"] = top_level_claim["role"]
    if top_level_claim["grant_id"] and not str(claim.get("grant_id") or "").strip():
        claim["grant_id"] = top_level_claim["grant_id"]
    if delegation_ref and not str(claim.get("grant_id") or "").strip():
        claim["grant_id"] = delegation_ref

    registry = _load_delegation_grants(delegation_grants_path)
    grant = _resolve_delegation_grant_for_intake(claim, registry)
    merged = _merge_delegation_claim_with_grant(claim, grant)
    return {key: value for key, value in merged.items() if value not in ("", None, [], {})}
