"""Recovery checks for the retention life table and 12-month value."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from acr.retention import life_table, value_draws

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs" / "tables"
LONG_HISTORY = [
    "affiliate",
    "direct_mail",
    "paid_search",
    "paid_social",
    "referral",
]


def _planted() -> dict[str, dict]:
    payload = json.loads((ROOT / "data" / "truth.json").read_text(encoding="utf-8"))
    return {row["channel"]: row for row in payload["channels"]}


def _estimated(frame: pd.DataFrame) -> pd.Series:
    return frame["estimated"].astype(str).str.lower().isin(["true", "1", "1.0"])


def test_unknown_months_are_null_and_estimated_months_have_enough_risk():
    life = life_table()
    estimated = _estimated(life)
    assert (life.loc[estimated, "at_risk"] >= 30).all()
    assert life.loc[~estimated, "hazard"].isna().all()


def test_long_history_channels_recover_planted_retention():
    life = life_table()
    value_draws(life=life)
    summary = pd.read_csv(TABLES / "value_summary.csv")
    planted = _planted()

    for channel in LONG_HISTORY:
        part = life.loc[life["channel"] == channel]
        month1 = float(part.loc[part["month"] == 1, "hazard"].iloc[0])
        p1 = float(planted[channel]["p1"])
        gap1 = abs(month1 - p1)
        assert gap1 <= 0.03, f"{channel} month 1 hazard {month1:.4f} vs p1 {p1:.4f}"

        later = part.loc[part["month"].between(2, 11), "hazard"]
        assert later.notna().all(), f"{channel} has an unknown hazard in months 2 to 11"
        mean_hazard = float(later.mean())
        h = float(planted[channel]["h"])
        gap_h = abs(mean_hazard - h)
        assert gap_h <= 0.015, f"{channel} mean hazard {mean_hazard:.4f} vs h {h:.4f}"

        median_v = float(summary.loc[summary["channel"] == channel, "V_median"].iloc[0])
        true_v = float(planted[channel]["V"])
        relative = abs(median_v - true_v) / true_v
        assert relative <= 0.04, (
            f"{channel} V_median {median_v:.3f} vs V {true_v:.3f} relative gap {relative:.3%}"
        )


def test_podcast_value_range_covers_the_planted_value():
    life = life_table()
    podcast = life.loc[life["channel"] == "podcast"]
    unknown = int((~_estimated(podcast)).sum())
    assert unknown >= 6, unknown

    value_draws(life=life)
    summary = pd.read_csv(TABLES / "value_summary.csv")
    row = summary.loc[summary["channel"] == "podcast"].iloc[0]
    true_v = float(_planted()["podcast"]["V"])
    assert float(row["V_p5"]) <= true_v <= float(row["V_p95"]), (
        f"podcast V {true_v:.3f} outside {row['V_p5']:.3f} to {row['V_p95']:.3f}"
    )


def test_each_channel_has_2000_draws_inside_the_value_bounds():
    draws = value_draws()
    counts = draws.groupby("channel").size()
    assert (counts == 2000).all()
    assert len(counts) == 6
    assert draws["V"].between(11, 132).all()


def test_value_draws_are_identical_across_runs():
    first = value_draws()
    second = value_draws()
    pd.testing.assert_frame_equal(first, second)
