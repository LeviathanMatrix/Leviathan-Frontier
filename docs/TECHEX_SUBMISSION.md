# TechEx Submission Notes

This repository is the public AEP Open Core foundation of LeviathanMatrix.

AEP is an execution-control layer for autonomous agents. It converts messy agent
requests into deterministic authorization objects, applies policy and notional
limits, binds execution through a capital capsule, records receipts and review
state, and can anchor compact lifecycle commitments to Solana Devnet.

## Track Fit

Primary fit:

- agent security
- AI governance
- autonomous execution controls
- auditability for high-value agent actions
- policy-bound capital movement

The open-core repository is intentionally runnable and inspectable. Judges can
run tests, execute a governed demo action, inspect the generated case, export a
claim, and reproduce fail-closed behavior when authorization scope is mutated.

## Public Capability Summary

The public repository demonstrates:

- deterministic action normalization
- constitution-based policy evaluation
- Execution Pass issuance
- Capital Capsule binding and lifecycle pressure
- bounded demo execution
- receipt and review artifacts
- accountability hash-chain replay
- Solana Devnet proof anchoring for lifecycle commitments

Hosted LeviathanMatrix pilot capabilities are available by private request for
teams that need managed agent onboarding, external workflow integration,
security inspection, receipt and proof review, and clearing review surfaces
around live agent workflows.

## Repository Boundary

This repository does not include:

- hosted service source code
- managed integration packages
- commercial clearing internals
- production deployment configuration
- private policy configuration
- secrets, wallets, API keys, or service credentials

## Suggested Evaluation Path

1. Read the README to understand the AEP thesis and object lifecycle.
2. Run the test suite.
3. Run the quickstart governed action.
4. Inspect generated artifacts under `artifacts/cases`.
5. Export an execution claim.
6. Mutate scope or limits and confirm AEP fails closed.
7. Review the Solana Devnet proof-anchor document for the public on-chain
   verification surface.

## Contact

Private pilot access, live product demonstrations, and commercial use require
permission from LeviathanMatrix.

```text
Gauss8008@gmail.com
```
