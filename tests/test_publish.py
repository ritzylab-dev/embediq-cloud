# tests/test_publish.py — the OSS publish script: curated copy, guards, dry-run (PR-FREEZE)
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
"""scripts/publish.sh stages a curated public snapshot of this repo. These tests assert the
public set is copied, the private set (pm/, CLAUDE.md, .claude/) is excluded, the guard refuses
a leaked tree (non-zero), and --dry-run writes nothing. No Docker; runs in the unit suite."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "publish.sh"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    # The test runs a fixed interpreter (bash) on a repo-internal script with controlled args;
    # the subprocess call (S603) is not a real risk here.
    cmd = ["bash", str(SCRIPT), *args]
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)  # noqa: S603


def test_publish_copies_oss_and_excludes_private(tmp_path: Path) -> None:
    target = tmp_path / "public"
    target.mkdir()
    result = _run(str(target))
    assert result.returncode == 0, result.stdout + result.stderr

    # The OSS showcase publishes — code, tests (incl. integration), config, compose, docs.
    assert (target / "LICENSE").is_file()
    assert (target / "README.md").is_file()
    assert (target / "app").is_dir()
    assert (target / "tests" / "integration").is_dir()
    assert (target / "config" / "mosquitto" / "mosquitto.prod.conf").is_file()
    assert (target / "docker-compose.yml").is_file()
    assert (target / ".github" / "workflows" / "ci.yml").is_file()
    assert (target / ".env.example").is_file()

    # The private set never publishes.
    assert not (target / "pm").exists()
    assert not (target / "CLAUDE.md").exists()
    assert not (target / ".claude").exists()
    assert not (target / "CODEOWNERS").exists()
    assert not (target / ".github" / "CODEOWNERS").exists()
    assert not (target / "scripts" / "publish.sh").exists()
    assert not (target / "scripts" / "verify-release.sh").exists()


def test_publish_guard_fails_on_injected_private(tmp_path: Path) -> None:
    # A leaked CLAUDE.md already in the target must make the script exit non-zero.
    target = tmp_path / "public"
    target.mkdir()
    (target / "CLAUDE.md").write_text("leaked\n", encoding="utf-8")
    result = _run(str(target))
    assert result.returncode != 0


def test_publish_guard_fails_on_injected_pm(tmp_path: Path) -> None:
    target = tmp_path / "public"
    (target / "pm").mkdir(parents=True)
    (target / "pm" / "secret.md").write_text("planning\n", encoding="utf-8")
    result = _run(str(target))
    assert result.returncode != 0


def test_dry_run_lists_and_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "public"
    target.mkdir()
    result = _run("--dry-run", str(target))
    assert result.returncode == 0
    assert "app/" in result.stdout  # lists files that would copy
    assert list(target.iterdir()) == []  # but writes nothing
