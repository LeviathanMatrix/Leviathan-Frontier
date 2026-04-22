from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_ACCOUNTABILITY_LOG_PATH = Path("artifacts") / "accountability" / "events.jsonl"
GENESIS_HASH = "GENESIS"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


def canonical_json(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def compute_json_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def resolve_accountability_log_path(log_path: str | Path | None = None) -> Path:
    path = Path(log_path) if log_path is not None else DEFAULT_ACCOUNTABILITY_LOG_PATH
    path = path.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_last_hash(log_path: Path) -> str:
    if not log_path.exists() or log_path.stat().st_size == 0:
        return GENESIS_HASH
    lines = [line.strip() for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return GENESIS_HASH
    try:
        last = json.loads(lines[-1])
    except json.JSONDecodeError:
        return GENESIS_HASH
    return str(last.get("event_hash") or "").strip() or GENESIS_HASH


def record_accountability_event(
    *,
    stage: str,
    payload: Mapping[str, Any],
    log_path: str | Path | None = None,
) -> dict[str, Any]:
    path = resolve_accountability_log_path(log_path)
    prev_hash = _read_last_hash(path)
    body = {
        "timestamp": _utc_now_iso(),
        "stage": str(stage or "").strip() or "unspecified",
        "payload": _json_safe(payload),
    }
    body_digest = compute_json_digest(body)
    event_hash = hashlib.sha256(f"{prev_hash}|{body_digest}".encode("utf-8")).hexdigest()
    row = {
        "event_id": f"evt_{event_hash[:16]}",
        "prev_hash": prev_hash,
        "event_hash": event_hash,
        **body,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=True) + "\n")
    return {
        "event_id": row["event_id"],
        "event_hash": event_hash,
        "prev_hash": prev_hash,
        "log_path": str(path),
    }


def load_accountability_events(log_path: str | Path | None = None) -> list[dict[str, Any]]:
    path = resolve_accountability_log_path(log_path)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def replay_accountability_chain(log_path: str | Path | None = None) -> dict[str, Any]:
    rows = load_accountability_events(log_path)
    issues: list[str] = []
    expected_prev = GENESIS_HASH
    head_hash = GENESIS_HASH
    for idx, row in enumerate(rows, start=1):
        prev_hash = str(row.get("prev_hash") or "").strip() or GENESIS_HASH
        if prev_hash != expected_prev:
            issues.append(
                f"row {idx}: prev_hash mismatch (expected {expected_prev}, got {prev_hash})"
            )
        body = {
            "timestamp": row.get("timestamp"),
            "stage": row.get("stage"),
            "payload": row.get("payload"),
        }
        body_digest = compute_json_digest(body)
        expected_hash = hashlib.sha256(f"{prev_hash}|{body_digest}".encode("utf-8")).hexdigest()
        actual_hash = str(row.get("event_hash") or "").strip()
        if expected_hash != actual_hash:
            issues.append(f"row {idx}: event_hash mismatch")
        expected_prev = actual_hash or expected_prev
        head_hash = actual_hash or head_hash
    return {
        "ok": len(issues) == 0,
        "count": len(rows),
        "head_event_hash": head_hash,
        "issues": issues,
    }
