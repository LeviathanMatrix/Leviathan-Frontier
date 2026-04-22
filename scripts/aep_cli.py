from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aep.kernel import (
    authorize_action,
    execute_case,
    export_execution_claim,
    load_case,
    review_case,
    run_text,
    simulate_case,
)
from aep.issuance import validate_issuance_for_execution
from aep.capsule import extract_requested_notional_usd, validate_capsule_for_execution


def _load_json(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must decode to a JSON object")
    return payload


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=True, indent=2))


def cmd_authorize_text(args: argparse.Namespace) -> None:
    case_doc = authorize_action(
        text=args.text,
        agent_id=args.agent_id,
        authority_pubkey=args.authority_pubkey,
        runtime_type=args.runtime_type,
        framework=args.framework,
        session_id=args.session_id,
        case_root=args.case_root,
    )
    authorization = case_doc.get("authorization") if isinstance(case_doc.get("authorization"), dict) else {}
    issuance = authorization.get("issuance") if isinstance(authorization.get("issuance"), dict) else {}
    capsule = authorization.get("decision", {}).get("capital_capsule") if isinstance(authorization.get("decision"), dict) else {}
    _print(
        {
            "ok": str(authorization.get("status") or "").upper() == "AUTHORIZED",
            "case_id": case_doc.get("case_id"),
            "authorization": {
                "status": authorization.get("status"),
                "issuance_id": issuance.get("issuance_id"),
                "capsule_id": capsule.get("capsule_id") if isinstance(capsule, dict) else None,
            },
        }
    )


def cmd_run_text(args: argparse.Namespace) -> None:
    result = run_text(
        text=args.text,
        agent_id=args.agent_id,
        authority_pubkey=args.authority_pubkey,
        runtime_type=args.runtime_type,
        framework=args.framework,
        session_id=args.session_id,
        case_root=args.case_root,
    )
    _print(result)


def _load_case_for_cmd(args: argparse.Namespace) -> dict[str, Any]:
    if args.case_path:
        return _load_json(args.case_path)
    if args.case_id:
        return load_case(args.case_id, case_root=args.case_root)
    raise ValueError("case_id or case_path is required")


def cmd_execute_case(args: argparse.Namespace) -> None:
    case_doc = _load_case_for_cmd(args)
    updated = execute_case(case_doc, case_root=args.case_root)
    _print(updated)


def cmd_simulate_case(args: argparse.Namespace) -> None:
    case_doc = _load_case_for_cmd(args)
    updated = simulate_case(case_doc, case_root=args.case_root)
    _print(updated)


def cmd_review_case(args: argparse.Namespace) -> None:
    case_doc = _load_case_for_cmd(args)
    updated = review_case(case_doc, case_root=args.case_root)
    _print(updated)


def cmd_export_claim(args: argparse.Namespace) -> None:
    case_doc = _load_case_for_cmd(args)
    claim = export_execution_claim(case_doc)
    _print(claim)


def cmd_verify_pass(args: argparse.Namespace) -> None:
    case_doc = _load_case_for_cmd(args)
    authorization = case_doc.get("authorization") if isinstance(case_doc.get("authorization"), dict) else {}
    issuance = authorization.get("issuance") if isinstance(authorization.get("issuance"), dict) else {}
    result = validate_issuance_for_execution(issuance)
    _print(result)


def cmd_verify_capsule(args: argparse.Namespace) -> None:
    case_doc = _load_case_for_cmd(args)
    authorization = case_doc.get("authorization") if isinstance(case_doc.get("authorization"), dict) else {}
    decision = authorization.get("decision") if isinstance(authorization.get("decision"), dict) else {}
    capsule = decision.get("capital_capsule") if isinstance(decision.get("capital_capsule"), dict) else {}
    request = case_doc.get("request") if isinstance(case_doc.get("request"), dict) else {}
    notional = extract_requested_notional_usd(request)
    result = validate_capsule_for_execution(capsule, requested_notional_usd=notional)
    _print(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AEP Open Core CLI")
    parser.add_argument("--case-root", default=None, help="Directory for persisted cases")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("authorize-text")
    p.add_argument("--text", required=True)
    p.add_argument("--agent-id", required=True)
    p.add_argument("--authority-pubkey", default="")
    p.add_argument("--runtime-type", default="generic-agent")
    p.add_argument("--framework", default="")
    p.add_argument("--session-id", default="")
    p.set_defaults(func=cmd_authorize_text)

    p = sub.add_parser("run-text")
    p.add_argument("--text", required=True)
    p.add_argument("--agent-id", required=True)
    p.add_argument("--authority-pubkey", default="")
    p.add_argument("--runtime-type", default="generic-agent")
    p.add_argument("--framework", default="")
    p.add_argument("--session-id", default="")
    p.set_defaults(func=cmd_run_text)

    for name, fn in (
        ("execute-case", cmd_execute_case),
        ("simulate-case", cmd_simulate_case),
        ("review-case", cmd_review_case),
        ("export-claim", cmd_export_claim),
        ("verify-pass", cmd_verify_pass),
        ("verify-capsule", cmd_verify_capsule),
    ):
        p = sub.add_parser(name)
        p.add_argument("--case-id", default="")
        p.add_argument("--case-path", default="")
        p.set_defaults(func=fn)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
