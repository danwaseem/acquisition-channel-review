#!/usr/bin/env bash
# Run the full acquisition channel review pipeline from the repo root.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Sync Python environment"
uv sync

echo "==> Simulate weekly channel and subscriber data"
uv run python -m acr.simulate

echo "==> Build retention life table and 12-month value draws"
uv run python -m acr.retention

echo "==> Back-test seasonal forecast variants in R"
Rscript r/backtest.R

echo "==> Fit final 52-week forecasts in R"
Rscript r/forecast.R

echo "==> Estimate paid social spend change in R"
Rscript r/did.R

echo "==> Score channels and apply fund, cut or hold rules"
uv run python -m acr.decide

echo "==> Build charts"
uv run python -m acr.charts

echo "==> Build the stakeholder deck"
uv run python -m acr.deck

echo "==> Run tests"
uv run pytest -q

echo "==> Done"
