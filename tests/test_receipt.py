from aep.receipt import ACCOUNTING_RECEIPT_STATUSES, INGEST_ALLOWED_RECEIPT_STATUSES


def test_accounting_statuses_subset_of_ingest_allowed() -> None:
    assert ACCOUNTING_RECEIPT_STATUSES.issubset(INGEST_ALLOWED_RECEIPT_STATUSES)


def test_ingest_allowed_contains_core_statuses() -> None:
    assert {"PENDING", "EXECUTED", "FAILED"}.issubset(INGEST_ALLOWED_RECEIPT_STATUSES)
