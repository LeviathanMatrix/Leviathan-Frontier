from __future__ import annotations

from pathlib import Path

from scripts.aep_anchor_payload import build_anchor_payload


def test_anchor_payload_hashes_case_lifecycle(tmp_path: Path) -> None:
    case_doc = {
        "spec_id": "leviathanmatrix.aep.open-core.v1",
        "case_id": "case_demo",
        "status": "EXECUTED",
        "authorization": {
            "status": "AUTHORIZED",
            "issuance": {
                "execution_pass": {
                    "pass_id": "pass_demo",
                    "status": "ISSUED",
                    "capability_hash": "capability",
                }
            },
            "decision": {
                "capital_capsule": {
                    "capsule_id": "capsule_demo",
                    "capsule_status": "EXHAUSTED",
                }
            },
        },
        "execution": {
            "status": "EXECUTED",
            "tx_id": "tx_demo",
        },
        "receipt": {
            "status": "EXECUTED",
            "tx_id": "tx_demo",
        },
        "review": {
            "status": "PASSED",
        },
    }
    payload = build_anchor_payload(
        case_doc,
        accountability_log_path=tmp_path / "missing-events.jsonl",
    )

    assert payload["schema_version"] == "leviathanmatrix.aep.anchor_payload.v1"
    assert payload["case_id"] == "case_demo"
    assert payload["verdict_code"] == 3
    assert payload["source"]["pass_id"] == "pass_demo"
    assert payload["source"]["capsule_id"] == "capsule_demo"
    assert payload["source"]["tx_id"] == "tx_demo"
    assert set(payload["hashes"]) == {
        "case_id_hash",
        "case_hash",
        "pass_hash",
        "capsule_hash",
        "receipt_hash",
        "review_hash",
        "accountability_head_hash",
    }
    assert all(len(value) == 64 for value in payload["hashes"].values())
    assert payload["hashes"]["accountability_head_hash"] == "0" * 64


def test_anchor_payload_denied_case_verdict() -> None:
    payload = build_anchor_payload(
        {
            "case_id": "case_denied",
            "authorization": {"status": "DENIED"},
            "execution": {"status": "BLOCKED"},
            "review": {"status": "FAILED"},
        },
        accountability_log_path=Path("does-not-exist.jsonl"),
    )

    assert payload["verdict_code"] == 1
