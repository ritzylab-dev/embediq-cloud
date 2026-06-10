# Coding Rules — EmbedIQ Cloud

- **R-1 Locked stack (D-08):** Python 3.12 + FastAPI; one docker-compose, no k8s; do not deviate.
- **R-2 Boundaries:** code stays Apache-2.0; never copy AGPL source into our code (consume Loki/Grafana as services); `pro/` proprietary code (Phase B) never mixes into the OSS tree.
- **R-3 Headers:** every new `.py` opens with the 4-line header (`# <file> — <desc>`, `@author Ritesh Anand`, `@company embediq.com | ritzylab.com`, `SPDX-License-Identifier: Apache-2.0`). `pro/` files use `LicenseRef-EmbedIQ-Commercial`.
- **R-4 Tests first** (pytest, fail before implement); config-only changes are smoke-tested (mark N/A).
- **R-5 Verify before commit:** the full §7 DoD, all green. No commit on a red check.
- **R-6 Git:** branch from `dev`; never push to `dev`/`main`; never `gh pr merge` (humans merge); PR base `dev`; PR body = (1) what it implements + cite, (2) why sequenced here, (3) how to verify.
- **R-7 API fidelity:** base `/api/v1`, envelope `{"data":..,"error":..}`, standard HTTP codes; OpenAPI at `/docs` must reflect reality (future MCP contract). (Applies from Phase A onward.)
- **R-8 Security:** prod TLS-only; secrets in `.env` (never committed); bcrypt for passwords; never log secrets.
- **R-9 Name for permanence:** no version/count/phase in any identifier.
- **R-10 Smallest change** that closes the loop; if the spec seems wrong, STOP and raise it — don't "improve" it.
- **R-11 Never write under `pm/`** — planning lane, read-only (one exception: an escalation file in `pm/governance/inbox-to-pm/`).
- **R-12 Documentation = code in quality (D-10).** Every design doc / ADR / PR body / README answers, up front: **Why · What · Where it impacts · How it impacts · Caveats & edges**; first-principles, to the point, low cognitive load, no prior knowledge assumed. See `docs/DOCUMENTATION_STANDARD.md`.
