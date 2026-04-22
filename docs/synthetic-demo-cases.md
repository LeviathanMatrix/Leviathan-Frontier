# Synthetic Demo Cases

These cases are **synthetic demonstration data**.

They are not real user activity, not real trading performance, and not evidence
of live production usage. They exist to help judges and developers understand
how AEP objects look across allow, deny, and review-heavy execution paths.

## Case A: Low-Risk Solana Paper Trade

Use this as the happy-path demo.

```json
{
  "demo_label": "synthetic_low_risk_sol_trade",
  "request": "buy 1 USDC of SOL",
  "agent_id": "demo-agent",
  "chain": "solana",
  "network": "paper",
  "policy_result": {
    "hard_constraints_passed": true,
    "risk_score_post_advisory": 14.72,
    "final_decision": "ALLOW_WITH_LIGHT_BOND",
    "reason_codes": []
  },
  "execution_pass": {
    "status": "ISSUED",
    "ttl_seconds": 900,
    "capability_hash_behavior": "stable unless action, scope, policy, or delegation changes"
  },
  "capital_capsule": {
    "status": "ARMED",
    "max_notional_usd": 1.0,
    "remaining_notional_usd_before_execution": 1.0,
    "remaining_notional_usd_after_execution": 0.0,
    "capsule_pressure": 23.4,
    "mode_restriction": "paper_devnet"
  },
  "execution": {
    "status": "EXECUTED",
    "receipt_status": "EXECUTED",
    "review_status": "PASSED"
  },
  "what_it_proves": [
    "AEP can turn a simple agent request into a full governed lifecycle",
    "Execution does not happen until pass and capsule validation succeed",
    "The final claim is portable and branded with LeviathanMatrix AEP metadata"
  ]
}
```

## Case B: Notional Limit Denial

Use this to show fail-closed controls.

```json
{
  "demo_label": "synthetic_notional_limit_denial",
  "request": "buy 1000000 USDC of SOL",
  "agent_id": "demo-agent",
  "chain": "solana",
  "network": "paper",
  "policy_result": {
    "hard_constraints_passed": false,
    "risk_score_post_advisory": 15.0,
    "final_decision": "DENY",
    "reason_codes": ["HC_NOTIONAL_EXCEEDED"]
  },
  "execution_pass": {
    "status": "DENIED",
    "ttl_seconds": 60
  },
  "capital_capsule": {
    "status": "NOT_ISSUED",
    "max_notional_usd": 0.0
  },
  "execution": {
    "status": "BLOCKED",
    "receipt_status": "",
    "review_status": "FAILED"
  },
  "what_it_proves": [
    "A low risk score cannot override a hard constitution constraint",
    "No Capital Capsule is issued for denied actions",
    "AEP blocks execution before any value-moving adapter is called"
  ]
}
```

## Case C: Review-Heavy Volatile Asset

Use this to show that AEP is not just yes/no. It can shape capital authority.

```json
{
  "demo_label": "synthetic_review_heavy_volatile_asset",
  "request": "buy 5 USDC of HELP",
  "agent_id": "demo-agent",
  "chain": "solana",
  "network": "paper",
  "policy_result": {
    "hard_constraints_passed": true,
    "risk_score_post_advisory": 72.8,
    "final_decision": "ALLOW_WITH_HEAVY_BOND",
    "reason_codes": ["RISK_SCORE_HEAVY_BOND"]
  },
  "execution_pass": {
    "status": "DENIED",
    "decision": "NEEDS_REVIEW",
    "capability_hash_behavior": "action is not executable as a normal pass"
  },
  "capital_capsule": {
    "status": "NOT_ISSUED",
    "capsule_pressure": 82.5,
    "mode_restriction": "paper_only",
    "review_intensity": "strict",
    "revocation_sensitivity": "high"
  },
  "execution": {
    "status": "BLOCKED",
    "review_status": "FAILED"
  },
  "what_it_proves": [
    "AEP can distinguish allowed, denied, and review-heavy execution posture",
    "High pressure does not silently become ordinary execution authority",
    "Capital Capsules are shaped by risk, mode, uncertainty, and review intensity"
  ]
}
```

## Which One To Use In The Demo

Recommended flow:

1. Start with Case A to show the clean lifecycle.
2. Then show Case B to prove fail-closed behavior.
3. Use Case C only if the audience asks whether AEP is more than a binary gate.

The strongest line:

```text
The demo is not that an agent can trade.
The demo is that an agent cannot trade unless the action becomes policy-bound,
capability-bound, notional-bound, and reviewable.
```
