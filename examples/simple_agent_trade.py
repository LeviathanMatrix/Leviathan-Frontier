from __future__ import annotations

import json

from aep.kernel import run_text


def main() -> None:
    result = run_text(
        text="buy 1 USDC of SOL",
        agent_id="demo-agent",
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
