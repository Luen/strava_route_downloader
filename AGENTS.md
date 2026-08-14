# AGENTS.md

Agent-focused guidance for this repository ([AGENTS.md format](https://agents.md/)). Human-facing docs live in `README.md`.

Treat this file as living documentation: update it when the stack, scripts, or project facts change.

## Project overview

Flask app: paste a Strava route URL and download GPX / KML / GeoJSON. Tries an anonymous fetch first; retries with session cookies from `STRAVA_COOKIES_FILE` for private routes.

## Setup

```bash
docker compose up --build
# or
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
export CACHE_DIR=./cache
flask --app app run --debug
```

## Checks

```bash
pytest -q
```

Add or update tests for code you change. Fix failures before finishing.

## Conventions

- Python: PEP 8, type hints where helpful, `pathlib` where practical.
- Never commit secrets, cookie exports, or `STRAVA_COOKIES_FILE` contents.
- Keep README accurate for public vs private route behavior.


## Pull requests

Before merging any pull request:

1. **Read all comments** on the PR — conversation comments, review comments (including those on specific lines), and bot comments. Address or acknowledge them. Do not merge while review feedback is unresolved.
2. **Wait for CI to complete successfully.** GitHub Actions (and other required checks) on the PR must finish and pass. Do not merge while checks are pending, failed, cancelled, or skipped when they are required. If CI fails, fix the cause and wait for a green run before merging.
