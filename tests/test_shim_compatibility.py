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


@pytest.mark.parametrize(
    "shim,class_name,ref_class",
    [
        (yaml_shim, "YAMLValidator", YAMLValidator),
        (reference_shim, "ReferenceValidator", ReferenceValidator),
        (ha_official_shim, "HAOfficialValidator", HAOfficialValidator),
    ],
)
def test_shim_exposes_class(shim, class_name, ref_class):
    assert getattr(shim, class_name) is ref_class


@pytest.mark.parametrize(
    "shim,main_name,ref_main",
    [
        (yaml_shim, "main", yaml_main),
        (reference_shim, "main", reference_main),
        (ha_official_shim, "main", ha_official_main),
    ],
)
def test_shim_exposes_main(shim, main_name, ref_main):
    assert callable(getattr(shim, main_name))
    assert getattr(shim, main_name) is ref_main


def test_yaml_shim_subprocess_attribute():
    """`patch('tools.yaml_validator.subprocess.run')` must resolve."""
    assert yaml_shim.subprocess is subprocess


def test_yaml_shim_argparse_attribute():
    assert yaml_shim.argparse is argparse


def test_ha_official_shim_subprocess_attribute():
    """`patch('tools.ha_official_validator.subprocess.run')` must resolve."""
    assert ha_official_shim.subprocess is subprocess


@pytest.mark.parametrize(
    "cls",
    [
        YAMLValidator,
        ReferenceValidator,
        HAOfficialValidator,
    ],
)
def test_shim_quiet_kwarg(cls):
    v = cls(quiet=True)
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
