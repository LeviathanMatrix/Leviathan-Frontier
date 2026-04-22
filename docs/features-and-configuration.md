# Features And Configuration

This guide explains what AEP Open Core does, how to use each feature, and how to tune the policy thresholds.

## Feature Summary

| Feature | What It Does | Main File |
|---|---|---|
| Intake Compiler | Converts natural language or structured requests into canonical action requests | `aep/intake.py` |
| Constitution Policy Engine | Applies hard constraints and risk decision bands | `policy_engine/engine.py` |
| Delegation Grant Resolver | Resolves principal/delegate/role authority from grant fixtures | `aep/delegation.py` |
| Execution Pass | Issues a scoped, expiring capability object before execution | `aep/issuance.py` |
| Capability Hash | Binds pass to action payload, policy result, scope, and delegation identity | `aep/issuance.py` |
| Capital Capsule | Wraps capital authority into finite notional and time bounds | `aep/capsule.py` |
| Capsule Pressure | Computes envelope pressure from risk, volatility, mode, and review intensity | `aep/capsule_pricing.py` |
| Execution Guard | Revalidates pass and capsule before execution | `aep/kernel.py` |
| Receipt + Review | Produces execution receipt and counterfactual review | `aep/execution.py`, `aep/review.py` |
| Accountability Hash Chain | Records local lifecycle events with hash chaining | `aep/accountability.py` |
| Claim Export | Produces a shareable execution claim | `aep/kernel.py` |

## 1. Intake Compiler

Use:

```bash
python scripts/aep_cli.py authorize-text \
  --text "buy 1 USDC of SOL" \
  --agent-id demo-agent
```

The intake layer extracts:

- action kind
- source asset
- destination asset
- notional value
- chain
- network
- venue
- slippage
- agent identity
- optional delegation claim

Why it exists:

```text
Agents speak in messy requests.
Execution policy needs canonical objects.
```

## 2. Constitution Policy Engine

Main config:

```text
fixtures/constitution.paper_trade.v1.json
```

The constitution controls:

```json
{
  "hard_constraints": {
    "allowed_chains": ["solana"],
    "max_notional_per_tx_usd": 500,
    "max_daily_notional_usd": 10000,
    "max_slippage_bps": 150,
    "max_bridge_exposure_usd": 500,
    "max_leverage": 1,
    "require_counterparty_score_min": 55,
    "simulation_required": true
  }
}
```

### Change Max Trade Size

Edit:

```json
"max_notional_per_tx_usd": 500
```

Example:

```json
"max_notional_per_tx_usd": 50
```

Now a 100 USDC request should be denied.

Test:

```bash
python scripts/aep_cli.py run-text \
  --text "buy 100 USDC of SOL" \
  --agent-id demo-agent
```

### Restrict Chains

Edit:

```json
"allowed_chains": ["solana"]
```

AEP is chain-aware, and Solana is the default first environment for this open-core demo.

### Restrict Programs

Edit:

```json
"allowed_programs": [
  "paper.virtual.exchange",
  "paper.virtual.payment",
  "paper.virtual.approve",
  "paper.virtual.contract_call",
  "paper.virtual.bridge"
]
```

This defines which execution surfaces are valid.

## 3. Risk Thresholds

Main config:

```json
"decision_thresholds": {
  "allow_light_max": 35,
  "allow_standard_max": 65,
  "allow_heavy_max": 84.99,
  "deny_min": 85
}
```

Meaning:

```text
risk < 35       -> ALLOW_WITH_LIGHT_BOND
risk < 65       -> ALLOW_WITH_STANDARD_BOND
risk < 84.99    -> ALLOW_WITH_HEAVY_BOND
risk >= 85      -> DENY
```

### Make AEP Stricter

Lower the bands:

```json
"decision_thresholds": {
  "allow_light_max": 25,
  "allow_standard_max": 50,
  "allow_heavy_max": 70,
  "deny_min": 70
}
```

### Make AEP More Permissive

Raise the bands:

