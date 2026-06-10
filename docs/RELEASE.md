# Release runbook (HC-7)

## Why

Publishing EmbedIQ Cloud means copying a **curated snapshot** of this private repo to the public
`embediq-cloud` repository — the open-source showcase. The private planning lane, the
coding-agent contract, and any secrets must never leave. This runbook makes the freeze one
reviewed, repeatable procedure. The publish itself is a human checkpoint (HC-7); no automation
pushes to the public repo.

## What publishes, and what never does

`scripts/publish.sh` copies this repo's **tracked** tree into a public clone and **excludes** the
private set: `pm/`, `CLAUDE.md`, `.claude/`, the script itself, real `.env`/`.env.*` files (the
`.env.example` template does publish), `certs/`, and any `*.key`/`*.pem`. Everything else — the
app, tests (unit and integration), config, the compose files, `install.sh`, `docs/`, the CI
workflows, and the standards — is the showcase and publishes.

The script asserts the staged tree is clean, secret-scans it with gitleaks, prints a summary, and
**stops**. It never commits, tags, or pushes.

## Prerequisites

- A local clone of the public `embediq-cloud` repository (the publish target).
- `gitleaks` on your `PATH` (the script secret-scans the staged tree before you push).
- All work for this release merged to `dev` and `main`.

## Checklist

Do these in order. The first version is `v0.1.0`.

1. **Gates green on `dev`.** Confirm every CI workflow is green on `dev`, including the
   `integration` workflow (it runs on pull requests that touch integration paths — re-run it on
   the release PR if needed). Do not proceed on a red gate.
2. **Sign-off (HC-7).** Get Ritesh's explicit go-ahead to publish this version.
3. **Tag `main`.** With the release commit on `main`, create an annotated tag:

   ```sh
   git checkout main && git pull
   git tag -a v0.1.0 -m "EmbedIQ Cloud v0.1.0"
   ```

4. **Stage the public tree.** Run the publish tool against your public clone:

   ```sh
   bash scripts/publish.sh /path/to/embediq-cloud
   ```

   It refuses (non-zero) on any leak or gitleaks finding. Use `--dry-run` first to preview the
   file list.
5. **Review the staged tree (human gate).** In the public clone, confirm by eye:

   - no `pm/`, no `CLAUDE.md`, no `.claude/`, no `.env`/secrets, no `certs/` or `*.key`/`*.pem`;
   - `LICENSE` and `README.md` are present and correct;
   - `git status` shows only the intended files.

6. **Commit and push.** In the public clone, commit the snapshot and push it, then push the tag
   to the public repo:

   ```sh
   git add -A && git commit -m "Release v0.1.0"
   git push origin main
   git push origin v0.1.0
   ```

7. **Acceptance — prove the published artifact runs (D-25).** Against the freshly published
   public repo, run:

   ```sh
   bash scripts/verify-release.sh <public-repo-url>
   ```

   It clones the public repo read-only into a temp dir and runs the documented quickstart
   (health + login + a UI route; the Docker full-stack too when Docker is available). If it
   fails, fix in the **private** repo, re-run `scripts/publish.sh`, and re-verify. **Do not
   announce until acceptance passes.** Then true-up the public docs so they match exactly what
   the run actually required.
8. **Announce.** Publish the release notes (from `CHANGELOG.md`) and announce the release.

## Caveats

- The script copies only **tracked** files, so untracked local artifacts (a `.venv`, `dev.db`,
  generated `certs/`) never leak — but the explicit excludes and the post-copy assertions are the
  real guard, not the `.gitignore`.
- The CI workflows publish; confirm in the step-5 review that they reference nothing private
  before pushing.
- `scripts/verify-release.sh` is release-ops — `publish.sh` excludes it, so it never ships to the
  public repo; run it from this private repo against the public URL.
- Neither `publish.sh` nor `verify-release.sh` pushes. Steps 3, 6, 7, and 8 are deliberate human
  actions so the freeze is always reviewed and proven before it goes public.
