#!/usr/bin/env python3
"""Backward-compat shim. Implementation moved to tools.validators.ha_official."""

import argparse  # noqa: F401  (re-exported for patch targets)
import subprocess  # noqa: F401  (re-exported for patch targets)
import sys  # noqa: F401  (re-exported for patch targets)

from tools.validators.ha_official import *  # noqa: F401,F403
from tools.validators.ha_official import HAOfficialValidator, main

__all__ = ["HAOfficialValidator", "main"]

if __name__ == "__main__":
    main()
