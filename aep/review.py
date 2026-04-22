from __future__ import annotations

from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _policy_decision(*, risk_score: float, confidence: float, deny_threshold: float, review_threshold: float, min_confidence: float) -> str:
    if risk_score >= deny_threshold:
        return "DENY"
    if confidence < min_confidence:
        return "REVIEW"
    if risk_score >= review_threshold:
        return "REVIEW"
    return "ALLOW"


def _would_allow(decision: str) -> bool:
    return str(decision or "").upper() == "ALLOW"


def build_counterfactual_review(summary: dict[str, Any]) -> dict[str, Any]:
    risk_score = _safe_float(summary.get("risk_score"), 100.0)
    confidence = _clamp(_safe_float(summary.get("decision_confidence"), 0.0), 0.0, 1.0)

    strict_decision = _policy_decision(
        risk_score=risk_score,
        confidence=confidence,
        deny_threshold=60.0,
        review_threshold=40.0,
        min_confidence=0.60,
    )
    baseline_decision = _policy_decision(
        risk_score=risk_score,
        confidence=confidence,
        deny_threshold=70.0,
        review_threshold=50.0,
        min_confidence=0.50,
    )
    lenient_decision = _policy_decision(
        risk_score=risk_score,
        confidence=confidence,
        deny_threshold=80.0,
        review_threshold=60.0,
        min_confidence=0.40,
    )

    return {
        "schema_version": "aep.counterfactual_review.v1",
        "input": {
            "risk_score": round(risk_score, 6),
            "decision_confidence": round(confidence, 6),
        },
        "scenarios": [
            {
                "name": "strict",
                "deny_threshold": 60.0,
                "review_threshold": 40.0,
                "min_confidence": 0.60,
                "decision": strict_decision,
                "would_allow_execute": _would_allow(strict_decision),
            },
            {
                "name": "baseline",
                "deny_threshold": 70.0,
                "review_threshold": 50.0,
                "min_confidence": 0.50,
                "decision": baseline_decision,
                "would_allow_execute": _would_allow(baseline_decision),
            },
            {
                "name": "lenient",
                "deny_threshold": 80.0,
                "review_threshold": 60.0,
                "min_confidence": 0.40,
                "decision": lenient_decision,
                "would_allow_execute": _would_allow(lenient_decision),
            },
        ],
        "summary": {
            "strict_vs_baseline_changed": strict_decision != baseline_decision,
            "lenient_vs_baseline_changed": lenient_decision != baseline_decision,
        },
    }

