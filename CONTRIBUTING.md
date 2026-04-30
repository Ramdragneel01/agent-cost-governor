# Contributing

Thanks for considering a contribution!

## Dev Setup

```bash
python -m venv .venv && .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pip install -e .
pytest
```

## Standards

- Python 3.10+ with type hints.
- `ruff check src tests` must be clean.
- Tests for every new behaviour. Aim ≥ 85% coverage.
- Pure functions where possible — keep HTTP and decision logic separate.
- One feature per PR; keep diffs small.

## Branching

- `main` is always shippable.
- Open a PR against `main`.

## Commit Messages

Conventional commits preferred:

```
feat(routing): add per-route override
fix(ledger): correct window expiry boundary
docs(readme): clarify policy file mounting
```

## What's a Good First PR?

- New judges or pricing entries
- Clearer error messages
- Docs improvements
- Tests for edge cases (empty policy, mixed-case headers)

## Code of Conduct

Be kind, technical, and brief. Mean reviews aren't accepted; mean code is.
