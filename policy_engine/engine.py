from __future__ import annotations

from typing import Any

from .validation import validate_aep_inputs


Decision = str


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def round2(value: float) -> float:
    return round(value + 1e-9, 2)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_token_penalty(token_score: dict[str, Any]) -> float:
    if "weighted_score" in token_score:
        return clamp(float(token_score["weighted_score"]))

    base = (
        0.40 * float(token_score["permission"])
        + 0.35 * float(token_score["rug"])
        + 0.25 * float(token_score["history"])
    )
    adjustment = float(token_score.get("consistency_adjustment", 0.0))
    return clamp(base + adjustment)


def compute_mcp_structural_risk(risk_input: dict[str, Any]) -> float:
    scores = risk_input["mcp_scores"]
    base = (
        0.18 * float(scores["r1_control"])
        + 0.17 * float(scores["r2_funding"])
        + 0.12 * float(scores["r3_convergence"])
        + 0.10 * float(scores["r4_terminal"])
        + 0.10 * float(scores["r5_history"])
        + 0.13 * float(scores["r6_lp_behavior"])
        + 0.10 * float(scores["r7_anomaly"])
        + 0.10 * float(scores["x_cross_signal"])
    )
    token_penalty = _get_token_penalty(scores["token_score"])
    structural = 0.80 * base + 0.20 * token_penalty
    return round2(clamp(structural))


def compute_risk_score_pre_advisory(
    risk_input: dict[str, Any], mcp_structural_risk: float
) -> float:
    context = risk_input["aep_context"]
    raw_risk_before_bonus = (
        0.30 * mcp_structural_risk
        + 0.15 * float(context["counterparty_risk"])
        + 0.15 * float(context["execution_complexity_risk"])
        + 0.10 * float(context["market_risk"])
        + 0.10 * float(context["anomaly_risk"])
        + 0.10 * float(context["evidence_gap_risk"])
        + 0.10 * float(context["governance_surface_risk"])
    )
    bonus_reduction = (
        0.10 * float(context["agent_reputation_bonus"])
        + 0.10 * float(context["treasury_health_bonus"])
    )
    # Keep reputation/treasury bonuses meaningful, but avoid reducing risk to near zero.
    bonus_reduction_cap = max(raw_risk_before_bonus, 0.0) * 0.80
    effective_bonus_reduction = min(bonus_reduction, bonus_reduction_cap)
    score = raw_risk_before_bonus - effective_bonus_reduction
    return round2(clamp(score))


def apply_advisory_floor(
    risk_score_pre: float, advisory_decision: str, constitution: dict[str, Any]
) -> float:
    mapping = constitution["risk_parameters"]["advisory_mapping"]
    floor = float(mapping["allow_floor_score"])
    if advisory_decision == "REVIEW":
        floor = float(mapping["review_floor_score"])
    elif advisory_decision == "BLOCK":
        floor = float(mapping["block_floor_score"])
    return round2(max(risk_score_pre, floor))


