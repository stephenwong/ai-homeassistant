#!/usr/bin/env python3
"""Test suite runner for Home Assistant configuration validation.

Runs all validators and provides a comprehensive report.
"""

import argparse
import concurrent.futures
import importlib.util
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


class ValidationTestRunner:
    """Runs all validation tests and reports results."""

    def __init__(self, config_dir: str = "config"):
        """Initialize the test runner."""
        self.config_dir = Path(config_dir).resolve()
        self.tools_dir = Path(__file__).parent
        self.venv_dir = self.tools_dir.parent / ".venv"
        self.results: dict[str, dict[str, Any]] = {}

    def get_python_executable(self) -> str:
        """Get the Python executable from venv if available."""
        venv_python = self.venv_dir / "bin" / "python"
        if venv_python.exists():
            return str(venv_python)
        return sys.executable

    def run_validator(
        self, script_name: str, description: str
    ) -> tuple[bool, str, str, float]:
        """Run a single validator script."""
        script_path = self.tools_dir / script_name
        if not script_path.exists():
            return False, "", f"Script {script_name} not found", 0.0

        python_exe = self.get_python_executable()
        cmd = [python_exe, str(script_path), str(self.config_dir)]

        start_time = time.time()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            end_time = time.time()
            duration = end_time - start_time

            return (
                result.returncode == 0,
                result.stdout,
                result.stderr,
                duration,
            )

        except subprocess.TimeoutExpired:
            end_time = time.time()
            duration = end_time - start_time
            return (
                False,
                "",
                "Validator timed out after 120 seconds",
                duration,
            )

        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            return (False, "", f"Failed to run validator: {e}", duration)

    def run_all_tests(self) -> bool:
        """Run all validation tests in parallel."""
        validators = [
            ("yaml_validator.py", "YAML Syntax Validation"),
            ("reference_validator.py", "Entity/Device Reference Validation"),
            (
                "ha_official_validator.py",
                "Official Home Assistant Configuration Validation",
            ),
        ]

        print("🔍 Running Home Assistant Configuration Validation Tests")
        print("=" * 60)
        print()
        print("Running all validators in parallel...")
        print()

        overall_start = time.time()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_list = [
                (
                    script_name,
                    description,
                    executor.submit(self.run_validator, script_name, description),
                )
                for script_name, description in validators
            ]

            all_passed = True
            for script_name, description, future in future_list:
                passed, stdout, stderr, duration = future.result()

                self.results[script_name] = {
                    "description": description,
                    "passed": passed,
                    "stdout": stdout,
                    "stderr": stderr,
                    "duration": duration,
                }

                if passed:
                    print(f"  ✅ {description}: PASSED ({duration:.2f}s)")
                else:
                    print(f"  ❌ {description}: FAILED ({duration:.2f}s)")
                    all_passed = False

        overall_duration = time.time() - overall_start
        print()
        print(f"Total execution time: {overall_duration:.2f}s (parallel)")
        print("=" * 60)

        return all_passed

    def print_detailed_results(self):
        """Print detailed results for each validator."""
        for _script_name, result in self.results.items():
            print(f"\n📋 {result['description']}")
            print("-" * 50)

            if result["passed"]:
                print("Status: ✅ PASSED")
            else:
                print("Status: ❌ FAILED")

            print(f"Duration: {result['duration']:.2f}s")

            if result["stdout"].strip():
                print("\nOutput:")
                for line in result["stdout"].strip().split("\n"):
                    print(f"  {line}")

            if result["stderr"].strip():
                print("\nErrors:")
                for line in result["stderr"].strip().split("\n"):
                    print(f"  {line}")

            print()

    def print_summary(self):
        """Print test summary."""
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results.values() if r["passed"])
        failed_tests = total_tests - passed_tests

        print("\n📊 TEST SUMMARY")
        print("=" * 30)
        print(f"Total tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")

        if failed_tests == 0:
            print("\n🎉 All tests passed! Your Home Assistant configuration is valid.")
        else:
            print(
                f"\n⚠️  {failed_tests} test(s) failed. Please review the errors above."
            )

        print()

    def check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        required_modules = ["yaml", "voluptuous", "jsonschema"]
        missing_modules = [
            module
            for module in required_modules
            if importlib.util.find_spec(module) is None
        ]

        if missing_modules:
            python_exe = self.get_python_executable()
            modules_str = ", ".join(missing_modules)
            print(f"❌ Missing required Python modules: {modules_str}")
            print("Please install them with:")
            modules_to_install = " ".join(missing_modules)
            print(f"  {python_exe} -m pip install {modules_to_install}")
            return False

        return True

    def run(self) -> bool:
        """Run the complete test suite."""
        if not self.config_dir.exists():
            print(f"❌ Config directory not found: {self.config_dir}")
            return False

        if not self.check_dependencies():
            return False

        all_passed = self.run_all_tests()

        self.print_detailed_results()
        self.print_summary()

        return all_passed


def main():
    """Run main function for command line usage."""
    parser = argparse.ArgumentParser(
        description="Run all Home Assistant configuration validation tests."
    )
    parser.add_argument(
        "config_dir",
        nargs="?",
        default="config",
        help="Path to the config directory (default: config)",
    )
    args = parser.parse_args()

    runner = ValidationTestRunner(args.config_dir)
    success = runner.run()

    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
