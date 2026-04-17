# Judge Runtime Access

Leviathan can be tested through a controlled runtime access path.

This is not a source release. Judges and selected reviewers receive a local runtime shell and connect it to a Leviathan API endpoint with an issued access token.

## What To Request

To test Leviathan, contact the team and request:

- a Leviathan API base URL
- a short-lived access token
- optional demo prompts and expected test scope

Reviewers provide their own model API key locally.

## Runtime Package

The recommended alpha runtime path is direct pull from GHCR:

```bash
docker pull ghcr.io/leviathanmatrix/leviathan-alpha-runtime:latest
```

Version-pinned tag:

```bash
docker pull ghcr.io/leviathanmatrix/leviathan-alpha-runtime:20260417
```

The runtime directory template remains in this repository:

- [runtime directory template](../runtime-assets/leviathan-alpha-runtime-20260416.tar.gz)

Unpack the runtime directory:

```bash
tar -xzf leviathan-alpha-runtime-20260416.tar.gz
cd leviathan-alpha-runtime
cp .env.example .env
```

## Local Configuration

After receiving access, configure the runtime environment with:

```env
LEVIATHAN_API_BASE_URL=<issued-api-url>
LEVIATHAN_API_ACCESS_TOKEN=<issued-access-token>
MODEL_API_KEY=<reviewer-model-key>
```

Optional model settings may also be configured locally:

```env
MODEL_PROVIDER=custom
MODEL_BASE_URL=<openai-compatible-model-endpoint>
MODEL_ID=<model-name>
```

Run local checks:

```bash
./scripts/smoke_test.sh
./scripts/api_smoke_test.sh
```

Start the runtime:

```bash
./scripts/start.sh
```

## What The Runtime Demonstrates

The current runtime can be used to:

- evaluate proposed agent actions before execution
- request governed paper execution
- test delegated execution boundaries
- observe Capital Capsule issuance and lifecycle summaries
- retrieve shareable case summaries
- export report bundles

## What Remains Protected

The runtime does not expose:

- AEP core source code
- attribution engine internals
- private policy and scoring logic
- Capital Capsule pricing internals
- raw liability ledger storage
- private audit infrastructure

The protected decision logic remains behind the Leviathan API boundary.

## Audit And Reporting

Each governed request creates server-side audit material such as cases, receipts, liability events, capsule events, and report bundles.

External users retrieve safe outputs through the runtime, such as:

- presentable case summaries
- execution or rejection summaries
- shareable audit summaries
- report bundles

Raw internal ledgers are not distributed by default.

## Current Attribution Mode

The external alpha path currently uses a lighter attribution mode by default for responsiveness and demo stability.

The deeper attribution engine remains under optimization and hardening for future runtime releases.

## Example Prompts

```text
Evaluate whether a 5 USDC paper buy of SOL is allowed. Do not execute.
```

```text
Paper execute a 5 USDC buy of SOL through Leviathan.
```

```text
Check whether this Solana token is safe to buy with 5 USDC: <token-address>
```

```text
Give me a shareable audit summary for the last case.
```

## Access Policy

Runtime access is issued selectively for hackathon review, demos, research collaboration, and controlled trials.

Tokens are short-lived and may be rotated or revoked after review windows.
