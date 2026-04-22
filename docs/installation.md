# Installation

This guide shows how to install and run LeviathanMatrix AEP Open Core from a fresh clone.

## Requirements

- Python 3.10 or newer
- Git
- A POSIX-like shell

Runtime dependencies:

```text
none
```

Development dependency:

```text
pytest
```

## 1. Clone

```bash
git clone https://github.com/LeviathanMatrix/Leviathan-Frontier.git
cd Leviathan-Frontier
```

## 2. Create Virtual Environment

```bash
python3 -m venv .venv
. .venv/bin/activate
```

## 3. Install Dev Dependency

```bash
pip install -r requirements.txt
```

## 4. Run Tests

```bash
pytest -q -p no:cacheprovider
```

Expected result:

```text
28 passed
```

The exact runtime may differ, but all tests should pass.

## 5. Run A Governed Agent Action

```bash
python scripts/aep_cli.py run-text \
  --text "buy 1 USDC of SOL" \
  --agent-id demo-agent
```

Expected high-level result:

```json
{
  "ok": true,
  "authorization": {
    "status": "AUTHORIZED"
  },
  "execution": {
    "status": "EXECUTED"
  },
  "review": {
    "status": "PASSED"
  }
}
```

## 6. Run A Denied Action

The default constitution caps per-transaction notional at 500 USD.

```bash
python scripts/aep_cli.py run-text \
  --text "buy 1000000 USDC of SOL" \
  --agent-id demo-agent
```

Expected high-level result:

```json
{
  "ok": false,
  "authorization": {
    "status": "DENIED"
  },
  "execution": {
    "status": "BLOCKED"
  }
}
```

This demonstrates fail-closed behavior.

## 7. Where Output Goes

Running CLI commands creates local artifacts:

```text
artifacts/cases/
artifacts/accountability/
```

These are ignored by Git.

## 8. Common Issues

### `No module named pytest`

Install requirements inside the virtual environment:

```bash
. .venv/bin/activate
pip install -r requirements.txt
```

### `python: command not found`

Use `python3`:

```bash
python3 scripts/aep_cli.py run-text \
  --text "buy 1 USDC of SOL" \
  --agent-id demo-agent
```

### Case Not Found

If you use a custom case root, pass the same `--case-root` to follow-up commands:

```bash
python scripts/aep_cli.py --case-root ./demo-cases authorize-text \
  --text "buy 1 USDC of SOL" \
  --agent-id demo-agent

python scripts/aep_cli.py --case-root ./demo-cases export-claim \
  --case-id <case_id>
```

## 9. Minimal Smoke Test

```bash
python scripts/aep_cli.py run-text \
  --text "buy 1 USDC of SOL" \
  --agent-id demo-agent
```

If this returns `ok: true`, the open-core path is working.
