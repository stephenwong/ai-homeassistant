#!/usr/bin/env python3
"""Backward-compat shim. Implementation moved to tools.validators.services."""

import argparse  # noqa: F401  (re-exported for patch targets)
import re  # noqa: F401  (re-exported for patch targets)

from tools.validators.services import *  # noqa: F401,F403
from tools.validators.services import ServiceValidator, main

__all__ = ["ServiceValidator", "main"]

if __name__ == "__main__":
    main()
