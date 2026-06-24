"""Re-import tests for moved validators under tools/validators/."""

from tools.validators.duplicate_ids import DuplicateIDValidator
from tools.validators.ha_official import HAOfficialValidator
from tools.validators.references import ReferenceValidator
from tools.validators.services import ServiceValidator
from tools.validators.templates import TemplateValidator
from tools.validators.yaml import YAMLValidator
from tools.validators.yaml import main as yaml_main


def test_yaml_validator_import():
    v = YAMLValidator()
    assert v.validator_name == "YAML syntax"
    assert v.errors == []
    assert v.warnings == []
    assert v.info == []


def test_duplicate_id_validator_import():
    v = DuplicateIDValidator()
    assert v.validator_name == "Duplicate automation IDs"
    assert v.errors == []
    assert v.warnings == []
    assert v.info == []


def test_duplicate_id_validator_quiet_kwarg_accepted():
    v = DuplicateIDValidator(quiet=True)
    assert v.quiet is True


def test_yaml_validator_quiet_kwarg_accepted():
    v = YAMLValidator(quiet=True)
    assert v.quiet is True


def test_reference_validator_import():
    v = ReferenceValidator()
    assert v.validator_name == "Entity/device references"


def test_reference_validator_quiet_kwarg_accepted():
    v = ReferenceValidator(quiet=True)
    assert v.quiet is True


def test_service_validator_import():
    v = ServiceValidator()
    assert v.validator_name == "Service references"
    assert v.errors == []
    assert v.warnings == []
    assert v.info == []


def test_service_validator_quiet_kwarg_accepted():
    v = ServiceValidator(quiet=True)
    assert v.quiet is True


def test_ha_official_validator_import():
    v = HAOfficialValidator()
    assert v.validator_name == "Home Assistant configuration"


def test_ha_official_validator_quiet_kwarg_accepted():
    v = HAOfficialValidator(quiet=True)
    assert v.quiet is True


def test_template_validator_import():
    v = TemplateValidator()
    assert v.validator_name == "Jinja2 templates"
    assert v.errors == []
    assert v.warnings == []
    assert v.info == []


def test_template_validator_quiet_kwarg_accepted():
    v = TemplateValidator(quiet=True)
    assert v.quiet is True


def test_yaml_module_main_callable():
    assert callable(yaml_main)


class TestFileDeps:
    def test_yaml_validator_file_deps_yaml_files(self):
        """YAMLValidator depends on top-level YAML files (base class default)."""
        v = YAMLValidator()
        deps = v.file_deps()
        assert "*.yaml" in deps
        assert "*.yml" in deps

    def test_reference_validator_file_deps_includes_storage(self):
        """ReferenceValidator depends on YAML files + .storage registries."""
        v = ReferenceValidator()
        deps = v.file_deps()
        assert "*.yaml" in deps
        assert ".storage/core.entity_registry" in deps
        assert ".storage/core.device_registry" in deps
        assert ".storage/core.area_registry" in deps

    def test_duplicate_id_validator_file_deps(self):
        """DuplicateIDValidator only reads automations.yaml (cacheable)."""
        v = DuplicateIDValidator()
        deps = v.file_deps()
        assert "automations.yaml" in deps
        assert len(deps) == 1

    def test_service_validator_file_deps(self):
        """ServiceValidator returns empty deps (depends on live HA)."""
        v = ServiceValidator()
        deps = v.file_deps()
        assert deps == []

    def test_template_validator_file_deps(self):
        """TemplateValidator returns empty deps (depends on live HA)."""
        v = TemplateValidator()
        deps = v.file_deps()
        assert deps == []

    def test_ha_official_validator_file_deps(self):
        """HAOfficialValidator returns empty deps (result depends on HA env)."""
        v = HAOfficialValidator()
        deps = v.file_deps()
        assert deps == []

    def test_file_deps_returns_strings(self):
        for cls in [
            YAMLValidator,
            DuplicateIDValidator,
            ServiceValidator,
            TemplateValidator,
            ReferenceValidator,
            HAOfficialValidator,
        ]:
            v = cls()
            deps = v.file_deps()
            assert isinstance(deps, list)
            for d in deps:
                assert isinstance(d, str)
