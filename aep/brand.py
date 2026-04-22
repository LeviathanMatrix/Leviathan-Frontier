from __future__ import annotations

from typing import Any

COMPANY_NAME = "LeviathanMatrix"
PRODUCT_NAME = "AEP"
PROJECT_NAME = "LeviathanMatrix AEP Open Core"
PROJECT_VERSION = "0.1.0"
SPEC_ID = "leviathanmatrix.aep.open-core.v1"
IMPLEMENTATION_ID = "leviathanmatrix-aep-open-core"
TRADEMARK_NOTICE = "AEP Open Core is produced by LeviathanMatrix."


def producer_metadata(component: str = "core") -> dict[str, Any]:
    return {
        "company": COMPANY_NAME,
        "product": PRODUCT_NAME,
        "project": PROJECT_NAME,
        "component": str(component or "core").strip() or "core",
        "version": PROJECT_VERSION,
        "spec_id": SPEC_ID,
        "implementation": IMPLEMENTATION_ID,
    }
