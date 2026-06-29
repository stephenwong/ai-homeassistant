#!/usr/bin/env python3
"""Backward-compat shim. Implementation moved to tools.validators.yaml."""

import argparse  # noqa: F401  (re-exported for patch targets)
import subprocess  # noqa: F401  (re-exported for patch targets)
import sys  # noqa: F401  (re-exported for patch targets)

from tools.validators.yaml import *  # noqa: F401,F403
from tools.validators.yaml import YAMLValidator, main

__all__ = ["YAMLValidator", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
