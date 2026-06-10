# Contributing to EmbedIQ Cloud

This guide covers local setup, the quality gates, and the branch and pull-request flow. Read
[CODING_RULES.md](CODING_RULES.md) and [docs/DOCUMENTATION_STANDARD.md](docs/DOCUMENTATION_STANDARD.md)
before you start.

## Local setup

Use Python 3.12. Create a virtual environment and install the dev extras:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Run locally (no Docker)

The fastest way to click through the admin panel — Overview, Fleet, a device, OTA, Settings:

```sh
bash scripts/dev.sh
```

This creates a `.venv`, installs the package, generates throwaway dev credentials and a random
JWT secret, uses a local `./dev.db` SQLite file, and skips the MQTT broker. Open
<http://localhost:8080> and sign in with **admin / admin**. The credentials are regenerated on
every run and are never committed. For the full stack (broker, InfluxDB, Grafana, hawkBit) use
Docker as described in [README.md](README.md).

## Run the gates

Most gates need **no Docker** — run them locally before you commit:

```sh
ruff format --check .
ruff check .
mypy app scripts
pytest                         # unit suite; excludes the integration marker by default
bandit -r app scripts
pip-audit
python scripts/check_headers.py
python scripts/check_doc_sections.py
```

The **integration** suite is separate: it boots the full stack and is marked `integration`, so
`pytest` skips it by default. It needs Docker and is the one gate you normally let CI run:

```sh
docker compose -f docker-compose.yml -f docker-compose.integration.yml up -d --build
pytest -m integration --no-cov
```

Documentation gates (markdownlint and vale) also run in CI. Never disable a gate to make it
pass. If a gate fails for a reason outside your task, stop and escalate (see
[CLAUDE.md](CLAUDE.md), §5).

## The design system

The admin UI is server-rendered Jinja2 with a hand-authored, framework-free design system in
`app/static/design-system.css` (no build step). Before changing the UI, read
[docs/UI_DESIGN.md](docs/UI_DESIGN.md) — it documents the tokens, component classes, the app
shell, and how to theme a chart.

## Branch and pull-request flow

- Branch from `dev`. Name the branch `feature/T<id>-<slug>`.
- Use Conventional Commit messages (`feat:`, `fix:`, `chore:`, `test:`, `docs:`).
- Write tests first and watch them fail before you implement.
- Open one pull request per change, based on `dev`.
- Fill the sections of the pull-request template.
- Maintainers merge. Do not merge your own pull request.

## Filing issues

Open a GitHub issue for bugs and feature requests. For anything security-sensitive, do not file a
public issue — follow [SECURITY.md](SECURITY.md) instead.

## Documentation

Every design doc, ADR, pull-request body, and README answers five questions up front:
**Why · What · Where it impacts · How it impacts · Caveats & edges**. The full doctrine lives in
[docs/DOCUMENTATION_STANDARD.md](docs/DOCUMENTATION_STANDARD.md).
