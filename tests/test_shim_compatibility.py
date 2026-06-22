"""Regression tests verifying backward-compat shims expose the same public API.

Locks the contract documented in the v3 migration plan: old module paths must
still resolve `subprocess`, `main`, and the validator class. Protects against
future `__all__` additions silently breaking patch targets in other tests.
"""

import argparse
import subprocess

import pytest

import tools.ha_official_validator as ha_official_shim
import tools.reference_validator as reference_shim
import tools.yaml_validator as yaml_shim
from tools.ha_official_validator import HAOfficialValidator
from tools.ha_official_validator import main as ha_official_main
from tools.reference_validator import ReferenceValidator
from tools.reference_validator import main as reference_main
from tools.yaml_validator import YAMLValidator
from tools.yaml_validator import main as yaml_main


def test_yaml_shim_exposes_class():
    assert yaml_shim.YAMLValidator is YAMLValidator


def test_yaml_shim_exposes_main():
    assert callable(yaml_shim.main)
    assert yaml_shim.main is yaml_main


def test_yaml_shim_subprocess_attribute():
    """`patch('tools.yaml_validator.subprocess.run')` must resolve."""
    assert yaml_shim.subprocess is subprocess


def test_yaml_shim_argparse_attribute():
    assert yaml_shim.argparse is argparse


def test_reference_shim_exposes_class():
    assert reference_shim.ReferenceValidator is ReferenceValidator


def test_reference_shim_exposes_main():
    assert callable(reference_shim.main)
    assert reference_shim.main is reference_main


def test_ha_official_shim_exposes_class():
    assert ha_official_shim.HAOfficialValidator is HAOfficialValidator


def test_ha_official_shim_exposes_main():
    assert callable(ha_official_shim.main)
    assert ha_official_shim.main is ha_official_main


def test_ha_official_shim_subprocess_attribute():
    """`patch('tools.ha_official_validator.subprocess.run')` must resolve.

    Verified by tests/test_ha_official_validator.py lines 36, 167, 179, 186,
    194, 202, 226 — all use this dotted path.
    """
    assert ha_official_shim.subprocess is subprocess


def test_yaml_validator_quiet_kwarg_via_shim():
    """End-to-end: construct via old path with quiet kwarg."""
    v = YAMLValidator(quiet=True)
    assert v.quiet is True


def test_reference_validator_quiet_kwarg_via_shim():
    v = ReferenceValidator(quiet=True)
    assert v.quiet is True


def test_ha_official_validator_quiet_kwarg_via_shim():
    v = HAOfficialValidator(quiet=True)
    assert v.quiet is True


def test_shim_main_dispatches(monkeypatch):
    """`python tools/yaml_validator.py` (no args) still dispatches to main."""
    import sys

    monkeypatch.setattr(sys, "argv", ["tools/yaml_validator.py"])
    with pytest.raises(SystemExit) as excinfo:
        yaml_main()
    # SystemExit code is either 0 (valid) or 1 (invalid config) — both are fine,
    # we just need to confirm dispatch works.
    assert excinfo.value.code in (0, 1)
