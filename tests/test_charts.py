"""Checks that the chart CLI writes the expected PNG files."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from acr.charts import make_all_charts

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "outputs" / "figures"

EXPECTED = {
    "forecast_by_channel.png": (2400, 1400),
    "backtest_error.png": (1600, 900),
    "backtest_bands.png": (1600, 900),
    "did_gap.png": (1600, 900),
    "ratio_ranges.png": (1600, 900),
    "net_contribution.png": (1600, 900),
    "retention_curves.png": (1600, 900),
    "budget_change.png": (1600, 900),
}


def test_chart_cli_writes_all_pngs_at_the_expected_size():
    make_all_charts()
    for name, size in EXPECTED.items():
        path = FIGURES / name
        assert path.exists(), name
        assert path.stat().st_size > 20_000, (name, path.stat().st_size)
        with Image.open(path) as image:
            assert image.size == size, (name, image.size)
