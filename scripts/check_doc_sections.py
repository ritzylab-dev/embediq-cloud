# scripts/check_doc_sections.py — enforce the five-questions structure in design docs and ADRs
# @author  Ritesh Anand
# @company embediq.com | ritzylab.com
# SPDX-License-Identifier: Apache-2.0
"""Fail (exit 1) if a design doc / ADR misses any of the five required sections.
Scope: docs/design/ and docs/adr/ only (READMEs, the standard, CONTRIBUTING are exempt)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOTS = ("docs/design", "docs/adr")
REQUIRED = {
    "why": r"(?im)^#+\s*why\b",
    "what": r"(?im)^#+\s*what\b",
    "where it impacts": r"(?im)^#+\s*where\b",
    "how it impacts": r"(?im)^#+\s*how\b",
    "caveats & edges": r"(?im)^#+\s*caveat",
}


def main() -> int:
    failures: list[str] = []
    for root in ROOTS:
        for path in Path(root).rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            for name, pattern in REQUIRED.items():
                if not re.search(pattern, text):
                    failures.append(f"{path}: missing section '{name}'")
    for f in failures:
        print(f"DOC SECTION FAIL: {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
