# Hackathon Demo Guide

This guide shows how to demo LeviathanMatrix AEP Open Core quickly.

## 1. Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

## 2. Run Tests

```bash
pytest -q -p no:cacheprovider
```

Expected result:

```text
all tests passed
```

## 3. Run A Governed Action

```bash
python scripts/aep_cli.py run-text \
  --text "buy 1 USDC of SOL" \
  --agent-id demo-agent
```

What to point out:

- the agent did not execute directly
- AEP compiled the request first
- AEP created an authorization case
- AEP issued an Execution Pass
- AEP wrapped the notional in a Capital Capsule
- execution produced a receipt
- review produced a final status

## 4. Inspect The Case

Cases are written under:

```text
artifacts/cases/
```

Open the generated case and point to:

- `producer`
- `spec_id`
- `request`
- `intent`
- `policy_output`
- `authorization.issuance`
- `authorization.decision.capital_capsule`
- `execution`
- `receipt`
- `review`

## 5. Export The Execution Claim

```bash
python scripts/aep_cli.py export-claim \
  --case-id <case_id>
```

The exported claim is the shareable summary of the governed action.

## 6. Demo A Denial

```bash
python scripts/aep_cli.py run-text \
  --text "buy 1000000 USDC of SOL" \
  --agent-id demo-agent
```

What to point out:

- the request compiles
- policy denies it
- no capsule is issued
- execution is blocked
- review fails the case

This demonstrates fail-closed behavior.

## 7. Demo The Core Thesis

The one-line demo:

```text
We are not showing that an agent can trade. Everybody can do that.
We are showing that an agent cannot trade unless its action becomes policy-bound, time-limited, notional-limited, and reviewable.
```

## 8. Judge Talking Points

Use these:

- AEP is a deterministic execution kernel, not a prompt trick.
- Execution Pass turns approval into a cryptographic capability object.
- Capital Capsule turns broad capital access into a finite envelope.
- Capability hash blocks scope mutation between authorization and execution.
- Constitution rules make policy portable across agent runtimes.
- Solana is the natural first target because high-speed agent finance needs high-speed execution policy.

## 9. Thirty-Second Pitch

```text
Most agent demos prove that an AI can call a tool.
LeviathanMatrix AEP proves something more important:
an AI cannot call a value-moving tool unless its action becomes a scoped, expiring, policy-bound execution object.

We turn agent execution into a deterministic lifecycle:
intent, constitution, risk score, execution pass, capital capsule, receipt, review.

This is the control plane agents need before they can safely operate in Solana-speed finance.
```

## 10. What To Show On Screen

Open these files during the demo:

- `aep/kernel.py`: the lifecycle orchestration
- `policy_engine/engine.py`: deterministic policy scoring and reason codes
- `aep/issuance.py`: Execution Pass and capability hash
- `aep/capsule.py`: Capital Capsule lifecycle and notional guard
- `aep/capsule_pricing.py`: capsule pressure model
- `docs/algorithm-notes.md`: algorithm explanation
- `docs/design-rationale.md`: why the architecture exists

## 11. Solana Framing

Say this clearly:

```text
Solana made machine-speed capital actions practical.
AEP makes machine-speed capital actions governable.
```

Then explain:

- low fees make repeated agent actions viable
- fast confirmation means weak policy fails faster
- high throughput needs automated execution boundaries
- agentic payment flows need policy objects, not just wallet signatures
- long-tail assets make scoped authority safer than broad approvals
