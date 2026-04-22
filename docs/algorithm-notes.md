# Algorithm Notes

This document summarizes the deterministic algorithms inside LeviathanMatrix AEP Open Core.

## 1. Intake Normalization

The intake layer accepts natural language or structured JSON and compiles it into an action request.

The compiler extracts:

- action kind
- source asset
- destination asset
- notional value
- chain
- network
- venue
- slippage
- agent identity
- delegation claim

The output is stable enough to feed into policy, issuance, capsule creation, execution, and review.

## 2. Hard Constraint Evaluation

The constitution contains hard constraints.

Hard constraints are not advisory. If they fail, execution is denied.

Examples:

```text
chain not allowed
program not allowed
notional too large
daily limit exceeded
slippage too high
counterparty score too low
bridge exposure too high
leverage too high
simulation missing
```

The evaluator returns explicit reason codes so agent runtimes can explain the rejection without guessing.

## 3. Structural Risk Score

AEP accepts a structured risk input with eight risk axes:

```text
r1_control
r2_funding
r3_convergence
r4_terminal
r5_history
r6_lp_behavior
r7_anomaly
x_cross_signal
```

The structural risk model is:

```text
base =
  0.18 * r1_control
+ 0.17 * r2_funding
+ 0.12 * r3_convergence
+ 0.10 * r4_terminal
+ 0.10 * r5_history
+ 0.13 * r6_lp_behavior
+ 0.10 * r7_anomaly
+ 0.10 * x_cross_signal
```

Token-level risk is either supplied as a weighted score or derived:

```text
token_penalty =
  0.40 * permission
+ 0.35 * rug
+ 0.25 * history
+ consistency_adjustment
```

Final structural score:

```text
structural_risk = clamp(0.80 * base + 0.20 * token_penalty)
```

## 4. Contextual Policy Score

The policy score adds execution context:

```text
raw =
  0.30 * structural_risk
+ 0.15 * counterparty_risk
+ 0.15 * execution_complexity_risk
+ 0.10 * market_risk
+ 0.10 * anomaly_risk
+ 0.10 * evidence_gap_risk
+ 0.10 * governance_surface_risk
```

Reputation and treasury strength can reduce risk, but only up to 80 percent of raw risk:

```text
bonus =
  0.10 * agent_reputation_bonus
+ 0.10 * treasury_health_bonus

effective_bonus = min(bonus, raw * 0.80)
risk_score = clamp(raw - effective_bonus)
```

This avoids the classic bug where a reputation bonus incorrectly turns an uncertain action into zero risk.

## 5. Advisory Floor

Advisory decisions impose a floor:

```text
ALLOW  -> allow_floor_score
REVIEW -> review_floor_score
BLOCK  -> block_floor_score
```

This means a review or block signal cannot be erased by a low raw number.

## 6. Decision Bands

Risk bands map into policy outcomes:

```text
risk < allow_light_max     -> ALLOW_WITH_LIGHT_BOND
risk < allow_standard_max  -> ALLOW_WITH_STANDARD_BOND
risk < allow_heavy_max     -> ALLOW_WITH_HEAVY_BOND
otherwise                  -> DENY
```

The heavy-bond band is intentionally not treated as an ordinary execution pass. It creates a stricter posture.

## 7. Capability Hash

The capability hash is the core execution-binding primitive.

It hashes:

- case id
- request id
- agent id
- action kind
- action payload
- execution scope
- policy final decision
- policy reason codes
- delegation principal
- delegation delegate
- delegation role
- delegation grant id

Pseudocode:

```text
capability_hash = sha256(canonical_json(capability_tuple))
```

If any meaningful action or authority field changes, the hash changes.

## 8. Capsule Pressure

Capital Capsule pressure is computed independently from policy decision:

```text
pressure =
  risk_weight * open_risk_score
+ volatility_weight * volatility_proxy * 100
+ mode_penalty
+ review_penalty
```

Default profile:

```text
risk_weight = 0.50
volatility_weight = 0.20
mode_penalty: paper=0, devnet=10, mainnet=18
review_penalty: standard=8, enhanced=15, strict=20
```

Pressure drives:

- mode restriction
- review intensity
- revocation sensitivity
- advisory limit multiplier
- advisory TTL multiplier

## 9. Capsule Validation

Before execution, AEP validates:

```text
capsule status is active
capsule is not expired
requested notional > 0
requested notional <= remaining notional
```

If any check fails, execution is blocked.

## 10. Accountability Hash Chain

AEP records local lifecycle events into a hash chain:

```text
event_hash = sha256(prev_hash + canonical_json(event_body))
```

This creates a simple replayable integrity trail for local action history.

It is intentionally minimal and dependency-free.
