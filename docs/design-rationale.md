# Design Rationale

This document explains why LeviathanMatrix AEP Open Core uses this architecture and these algorithms.

## Thesis

Agent execution is not a wallet problem. It is a control-plane problem.

Wallets answer:

```text
Can this key sign?
```

AEP answers:

```text
Should this agent action become executable under policy, scope, capital limits, and review requirements?
```

That is why the system is built as an execution kernel instead of a wallet plugin or dashboard.

## Why A Deterministic Kernel

Agent systems are probabilistic. Capital controls should not be.

AEP deliberately uses deterministic components:

- JSON schemas
- rule-based constitution checks
- weighted risk aggregation
- fixed decision bands
- capability hashes
- stateful capsule validation
- replayable event hashes

The reason is operational:

```text
When an agent is wrong, you need deterministic reconstruction.
```

If the execution boundary is another probabilistic layer, the system becomes hard to audit and hard to debug.

## Why A Constitution

The constitution is the policy root.

It externalizes execution policy into a document instead of hiding it inside prompts or code paths.

This makes policy:

- inspectable
- portable
- versionable
- testable
- runtime-independent

An agent built in one framework and an agent built in another framework can both route through the same constitution.

## Why Execution Pass

A normal approval is too broad.

An Execution Pass is a capability object. It says:

```text
this exact agent
for this exact request
under this exact policy result
inside this exact scope
until this exact expiry
```

The pass is not merely a yes. It is a scoped, expiring permission object.

This is a capability-based security model adapted for agent execution.

## Why Capability Hash

Authorization and execution are not the same moment.

An agent could be authorized for one action and later attempt a different action.

The capability hash prevents that by binding the pass to the canonical action and authority tuple.

If the tuple changes, validation fails:

```text
authorized action != attempted action
=> capability hash mismatch
=> execution blocked
```

This closes the classic gap:

```text
approved A, executed B
```

## Why Capital Capsule

Agents should not receive open-ended capital authority.

The Capital Capsule converts broad capital access into a finite envelope:

- max notional
- remaining notional
- valid time window
- execution mode
- bound pass id
- lifecycle status

The model is intentionally stateful because capital authority changes as execution happens.

After consumption, the remaining notional shrinks.

After expiry, authority disappears.

After revocation, execution stops.

## Why Capsule Pressure

Policy decision and capital shape are related but not identical.

A decision may allow an action, but still require a tighter capital envelope.

Capsule pressure gives AEP a second control dimension:

```text
policy decision = can this action proceed?
capsule pressure = how tightly should capital authority be wrapped?
```

The pressure model combines:

- open risk score
- volatility proxy
- execution mode penalty
- review intensity penalty

This makes the envelope adaptive without making the system opaque.

## Why Weighted Risk Instead Of A Black Box

AEP uses a transparent weighted model because open-source execution policy needs to be explainable.

The system favors:

- stable scores
- visible weights
- reason codes
- reproducible decisions
- simple tuning

over a model that is impressive but impossible to inspect.

For hackathon and infrastructure evaluation, this is a feature.

The goal is not to hide judgment inside a model.

The goal is to make execution control legible.

## Why Advisory Floors

A numeric risk score can understate a categorical warning.

Advisory floors solve that.

If an upstream system says `REVIEW`, AEP forces the risk score to at least the review floor.

If an upstream system says `BLOCK`, AEP forces the risk score to at least the block floor.

This prevents a low weighted average from erasing a critical signal.

## Why Fail-Closed

Agent systems fail in strange ways:

- missing fields
- malformed requests
- stale authority
- changed payloads
- expired approvals
- over-consumption
- inconsistent receipts

AEP treats ambiguity as non-executable.

That is the correct default for capital actions.

```text
uncertain state -> no execution
```

## Why Solana First

Solana is the strongest first environment for this architecture because agent execution needs:

- low marginal transaction cost
- high-throughput workflows
- fast confirmation
- composable program calls
- machine-native payment experiments
- a developer ecosystem already exploring autonomous finance

On a slow or expensive chain, weak execution control is hidden by friction.

On Solana, speed removes that friction.

That makes the missing control layer obvious.

```text
Solana makes high-speed agent capital realistic.
AEP makes high-speed agent capital controllable.
```

## Why Open Source AEP

The purpose of open-sourcing AEP is to make agent execution control legible and composable.

Developers should be able to see:

- how a request becomes an intent
- how an intent is evaluated
- how an execution pass is issued
- how capital is bounded
- how execution is blocked
- how review is produced

This turns AEP into a public execution-control primitive rather than a black-box demo.

## Final Design Position

AEP is not a trading bot.

AEP is not a wallet.

AEP is not a dashboard.

AEP is a policy-bound execution kernel for agents that may touch capital.

That is the technical wedge.
