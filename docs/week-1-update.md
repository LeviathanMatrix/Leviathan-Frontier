# Week 1 Update

Week 1 pushed AEP materially closer to a real execution governance kernel.

The core change is not cosmetic schema growth. The system moved from a simpler execution gateway toward a model that can express **who** is acting, **on whose behalf**, **under what role**, and **within what exact boundaries**.

## Core Progress

### 1. Delegated execution model is now part of the main path

Execution is no longer modeled as a flat “agent may act” decision.

The system now carries delegation state directly in the action lifecycle:

- `principal`
- `delegate`
- `role`
- `allowed_actions`
- `asset_scope`
- `program_scope`
- `per_tx_cap`
- `daily_cap`
- `valid_from`
- `valid_until`
- `grant_id`
- `grant_version`

This turns execution from a binary gate into a boundary-aware authorization model.

### 2. Delegation Grant Registry is connected

Delegation rights are no longer treated as disposable inline request data.

Instead, AEP can now resolve execution authority through a separate grant registry, which means delegation can be:

- versioned
- governed
- reused
- audited independently from a single request

That is a meaningful step toward durable execution policy instead of request-local permissions.

### 3. Enforcement mode is configurable

Delegation controls are no longer limited to passive observation.

The system now supports:

- `observe`: record and surface violations without blocking
- `enforce`: hard-stop execution when delegation boundaries are violated

This makes it possible to phase in governance controls without forcing a single deployment posture across all actions or all risk bands.

### 4. Merged budget enforcement is now real

Budget control is no longer equivalent to a policy cap alone.

Effective execution capacity is now bounded by:

`min(policy_cap, principal_cap, delegate_cap)`

That matters because even if a strategy would otherwise be allowed, the action still cannot exceed the actual authority and budget granted by the delegating principal and the delegate’s own boundary.

### 5. Tickets are now capability-bound

A valid ticket is no longer sufficient by itself.

The flow now binds execution tickets to delegation state using a `capability_hash`:

- authorization produces capability state
- ticket stores `capability_hash`
- execute checks `capability_hash`
- review checks it again

If state no longer matches, execution is denied with:

- `DELEGATION_TICKET_MISMATCH`

This closes an important gap between authorization and actual execution.

### 6. Review is becoming governance, not just checking

Review has moved beyond basic execution inspection.

It now validates capability consistency and helps turn post-action review into something closer to:

- execution accountability
- delegation integrity review
- policy-aware governance replay

## Engineering Progress

The following surfaces were updated in the live chain of control:

- `action_request`
- `decision`
- `execution_ticket`
- kernel-side delegation logic
- gateway-side delegation enforcement
- registry-backed grant handling

New rejection paths are now represented explicitly:

- `DELEGATION_NOT_FOUND`
- `DELEGATION_EXPIRED`
- `DELEGATION_ROLE_NOT_ALLOWED`
- `DELEGATION_ACTION_NOT_ALLOWED`
- `DELEGATION_ASSET_SCOPE_DENIED`
- `DELEGATION_PROGRAM_SCOPE_DENIED`
- `DELEGATION_CAP_EXCEEDED`
- `DELEGATION_TICKET_MISMATCH`

## Why This Matters

This update moves Leviathan from:

- “can an agent execute?”

toward:

- “who is executing, under whose authority, under which capability envelope, with what budget boundary, and with what review path?”

That is a more serious model for Web4 execution than a simple pre-trade gate.

## Validation

Full local regression had previously passed on the updated environment:

- `.venv/bin/python -m pytest -q`
- `109 passed`

## Public Boundary

This repository intentionally documents the product and governance surface of the hackathon work.

It does **not** expose sealed production internals or proprietary attribution logic.

The public goal for now is clarity, architecture, and visible progress. Demo-facing artifacts can be layered in later without opening the internal engine.
