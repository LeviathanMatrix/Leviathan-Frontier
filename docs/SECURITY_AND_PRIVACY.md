# Security And Privacy Boundary

This repository is designed to be public and open-core. It should contain only
the AEP kernel, public schemas, reproducible demos, tests, and public-safe
documentation.

## What Must Not Be Committed

Do not commit:

- API keys
- private keys
- seed phrases
- wallet files
- wallet paths
- exchange credentials
- service credentials
- production environment files
- private customer configuration
- raw private prompts or proprietary strategy code

## Artifact Hygiene

Public artifacts should be reviewable without exposing operational secrets.

Allowed public artifact content includes:

- case identifiers
- policy decisions
- reason codes
- hash commitments
- bounded request summaries
- receipt status
- review status
- proof-anchor transaction references

Sensitive artifact content should be removed or replaced with hashes before
publication:

- raw prompts containing private strategy
- private customer names
- private wallet metadata
- local filesystem paths
- service endpoints that are not intended for public use
- credentials or bearer tokens

## Hosted Pilot Boundary

Hosted LeviathanMatrix pilot access is separate from this open-core repository.
The hosted environment may add managed onboarding, security inspection,
receipt/proof review, and clearing review surfaces around live agent workflows,
but those production service internals are not part of this repository.

Public documentation should describe hosted pilot capabilities at a product
level only. It should not publish private endpoints, deployment topology,
managed integration distribution paths, production service configuration, or
access tokens.

## Disclosure

For security issues or private pilot access:

```text
Gauss8008@gmail.com
```
