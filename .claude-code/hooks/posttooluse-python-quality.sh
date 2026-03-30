#!/bin/bash
# Post-tool-use hook: Python code quality checks after editing Python files
# Runs ruff (format + lint) and mypy on tools/ and tests/ directories

# Only run in projects with our Python setup
if [ ! -f "pyproject.toml" ] || [ ! -d "tools" ]; then
    exit 0
fi

# Check if uv is available
if ! command -v uv >/dev/null 2>&1; then
    exit 0
fi

# Read stdin to check if the edited file is a Python file in scope
file_path=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)
if [ -z "$file_path" ]; then
    exit 0
fi

case "$file_path" in
    */tools/*.py|*/tests/*.py) ;;
    *) exit 0 ;;
esac

echo "Running Python quality checks..."

FAILED=0

# 1. Formatting check
if ! uv run ruff format --check tools/ tests/ 2>&1; then
    echo "Formatting issues found. Run: make lint-fix"
    FAILED=1
fi

# 2. Lint check
if ! uv run ruff check tools/ tests/ 2>&1; then
    echo "Lint issues found. Run: make lint-fix"
    FAILED=1
fi

# 3. Type checking (non-blocking)
if ! uv run mypy tools/ 2>&1; then
    echo "mypy found type issues (non-blocking)"
fi

if [ $FAILED -eq 0 ]; then
    echo "All Python quality checks passed."
fi

exit 0
