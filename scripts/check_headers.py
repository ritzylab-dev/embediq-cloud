# scripts/check_headers.py — enforce the SPDX + author/company header on every source file
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
"""Fail (exit 1) if any .py under app/, tests/, scripts/ misses required header lines."""

from __future__ import annotations

import sys
from pathlib import Path

REQUIRED = (
    "@author  Ritesh Anand",
    "@company embediq.com | ritzylab.com",
    "SPDX-License-Identifier: Apache-2.0",
)
ROOTS = ("app", "tests", "scripts")


def main() -> int:
    failures: list[str] = []
    for root in ROOTS:
        for path in Path(root).rglob("*.py"):
            head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:8])
            missing = [r for r in REQUIRED if r not in head]
            if missing:
                failures.append(f"{path}: missing {missing}")
    for f in failures:
        print(f"HEADER CHECK FAIL: {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
