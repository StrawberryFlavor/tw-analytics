# Repository Guidelines

## Project Structure & Module Organization
- `src/app/` – Flask app factory, APIs (`api/`), DI container (`core/`), and domain services (`services/`).
- `src/account_management/` – Twitter account models, parsing, switching.
- `src/client/` – Low-level Twitter client helpers.
- `src/config/` – `accounts.json` and examples.
- `scripts/` – Dev/ops utilities (`manage.sh`, `view_booster_multi.py`).
- `docker/` – Dockerfile and `docker-compose.yml`.
- `run.py` (dev) and `wsgi.py` (prod entry), `docs/` (API and architecture notes).

## Build, Test, and Development Commands
- Setup env: `./scripts/manage.sh setup` (optional login deps: `./scripts/manage.sh setup login`). Then `source .venv/bin/activate`.
- Run locally: `./scripts/manage.sh start` or `python run.py`.
- Docker (prod-like): `docker-compose -f docker/docker-compose.yml up -d`.
- Data sync: `./scripts/manage.sh sync-test`, `sync`, `update-all`, `priority-sync`.
- View booster: `python scripts/view_booster_multi.py`.
- Tests: no suite committed yet; if added, run `pytest -q`.

## Coding Style & Naming Conventions
- Python ≥3.10, 4-space indentation, PEP 8 with type hints where practical.
- Names: `snake_case` for modules/functions/vars, `PascalCase` for classes.
- Keep modules focused; prefer placing new logic under `src/app/services/<area>/` and expose via DI in `src/app/core/providers.py`.
- Imports: prefer absolute imports from the `src` package path.
- JSON/HTTP responses should be UTF-8 and stable field names (see `docs/api-response-structure.md`).

## Testing Guidelines
- Framework: `pytest` recommended.
- Layout: mirror `src/` under `tests/`; files named `test_*.py`.
- Add unit tests for extractors/formatters and integration tests using Flask test client for `src/app/api/*`.
- Aim for ≥80% coverage on changed modules (use `pytest --cov` if configured).

## Commit & Pull Request Guidelines
- History is minimal; adopt Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `test:`.
- Commits: imperative mood, short subject (<72 chars), body for rationale.
- PRs: clear description, scope, linked issue, before/after notes; include example `curl` and sample JSON for API changes; note config/env impacts.

## Security & Configuration Tips
- Never commit secrets (tokens/cookies). Copy `.env.example` to `.env` and set `TWITTER_BEARER_TOKEN` etc.
- Use Docker volumes for `instance/`; avoid logging sensitive fields.
- Validate config at startup (`run.py` uses `get_config().validate()`).

## Agent-Specific Instructions
- Wire new services via the container and providers, then expose through an API blueprint under `src/app/api/`.
- Update docs in `docs/` and relevant script entries in `scripts/manage.sh` when adding features.
