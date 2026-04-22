from pathlib import Path

from aep.accountability import (
    load_accountability_events,
    record_accountability_event,
    replay_accountability_chain,
)


def test_accountability_chain_replay_ok(tmp_path: Path) -> None:
    log_path = tmp_path / "events.jsonl"
    record_accountability_event(stage="authorization", payload={"a": 1}, log_path=log_path)
    record_accountability_event(stage="execution", payload={"b": 2}, log_path=log_path)
    replay = replay_accountability_chain(log_path)
    assert replay["ok"] is True
    assert replay["count"] == 2


def test_accountability_chain_tamper_detected(tmp_path: Path) -> None:
    log_path = tmp_path / "events.jsonl"
    record_accountability_event(stage="authorization", payload={"a": 1}, log_path=log_path)
    rows = load_accountability_events(log_path)
    rows[0]["payload"]["a"] = 999
    log_path.write_text("\n".join(__import__("json").dumps(row, ensure_ascii=True) for row in rows) + "\n", encoding="utf-8")
    replay = replay_accountability_chain(log_path)
    assert replay["ok"] is False
    assert replay["issues"]
