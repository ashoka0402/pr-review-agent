#!/bin/bash

# run_static_checks.sh
# Runs all static analysis checks for the PR Review Agent project

set -e  # Exit on first error

echo "========================================="
echo "  Running Static Analysis Checks"
echo "========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ $2 passed${NC}"
    else
        echo -e "${RED}✗ $2 failed${NC}"
    fi
}

# Track overall status
OVERALL_STATUS=0

# 1. Flake8 (Style and Error Checking)
echo "Running flake8..."
if flake8 app/ --max-line-length=120 --exclude=__pycache__,*.pyc,.git,venv,env; then
    print_status 0 "flake8"
else
    print_status 1 "flake8"
    OVERALL_STATUS=1
fi
echo ""

# 2. Pylint (Code Quality)
echo "Running pylint..."
if pylint app/ --max-line-length=120 --disable=C0111,R0903 --output-format=colorized; then
    print_status 0 "pylint"
else
    print_status 1 "pylint"
    OVERALL_STATUS=1
fi
echo ""

# 3. Bandit (Security Scanning)
echo "Running bandit (security scan)..."
if bandit -r app/ -f screen -ll; then
    print_status 0 "bandit"
else
    print_status 1 "bandit"
    OVERALL_STATUS=1
fi
echo ""

# 4. Radon (Complexity Analysis)
echo "Running radon (cyclomatic complexity)..."
echo "Files with complexity > 10:"
radon cc app/ -a -nb --min B
echo ""

echo "Running radon (maintainability index)..."
echo "Files with maintainability < 65:"
radon mi app/ -nb --min B
echo ""
print_status 0 "radon"

# 5. MyPy (Type Checking - optional)
if command -v mypy &> /dev/null; then
    echo "Running mypy (type checking)..."
    if mypy app/ --ignore-missing-imports --no-strict-optional; then
        print_status 0 "mypy"
    else
        print_status 1 "mypy"
        OVERALL_STATUS=1
    fi
    echo ""
fi

# 6. Black (Format Checking)
if command -v black &> /dev/null; then
    echo "Running black (format check)..."
    if black --check app/ --line-length 120; then
        print_status 0 "black format check"
    else
        echo -e "${YELLOW}⚠ black suggests formatting changes (run 'black app/' to fix)${NC}"
    fi
    echo ""
fi

# Summary
echo "========================================="
if [ $OVERALL_STATUS -eq 0 ]; then
    echo -e "${GREEN}All critical checks passed!${NC}"
else
    echo -e "${RED}Some checks failed. Please review output above.${NC}"
fi
echo "========================================="

exit $OVERALL_STATUS