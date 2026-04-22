from __future__ import annotations

import json
import urllib.request
from typing import Any

from aep.kernel import authorize_action, execute_case, export_execution_claim, review_case


def submit_claim_to_verifier_api(
    *, verifier_api_url: str, verifier_api_key: str, claim: dict[str, Any]
) -> dict[str, Any]:
    payload = json.dumps(claim, ensure_ascii=True).encode("utf-8")
    request = urllib.request.Request(
        verifier_api_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {verifier_api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read().decode("utf-8")
    decoded = json.loads(body)
    if not isinstance(decoded, dict):
        raise ValueError("verifier api response must be a JSON object")
    return decoded


def main() -> None:
    # Demo only: no external verifier credentials are shipped in open core.
    case_doc = authorize_action(text="buy 1 USDC of SOL", agent_id="demo-agent")
    case_doc = execute_case(case_doc)
    case_doc = review_case(case_doc)
    claim = export_execution_claim(case_doc)
    print(json.dumps(claim, ensure_ascii=True, indent=2))
    print("Set VERIFIER_API_URL and VERIFIER_API_KEY, then call submit_claim_to_verifier_api(...).")


if __name__ == "__main__":
    main()
