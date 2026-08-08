#!/usr/bin/env bash
# ============================================================
#  CV Attendance System - Linux/macOS Launcher
#  Usage:  bash run.sh   (or  chmod +x run.sh && ./run.sh)
# ============================================================
set -euo pipefail

echo "========================================="
echo "  CV Attendance System - Unified Launcher"
echo "========================================="

# Check if Python 3 is available
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: Python 3 not found. Please install Python 3.11+"
    exit 1
fi

# Run the unified Python launcher with all arguments passed through
exec python3 run.py "$@"