def evaluate_hard_constraints(
    constitution: dict[str, Any],
    intent: dict[str, Any],
    risk_input: dict[str, Any],
    prior_state: dict[str, Any] | None = None,
) -> list[str]:
    failed: list[str] = []
    rules = constitution["hard_constraints"]

    chain = intent["chain"]
    if chain not in rules["allowed_chains"]:
        failed.append("HC_CHAIN_NOT_ALLOWED")

    assets: list[str] = [item["asset"] for item in intent.get("assets_in", [])]
    assets.extend(item["asset"] for item in intent.get("assets_out_expectation", []))
    # Asset list guard can be re-enabled via constitution hard_constraints.enforce_asset_lists=true.
    # Default is off to avoid forcing static token lists in a long-tail Solana market.
    enforce_asset_lists = bool(rules.get("enforce_asset_lists", False))
    if enforce_asset_lists:
        allowed_assets = set(rules.get("allowed_assets", []))
        if allowed_assets and any(asset not in allowed_assets for asset in assets):
            failed.append("HC_ASSET_NOT_ALLOWED")
        forbidden_assets = set(rules.get("forbidden_assets", []))
        if any(asset in forbidden_assets for asset in assets):
            failed.append("HC_ASSET_FORBIDDEN")

    allowed_programs = set(rules.get("allowed_programs", []))
    forbidden_programs = set(rules.get("forbidden_programs", []))
    for call in intent.get("program_calls", []):
        program_id = call["program_id"]
        if program_id in forbidden_programs or (
            allowed_programs and program_id not in allowed_programs
        ):
            failed.append("HC_PROGRAM_NOT_ALLOWED")
            break

    if float(intent["notional_usd"]) > float(rules["max_notional_per_tx_usd"]):
        failed.append("HC_NOTIONAL_EXCEEDED")

    prior_state = prior_state or {}
    daily_usage = float(prior_state.get("daily_usage_usd", 0.0))
    if daily_usage + float(intent["notional_usd"]) > float(rules["max_daily_notional_usd"]):
        failed.append("HC_DAILY_LIMIT_EXCEEDED")

    if int(intent.get("slippage_bps", 0)) > int(rules["max_slippage_bps"]):
        failed.append("HC_SLIPPAGE_EXCEEDED")

    counterparty_risk = float(risk_input["aep_context"]["counterparty_risk"])
    counterparty_score = 100.0 - counterparty_risk
    if counterparty_score < float(rules["require_counterparty_score_min"]):
        failed.append("HC_COUNTERPARTY_SCORE_LOW")

    forbidden_counterparties = set(rules.get("forbidden_counterparties", []))
    counterparty_ids = {entry["id"] for entry in intent.get("counterparties", [])}
    allowed_counterparties = set(rules.get("allowed_counterparties", []))
    if allowed_counterparties and any(
        counterparty not in allowed_counterparties for counterparty in counterparty_ids
    ):
        failed.append("HC_COUNTERPARTY_NOT_ALLOWED")
    if forbidden_counterparties.intersection(counterparty_ids):
        if "HC_COUNTERPARTY_SCORE_LOW" not in failed:
            failed.append("HC_COUNTERPARTY_SCORE_LOW")

    metadata = intent.get("metadata") or {}
    max_bridge_exposure = float(rules.get("max_bridge_exposure_usd", 0.0))
    current_bridge_exposure = _as_float(
        prior_state.get("current_bridge_exposure_usd", prior_state.get("bridge_exposure_usd", 0.0)),
        0.0,
    )
    bridge_exposure_delta = _as_float(
        metadata.get("bridge_exposure_delta_usd", metadata.get("bridge_exposure_usd", 0.0)),
        0.0,
    )
    if bridge_exposure_delta == 0.0 and intent.get("intent_type") == "bridge":
        bridge_exposure_delta = float(intent["notional_usd"])
    projected_bridge_exposure = current_bridge_exposure + bridge_exposure_delta
    if projected_bridge_exposure > max_bridge_exposure:
        failed.append("HC_BRIDGE_EXPOSURE_EXCEEDED")

    max_leverage = float(rules.get("max_leverage", 0.0))
    requested_leverage = _as_float(
        metadata.get("requested_leverage", metadata.get("leverage", 1.0)),
        1.0,
    )
    if requested_leverage > max_leverage:
        failed.append("HC_LEVERAGE_EXCEEDED")

    if rules.get("simulation_required", True) and not intent.get("sim_result_hash"):
        failed.append("HC_SIMULATION_REQUIRED")

    return failed


def classify_decision(risk_score: float, constitution: dict[str, Any]) -> Decision:
    thresholds = constitution["risk_parameters"]["decision_thresholds"]
    if risk_score < float(thresholds["allow_light_max"]):
        return "ALLOW_WITH_LIGHT_BOND"
    if risk_score < float(thresholds["allow_standard_max"]):
        return "ALLOW_WITH_STANDARD_BOND"
    if risk_score < float(thresholds["allow_heavy_max"]):
        return "ALLOW_WITH_HEAVY_BOND"
    return "DENY"


def compute_bond_and_review_window(
    final_decision: Decision, constitution: dict[str, Any], intent: dict[str, Any]
) -> tuple[float, int]:
    if final_decision == "DENY":
        return 0.0, 0

    params = constitution["risk_parameters"]
    notional = float(intent["notional_usd"])
    base_bond = notional * (float(params["base_bond_bps"]) / 10000.0) * float(
        params["risk_multiplier"]
    )
    base_window = int(params["base_bond_review_window_secs"])

    if final_decision == "ALLOW_WITH_LIGHT_BOND":
        return round2(base_bond), base_window
    if final_decision == "ALLOW_WITH_STANDARD_BOND":
        return round2(base_bond * 1.8), base_window * 2
    return round2(base_bond * 3.0), base_window * 4


