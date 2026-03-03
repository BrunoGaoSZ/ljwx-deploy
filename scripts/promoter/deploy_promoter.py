#!/usr/bin/env python3
"""Compatibility wrapper for legacy deploy_promoter entrypoint.

Canonical promoter implementation lives in scripts/promoter/promote.py.
"""

from __future__ import annotations

import sys

from promote import main as promote_main


if __name__ == "__main__":
    print(
        "[deprecated] use scripts/promoter/promote.py; deploy_promoter.py is a compatibility wrapper",
        file=sys.stderr,
    )
    raise SystemExit(promote_main())
