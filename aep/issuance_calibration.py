from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .issuance_ledger import verify_issuance_chain


REPORT_SCHEMA_VERSION = "aep.issuance_calibration_report.v1"
KNOWN_PRESSURE_BANDS = ("fast", "standard", "guarded", "review", "deny", "unknown")
DEFAULT_PRESSURE_THRESHOLDS = {
    "fast": 25,
    "standard": 50,
    "guarded": 70,
    "review": 84,
    "deny": 85,
}
MAX_SAMPLE_ROWS = 20


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return default
        if isinstance(value, int):
            return value
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _round(value: float, digits: int = 6) -> float:
    return round(float(value) + 1e-9, digits)


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return _round(float(numerator) / float(denominator), 6)


def _ts_iso(ts: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(max(0, int(ts))))


def _json_load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must decode to an object")
    return payload


def _iter_case_docs(case_root: Path) -> list[dict[str, Any]]:
    if not case_root.exists():
        return []
    docs: list[dict[str, Any]] = []
    for path in sorted(case_root.glob("*.json")):
        try:
            doc = _json_load(path)
        except Exception:
            continue
        doc["_path"] = str(path)
        docs.append(doc)
    return docs


def _select_issuance_ledger_path(case_docs: list[dict[str, Any]], override: Any) -> Path | None:
    if override is not None and str(override).strip():
        return Path(str(override)).expanduser().resolve()
    candidates: list[str] = []
    for doc in case_docs:
        storage = doc.get("storage") if isinstance(doc.get("storage"), dict) else {}
        ledger_path = str(storage.get("issuance_ledger_path") or "").strip()
        if ledger_path:
            candidates.append(str(Path(ledger_path).expanduser().resolve()))
    if not candidates:
        return None
    most_common = Counter(candidates).most_common(1)[0][0]
    return Path(most_common)


