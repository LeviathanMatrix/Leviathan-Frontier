from __future__ import annotations

from typing import Any

from policy_engine import evaluate_policy, validate_document


POLICY_OUTPUT_VERSION = "policy_output.v1"


def evaluate_policy_decision(
    constitution: dict[str, Any],
    intent: dict[str, Any],
    risk_input: dict[str, Any],
    *,
    prior_state: dict[str, Any] | None = None,
    validate_schema: bool = False,
) -> dict[str, Any]:
    return evaluate_policy(
        constitution,
        intent,
        risk_input,
        prior_state=prior_state,
        validate_schema=validate_schema,
    )


def validate_policy_constitution(document: dict[str, Any]) -> list[str]:
    return validate_document(document, "constitution.schema.json")


def validate_policy_intent(document: dict[str, Any]) -> list[str]:
    return validate_document(document, "intent.schema.json")


def validate_policy_risk_input(document: dict[str, Any]) -> list[str]:
    return validate_document(document, "risk_input.schema.json")
