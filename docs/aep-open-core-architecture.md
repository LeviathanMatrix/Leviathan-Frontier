# AEP Open Core Architecture

This document describes the technical architecture of LeviathanMatrix AEP Open Core.

AEP stands for Agent Execution Policy. It is a deterministic execution-control kernel for autonomous agent actions.

## Design Goal

The design goal is to separate agent reasoning from execution authority.

An agent may suggest an action. AEP decides whether the action can become executable.

```mermaid
flowchart LR
    A["Agent reasoning"] --> B["AEP boundary"]
    B --> C{"Policy + authority + capital checks"}
    C -->|valid| D["Execution Pass"]
    D --> E["Capital Capsule"]
    E --> F["Bounded execution"]
    C -->|invalid| X["Fail closed"]
```

## Module Map

```mermaid
flowchart TD
    subgraph "Input Layer"
        A1["Natural language request"]
        A2["Structured request"]
        A3["Delegation claim"]
    end

    subgraph "Normalization Layer"
        B1["Intake compiler"]
        B2["Asset registry"]
        B3["Action request schema"]
    end

    subgraph "Policy Layer"
        C1["Intent builder"]
        C2["Constitution"]
        C3["Risk input"]
        C4["Policy engine"]
    end

    subgraph "Authority Layer"
        D1["Execution Pass"]
        D2["Capability hash"]
        D3["TTL validation"]
    end

    subgraph "Capital Layer"
        E1["Capital Capsule"]
        E2["Pressure profile"]
        E3["Notional guard"]
        E4["Lifecycle state"]
    end

    subgraph "Execution Layer"
        F1["Execution guard"]
        F2["Paper adapter"]
        F3["Receipt"]
        F4["Review"]
    end

    subgraph "Accountability Layer"
        G1["Event hash chain"]
        G2["Execution claim export"]
    end

    A1 --> B1
    A2 --> B1
    A3 --> B1
    B1 --> B2
    B2 --> B3
    B3 --> C1
    C1 --> C2
    C1 --> C3
    C2 --> C4
    C3 --> C4
    C4 --> D1
    D1 --> D2
    D1 --> D3
    D1 --> E1
    E1 --> E2
    E1 --> E3
    E1 --> E4
    E1 --> F1
    F1 --> F2
    F2 --> F3
    F3 --> F4
    B1 --> G1
    C4 --> G1
    F2 --> G1
    F4 --> G1
    F4 --> G2
```

## Object Lifecycle

```mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> COMPILED: intake ok
    REQUESTED --> REJECTED: intake invalid
    COMPILED --> AUTHORIZED: policy allow
    COMPILED --> DENIED: policy deny
    AUTHORIZED --> PASS_ISSUED
    PASS_ISSUED --> CAPSULE_ISSUED
    CAPSULE_ISSUED --> CAPSULE_ARMED
    CAPSULE_ARMED --> EXECUTED: guard ok
    CAPSULE_ARMED --> BLOCKED: guard fail
    EXECUTED --> RECEIPTED
    RECEIPTED --> REVIEW_PASSED
    RECEIPTED --> REVIEW_FAILED
    REVIEW_PASSED --> CLAIM_EXPORTED
    DENIED --> [*]
    BLOCKED --> [*]
    CLAIM_EXPORTED --> [*]
```

## Fail-Closed Invariants

AEP is built around fail-closed invariants:

- no compiled request, no policy decision
- no policy allow, no pass
- no valid pass, no execution
- no matching capability hash, no execution
- no active capsule, no execution
- no remaining notional, no execution
- expired pass or capsule cannot execute
- denied authorization cannot be upgraded by review

These invariants make the system boring in the best possible way: if the chain of authority breaks, execution stops.

## Execution Pass

The Execution Pass is the central permission object.

It is not a text approval. It is a structured object with:

- `issuance_id`
- `pass_id`
- `status`
- `issued_at`
- `expires_at`
- `scope`
- `capability_hash`

The pass is short-lived and bound to the request state.

## Capital Capsule

The Capital Capsule turns capital authority into a finite object.

It limits:

- maximum notional
- remaining notional
- valid time
- execution mode
- bound pass id

It tracks state transitions:

```text
ISSUED -> ARMED -> PARTIALLY_CONSUMED -> EXHAUSTED
ISSUED -> REVOKED
ISSUED -> EXPIRED
EXHAUSTED -> FINALIZED
```

The point is direct: an agent should not receive infinite reusable authority when one bounded action is enough.

## Hash Anchors

AEP uses deterministic hashes for integrity:

- capability hash binds the pass to the request and policy context
- capsule hash binds the capsule to its state
- accountability event hash links local events into a replayable chain

This gives developers a stable way to detect mutation without trusting the agent's narration.

## Producer Metadata

Every major exported object includes:

```json
{
  "producer": {
    "company": "LeviathanMatrix",
    "product": "AEP",
    "project": "LeviathanMatrix AEP Open Core",
    "spec_id": "leviathanmatrix.aep.open-core.v1"
  }
}
```

This gives downstream systems a stable origin marker without adding any closed-source dependency.
