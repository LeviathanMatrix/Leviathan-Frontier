# OpenClaw Demo (AEP Open Core)

This demo runs a full open-core path:

1. intake from plain text
2. risk input build
3. policy decision
4. issuance + capsule authorization
5. execution + receipt
6. review

## Command

```bash
python3 scripts/aep_cli.py run-text \
  --text "buy 1 USDC of SOL" \
  --agent-id demo-agent
```

Expected fields in output:

- `ok`
- `case_id`
- `authorization.status`
- `execution.status`
- `receipt.status`
- `review.status`
