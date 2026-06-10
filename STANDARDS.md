# Standards Ledger — EmbedIQ Cloud

A standard without a gate is advisory. To adopt one, add its gate.

Every row below is enforced by a concrete gate in CI (`.github/workflows/ci.yml`)
and, where possible, mirrored locally in `.pre-commit-config.yaml`.

| Standard | Enforcing gate | Status |
| --- | --- | --- |
| Consistent code formatting | `ruff format --check .` | enforced |
| Lint rules (errors, bugs, imports, security idioms) | `ruff check .` | enforced |
| Static type safety (strict) | `mypy app scripts` | enforced |
| Tests pass with coverage ≥ 80% | `pytest` (`--cov-fail-under=80`) | enforced |
| No insecure code patterns | `bandit -r app scripts` | enforced |
| No known-vulnerable dependencies | `pip-audit` | enforced |
| SPDX + author/company header on every source file | `python scripts/check_headers.py` | enforced |
| No committed secrets | `gitleaks/gitleaks-action` | enforced |
| Dockerfile best practices | `hadolint` | enforced |
| Compose file is valid | `docker compose config` | enforced |
| Container builds and serves `/health` | build + smoke (`curl /health`) | enforced |
| Markdown is well-formed | `markdownlint-cli2` | enforced |
| Design docs / ADRs answer the five questions | `python scripts/check_doc_sections.py` | enforced |
| Prose style (filler, passive voice, sentence length) | `vale` | enforced |
| Conventional commit messages | `cz check` | enforced |
