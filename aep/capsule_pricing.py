from __future__ import annotations

from typing import Any


CAPSULE_PRICING_SCHEMA_VERSION = "aep.capsule_pricing_profile.v1"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _round(value: float, digits: int = 6) -> float:
    return round(float(value) + 1e-9, digits)


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _policy_band_value(policy: dict[str, Any]) -> float:
    raw = str(policy.get("risk_band") or policy.get("policy_band") or "medium").strip().lower()
    if raw in {"low", "safe"}:
        return 0.0
    if raw in {"high", "strict"}:
        return 1.0
    return 0.5


def _normalize_review_intensity(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"strict", "high"}:
        return "strict"
    if text in {"enhanced", "elevated", "medium"}:
        return "enhanced"
    return "standard"


def _normalize_execution_mode(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"mainnet", "mainnet-beta"}:
        return "mainnet"
    if text == "devnet":
        return "devnet"
    return "paper"


def _limit_multiplier(pressure: float) -> float:
    if pressure <= 30.0:
        return 1.0
    if pressure <= 50.0:
        return 0.85
    if pressure <= 70.0:
        return 0.65
    if pressure <= 85.0:
        return 0.45
    return 0.25


def _ttl_multiplier(pressure: float) -> float:
    if pressure <= 30.0:
        return 1.0
    if pressure <= 50.0:
        return 0.80
    if pressure <= 70.0:
        return 0.65
    if pressure <= 85.0:
        return 0.50
    return 0.35


def build_capsule_pricing_profile(
    *,
    risk_input: dict[str, Any] | None = None,
    delegation_guard: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    execution_mode: str | None = None,
    review_intensity: str | None = None,
    capsule_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    risk_doc = risk_input if isinstance(risk_input, dict) else {}
    _ = delegation_guard
    policy_doc = policy if isinstance(policy, dict) else {}
    params = capsule_params if isinstance(capsule_params, dict) else {}

    risk_score = _clamp(
        _safe_float(
            risk_doc.get("open_risk_score"),
            _safe_float(
                risk_doc.get("policy_risk_score"),
                _safe_float(risk_doc.get("risk_score_post_advisory"), 50.0),
            ),
        ),
        0.0,
        100.0,
    )
    uncertainty = _clamp(_safe_float(risk_doc.get("uncertainty"), 0.5), 0.0, 1.0)
    evidence_coverage = _clamp(
        _safe_float(
            risk_doc.get("effective_coverage"),
            _safe_float(risk_doc.get("evidence_coverage"), 0.5),
        ),
        0.0,
        1.0,
    )

    volatility_proxy = _clamp(
        _safe_float(
            risk_doc.get("volatility_proxy"),
            max(uncertainty, 1.0 - evidence_coverage),
        ),
        0.0,
        1.0,
    )
    resolved_mode = _normalize_execution_mode(
        execution_mode
        or risk_doc.get("execution_mode")
        or policy_doc.get("execution_mode")
        or "paper"
    )
    resolved_review_intensity = _normalize_review_intensity(
        review_intensity
        or risk_doc.get("review_intensity")
        or policy_doc.get("review_intensity")
    )
    if (
        review_intensity is None
        and risk_doc.get("review_intensity") is None
        and policy_doc.get("review_intensity") is None
    ):
        if risk_score >= 80.0 or uncertainty >= 0.55 or evidence_coverage <= 0.30:
            resolved_review_intensity = "strict"
        elif risk_score >= 45.0:
            resolved_review_intensity = "enhanced"

    mode_penalty_map = _safe_dict(params.get("pressure_mode_penalty")) or {"paper": 0.0, "devnet": 10.0, "mainnet": 18.0}
    review_penalty_map = _safe_dict(params.get("pressure_review_penalty")) or {"standard": 8.0, "enhanced": 15.0, "strict": 20.0}
    mode_penalty = _safe_float(mode_penalty_map.get(resolved_mode), _safe_float(mode_penalty_map.get("paper"), 0.0))
    review_penalty = _safe_float(
        review_penalty_map.get(resolved_review_intensity),
        _safe_float(review_penalty_map.get("standard"), 8.0),
    )
    risk_weight = _safe_float(params.get("pressure_risk_weight"), 0.50)
    volatility_weight = _safe_float(params.get("pressure_volatility_weight"), 0.20)
    risk_component = risk_weight * risk_score
    volatility_component = volatility_weight * volatility_proxy * 100.0
    raw_pressure = risk_component + volatility_component + mode_penalty + review_penalty
    pressure = _clamp(raw_pressure, 0.0, 100.0)

    # Module C keeps capsule limit logic simple; multipliers are advisory only.
    limit_multiplier = 1.0
    ttl_multiplier = 1.0
    advisory_limit_multiplier = _limit_multiplier(pressure)
    advisory_ttl_multiplier = _ttl_multiplier(pressure)

    if resolved_mode == "mainnet" or uncertainty >= 0.45 or evidence_coverage <= 0.45 or pressure >= 75.0:
        mode_restriction = "paper_only"
    elif pressure >= 55.0:
        mode_restriction = "paper_preferred"
    else:
        mode_restriction = "paper_devnet"

    if pressure >= 80.0 and resolved_review_intensity != "strict":
        resolved_review_intensity = "strict"
        revocation_sensitivity = "high"
    elif pressure >= 60.0:
        revocation_sensitivity = "medium"
    else:
        revocation_sensitivity = "normal"

    reasons: list[str] = []
    if risk_score >= 70.0:
        reasons.append("risk_score_high")
    if uncertainty >= 0.45:
        reasons.append("uncertainty_high")
    if evidence_coverage <= 0.45:
        reasons.append("evidence_coverage_low")
    if volatility_proxy >= 0.50:
        reasons.append("volatility_proxy_high")
    if resolved_mode == "devnet":
        reasons.append("mode_devnet_penalty")
    if resolved_mode == "mainnet":
        reasons.append("mode_mainnet_penalty")
    if _policy_band_value(policy_doc) >= 1.0:
        reasons.append("policy_band_strict")

    return {
        "schema_version": CAPSULE_PRICING_SCHEMA_VERSION,
        "inputs": {
            "open_risk_score": _round(risk_score, 2),
            "uncertainty": _round(uncertainty, 4),
            "evidence_coverage": _round(evidence_coverage, 4),
            "volatility_proxy": _round(volatility_proxy, 4),
            "execution_mode": resolved_mode,
            "review_intensity": resolved_review_intensity,
        },
        "capsule_pressure": _round(pressure, 2),
        "pressure_components": {
            "risk_weight": _round(risk_weight, 6),
            "volatility_weight": _round(volatility_weight, 6),
            "risk_component": _round(risk_component, 4),
            "volatility_component": _round(volatility_component, 4),
            "mode_penalty": _round(mode_penalty, 4),
            "review_penalty": _round(review_penalty, 4),
            "raw_pressure": _round(raw_pressure, 4),
            "volatility_proxy": _round(volatility_proxy, 4),
        },
        "limit_multiplier": _round(limit_multiplier, 4),
        "ttl_multiplier": _round(ttl_multiplier, 4),
        "advisory_limit_multiplier": _round(advisory_limit_multiplier, 4),
        "advisory_ttl_multiplier": _round(advisory_ttl_multiplier, 4),
        "mode_restriction": mode_restriction,
        "review_intensity": resolved_review_intensity,
        "revocation_sensitivity": revocation_sensitivity,
        "reasons": reasons,
    }
