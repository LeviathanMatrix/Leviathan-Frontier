from __future__ import annotations

# Receipt statuses that should count toward daily budget accounting.
ACCOUNTING_RECEIPT_STATUSES = frozenset({"EXECUTED", "CONFIRMED", "FINALIZED"})

# Receipt statuses accepted by ingest_trade_receipt.
INGEST_ALLOWED_RECEIPT_STATUSES = frozenset(
    {"PENDING", "EXECUTED", "FAILED", "CONFIRMED", "FINALIZED"}
)
