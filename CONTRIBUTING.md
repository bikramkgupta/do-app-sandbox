# Contributing

Thank you for contributing to DO App Sandbox.

## Development setup

1. Clone and enter the repository.
2. Install dependencies:

```bash
uv sync --extra dev
```

If `uv` is unavailable, use a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pip install ruff mypy pip-audit
```

## Quality checks

Run before opening a PR:

```bash
make check
```

Additional checks:

```bash
make security
cd tests && make test-unit
```

## Pull request expectations

- Keep changes focused and minimal.
- Include tests for behavioral changes.
- Update docs when APIs or workflows change.
- Ensure CI is passing.

## Commit style

Use clear, imperative commit messages, for example:

- `fix: validate executor inputs before doctl invocation`
- `test: add unit coverage for command builder`