```json
"decision_thresholds": {
  "allow_light_max": 45,
  "allow_standard_max": 75,
  "allow_heavy_max": 90,
  "deny_min": 90
}
```

## 4. Advisory Floors

Main config:

```json
"advisory_mapping": {
  "allow_floor_score": 0,
  "review_floor_score": 50,
  "block_floor_score": 85
}
```

Meaning:

- `ALLOW` does not raise the score
- `REVIEW` forces at least 50
- `BLOCK` forces at least 85

Why it matters:

```text
A single categorical block signal should not disappear inside a weighted average.
```

## 5. Execution Pass TTL

Main config:

```json
"issuance": {
  "max_ttl_seconds": 3600,
  "default_ttl_seconds": 900
}
```

Meaning:

- default pass lifetime: 15 minutes
- max pass lifetime: 1 hour

Make passes shorter:

```json
"default_ttl_seconds": 120
```

Now execution must happen closer to authorization.

## 6. Delegation Grants

Main config:

```text
fixtures/delegation_grants.v1.json
```

A delegation grant defines:

- principal
- delegate
- role
- allowed actions
- asset scope
- program scope
- per-transaction notional limit
- daily notional limit
- validity window

Example:

```json
{
  "principal_id": "principal:fund-alpha",
  "delegate_id": "aep:solana:agent-alpha",
  "role": "trader_agent",
  "allowed_actions": ["trade", "payment", "approve", "bridge", "contract_call"],
  "asset_scope_mode": "all",
  "notional_limits": {
    "per_tx_usd": 10.0,
    "daily_usd": 1000.0
  }
}
```

Why it matters:

```text
The agent is not just allowed or denied.
It acts under a principal, role, scope, cap, and time window.
```

## 7. Asset Registry

Main config:

```text
fixtures/paper_asset_registry.v1.json
```

The registry controls:

- aliases
- identifiers
- decimals
- paper price
- slippage assumption
- paper depth
- open risk profile

Example:

```json
{
  "symbol": "SOL",
  "aliases": ["sol", "wsol", "wrapped sol"],
  "price_usd": 145.0,
  "expected_slippage_bps": 18,
  "paper_depth_usd": 300000
}
```

Add a new paper asset by adding another object to `assets`.

## 8. Capital Capsule Pressure

Main file:

```text
aep/capsule_pricing.py
```

Formula:

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

Pressure affects:

- mode restriction
- review intensity
- revocation sensitivity
- advisory limit multiplier
- advisory TTL multiplier

## 9. Execution Claim Export

After a case runs:

```bash
python scripts/aep_cli.py export-claim \
  --case-id <case_id>
```

The claim includes:

- producer metadata
- case id
- request id
- agent id
- authorization status
- issuance id
- pass id
- capsule id
- execution status
- receipt status
- review status

This is the portable output a downstream system can inspect.

## 10. Recommended Tuning Profiles

### Demo Profile

Use when showing the happy path:

```json
"max_notional_per_tx_usd": 500,
"allow_light_max": 35,
"allow_standard_max": 65,
"deny_min": 85
```

### Strict Profile

Use when showing institutional controls:

```json
"max_notional_per_tx_usd": 50,
"max_slippage_bps": 50,
"allow_light_max": 25,
"allow_standard_max": 50,
"deny_min": 70,
"default_ttl_seconds": 120
```

### Long-Tail Solana Profile

Use when demonstrating unknown or volatile assets:

```json
"enforce_asset_lists": false,
"max_notional_per_tx_usd": 10,
"max_slippage_bps": 100,
"default_ttl_seconds": 180
```

This keeps long-tail support while reducing capital exposure.

## 11. Validation Checklist

After changing thresholds:

```bash
pytest -q -p no:cacheprovider
```

Then run:

```bash
python scripts/aep_cli.py run-text \
  --text "buy 1 USDC of SOL" \
  --agent-id demo-agent
```

And denial test:

```bash
python scripts/aep_cli.py run-text \
  --text "buy 1000000 USDC of SOL" \
  --agent-id demo-agent
```

If the first succeeds and the second fails, the core control path is intact.
