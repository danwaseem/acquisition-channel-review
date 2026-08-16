"""Checks for the simulated coffee-subscription data."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from acr.simulate import generate, seasonal_index

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LONG_HISTORY = ["paid_search", "paid_social", "affiliate", "referral", "direct_mail"]
SIGNUPS_PER_WEEK = {
    "paid_search": 150,
    "paid_social": 120,
    "affiliate": 80,
    "referral": 60,
    "direct_mail": 40,
}


def _weekly() -> pd.DataFrame:
    frame = pd.read_csv(DATA / "weekly_channel.csv", parse_dates=["week_start"])
    return frame


def _spend_ratio(frame: pd.DataFrame, channel: str) -> float:
    rows = frame[frame["channel"] == channel]
    post = rows[rows["week"].between(79, 90)]["spend"].mean()
    pre = rows[rows["week"].between(53, 78)]["spend"].mean()
    return float(post / pre)


def _m_obs(signup_date: pd.Series) -> pd.Series:
    days = (pd.Timestamp("2025-12-29") - pd.to_datetime(signup_date)).dt.days
    values = np.floor(days.to_numpy(dtype=float) / 30.4375).astype(int)
    return pd.Series(values, index=signup_date.index)


def test_weekly_file_shape_and_calendar():
    frame = _weekly()
    assert len(frame) == 794
    assert list(frame.columns) == ["channel", "week", "week_start", "spend", "signups"]
    assert frame["week_start"].min() == pd.Timestamp("2023-01-02")
    assert frame["week_start"].max() == pd.Timestamp("2025-12-22")

    for channel in LONG_HISTORY:
        rows = frame[frame["channel"] == channel].sort_values("week")
        assert rows["week"].tolist() == list(range(1, 157))
        assert rows["week_start"].iloc[0] == pd.Timestamp("2023-01-02")
        assert rows["week_start"].iloc[-1] == pd.Timestamp("2025-12-22")

    podcast = frame[frame["channel"] == "podcast"].sort_values("week")
    assert podcast["week"].tolist() == list(range(143, 157))
    assert len(podcast) == 14
    expected_start = pd.Timestamp("2023-01-02") + pd.Timedelta(days=7 * 142)
    assert podcast["week_start"].iloc[0] == expected_start


def test_seasonal_index_averages_one():
    index = seasonal_index()
    assert len(index) == 52
    assert abs(float(index.mean()) - 1.0) < 1e-9


def test_spend_shift_is_limited_to_paid_social():
    frame = _weekly()
    social = _spend_ratio(frame, "paid_social")
    assert 1.4 <= social <= 1.6
    for channel in ["paid_search", "affiliate", "referral", "direct_mail"]:
        ratio = _spend_ratio(frame, channel)
        assert 0.95 <= ratio <= 1.05, (channel, ratio)


def test_long_history_signups_stay_near_the_planted_level():
    frame = _weekly()
    for channel, level in SIGNUPS_PER_WEEK.items():
        mean_signups = float(frame.loc[frame["channel"] == channel, "signups"].mean())
        ratio = mean_signups / level
        assert 0.90 <= ratio <= 1.10, (channel, ratio)


def test_subscriber_counts_match_signups():
    weekly = _weekly()
    subscribers = pd.read_parquet(DATA / "subscribers.parquet")
    for channel, total in weekly.groupby("channel")["signups"].sum().items():
        found = int((subscribers["channel"] == channel).sum())
        assert found == int(total)


def test_censoring_rules():
    subscribers = pd.read_parquet(DATA / "subscribers.parquet")
    assert (subscribers["months_paid"] >= 1).all()
    observed = _m_obs(subscribers["signup_date"])
    cancelled = subscribers["cancelled"].astype(bool)
    assert (subscribers.loc[cancelled, "months_paid"].to_numpy() <= observed[cancelled].to_numpy()).all()
    active = ~cancelled
    assert (
        subscribers.loc[active, "months_paid"].to_numpy() == observed[active].to_numpy() + 1
    ).all()


def test_planted_ratios_match_the_calls():
    truth = json.loads((DATA / "truth.json").read_text(encoding="utf-8"))
    by_channel = {row["channel"]: row for row in truth["channels"]}
    assert by_channel["paid_search"]["R"] >= 1.5
    assert by_channel["referral"]["R"] >= 1.5
    assert by_channel["paid_social"]["R"] <= 0.70
    assert by_channel["affiliate"]["R"] <= 0.70
    assert abs(by_channel["direct_mail"]["R"] - 1.0) <= 0.01
    assert abs(by_channel["podcast"]["R"] - 1.0) <= 0.01


def test_generate_is_identical_across_runs(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate(2026, first)
    generate(2026, second)

    weekly_first = pd.read_csv(first / "weekly_channel.csv")
    weekly_second = pd.read_csv(second / "weekly_channel.csv")
    pd.testing.assert_frame_equal(weekly_first, weekly_second)

    subs_first = pd.read_parquet(first / "subscribers.parquet")
    subs_second = pd.read_parquet(second / "subscribers.parquet")
    pd.testing.assert_frame_equal(subs_first, subs_second)

    costs_first = pd.read_csv(first / "channel_costs.csv")
    costs_second = pd.read_csv(second / "channel_costs.csv")
    pd.testing.assert_frame_equal(costs_first, costs_second)

    truth_first = json.loads((first / "truth.json").read_text(encoding="utf-8"))
    truth_second = json.loads((second / "truth.json").read_text(encoding="utf-8"))
    assert truth_first == truth_second


def test_analysis_sources_do_not_name_the_planted_file():
    offenders: list[str] = []
    for folder in (ROOT / "src" / "acr", ROOT / "r"):
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            if path.name == "simulate.py":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "truth" in text:
                offenders.append(str(path))
    assert offenders == []
