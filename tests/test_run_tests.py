"""Tests for tools/run_tests.py — backward-compat shim.

The original ValidationTestRunner has been removed. ``run_tests.py`` is now a
thin shim that delegates to ``ha_cli validate``. Tests here verify:
  - The module imports cleanly.
  - main() dispatches to ha_cli and propagates exit codes.
  - SystemExit propagation works for direct script execution.
"""

from unittest.mock import patch

import pytest


def test_module_imports():
    """Sanity check: importing the module should not fail."""
    import tools.run_tests

    assert hasattr(tools.run_tests, "main")
    assert callable(tools.run_tests.main)


def test_main_delegates_to_ha_cli_validate():
    """main() should invoke ha_cli.main with ["validate", ...]."""
    from tools.run_tests import main

    with patch("tools.run_tests.ha_cli_main", return_value=0) as mock_ha_cli:
        result = main()
    assert result == 0
    mock_ha_cli.assert_called_once()
    # First arg is a list whose first element is "validate"
    call_args = mock_ha_cli.call_args[0][0]
    assert call_args[0] == "validate"


def test_main_propagates_argv_arguments():
    """Extra CLI args should pass through after the "validate" subcommand."""
    from tools.run_tests import main

    with (
        patch("sys.argv", ["run_tests.py", "config", "--quiet"]),
        patch("tools.run_tests.ha_cli_main", return_value=0) as mock_ha_cli,
    ):
        main()
    call_args = mock_ha_cli.call_args[0][0]
    assert call_args == ["validate", "config", "--quiet"]


def test_main_propagates_failure_exit_code():
    """A non-zero return from ha_cli.main should propagate."""
    from tools.run_tests import main

    with patch("tools.run_tests.ha_cli_main", return_value=1):
        result = main()
    assert result == 1


def test_main_propagates_success_exit_code():
    from tools.run_tests import main

    with patch("tools.run_tests.ha_cli_main", return_value=0):
        result = main()
    assert result == 0


def test_main_under_name_main(monkeypatch):
    """``python tools/run_tests.py`` invokes main() and exits with its code."""
    monkeypatch.setattr("sys.argv", ["run_tests.py"])
    with (
        patch("tools.run_tests.ha_cli_main", return_value=0) as mock_ha_cli,
        pytest.raises(SystemExit) as exc,
    ):
        # Simulate running the file as __main__.
        import tools.run_tests

        # The `if __name__ == "__main__"` guard runs sys.exit(main()).
        # We replicate that here by calling main and exiting.
        code = tools.run_tests.main()
        raise SystemExit(code)
    assert exc.value.code == 0
    mock_ha_cli.assert_called_once()


def test_run_tests_end_to_end_via_subprocess(tmp_path):
    """Smoke test: invoking run_tests.py via subprocess should not crash.

    Uses a real (empty) config dir so the validators run for real. We only
    care that the shim dispatches and the process exits cleanly with 0/1.
    """
    import subprocess
    import sys

    (tmp_path / "configuration.yaml").write_text("homeassistant:\n  name: Test\n")
    result = subprocess.run(
        [sys.executable, "tools/run_tests.py", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode in (0, 1), (
        f"Expected exit 0 or 1, got {result.returncode}. stderr: {result.stderr[:500]}"
    )
