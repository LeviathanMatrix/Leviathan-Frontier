from __future__ import annotations

from pathlib import Path

from aep.delegation import resolve_structured_delegation_for_intake


def _fixtures_root() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures"


def test_resolve_structured_delegation_by_ref() -> None:
    doc = {
        "delegation_ref": "grant-public-api-shell-alpha",
    }
    actor_context = {"agent_id": "aep:solana:agent-alpha"}
    delegation = resolve_structured_delegation_for_intake(
        doc,
        actor_context=actor_context,
        delegation_grants_path=_fixtures_root() / "delegation_grants.v1.json",
    )
    assert delegation is not None
    assert delegation["grant_id"] == "grant-public-api-shell-alpha"
    assert delegation["delegate_id"] == "aep:solana:agent-alpha"


def test_resolve_structured_delegation_none_when_missing_claim() -> None:
    delegation = resolve_structured_delegation_for_intake(
        {},
        actor_context={"agent_id": "agent-x"},
        delegation_grants_path=_fixtures_root() / "delegation_grants.v1.json",
    )
    assert delegation is None
