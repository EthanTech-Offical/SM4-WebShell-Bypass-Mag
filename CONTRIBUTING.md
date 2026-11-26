# Contributing

Thanks for taking the time to contribute.

## Development setup

```bash
uv sync --extra tls
uv run webshell-mag --version
```

## Before opening a PR

- Keep changes focused; avoid unrelated refactors.
- Run the smoke checks:

  ```bash
  python -m compileall -q src
  uv run webshell-mag --generate /tmp/shell.php
  php -l /tmp/shell.php
  ```

- Do **not** commit generated payloads (`shell.php`), credentials, session
  stores, or logs.
- If you change the PHP template, re-generate a payload and verify at least
  `ping`, `cmd`, `read`, `write` against a local PHP server.
- If you change the protocol, update `README.md` and `CHANGELOG.md`.

## Code style

- Python 3.10+, 4-space indentation, type hints where practical.
- Keep the payload template readable; the build-time randomiser handles
  per-payload polymorphism.
- No new third-party runtime dependencies without discussion.

## Security

See [SECURITY.md](SECURITY.md). Do not report vulnerabilities in public issues.
