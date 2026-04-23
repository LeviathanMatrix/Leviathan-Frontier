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

## 4. Show The Agent Runtime Demo Videos

The README includes two YouTube demos:

- [AEP execution through Hermes](https://youtu.be/vRsmemDOKdg?si=5tm1mhnhGgrR81CL)
- [AEP audit retrieval through Hermes](https://youtu.be/EK7J59XoqpI?si=j_M1hljHsk-xs7T5)

Use them to show that AEP can sit between an external agent runtime and the
execution path, not only behind a standalone CLI.

## 5. Inspect The Case

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

## 6. Export The Execution Claim

```bash
python scripts/aep_cli.py export-claim \
  --case-id <case_id>
```

The exported claim is the shareable summary of the governed action.

## 7. Demo A Denial

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

## 8. Show The Solana Devnet Proof Anchor

AEP Open Core includes a minimal Anchor program for recording the execution
lifecycle as a Solana Devnet proof anchor.

Program ID:

```text
5LY2YsVpAhES2nq9TT7iQn4gGAy8vdb4nkE3XyQzMw4q
```

Confirmed Devnet transaction:

```text
https://explorer.solana.com/tx/57c51zE8QZ3vrZ4My5Jgp1ssFAhEP8vRa72X8apg8QKxE3VSCY1J1gQCU8SZFU83gu2XTryWopGZvTRd4P6SV5Qx?cluster=devnet
```

What to point out:

- the AEP decision happens off-chain;
- the proof of the AEP lifecycle is anchored on Solana Devnet;
- the chain account stores hashes, not raw strategy or private data;
- judges can inspect the transaction in Solana Explorer.

## 9. Demo The Core Thesis

The one-line demo:

```text
We are not showing that an agent can trade. Everybody can do that.
We are showing that an agent cannot trade unless its action becomes policy-bound, time-limited, notional-limited, and reviewable.
```

## 10. Judge Talking Points

Use these:

- AEP is a deterministic execution kernel, not a prompt trick.
- Execution Pass turns approval into a cryptographic capability object.
- Capital Capsule turns broad capital access into a finite envelope.
- Capability hash blocks scope mutation between authorization and execution.
- Constitution rules make policy portable across agent runtimes.
- Solana is the natural first target because high-speed agent finance needs high-speed execution policy.
- The Devnet proof anchor gives the local AEP lifecycle a public Solana verification surface.

## 11. Thirty-Second Pitch

```text
Most agent demos prove that an AI can call a tool.
LeviathanMatrix AEP proves something more important:
an AI cannot call a value-moving tool unless its action becomes a scoped, expiring, policy-bound execution object.

We turn agent execution into a deterministic lifecycle:
intent, constitution, risk score, execution pass, capital capsule, receipt, review.

This is the control plane agents need before they can safely operate in Solana-speed finance.
```

## 12. What To Show On Screen

Open these files during the demo:

- `aep/kernel.py`: the lifecycle orchestration
- `programs/aep-proof-anchor/src/lib.rs`: the minimal Solana proof anchor
- `policy_engine/engine.py`: deterministic policy scoring and reason codes
- `aep/issuance.py`: Execution Pass and capability hash
- `aep/capsule.py`: Capital Capsule lifecycle and notional guard
- `aep/capsule_pricing.py`: capsule pressure model
- `docs/algorithm-notes.md`: algorithm explanation
- `docs/design-rationale.md`: why the architecture exists

## 13. Solana Framing

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
