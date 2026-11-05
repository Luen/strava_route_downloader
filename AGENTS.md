# AGENTS.md

Agent-focused guidance for this repository ([AGENTS.md format](https://agents.md/)). Human-facing docs live in `README.md`.

## Living document

Treat this file as **living documentation**. Update it in the same PR when the stack, scripts, branch model, deploy path, or other project facts change. Future agents should keep it accurate rather than leaving stale instructions.

## Branch model

| Branch | Role |
| --- | --- |
| `dev` | Default branch for features and improvements |
| `main` | Production. Safe dependency bumps and releases land here |

- Open feature/fix PRs against **`dev`**.
- Promote to **`main`** when ready for production.
- Do not use `master` (rename to `main` if any remnant remains).

### Keeping `dev` and `main` in sync (Back-merge rule)

- **Never leave `main` ahead of `dev`.** Whenever `dev` is promoted to `main` (via merge commit or release PR) or when automated nightly dependency workflows commit directly to `main`, immediately back-merge `main` into `dev` so both branches share the same history and future PRs do not conflict on `package.json` or lockfiles.
- Verify sync status:
  ```bash
  git fetch origin && git rev-list --left-right --count origin/dev...origin/main
  # Expected after sync: 0	0
  ```
- Back-merge `main` into `dev`:
  ```bash
  git checkout dev && git merge origin/main --no-edit && git push origin dev
  ```

## Dependency and deploy notes

### Tier C - Branches + agent docs

- No nightly Docker dependency-release workflow in this PR.
- Use `dev` for features and `main` for production when applicable.

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

1. **Read all comments** on the PR �— conversation comments, review comments (including those on specific lines), and bot comments. Address or acknowledge them. Do not merge while review feedback is unresolved.
2. **Wait for CI to complete successfully.** GitHub Actions (and other required checks) on the PR must finish and pass. Do not merge while checks are pending, failed, cancelled, or skipped when they are required. If CI fails, fix the cause and wait for a green run before merging.

## Major-version dependency updates & migration checks

When reviewing or merging **major-version** Dependabot or package updates:

1. **Read the upstream migration guide / changelog** before merging. Do not rely solely on a passing container build (`docker build` only verifies `install`, not runtime execution paths).
2. **Verify exports and constructors at runtime:**
   - Check whether default exports moved to named exports (e.g., `pbf` v5 exporting `{ PbfReader, PbfWriter }` instead of a default constructor) or factory functions became ES classes requiring `new` (e.g., `geojson-vt` v5).
   - Check framework route syntax and middleware compatibility (e.g., Express 5 path-to-regexp rules, React peer dependency alignment across `@types/react` and `@types/react-dom`).
   - For Python lockfile repos (`uv pip compile`), always recompile `requirements.lock` and `requirements-dev.lock` when `requirements.txt` ranges change so `uv pip sync` and nightly constrained upgrades stay consistent.
3. **Regenerate lockfiles with the repo's pinned package manager** (e.g., `pnpm@10.33.0`, `pnpm@12.15.0`, `npm`, or `uv==0.13.7`) when rebasing or combining multiple dependency PRs.
4. **Run a runtime smoke test** (lint, unit tests, module import check, and endpoint/container health check) before promoting to `main` and publishing a release.