def _normalize_pressure_thresholds(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    out: dict[str, int] = {}
    for key in ("fast", "standard", "guarded", "review", "deny"):
        if key not in value:
            return None
        out[key] = _safe_int(value.get(key), -1)
        if out[key] < 0:
            return None
    return out


def _resolve_pressure_thresholds(case_docs: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    by_signature: dict[str, dict[str, int]] = {}
    for doc in case_docs:
        authorization = doc.get("authorization") if isinstance(doc.get("authorization"), dict) else {}
        constitution = (
            authorization.get("constitution_snapshot")
            if isinstance(authorization.get("constitution_snapshot"), dict)
            else {}
        )
        issuance_cfg = constitution.get("issuance") if isinstance(constitution.get("issuance"), dict) else {}
        thresholds = _normalize_pressure_thresholds(issuance_cfg.get("pressure_thresholds"))
        if thresholds is None:
            continue
        signature = json.dumps(thresholds, sort_keys=True)
        counts[signature] += 1
        by_signature[signature] = thresholds

    if not counts:
        return {
            "source": "default",
            "values": dict(DEFAULT_PRESSURE_THRESHOLDS),
        }
    signature = counts.most_common(1)[0][0]
    return {
        "source": "case_constitution_snapshot",
        "values": by_signature[signature],
    }


def _derive_outcome(case_doc: dict[str, Any], issuance_status: str) -> tuple[dict[str, Any], str]:
    authorization = case_doc.get("authorization") if isinstance(case_doc.get("authorization"), dict) else {}
    provided = authorization.get("issuance_outcome")
    if isinstance(provided, dict):
        return dict(provided), "authorization.issuance_outcome"

    execution = case_doc.get("execution") if isinstance(case_doc.get("execution"), dict) else {}
    review = case_doc.get("review") if isinstance(case_doc.get("review"), dict) else {}
    capsule = (
        case_doc.get("authorization", {}).get("decision", {}).get("capital_capsule")
        if isinstance(case_doc.get("authorization"), dict)
        and isinstance(case_doc.get("authorization", {}).get("decision"), dict)
        else {}
    )
    capsule = capsule if isinstance(capsule, dict) else {}

    receipt_ingest = execution.get("receipt_ingest") if isinstance(execution.get("receipt_ingest"), dict) else {}
    receipt = receipt_ingest.get("receipt") if isinstance(receipt_ingest.get("receipt"), dict) else {}

    error = str(execution.get("error") or "").strip()
    timed_out = "timeout" in error.lower()
    executed = bool(execution.get("ok", False) and not bool(execution.get("simulated", False)))
    failed = bool(error) or (bool(execution) and not bool(execution.get("ok", False)))
    review_passed = _safe_bool_or_none(review.get("passed"))
    review_verdict = "pass" if review_passed is True else "fail" if review_passed is False else None

    execution_outcome_status = ""
    if issuance_status == "FINALIZED":
        execution_outcome_status = "completed"
    elif issuance_status in {"DENIED", "FAILED", "REVOKED", "EXPIRED"}:
        execution_outcome_status = "failed"
    else:
        execution_outcome_status = "pending"
    finalization_summary = (
        capsule.get("finalization_summary")
        if isinstance(capsule.get("finalization_summary"), dict)
        else {}
    )
    legacy_status = str(finalization_summary.get("status") or "").strip().lower()
    if legacy_status == "finalized":
        execution_outcome_status = "completed"
    elif legacy_status in {"failed", "pending"}:
        execution_outcome_status = legacy_status

    return (
        {
            "executed": executed,
            "failed": failed,
            "timed_out": timed_out,
            "revoked": issuance_status == "REVOKED",
            "receipt_status": str(receipt.get("status") or "").strip().upper() or None,
            "review_verdict": review_verdict,
            "review_passed": review_passed,
            "execution_outcome_status": execution_outcome_status,
            "review_outcome": review_verdict,
            "issuance_status": issuance_status or None,
            "algorithm_version": None,
            "error": error or None,
        },
        "derived_from_case",
    )


def _build_case_row(case_doc: dict[str, Any]) -> dict[str, Any] | None:
    authorization = case_doc.get("authorization") if isinstance(case_doc.get("authorization"), dict) else {}
    issuance = authorization.get("issuance") if isinstance(authorization.get("issuance"), dict) else {}
    if not issuance:
        return None

    summary = authorization.get("summary") if isinstance(authorization.get("summary"), dict) else {}
    eligibility = issuance.get("eligibility") if isinstance(issuance.get("eligibility"), dict) else {}
    pricing = issuance.get("pricing") if isinstance(issuance.get("pricing"), dict) else {}
    replay = issuance.get("replay") if isinstance(issuance.get("replay"), dict) else {}
    issuance_status = str(issuance.get("status") or "").strip().upper()
    pressure_band = str(pricing.get("pressure_band") or "").strip().lower() or "unknown"
    if pressure_band not in KNOWN_PRESSURE_BANDS:
        pressure_band = "unknown"
    outcome, outcome_source = _derive_outcome(case_doc, issuance_status)
    review_passed = _safe_bool_or_none(outcome.get("review_passed"))
    if review_passed is None:
        if str(outcome.get("review_verdict") or "").strip().lower() == "pass":
            review_passed = True
        elif str(outcome.get("review_verdict") or "").strip().lower() == "fail":
            review_passed = False
    executed = bool(outcome.get("executed", False))
    failed = bool(outcome.get("failed", False))
    execution_observed = executed or failed

    return {
        "case_id": str(case_doc.get("case_id") or "").strip() or None,
        "created_at": _safe_int(case_doc.get("created_at"), 0),
        "agent_id": str(case_doc.get("request", {}).get("agent", {}).get("agent_id") or "").strip() or None
        if isinstance(case_doc.get("request"), dict)
        else None,
        "case_status": str(case_doc.get("status") or "").strip() or None,
        "issuance_id": str(issuance.get("issuance_id") or "").strip() or None,
        "issuance_status": issuance_status or None,
        "pressure_band": pressure_band,
        "issuance_pressure": _safe_float(pricing.get("issuance_pressure"), 0.0),
        "algorithm_version": str(replay.get("algorithm_version") or "").strip() or None,
        "risk_score": _safe_float(summary.get("risk_score"), 0.0),
        "decision_confidence": _safe_float(summary.get("decision_confidence"), 0.0),
        "hard_block_reasons": list(eligibility.get("hard_block_reasons", [])),
        "review_reasons": list(eligibility.get("review_reasons", [])),
        "clarification_reasons": list(eligibility.get("clarification_reasons", [])),
        "executed": executed,
        "failed": failed,
        "execution_observed": execution_observed,
        "timed_out": bool(outcome.get("timed_out", False)),
        "review_passed": review_passed,
        "review_failed": review_passed is False,
        "execution_outcome_status": str(outcome.get("execution_outcome_status") or "").strip().lower() or None,
        "revoked": bool(outcome.get("revoked", False)),
        "outcome_source": outcome_source,
        "outcome": outcome,
    }


def _collect_false_allow_samples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in rows:
        status = str(row.get("issuance_status") or "").strip().upper()
        if not status or status == "DENIED":
            continue
        signals: list[str] = []
        if bool(row.get("failed", False)):
            signals.append("execution_failed")
        if bool(row.get("timed_out", False)):
            signals.append("execution_timed_out")
        if bool(row.get("review_failed", False)):
            signals.append("review_failed")
        if status in {"REVOKED", "EXPIRED", "FAILED"}:
            signals.append(f"terminal_status_{status.lower()}")
        if str(row.get("execution_outcome_status") or "").strip().lower() == "failed":
            signals.append("execution_outcome_failed")
        if not signals:
            continue
        samples.append(
            {
                "case_id": row.get("case_id"),
                "issuance_id": row.get("issuance_id"),
                "pressure_band": row.get("pressure_band"),
                "issuance_pressure": row.get("issuance_pressure"),
                "issuance_status": row.get("issuance_status"),
                "algorithm_version": row.get("algorithm_version"),
                "signals": signals,
            }
        )
    samples.sort(
        key=lambda item: (
            -len(item.get("signals", [])),
            _safe_float(item.get("issuance_pressure"), 0.0),
            str(item.get("case_id") or ""),
        )
    )
    return samples[:MAX_SAMPLE_ROWS]


def _collect_false_deny_samples(
    rows: list[dict[str, Any]],
    *,
    thresholds: dict[str, int],
) -> list[dict[str, Any]]:
    deny_threshold = _safe_float(thresholds.get("deny"), 85.0)
    review_threshold = _safe_float(thresholds.get("review"), 84.0)
    samples: list[dict[str, Any]] = []
    for row in rows:
        status = str(row.get("issuance_status") or "").strip().upper()
        if status != "DENIED":
            continue
        pressure = _safe_float(row.get("issuance_pressure"), 0.0)
        hard_blocks = [str(x or "").strip() for x in list(row.get("hard_block_reasons", [])) if str(x or "").strip()]
        review_reasons = [str(x or "").strip() for x in list(row.get("review_reasons", [])) if str(x or "").strip()]
        clarification_reasons = [
            str(x or "").strip() for x in list(row.get("clarification_reasons", [])) if str(x or "").strip()
        ]
        risk_score = _safe_float(row.get("risk_score"), 0.0)
        confidence = _safe_float(row.get("decision_confidence"), 0.0)

        signals: list[str] = []
        if pressure < deny_threshold:
            signals.append("denied_below_deny_threshold")
        if pressure <= review_threshold:
            signals.append("denied_at_or_below_review_threshold")
        if not hard_blocks:
            signals.append("no_hard_block_reasons")
        if risk_score < 70.0:
            signals.append("risk_score_below_high")
        if confidence >= 0.75:
            signals.append("high_decision_confidence")

        is_candidate = (
            ("denied_below_deny_threshold" in signals)
            and ("no_hard_block_reasons" in signals)
            and (len(review_reasons) == 0)
            and (len(clarification_reasons) == 0)
        )
        if not is_candidate:
            continue

        samples.append(
            {
                "case_id": row.get("case_id"),
                "issuance_id": row.get("issuance_id"),
                "pressure_band": row.get("pressure_band"),
                "issuance_pressure": pressure,
                "risk_score": risk_score,
                "decision_confidence": confidence,
                "algorithm_version": row.get("algorithm_version"),
                "signals": signals,
            }
        )

    samples.sort(
        key=lambda item: (
            _safe_float(item.get("issuance_pressure"), 0.0),
            _safe_float(item.get("risk_score"), 0.0),
            -_safe_float(item.get("decision_confidence"), 0.0),
        )
    )
    return samples[:MAX_SAMPLE_ROWS]


def _build_threshold_recommendations(
    *,
    rows: list[dict[str, Any]],
    false_allow_samples: list[dict[str, Any]],
    false_deny_samples: list[dict[str, Any]],
    threshold_info: dict[str, Any],
) -> dict[str, Any]:
    thresholds = threshold_info.get("values") if isinstance(threshold_info.get("values"), dict) else DEFAULT_PRESSURE_THRESHOLDS
    allowed_rows = [row for row in rows if str(row.get("issuance_status") or "").strip().upper() != "DENIED"]
    denied_rows = [row for row in rows if str(row.get("issuance_status") or "").strip().upper() == "DENIED"]
    false_allow_rate = _ratio(len(false_allow_samples), len(allowed_rows))
    false_deny_rate = _ratio(len(false_deny_samples), len(denied_rows))

    recommendations: list[dict[str, Any]] = []
    allow_min_samples = 5
    deny_min_samples = 5
    if len(allowed_rows) >= allow_min_samples and (false_allow_rate or 0.0) >= 0.2:
        recommendations.append(
            {
                "type": "tighten_allow_thresholds",
                "priority": "high",
                "suggested_changes": {
                    "fast": _safe_int(thresholds.get("fast"), 25) - 5 if _safe_int(thresholds.get("fast"), 25) >= 10 else _safe_int(thresholds.get("fast"), 25),
                    "standard": _safe_int(thresholds.get("standard"), 50) - 5
                    if _safe_int(thresholds.get("standard"), 50) >= 20
                    else _safe_int(thresholds.get("standard"), 50),
                },
                "reason": "potential false-allow rate is elevated in issued paths",
                "evidence": {
                    "allowed_cases": len(allowed_rows),
                    "potential_false_allow_cases": len(false_allow_samples),
                    "potential_false_allow_rate": false_allow_rate,
                },
            }
        )
    if len(denied_rows) >= deny_min_samples and (false_deny_rate or 0.0) >= 0.2:
        recommendations.append(
            {
                "type": "relax_deny_threshold",
                "priority": "medium",
                "suggested_changes": {
                    "deny": max(_safe_int(thresholds.get("deny"), 85) - 3, _safe_int(thresholds.get("review"), 84) + 1),
                },
                "reason": "potential false-deny samples observed below deny threshold without hard blocks",
                "evidence": {
                    "denied_cases": len(denied_rows),
                    "potential_false_deny_cases": len(false_deny_samples),
                    "potential_false_deny_rate": false_deny_rate,
                },
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "type": "hold_thresholds",
                "priority": "info",
                "reason": "no statistically strong threshold drift signal yet",
                "evidence": {
                    "allowed_cases": len(allowed_rows),
                    "denied_cases": len(denied_rows),
                    "potential_false_allow_cases": len(false_allow_samples),
                    "potential_false_deny_cases": len(false_deny_samples),
                },
            }
        )
    return {
        "classification_mode": "heuristic_v1",
        "pressure_thresholds_source": threshold_info.get("source"),
        "current_thresholds": thresholds,
        "signals": {
            "allowed_cases": len(allowed_rows),
            "denied_cases": len(denied_rows),
            "potential_false_allow_rate": false_allow_rate,
            "potential_false_deny_rate": false_deny_rate,
        },
        "recommendations": recommendations,
    }


def run_issuance_calibration_report(
    *,
    case_root: Any,
    issuance_ledger_path: Any = None,
    agent_id: str = "",
    limit: int = 0,
) -> dict[str, Any]:
    case_root_path = Path(str(case_root)).expanduser().resolve()
    docs = _iter_case_docs(case_root_path)
    if agent_id:
        agent_filter = str(agent_id).strip()
        docs = [
            doc
            for doc in docs
            if str(doc.get("request", {}).get("agent", {}).get("agent_id") or "").strip() == agent_filter
        ]
    docs.sort(key=lambda row: _safe_int(row.get("created_at"), 0))
    if limit > 0:
        docs = docs[-int(limit) :]
    threshold_info = _resolve_pressure_thresholds(docs)

    rows: list[dict[str, Any]] = []
    algorithm_versions: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    band_counter: Counter[str] = Counter()
    outcome_present_count = 0

    band_metrics: dict[str, dict[str, Any]] = {}

    for doc in docs:
        row = _build_case_row(doc)
        if row is None:
            continue
        rows.append(row)
        if row["outcome_source"] == "authorization.issuance_outcome":
            outcome_present_count += 1
        band = str(row.get("pressure_band") or "unknown")
        band_counter[band] += 1
        status = str(row.get("issuance_status") or "").strip().upper()
        if status:
            status_counter[status] += 1
        algo = str(row.get("algorithm_version") or "").strip()
        if algo:
            algorithm_versions[algo] += 1

        stats = band_metrics.setdefault(
            band,
            {
                "cases": 0,
                "execution_observed_cases": 0,
                "execution_successes": 0,
                "reviewed_cases": 0,
                "review_failures": 0,
            },
        )
        stats["cases"] += 1
        if bool(row.get("execution_observed", False)):
            stats["execution_observed_cases"] += 1
            if bool(row.get("executed", False)) and not bool(row.get("failed", False)):
                stats["execution_successes"] += 1
        if row.get("review_passed") is not None:
            stats["reviewed_cases"] += 1
            if row.get("review_passed") is False:
                stats["review_failures"] += 1

    issuance_cases = len(rows)
    for band, stats in band_metrics.items():
        stats["execution_success_rate"] = _ratio(stats["execution_successes"], stats["execution_observed_cases"])
        stats["review_failure_rate"] = _ratio(stats["review_failures"], stats["reviewed_cases"])
        stats["share_of_issuance_cases"] = _ratio(stats["cases"], issuance_cases)

    ordered_bands = [band for band in KNOWN_PRESSURE_BANDS if band in band_metrics]
    for band in band_metrics:
        if band not in ordered_bands:
            ordered_bands.append(band)
    ordered_band_metrics = {band: band_metrics[band] for band in ordered_bands}

    pressure_band_distribution = {
        band: {"count": int(band_counter.get(band, 0)), "ratio": _ratio(int(band_counter.get(band, 0)), issuance_cases)}
        for band in ordered_bands
    }

    execution_observed_total = sum(int(stats["execution_observed_cases"]) for stats in band_metrics.values())
    execution_success_total = sum(int(stats["execution_successes"]) for stats in band_metrics.values())
    reviewed_total = sum(int(stats["reviewed_cases"]) for stats in band_metrics.values())
    review_failures_total = sum(int(stats["review_failures"]) for stats in band_metrics.values())

    status_keys = ("REVOKED", "EXPIRED", "FAILED")
    status_ratios = {
        key.lower(): {
            "count": int(status_counter.get(key, 0)),
            "ratio": _ratio(int(status_counter.get(key, 0)), issuance_cases),
        }
        for key in status_keys
    }

    resolved_ledger_path = _select_issuance_ledger_path(docs, issuance_ledger_path)
    ledger_quality: dict[str, Any] = {
        "ledger_path": str(resolved_ledger_path) if resolved_ledger_path else None,
        "ledger_chain_ok": None,
        "ledger_event_count": 0,
        "ledger_issues": [],
    }
    if resolved_ledger_path is not None:
        verification = verify_issuance_chain(ledger_path=resolved_ledger_path)
        ledger_quality = {
            "ledger_path": str(resolved_ledger_path),
            "ledger_chain_ok": bool(verification.get("ok", False)),
            "ledger_event_count": int(verification.get("count", 0)),
            "ledger_issues": list(verification.get("issues", []))[:20],
        }

    false_allow_samples = _collect_false_allow_samples(rows)
    false_deny_samples = _collect_false_deny_samples(
        rows,
        thresholds=threshold_info.get("values") if isinstance(threshold_info.get("values"), dict) else DEFAULT_PRESSURE_THRESHOLDS,
    )
    threshold_recommendations = _build_threshold_recommendations(
        rows=rows,
        false_allow_samples=false_allow_samples,
        false_deny_samples=false_deny_samples,
        threshold_info=threshold_info,
    )

    now_ts = int(time.time())
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": now_ts,
        "generated_at_iso": _ts_iso(now_ts),
        "input": {
            "case_root": str(case_root_path),
            "issuance_ledger_path": str(resolved_ledger_path) if resolved_ledger_path else None,
            "agent_id": str(agent_id or "").strip() or None,
            "limit": int(limit),
        },
        "totals": {
            "loaded_cases": len(docs),
            "issuance_cases": issuance_cases,
            "outcome_present_cases": outcome_present_count,
            "outcome_coverage_rate": _ratio(outcome_present_count, issuance_cases),
            "execution_observed_cases": execution_observed_total,
            "execution_successes": execution_success_total,
            "overall_execution_success_rate": _ratio(execution_success_total, execution_observed_total),
            "reviewed_cases": reviewed_total,
            "review_failures": review_failures_total,
            "overall_review_failure_rate": _ratio(review_failures_total, reviewed_total),
        },
        "pressure_band_distribution": pressure_band_distribution,
        "band_metrics": ordered_band_metrics,
        "status_ratios": status_ratios,
        "false_allow_samples": false_allow_samples,
        "false_deny_samples": false_deny_samples,
        "threshold_recommendations": threshold_recommendations,
        "algorithm_versions": dict(sorted(algorithm_versions.items())),
        "data_quality": ledger_quality,
        "cases": rows,
    }


def write_issuance_calibration_report(path: str | Path, report: dict[str, Any]) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
