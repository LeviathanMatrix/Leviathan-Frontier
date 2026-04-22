from __future__ import annotations

from pathlib import Path

from aep.kernel import authorize_action, execute_case, export_execution_claim, review_case, run_text, simulate_case


def test_run_text_end_to_end(tmp_path: Path) -> None:
    result = run_text(text="buy 1 USDC of SOL", agent_id="agent-e2e", case_root=tmp_path / "cases")
    assert result["ok"] is True
    assert result["authorization"]["status"] == "AUTHORIZED"
    assert result["execution"]["status"] == "EXECUTED"
    assert result["receipt"]["status"] == "EXECUTED"
    assert result["review"]["status"] == "PASSED"
    assert result["producer"]["company"] == "LeviathanMatrix"
    assert result["spec_id"] == "leviathanmatrix.aep.open-core.v1"


def test_simulate_then_review(tmp_path: Path) -> None:
    case_root = tmp_path / "cases"
    case_doc = authorize_action(text="buy 1 USDC of SOL", agent_id="agent-sim", case_root=case_root)
    case_doc = simulate_case(case_doc, case_root=case_root)
    assert case_doc["execution"]["status"] == "SIMULATED"
    case_doc = review_case(case_doc, case_root=case_root)
    assert case_doc["review"]["status"] == "PASSED"


def test_export_claim_has_no_private_fields(tmp_path: Path) -> None:
    case_root = tmp_path / "cases"
    case_doc = authorize_action(text="buy 1 USDC of SOL", agent_id="agent-claim", case_root=case_root)
    case_doc = execute_case(case_doc, case_root=case_root)
    case_doc = review_case(case_doc, case_root=case_root)
    claim = export_execution_claim(case_doc)
    assert claim["schema_version"] == "aep.execution_claim.v1"
    assert claim["producer"]["company"] == "LeviathanMatrix"
    assert claim["spec_id"] == "leviathanmatrix.aep.open-core.v1"
    assert "authorization" in claim
    assert "execution" in claim
    assert "review" in claim
