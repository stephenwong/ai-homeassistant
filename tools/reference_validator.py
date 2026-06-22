#!/usr/bin/env python3
"""Backward-compat shim. Implementation moved to tools.validators.references."""

import argparse  # noqa: F401  (re-exported for patch targets)
import concurrent.futures  # noqa: F401  (re-exported for patch targets)
import json  # noqa: F401  (re-exported for patch targets)
import re  # noqa: F401  (re-exported for patch targets)

# Importing yaml here ensures `patch("tools.reference_validator.yaml")` resolves.
import yaml  # noqa: F401

from tools.validators.references import *  # noqa: F401,F403
from tools.validators.references import ReferenceValidator, main

__all__ = ["ReferenceValidator", "main"]

if __name__ == "__main__":
    main()