def build_reason_codes(
    failed_rules: list[str],
    risk_input: dict[str, Any],
    constitution: dict[str, Any],
    risk_score_post: float,
    final_decision: Decision,
) -> list[str]:
    reason_codes = list(failed_rules)
    advisory = risk_input["mcp_scores"]["advisory_decision"]
    if advisory == "BLOCK":
        reason_codes.append("RISK_ADVISORY_BLOCK")
    elif advisory == "REVIEW":
        reason_codes.append("RISK_ADVISORY_REVIEW")

    evidence_score = 100.0 - float(risk_input["aep_context"]["evidence_gap_risk"])
    if evidence_score < float(constitution["risk_parameters"]["evidence_min_score"]):
        reason_codes.append("RISK_EVIDENCE_TOO_WEAK")

    governance_risk = float(risk_input["aep_context"]["governance_surface_risk"])
    if governance_risk >= 80:
        reason_codes.append("RISK_GOVERNANCE_SURFACE_HIGH")

    deny_min = float(constitution["risk_parameters"]["decision_thresholds"]["deny_min"])
    if final_decision == "ALLOW_WITH_HEAVY_BOND":
        reason_codes.append("RISK_SCORE_HEAVY_BOND")
    if final_decision == "DENY" and risk_score_post >= deny_min:
        reason_codes.append("RISK_SCORE_DENY")

    deduped: list[str] = []
    for code in reason_codes:
        if code not in deduped:
            deduped.append(code)
    return deduped


def build_explanation(
    final_decision: Decision,
    failed_rules: list[str],
    risk_score_post: float,
    bond_required_usd: float,
    reason_codes: list[str],
) -> str:
    if final_decision == "DENY" and failed_rules:
        return (
            "Denied due to hard constraint violations: "
            + ", ".join(failed_rules)
            + f". Risk score after advisory mapping: {risk_score_post:.2f}."
        )
    if final_decision == "DENY":
        return f"Denied because risk score {risk_score_post:.2f} exceeded the configured deny threshold."

    label = final_decision.removeprefix("ALLOW_WITH_").removesuffix("_BOND").lower()
    extra = ""
    if reason_codes:
        extra = " Key reasons: " + ", ".join(reason_codes) + "."
    return (
        f"Allowed with {label} bond because hard constraints passed and risk score "
        f"{risk_score_post:.2f} is within the configured threshold. "
        f"Required bond: ${bond_required_usd:.2f}.{extra}"
    ).strip()


def evaluate_policy(
    constitution: dict[str, Any],
    intent: dict[str, Any],
    risk_input: dict[str, Any],
    prior_state: dict[str, Any] | None = None,
    validate_schema: bool = False,
) -> dict[str, Any]:
    if validate_schema:
        validation_errors = validate_aep_inputs(constitution, intent, risk_input)
        flat_errors = [
            f"{name}: {error}"
            for name, errors in validation_errors.items()
            for error in errors
        ]
        if flat_errors:
            raise ValueError("Schema validation failed: " + " | ".join(flat_errors))

    failed_rules = evaluate_hard_constraints(constitution, intent, risk_input, prior_state)
    hard_constraints_passed = len(failed_rules) == 0

    mcp_structural_risk = compute_mcp_structural_risk(risk_input)
    risk_score_pre = compute_risk_score_pre_advisory(risk_input, mcp_structural_risk)
    advisory_decision = risk_input["mcp_scores"]["advisory_decision"]
    risk_score_post = apply_advisory_floor(risk_score_pre, advisory_decision, constitution)

    final_decision: Decision
    if hard_constraints_passed:
        final_decision = classify_decision(risk_score_post, constitution)
    else:
        final_decision = "DENY"

    bond_required_usd, bond_review_window_secs = compute_bond_and_review_window(
        final_decision, constitution, intent
    )
    reason_codes = build_reason_codes(
        failed_rules, risk_input, constitution, risk_score_post, final_decision
    )
    explanation = build_explanation(
        final_decision, failed_rules, risk_score_post, bond_required_usd, reason_codes
    )

    return {
        "output_version": "policy_output.v1",
        "intent_id": intent["intent_id"],
        "agent_id": intent["agent_id"],
        "hard_constraints_passed": hard_constraints_passed,
        "failed_rules": failed_rules,
        "derived_values": {
            "mcp_structural_risk": mcp_structural_risk,
            "risk_score_pre_advisory": risk_score_pre,
            "risk_score_post_advisory": risk_score_post,
        },
        "advisory_decision": advisory_decision,
        "final_decision": final_decision,
        "bond_required_usd": bond_required_usd,
        "bond_review_window_secs": bond_review_window_secs,
        "reason_codes": reason_codes,
        "explanation": explanation,
    }
