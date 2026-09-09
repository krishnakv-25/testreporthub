#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
pip install -e . >/dev/null

# Collect every fixture and write a unified report.
trh collect tests/fixtures -o demo-report.html

echo "✓ Wrote demo-report.html — open it in a browser."