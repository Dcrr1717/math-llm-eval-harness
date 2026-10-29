#!/usr/bin/env bash
# Full evaluation sweep: all three datasets x all three models, then report + dashboard.
# Each run has a hard cost cap as a safety net. Re-runs are free (cached).
set -euo pipefail
cd "$(dirname "$0")/.."

MODELS="${MODELS:-opus,sonnet,haiku}"
GSM_LIMIT="${GSM_LIMIT:-200}"
MATH_LIMIT="${MATH_LIMIT:-200}"
MAXCOST="${MAXCOST:-30}"

echo "== own (custom set) =="
python -m src.cli run --dataset own                      --models "$MODELS" --max-cost "$MAXCOST"
echo "== gsm8k =="
python -m src.cli run --dataset gsm8k --limit "$GSM_LIMIT"  --models "$MODELS" --max-cost "$MAXCOST"
echo "== math =="
python -m src.cli run --dataset math  --limit "$MATH_LIMIT" --models "$MODELS" --max-cost "$MAXCOST"

echo "== report + dashboard =="
python -m src.cli report
python -m src.cli dashboard
echo "Done. See results/summary.json and results/dashboard.html"
