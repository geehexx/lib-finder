# RTK - Token-Efficient Agent Command Policy

RTK is the default wrapper for noisy command output in agent sessions. Use it
when the result is long, repetitive, or otherwise wastes context.

## Preferred usage

- `rtk git status`
- `rtk git diff`
- `rtk summary <command>`
- `rtk read <path>`
- `rtk find <args>`
- `rtk wc <path>`

For project Python tools, prefer `uv run rtk ...` so the wrapper runs inside the
repository environment:

- `uv run rtk pytest -q`
- `uv run rtk ruff check src tests`
- `uv run rtk pytest tests/test_config.py -q`

Do not use bare `rtk pytest` in this repo for Python commands; it may not pick
up the project environment reliably. Keep the wrapper nested under `uv run`.

## Canonical commands

Use plain `uv run ...` in documentation, CI, and reproducible examples. RTK is
an agent-side output filter, not a replacement for the project command surface.

## When not to use RTK

- compound shell flows that need shell control operators or heredocs
- commands that are intentionally raw or already wrapped
- unsupported tools that should pass through unchanged

## Verification

- `rtk --version`
- `rtk gain`
- `rtk hook check git status`
