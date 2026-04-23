from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aep.accountability import compute_json_digest, replay_accountability_chain  # noqa: E402
from aep.kernel import load_case, run_text  # noqa: E402


def _hex32_from_text(value: str) -> str:
    return sha256(str(value or "").encode("utf-8")).hexdigest()


def _hex32_from_object(value: Any) -> str:
    return compute_json_digest(value if value is not None else {})


def _authorization_parts(case_doc: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    authorization = case_doc.get("authorization") if isinstance(case_doc.get("authorization"), dict) else {}
    issuance = authorization.get("issuance") if isinstance(authorization.get("issuance"), dict) else {}
    decision = authorization.get("decision") if isinstance(authorization.get("decision"), dict) else {}
    capsule = decision.get("capital_capsule") if isinstance(decision.get("capital_capsule"), dict) else {}
    execution_pass = issuance.get("execution_pass") if isinstance(issuance.get("execution_pass"), dict) else {}
    return execution_pass, capsule


def _verdict_code(case_doc: dict[str, Any]) -> int:
    authorization = case_doc.get("authorization") if isinstance(case_doc.get("authorization"), dict) else {}
    execution = case_doc.get("execution") if isinstance(case_doc.get("execution"), dict) else {}
    review = case_doc.get("review") if isinstance(case_doc.get("review"), dict) else {}
    auth_status = str(authorization.get("status") or "").strip().upper()
    execution_status = str(execution.get("status") or "").strip().upper()
    review_status = str(review.get("status") or "").strip().upper()
    if auth_status in {"DENIED", "FAILED"}:
        return 1
    if execution_status == "BLOCKED":
        return 2
    if execution_status == "EXECUTED" and review_status == "PASSED":
        return 3
    if execution_status == "EXECUTED":
        return 4
    if review_status == "FAILED":
        return 5
    return 0


def build_anchor_payload(case_doc: dict[str, Any], *, accountability_log_path: Path) -> dict[str, Any]:
    execution_pass, capsule = _authorization_parts(case_doc)
    receipt = case_doc.get("receipt") if isinstance(case_doc.get("receipt"), dict) else {}
    review = case_doc.get("review") if isinstance(case_doc.get("review"), dict) else {}
    case_id = str(case_doc.get("case_id") or "").strip()
    if not case_id:
        raise ValueError("case_id is required")

    accountability = replay_accountability_chain(accountability_log_path)

    hashes = {
        "case_id_hash": _hex32_from_text(case_id),
        "case_hash": _hex32_from_object(case_doc),
        "pass_hash": _hex32_from_object(execution_pass),
        "capsule_hash": _hex32_from_object(capsule),
        "receipt_hash": _hex32_from_object(receipt),
        "review_hash": _hex32_from_object(review),
        "accountability_head_hash": str(accountability.get("head_event_hash") or "").strip()
        if str(accountability.get("head_event_hash") or "").strip() and str(accountability.get("head_event_hash")) != "GENESIS"
        else "0" * 64,
    }

    return {
        "schema_version": "leviathanmatrix.aep.anchor_payload.v1",
        "case_id": case_id,
        "spec_id": str(case_doc.get("spec_id") or "leviathanmatrix.aep.open-core.v1"),
        "verdict_code": _verdict_code(case_doc),
        "hashes": hashes,
        "source": {
            "case_status": str(case_doc.get("status") or "").strip().upper(),
            "authorization_status": str(
                (case_doc.get("authorization") if isinstance(case_doc.get("authorization"), dict) else {}).get("status")
                or ""
            ).strip().upper(),
            "execution_status": str(
                (case_doc.get("execution") if isinstance(case_doc.get("execution"), dict) else {}).get("status") or ""
            ).strip().upper(),
            "review_status": str(
                (case_doc.get("review") if isinstance(case_doc.get("review"), dict) else {}).get("status") or ""
            ).strip().upper(),
            "pass_id": str(execution_pass.get("pass_id") or "").strip(),
            "capsule_id": str(capsule.get("capsule_id") or "").strip(),
            "tx_id": str(
                (case_doc.get("execution") if isinstance(case_doc.get("execution"), dict) else {}).get("tx_id") or ""
            ).strip(),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Solana proof-anchor payload from an AEP case.")
    parser.add_argument("--text", default="buy 1 USDC of SOL", help="Natural language AEP request to run.")
    parser.add_argument("--agent-id", default="demo-agent", help="Agent id for the AEP run.")
    parser.add_argument("--case-id", default="", help="Use an existing case id instead of running a new request.")
    parser.add_argument("--case-root", default=str(ROOT / "artifacts" / "cases"), help="AEP case storage directory.")
    parser.add_argument(
        "--out",
        default=str(ROOT / "artifacts" / "anchor" / "aep-anchor-payload.json"),
        help="Output payload JSON path.",
    )
    args = parser.parse_args()

    case_root = Path(args.case_root).expanduser()
    if not case_root.is_absolute():
        case_root = (ROOT / case_root).resolve()

    if args.case_id.strip():
        case_doc = load_case(args.case_id.strip(), case_root=case_root)
    else:
        summary = run_text(text=args.text, agent_id=args.agent_id, case_root=case_root)
        case_doc = load_case(str(summary["case_id"]), case_root=case_root)

    payload = build_anchor_payload(
        case_doc,
        accountability_log_path=case_root.parent / "accountability" / "events.jsonl",
    )
    out_path = Path(args.out).expanduser()
    if not out_path.is_absolute():
        out_path = (ROOT / out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "payload_path": str(out_path), **payload}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
