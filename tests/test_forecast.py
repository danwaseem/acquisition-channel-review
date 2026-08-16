"""Checks for the final 52-week forecasts."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from acr.io import ensure_forecast_paths_parquet

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs" / "tables"
STEADY = ["paid_search", "paid_social", "affiliate", "referral"]
WIDE = ["direct_mail", "podcast"]


@pytest.fixture(scope="module")
def forecast_paths() -> pd.DataFrame:
    path = ensure_forecast_paths_parquet(TABLES)
    return pd.read_parquet(path)


def _planted() -> dict[str, dict]:
    payload = json.loads((ROOT / "data" / "truth.json").read_text(encoding="utf-8"))
    return {row["channel"]: row for row in payload["channels"]}


def _true_seasonal_log() -> np.ndarray:
    p = np.arange(52, dtype=float)
    g = 0.10 * np.cos(2.0 * math.pi * p / 52.0)
    g = g + 0.15 * ((p >= 46.0) & (p <= 51.0))
    g = g + 0.08 * (p <= 2.0)
    raw = np.exp(g)
    seasonal = raw / raw.mean()
    log_index = np.log(seasonal)
    return log_index - log_index.mean()


def _flag(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower().isin(["true", "1", "1.0"])


def test_forecast_paths_cover_all_channels(forecast_paths: pd.DataFrame):
    counts = forecast_paths.groupby("channel").size()
    assert len(counts) == 6
    assert (counts == 2000).all()
    assert (forecast_paths["total_signups"] > 0).all()

    summary = pd.read_csv(TABLES / "forecast_summary.csv")
    for _, row in summary.iterrows():
        assert row["total_p5"] < row["total_median"] < row["total_p95"], row["channel"]


def test_forecast_weekly_calendar():
    weekly = pd.read_csv(TABLES / "forecast_weekly.csv", parse_dates=["week_start"])
    assert (weekly.groupby("channel").size() == 52).all()
    for channel, part in weekly.groupby("channel"):
        part = part.sort_values("week")
        assert part["week"].tolist() == list(range(157, 209)), channel
        assert part["week_start"].iloc[0] == pd.Timestamp("2025-12-29")


def test_medians_recover_expected_annual_signups():
    summary = pd.read_csv(TABLES / "forecast_summary.csv")
    planted = _planted()
    for _, row in summary.iterrows():
        channel = row["channel"]
        truth = planted[channel]
        expected = (
            truth["A"]
            * 52
            * math.sqrt(row["planned_weekly_spend"] / truth["S"])
        )
        relative = abs(row["total_median"] - expected) / expected
        limit = 0.15 if channel in WIDE else 0.05
        assert relative <= limit, (
            f"{channel}: median {row['total_median']:.1f} vs expected {expected:.1f} "
            f"relative gap {relative:.3%}"
        )


def test_noisy_and_short_channels_have_wider_ranges():
    summary = pd.read_csv(TABLES / "forecast_summary.csv")
    summary = summary.set_index("channel")
    width = (summary["total_p95"] - summary["total_p5"]) / summary["total_median"]
    for wide_channel in WIDE:
        for steady in STEADY:
            assert width[wide_channel] > width[steady], (
                f"{wide_channel} width {width[wide_channel]:.3f} "
                f"not above {steady} width {width[steady]:.3f}"
            )


def test_pooled_seasonal_matches_the_planted_pattern():
    pooled = pd.read_csv(TABLES / "pooled_seasonal.csv")
    assert len(pooled) == 52
    assert abs(float(pooled["log_index"].mean())) < 1e-10
    true = _true_seasonal_log()
    corr = float(np.corrcoef(pooled["log_index"].to_numpy(), true)[0, 1])
    assert corr > 0.85, corr


def test_methods_match_the_backtest_choices():
    summary = pd.read_csv(TABLES / "forecast_summary.csv")
    backtest = pd.read_csv(TABLES / "backtest_summary.csv")
    chosen = backtest.loc[_flag(backtest["chosen"]), ["channel", "variant"]]
    chosen_map = dict(zip(chosen["channel"], chosen["variant"], strict=True))
    for _, row in summary.iterrows():
        if row["channel"] == "podcast":
            assert row["method"] == "short_history"
        else:
            assert row["method"] == chosen_map[row["channel"]]
