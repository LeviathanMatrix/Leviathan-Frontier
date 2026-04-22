from aep.review import build_counterfactual_review


def test_counterfactual_review_has_three_scenarios() -> None:
    payload = build_counterfactual_review({"risk_score": 35.0, "decision_confidence": 0.8})
    names = [row["name"] for row in payload["scenarios"]]
    assert names == ["strict", "baseline", "lenient"]


def test_counterfactual_review_strict_is_not_more_lenient_than_baseline() -> None:
    payload = build_counterfactual_review({"risk_score": 75.0, "decision_confidence": 0.9})
    strict = next(row for row in payload["scenarios"] if row["name"] == "strict")
    baseline = next(row for row in payload["scenarios"] if row["name"] == "baseline")
    assert (strict["would_allow_execute"] is False) or (baseline["would_allow_execute"] is True)
