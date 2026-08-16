"""Checks for the R forecast back-test. This file does not run R."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs" / "tables"
SIMPLICITY = ["snaive", "fourier", "fourier_spend"]


def _flag(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower().isin(["true", "1", "1.0"])


def _chosen_variant(metrics: pd.DataFrame, channel: str) -> str:
    part = metrics.loc[metrics["channel"] == channel]
    mean_mape = part.groupby("variant")["mape"].mean()
    best = float(mean_mape.min())
    eligible = [
        name for name in SIMPLICITY if float(mean_mape[name]) <= best + 0.5
    ]
    return eligible[0]


def test_backtest_files_have_the_long_history_grid():
    metrics = pd.read_csv(TABLES / "backtest_metrics.csv")
    forecasts = pd.read_csv(TABLES / "backtest_forecasts.csv")
    assert len(metrics) == 60
    assert len(forecasts) == 780
    assert "podcast" not in set(metrics["channel"])
    assert "podcast" not in set(forecasts["channel"])


def test_mape_is_positive_and_coverage_is_a_share():
    metrics = pd.read_csv(TABLES / "backtest_metrics.csv")
    assert (metrics["mape"] > 0).all()
    assert metrics["coverage80"].between(0, 1).all()


def test_one_chosen_variant_follows_the_simplicity_rule():
    metrics = pd.read_csv(TABLES / "backtest_metrics.csv")
    summary = pd.read_csv(TABLES / "backtest_summary.csv")
    chosen = _flag(summary["chosen"])
    assert chosen.groupby(summary["channel"]).sum().eq(1).all()
    for channel in summary["channel"].unique():
        picked = summary.loc[
            (summary["channel"] == channel) & chosen, "variant"
        ].iloc[0]
        assert picked == _chosen_variant(metrics, channel), channel


def test_widen_flag_follows_the_coverage_rule():
    summary = pd.read_csv(TABLES / "backtest_summary.csv")
    chosen = _flag(summary["chosen"])
    widen = _flag(summary["widen"])
    expected = chosen & (summary["coverage80"] < 0.65)
    assert widen.reset_index(drop=True).equals(expected.reset_index(drop=True))


def test_paid_social_spend_fold_splits_the_variants():
    planted = json.loads((ROOT / "data" / "truth.json").read_text(encoding="utf-8"))
    window_start, window_end = planted["did_weeks"]
    echo_weeks = set(range(int(window_start) + 52, int(window_end) + 52 + 1))
    forecast_weeks = set(range(131, 144))
    assert echo_weeks <= forecast_weeks

    metrics = pd.read_csv(TABLES / "backtest_metrics.csv")
    fold = metrics[
        (metrics["channel"] == "paid_social") & (metrics["train_end_week"] == 130)
    ]
    snaive = float(fold.loc[fold["variant"] == "snaive", "total_pct_error"].iloc[0])
    with_spend = float(
        fold.loc[fold["variant"] == "fourier_spend", "total_pct_error"].iloc[0]
    )
    assert snaive > 10, snaive
    assert abs(with_spend) < 10, with_spend
