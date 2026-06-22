#!/usr/bin/env python3
"""Backward-compat shim. Implementation moved to tools.ha_cli.

``python tools/run_tests.py`` is equivalent to ``python tools/ha_cli.py validate``.
The ValidationTestRunner class has been removed — its functionality moved to
tools.commands.validate.run_validators() (in-process, parallel threads).
"""

import sys

from tools.ha_cli import main as ha_cli_main


def main() -> int:
    """Delegate to ``ha_cli validate``. Returns process exit code."""
    # Prepend "validate" so argparse dispatches correctly.
    return ha_cli_main(["validate", *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
