"""Regression tests verifying backward-compat shims expose the same public API.

Locks the contract documented in the v3 migration plan: old module paths must
still resolve `subprocess`, `main`, and the validator class. Protects against
future `__all__` additions silently breaking patch targets in other tests.
"""

import argparse
import subprocess

import pytest

import tools.duplicate_id_validator as duplicate_id_shim
import tools.ha_official_validator as ha_official_shim
import tools.reference_validator as reference_shim
import tools.service_validator as service_shim
import tools.template_validator as template_shim
import tools.yaml_validator as yaml_shim
from tools.duplicate_id_validator import DuplicateIDValidator
from tools.duplicate_id_validator import main as duplicate_id_main
from tools.ha_official_validator import HAOfficialValidator
from tools.ha_official_validator import main as ha_official_main
from tools.reference_validator import ReferenceValidator
from tools.reference_validator import main as reference_main
from tools.service_validator import ServiceValidator
from tools.service_validator import main as service_main
from tools.template_validator import TemplateValidator
from tools.template_validator import main as template_main
from tools.yaml_validator import YAMLValidator
from tools.yaml_validator import main as yaml_main


@pytest.mark.parametrize(
    "shim,class_name,ref_class",
    [
        (yaml_shim, "YAMLValidator", YAMLValidator),
        (reference_shim, "ReferenceValidator", ReferenceValidator),
        (ha_official_shim, "HAOfficialValidator", HAOfficialValidator),
        (duplicate_id_shim, "DuplicateIDValidator", DuplicateIDValidator),
        (service_shim, "ServiceValidator", ServiceValidator),
        (template_shim, "TemplateValidator", TemplateValidator),
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
        (duplicate_id_shim, "main", duplicate_id_main),
        (service_shim, "main", service_main),
        (template_shim, "main", template_main),
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
        DuplicateIDValidator,
        ServiceValidator,
        TemplateValidator,
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
    # main() returns int (no longer raises SystemExit)
    assert yaml_main() in (0, 1)


def test_duplicate_id_shim_main_dispatches(monkeypatch):
    """`python tools/duplicate_id_validator.py` (no args) dispatches to main."""
    import sys

    monkeypatch.setattr(sys, "argv", ["tools/duplicate_id_validator.py"])
    assert duplicate_id_main() in (0, 1)


def test_service_shim_main_dispatches(monkeypatch):
    """`python tools/service_validator.py` (no args) dispatches to main."""
    import sys

    monkeypatch.setattr(sys, "argv", ["tools/service_validator.py"])
    assert service_main() in (0, 1)


def test_template_shim_main_dispatches(monkeypatch):
    """`python tools/template_validator.py` (no args) dispatches to main."""
    import sys

    monkeypatch.setattr(sys, "argv", ["tools/template_validator.py"])
    assert template_main() in (0, 1)
