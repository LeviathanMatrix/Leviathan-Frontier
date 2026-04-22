from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .accountability import compute_json_digest


ROOT = Path(__file__).resolve().parent
DEFAULT_ISSUANCE_LEDGER_PATH = ROOT / "artifacts" / "aep_kernel" / "issuance" / "events.jsonl"
ISSUANCE_EVENT_SCHEMA_VERSION = "aep.issuance_event.v1"
ISSUANCE_EVENT_TYPES = {
    "requested",
    "evaluated",
    "issued",
    "denied",
    "bound",
    "revoked",
    "expired",
    "consumed",
    "reviewed",
    "finalized",
    "superseded",
}
GENESIS_HASH = "GENESIS"


def _now_ts() -> int:
    return int(time.time())


def _resolve_ledger_path(path_value: Any) -> Path:
    if path_value is None or (isinstance(path_value, str) and not path_value.strip()):
        path = DEFAULT_ISSUANCE_LEDGER_PATH
    else:
        path = Path(str(path_value)).expanduser()
        if not path.is_absolute():
            path = (ROOT / path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _safe_payload(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_status(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            doc = json.loads(line)
        except json.JSONDecodeError:
            rows.append({"_decode_error": True, "_raw": line})
            continue
        if isinstance(doc, dict):
            rows.append(doc)
    return rows


def _event_hash(prev_hash: str, body: dict[str, Any]) -> str:
    body_digest = compute_json_digest(body)
    return hashlib.sha256(f"{prev_hash}|{body_digest}".encode("utf-8")).hexdigest()


def record_issuance_event(
    *,
    issuance: dict[str, Any] | None,
    event_type: str,
    stage: str,
    case_id: str = "",
    payload: dict[str, Any] | None = None,
    ledger_path: Any = None,
    at_ts: int | None = None,
) -> dict[str, Any]:
    issuance_doc = issuance if isinstance(issuance, dict) else {}
    event_type_clean = str(event_type or "").strip().lower()
    if event_type_clean not in ISSUANCE_EVENT_TYPES:
        raise ValueError(f"unsupported issuance event_type: {event_type}")

    path = _resolve_ledger_path(ledger_path)
    existing = _read_events(path)
    prev_hash = GENESIS_HASH
    if existing:
        last = existing[-1]
        if isinstance(last, dict):
            prev_hash = str(last.get("event_hash") or "").strip() or GENESIS_HASH

    ts = int(max(0, int(at_ts if at_ts is not None else _now_ts())))
    issuance_id = str(issuance_doc.get("issuance_id") or "").strip() or None
    issuance_status = _safe_status(issuance_doc.get("status"))
    replay = issuance_doc.get("replay") if isinstance(issuance_doc.get("replay"), dict) else {}
    algorithm_version = str(replay.get("algorithm_version") or "").strip() or None
    base = {
        "schema_version": ISSUANCE_EVENT_SCHEMA_VERSION,
        "event_type": event_type_clean,
        "stage": str(stage or "").strip() or "unspecified",
        "event_ts": ts,
        "case_id": str(case_id or "").strip() or None,
        "issuance_id": issuance_id,
        "issuance_status": issuance_status,
        "algorithm_version": algorithm_version,
        "payload": _safe_payload(payload),
    }
    event_id = f"iss_evt_{compute_json_digest(base)[:20]}"
    body = {"event_id": event_id, "prev_hash": prev_hash, **base}
    body["event_hash"] = _event_hash(prev_hash, body)

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(body, ensure_ascii=True) + "\n")

    return {
        "event_id": event_id,
        "event_hash": body["event_hash"],
        "prev_hash": prev_hash,
        "ledger_path": str(path),
    }


def list_issuance_events(
    *,
    ledger_path: Any = None,
    issuance_id: str = "",
    case_id: str = "",
) -> list[dict[str, Any]]:
    path = _resolve_ledger_path(ledger_path)
    all_rows = _read_events(path)
    out: list[dict[str, Any]] = []
    issuance_filter = str(issuance_id or "").strip()
    case_filter = str(case_id or "").strip()
    for row in all_rows:
        if not isinstance(row, dict) or row.get("_decode_error"):
            continue
        if issuance_filter and str(row.get("issuance_id") or "").strip() != issuance_filter:
            continue
        if case_filter and str(row.get("case_id") or "").strip() != case_filter:
            continue
        out.append(row)
    return out


def get_issuance_latest_state(
    issuance_id: str,
    *,
    ledger_path: Any = None,
) -> dict[str, Any] | None:
    issuance_key = str(issuance_id or "").strip()
    if not issuance_key:
        raise ValueError("issuance_id is required")
    events = list_issuance_events(ledger_path=ledger_path, issuance_id=issuance_key)
    if not events:
        return None
    return events[-1]


def verify_issuance_chain(
    *,
    ledger_path: Any = None,
) -> dict[str, Any]:
    path = _resolve_ledger_path(ledger_path)
    rows = _read_events(path)
    issues: list[str] = []
    expected_prev = GENESIS_HASH
    last_hash = GENESIS_HASH
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or row.get("_decode_error"):
            issues.append(f"row {idx}: invalid json row")
            continue
        row_prev = str(row.get("prev_hash") or "").strip() or GENESIS_HASH
        if row_prev != expected_prev:
            issues.append(
                f"row {idx}: prev_hash mismatch (expected {expected_prev}, got {row_prev})"
            )
        expected_hash = _event_hash(row_prev, {k: v for k, v in row.items() if k != "event_hash"})
        actual_hash = str(row.get("event_hash") or "").strip()
        if expected_hash != actual_hash:
            issues.append(f"row {idx}: event_hash mismatch")
        expected_prev = actual_hash or expected_prev
        last_hash = actual_hash or last_hash
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "count": len(rows),
        "last_event_hash": last_hash,
        "ledger_path": str(path),
    }
