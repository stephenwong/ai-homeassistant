#!/usr/bin/env python3
"""Backward-compat shim. Implementation moved to tools.validators.duplicate_ids."""

import argparse  # noqa: F401 (re-exported for patch targets)
import collections  # noqa: F401 (re-exported for patch targets)

from tools.validators.duplicate_ids import *  # noqa: F401,F403
from tools.validators.duplicate_ids import DuplicateIDValidator, main

__all__ = ["DuplicateIDValidator", "main"]

if __name__ == "__main__":
    main()
