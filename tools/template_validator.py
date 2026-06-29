#!/usr/bin/env python3
"""Backward-compat shim. Implementation moved to tools.validators.templates."""

import argparse  # noqa: F401  (re-exported for patch targets)
import re  # noqa: F401  (re-exported for patch targets)

from tools.validators.templates import *  # noqa: F401,F403
from tools.validators.templates import TemplateValidator, main

__all__ = ["TemplateValidator", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
