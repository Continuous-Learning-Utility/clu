"""C# validation via dotnet build against Unity DLL references."""

import os
import re
import shutil
import subprocess
import logging

from validation.project_generator import generate_validation_csproj

logger = logging.getLogger(__name__)


class CSharpValidator:
    """
    Validates C# code by running dotnet build against a minimal .csproj
    that references Unity DLLs.
    """

    def __init__(
        self,
        unity_dll_path: str,
        dotnet_path: str = "dotnet",
        validation_timeout: int = 30,
        lang_version: str = "9.0",
        target_framework: str = "netstandard2.1",
    ):
        self.unity_dll_path = unity_dll_path
        self.dotnet_path = dotnet_path
        self.validation_timeout = validation_timeout
        self.lang_version = lang_version
        self.target_framework = target_framework
        self._cache_dir: str | None = None
        self._restored = False

    def setup_cache(self, project_path: str):
        """
        Set up the validation cache directory and generate/restore the .csproj.

        Call this once at agent startup for performance.
        """
        self._cache_dir = os.path.join(project_path, ".agent_validation_temp")
        csproj_path = os.path.join(self._cache_dir, "Validate.csproj")

        if not os.path.isfile(csproj_path):
            generate_validation_csproj(
                csproj_path,
                self.unity_dll_path,
                self.lang_version,
                self.target_framework,
            )

        # Run dotnet restore once
        if not self._restored:
            try:
                subprocess.run(
                    [self.dotnet_path, "restore", csproj_path],
                    capture_output=True,
                    text=True,
                    timeout=self.validation_timeout,
                    cwd=self._cache_dir,
                )
                self._restored = True
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.warning("dotnet restore failed: %s", e)

    def validate(self, code: str, project_path: str) -> dict:
        """
        Validate C# code.

        Args:
            code: C# source code to validate.
            project_path: Unity project root (used for cache directory).

        Returns:
            {"valid": bool, "errors": list[str], "warnings": list[str]}
        """
        if self._cache_dir is None:
            self.setup_cache(project_path)

        temp_cs = os.path.join(self._cache_dir, "Validate.cs")
        csproj_path = os.path.join(self._cache_dir, "Validate.csproj")

        # Write the code to the temp file
        with open(temp_cs, "w", encoding="utf-8") as f:
            f.write(code)

        # Clean previous build artifacts to avoid stale results
        bin_dir = os.path.join(self._cache_dir, "bin")
        obj_dir = os.path.join(self._cache_dir, "obj")
        for d in [bin_dir]:
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)

        try:
            result = subprocess.run(
                [self.dotnet_path, "build", csproj_path, "--no-restore"],
                capture_output=True,
                text=True,
                timeout=self.validation_timeout,
                cwd=self._cache_dir,
            )

            output = result.stdout + "\n" + result.stderr
            errors = self._parse_errors(output)
            warnings = self._parse_warnings(output)

            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings[:5],
            }

        except subprocess.TimeoutExpired:
            return {
                "valid": False,
                "errors": ["Validation timed out"],
                "warnings": [],
            }
        except FileNotFoundError:
            return {
                "valid": False,
                "errors": [f"dotnet not found at: {self.dotnet_path}"],
                "warnings": [],
            }

    def cleanup(self):
        """Remove the validation cache directory."""
        if self._cache_dir and os.path.isdir(self._cache_dir):
            shutil.rmtree(self._cache_dir, ignore_errors=True)

    @staticmethod
    def _parse_errors(output: str) -> list[str]:
        errors = []
        for line in output.split("\n"):
            if ": error CS" in line:
                # Clean up the path to show just the error
                match = re.search(r"error CS\d+: .+", line)
                if match:
                    errors.append(match.group())
                else:
                    errors.append(line.strip())
        return errors

    @staticmethod
    def _parse_warnings(output: str) -> list[str]:
        warnings = []
        for line in output.split("\n"):
            if ": warning CS" in line:
                match = re.search(r"warning CS\d+: .+", line)
                if match:
                    warnings.append(match.group())
                else:
                    warnings.append(line.strip())
        return warnings
