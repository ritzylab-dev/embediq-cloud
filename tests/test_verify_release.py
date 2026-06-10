# tests/test_verify_release.py — release-acceptance smoke self-test (PR-ACCEPT)
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
"""scripts/verify-release.sh clones a target read-only and runs the documented no-Docker
quickstart (health + login + a UI route). These tests exercise it against the current repo as a
local stand-in: it PASSES on the real tree and exits non-zero on a deliberately broken clone. No
Docker (the script skips the Docker path when docker is absent)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "verify-release.sh"


def _run(target: str, port: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "VERIFY_PORT": port}
    cmd = ["bash", str(SCRIPT), target]
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, env=env)  # noqa: S603


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_verify_release_passes_against_local_repo() -> None:
    result = _run(str(REPO), "8131")
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "no-Docker quickstart (health + login + UI): PASS" in out
    assert "ACCEPTANCE PASSED" in out
    # read-only: the source repo gains no acceptance artifacts
    assert not (REPO / "acceptance.db").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
def test_verify_release_fails_on_broken_quickstart(tmp_path: Path) -> None:
    broken = tmp_path / "broken"
    clone_cmd = ["git", "clone", "--quiet", str(REPO), str(broken)]
    subprocess.run(clone_cmd, check=True)  # noqa: S603
    # Break a documented quickstart step (the install): an invalid pyproject fails `pip install`.
    (broken / "pyproject.toml").write_text("this is not valid toml = = =\n", encoding="utf-8")
    commit_cmd = ["git", "-c", "user.email=t@e.st", "-c", "user.name=t", "commit", "-am", "break"]
    subprocess.run(commit_cmd, cwd=broken, check=True, capture_output=True)  # noqa: S603
    result = _run(str(broken), "8132")
    assert result.returncode != 0, result.stdout + result.stderr
