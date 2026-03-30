#!/bin/bash
# Manual Python quality check runner
# Runs the same checks as make lint + mypy
#
# Usage: .claude-code/hooks/run-python-quality.sh

set -e

echo "Running full Python quality checks..."

echo "Checking formatting..."
uv run ruff format --check tools/ tests/

echo "Running linter..."
uv run ruff check tools/ tests/

echo "Running type checker..."
uv run mypy tools/ || echo "mypy found issues (non-blocking)"

echo "All checks complete."
