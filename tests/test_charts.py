"""Checks that the chart CLI writes the expected PNG files."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from PIL import Image

from acr.charts import channel_name, make_all_charts, waterfall_segments

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "outputs" / "figures"
TABLES = ROOT / "outputs" / "tables"

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


def test_waterfall_segments_follow_the_budget_scenario():
    budget = pd.read_csv(TABLES / "budget_scenario.csv").set_index("channel")
    decisions = pd.read_csv(TABLES / "decisions.csv")
    fund = decisions.loc[decisions["call"] == "FUND", "channel"].tolist()

    stop = float(budget.loc["stop_cut_channels", "extra_net_median"])
    paid_search = float(budget.loc["paid_search", "extra_net_median"])
    referral = float(budget.loc["referral", "extra_net_median"])
    total = float(budget.loc["cut_and_redirect", "extra_net_median"])

    steps = [
        ("Stop paid social and affiliate", stop),
        (channel_name("paid_search"), paid_search),
        (channel_name("referral"), referral),
        ("Net change", total),
    ]
    segments = waterfall_segments(steps)
    by_label = {label: (start, end) for label, start, end in segments}

    assert by_label["Stop paid social and affiliate"] == (0.0, stop)
    paid_start, paid_end = by_label[channel_name("paid_search")]
    assert paid_start == stop
    assert paid_end == stop + paid_search
    ref_start, ref_end = by_label[channel_name("referral")]
    assert ref_start == paid_end
    assert ref_end == paid_end + referral
    assert abs(ref_end - total) <= 1e-6
    assert by_label["Net change"] == (0.0, total)
    assert fund == ["paid_search", "referral"]
