from aep.risk_provider import StaticRiskInputProvider, UserProvidedRiskInputProvider
from policy_engine.validation import validate_document


def test_static_provider_returns_policy_compatible_shape() -> None:
    provider = StaticRiskInputProvider()
    out = provider.build_risk_input({"request_id": "req-1", "agent": {"agent_id": "agent-1"}})
    assert out["schema_version"] == "risk_input.v1"
    assert "mcp_scores" in out and "aep_context" in out
    assert out["source_systems"][0]["name"] == "leviathanmatrix-aep-open-core:static-risk-provider"
    assert out["mcp_scores"]["token_score"]["grade"] in {"A", "B", "C", "D", "Rug"}


def test_static_provider_output_passes_risk_schema_validation() -> None:
    provider = StaticRiskInputProvider()
    out = provider.build_risk_input({"request_id": "req-1", "agent": {"agent_id": "agent-1"}})
    errors = validate_document(out, "risk_input.schema.json")
    assert errors == []


def test_user_provided_provider_returns_copy() -> None:
    src = {"schema_version": "risk_input.v1", "mcp_scores": {}, "aep_context": {}}
    provider = UserProvidedRiskInputProvider(src)
    out = provider.build_risk_input({})
    out["schema_version"] = "mutated"
    assert src["schema_version"] == "risk_input.v1"
