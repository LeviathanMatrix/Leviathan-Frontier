# Security Model

LeviathanMatrix AEP Open Core follows a fail-closed security model.

## Boundary Principle

The agent can request an action. AEP controls whether that action becomes executable.

This creates a boundary between:

```text
agent reasoning
```

and:

```text
capital authority
```

## Trust Model

AEP does not require trust in the agent's text.

It trusts structured objects and deterministic checks:

- compiled action request
- constitution
- risk input
- policy output
- Execution Pass
- Capital Capsule
- receipt
- review
- accountability hash chain

## Core Invariants

### 1. No pass, no execution

Execution requires an issued or bound Execution Pass.

### 2. No matching capability hash, no execution

The pass is bound to a capability hash. If the action scope changes, the hash check fails.

### 3. No capsule, no capital movement

Capital movement requires an active Capital Capsule.

### 4. No remaining notional, no execution

The capsule tracks consumed and remaining notional.

### 5. Expired authority cannot execute

Passes and capsules both carry time windows.

### 6. Denied authorization cannot be revived by review

Review can inspect outcomes. It cannot convert a denied action into an executed action.

## Common Failure Modes

| Failure | Result |
|---|---|
| bad intake | request rejected |
| hard policy violation | authorization denied |
| expired pass | execution blocked |
| changed action payload | capability mismatch |
| expired capsule | execution blocked |
| notional exceeds remaining capsule | execution blocked |
| invalid receipt | review failed |

## Why This Matters

In agent systems, the dangerous path is silent authority drift:

```text
authorized action A
executed action B
reported action C
```

AEP prevents that by forcing execution to stay attached to the authorized object graph:

```text
action request -> pass -> capsule -> execution -> receipt -> review
```

If the graph does not line up, the system stops.
