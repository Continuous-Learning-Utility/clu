"""Tests for path sandboxing."""

import os
import pytest

# Add project root to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sandbox.path_validator import PathValidator
from orchestrator.exceptions import SandboxViolation


@pytest.fixture
def validator():
    return PathValidator()


@pytest.fixture
def project_root(tmp_path):
    """Create a temporary Unity-like project structure."""
    assets = tmp_path / "Assets" / "Scripts"
    assets.mkdir(parents=True)
    (assets / "Test.cs").write_text("// test")
    (tmp_path / "Library").mkdir()
    (tmp_path / "ProjectSettings").mkdir()
    return str(tmp_path)


class TestPathValidator:

    def test_valid_assets_path(self, validator, project_root):
        path = os.path.join(project_root, "Assets", "Scripts", "Test.cs")
        assert validator.validate(path, project_root) is True

    def test_valid_assets_directory(self, validator, project_root):
        path = os.path.join(project_root, "Assets", "Scripts")
        assert validator.validate(path, project_root) is True

    def test_reject_library_path(self, validator, project_root):
        path = os.path.join(project_root, "Library", "something.dll")
        with pytest.raises(SandboxViolation, match="(?i)assets/"):
            validator.validate(path, project_root)

    def test_reject_project_settings(self, validator, project_root):
        path = os.path.join(project_root, "ProjectSettings", "settings.asset")
        with pytest.raises(SandboxViolation, match="(?i)assets/"):
            validator.validate(path, project_root)

    def test_reject_path_outside_project(self, validator, project_root):
        path = os.path.abspath(os.path.join(project_root, "..", "other_project", "file.cs"))
        with pytest.raises(SandboxViolation, match="escapes project root"):
            validator.validate(path, project_root)

    def test_reject_directory_traversal(self, validator, project_root):
        path = os.path.join(project_root, "Assets", "..", "Library", "file.dll")
        with pytest.raises(SandboxViolation):
            validator.validate(path, project_root)

    def test_validate_relative_returns_absolute(self, validator, project_root):
        result = validator.validate_relative("Assets/Scripts/Test.cs", project_root)
        assert os.path.isabs(result)
        assert result.endswith("Test.cs")

    def test_validate_relative_rejects_library(self, validator, project_root):
        with pytest.raises(SandboxViolation):
            validator.validate_relative("Library/file.dll", project_root)

    def test_validate_relative_rejects_root_file(self, validator, project_root):
        with pytest.raises(SandboxViolation):
            validator.validate_relative("settings.json", project_root)


class TestPathValidatorCustomPrefix:
    """Tests for config-driven source directory prefix."""

    def test_custom_prefix_accepts(self, tmp_path):
        """Validator with custom prefix should accept files under that prefix."""
        src = tmp_path / "src" / "main"
        src.mkdir(parents=True)
        (src / "app.py").write_text("# app")
        validator = PathValidator(allowed_prefix="src")
        path = os.path.join(str(tmp_path), "src", "main", "app.py")
        assert validator.validate(path, str(tmp_path)) is True

    def test_custom_prefix_rejects_other(self, tmp_path):
        """Validator with custom prefix should reject files outside that prefix."""
        (tmp_path / "lib").mkdir()
        validator = PathValidator(allowed_prefix="src")
        path = os.path.join(str(tmp_path), "lib", "file.py")
        with pytest.raises(SandboxViolation, match="src/"):
            validator.validate(path, str(tmp_path))

    def test_empty_prefix_allows_all(self, tmp_path):
        """Validator with empty prefix should allow any path within the project."""
        (tmp_path / "anywhere").mkdir()
        (tmp_path / "anywhere" / "file.txt").write_text("hi")
        validator = PathValidator(allowed_prefix="")
        path = os.path.join(str(tmp_path), "anywhere", "file.txt")
        assert validator.validate(path, str(tmp_path)) is True

    def test_custom_blocklist(self, tmp_path):
        """Validator should respect custom blocked prefixes."""
        (tmp_path / "src" / "vendor").mkdir(parents=True)
        validator = PathValidator(allowed_prefix="src", blocked_prefixes=["src/vendor"])
        path = os.path.join(str(tmp_path), "src", "vendor", "lib.py")
        with pytest.raises(SandboxViolation, match="blocked"):
            validator.validate(path, str(tmp_path))
