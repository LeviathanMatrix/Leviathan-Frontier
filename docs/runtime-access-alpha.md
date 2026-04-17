# Runtime Access Alpha

This document describes the current external trial shape for Leviathan.

It is not a source release.
It is a controlled runtime access path for external testers, judges, and research collaborators.

## What External Testers Receive

External users receive a local runtime shell:

- a containerized agent runtime
- a Leviathan MCP/API shell
- local model configuration
- local startup and smoke-test scripts

They do **not** receive:

- AEP core logic
- attribution source logic
- private policy internals
- capital capsule internals
- private case storage
- private audit infrastructure

## How The Current Runtime Works

The current alpha shape is:

```text
tester machine
-> local runtime shell
-> Leviathan API endpoint
-> AEP + attribution + capsule control + audit trail
```

This means the tester runs the interface locally, but the protected decision and execution-governance logic remains on the Leviathan side.

## Why This Matters

This approach gives external users a real runtime-facing experience without exposing the protected internals of the system.

It also keeps the product aligned with Leviathan's actual claim:

Leviathan is not a prompt trick or a local scoring toy.
It is infrastructure for deciding whether agent actions involving capital should be allowed, under what authority, and with what accountability.

## Current External Trial Flow

The current external tester flow is:

1. receive a Leviathan runtime package or image
2. configure the runtime with:
   - a Leviathan API base URL
   - a short-lived access token
   - the tester's own model key
3. run local smoke tests
4. use the local runtime to:
   - evaluate actions
   - request governed execution
   - fetch presentable cases
   - export report bundles


## Judge Access

Judges and selected reviewers can request controlled runtime access from the Leviathan team.

Access includes:

- a Leviathan API base URL
- a short-lived access token
- runtime image or pull instructions
- local configuration guidance

Reviewers provide their own model API key locally.

See [judge-runtime-access.md](judge-runtime-access.md) for the reviewer-facing access flow.

## Runtime Boundary

The runtime shell is intentionally narrow.

It exposes a public product surface such as:

- `evaluate_action`
- `run_action`
- `get_presentable_case`
- `export_report_bundle`

It does not expose the inner engine surface.

That separation is deliberate.

## Attribution Note

The current external runtime path uses a lighter attribution path by default for responsiveness and operator usability.

The full deeper attribution engine remains under active optimization and performance hardening.

This is not a removal of attribution.
It is a current runtime tradeoff to support practical external trials while the heavier path continues to be refined.

## Public Boundary

This repository documents:

- public product direction
- external runtime access shape
- infrastructure posture
- visible update progress

It does not publish sealed runtime logic or proprietary internal decision methods.
