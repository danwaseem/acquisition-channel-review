"""Checks for the paid_social difference-in-differences."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs" / "tables"


def _planted() -> dict:
    return json.loads((ROOT / "data" / "truth.json").read_text(encoding="utf-8"))


def _flag(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower().isin(["true", "1", "1.0"])


def _recompute_translation(estimate: float) -> dict[str, float]:
    weekly = pd.read_csv(ROOT / "data" / "weekly_channel.csv")
    costs = pd.read_csv(ROOT / "data" / "channel_costs.csv")
    social = weekly.loc[weekly["channel"] == "paid_social"].sort_values("week")
    cost = costs.loc[costs["channel"] == "paid_social"].iloc[0]
    variable_cost = float(cost["variable_cost_per_signup"])
    fixed_monthly_cost = float(cost["fixed_monthly_cost"])

    pre = social.loc[social["week"].between(53, 78)]
    post = social.loc[social["week"].between(79, 90)]
    mean_pre_spend = float(pre["spend"].mean())
    mean_post_spend = float(post["spend"].mean())
    mean_pre_signups = float(pre["signups"].mean())
    mean_post_signups = float(post["signups"].mean())

    multiplier = math.exp(estimate)
    effect_pct = (multiplier - 1.0) * 100.0
    spend_ratio = mean_post_spend / mean_pre_spend
    extra_signups_per_week = mean_post_signups * (1.0 - 1.0 / multiplier)
    extra_spend_per_week = mean_post_spend - mean_pre_spend
    cost_per_extra_signup = (
        extra_spend_per_week + variable_cost * extra_signups_per_week
    ) / extra_signups_per_week
    avg_cost_per_signup_pre = (
        mean_pre_spend
        + variable_cost * mean_pre_signups
        + fixed_monthly_cost * 12.0 / 52.0
    ) / mean_pre_signups
    elasticity = estimate / math.log(spend_ratio)

    return {
        "multiplier": multiplier,
        "effect_pct": effect_pct,
        "mean_pre_spend": mean_pre_spend,
        "mean_post_spend": mean_post_spend,
        "mean_pre_signups": mean_pre_signups,
        "mean_post_signups": mean_post_signups,
        "spend_ratio": spend_ratio,
        "extra_signups_per_week": extra_signups_per_week,
        "extra_spend_per_week": extra_spend_per_week,
        "variable_cost_per_signup": variable_cost,
        "fixed_monthly_cost": fixed_monthly_cost,
        "cost_per_extra_signup": cost_per_extra_signup,
        "avg_cost_per_signup_pre": avg_cost_per_signup_pre,
        "elasticity": elasticity,
    }


def test_main_effect_recovers_the_planted_log_effect():
    results = pd.read_csv(TABLES / "did_results.csv")
    main = results.loc[results["test"] == "main"].iloc[0]
    assert not bool(_flag(pd.Series([main["ci_covers_zero"]])).iloc[0])
    true_log = float(_planted()["did_true_log_effect"])
    assert abs(float(main["estimate"]) - true_log) <= 0.10


def test_placebo_and_reversal_are_small():
    results = pd.read_csv(TABLES / "did_results.csv")
    for name in ("placebo", "reversal"):
        estimate = float(results.loc[results["test"] == name, "estimate"].iloc[0])
        assert abs(estimate) < 0.15, (name, estimate)


def test_spend_ratio_and_elasticity():
    translation = pd.read_csv(TABLES / "did_translation.csv").iloc[0]
    planted = _planted()
    assert 1.4 <= float(translation["spend_ratio"]) <= 1.6
    assert abs(float(translation["elasticity"]) - float(planted["true_elasticity"])) <= 0.25


def test_translation_matches_python_recompute():
    translation = pd.read_csv(TABLES / "did_translation.csv").iloc[0]
    expected = _recompute_translation(float(translation["estimate"]))
    for key, value in expected.items():
        got = float(translation[key])
        denom = max(abs(value), 1e-12)
        assert abs(got - value) / denom <= 1e-6, (key, got, value)

    log_ratio = math.log(float(translation["spend_ratio"]))
    assert abs(
        float(translation["elasticity_ci_low"])
        - float(translation["ci_low"]) / log_ratio
    ) / max(abs(float(translation["elasticity_ci_low"])), 1e-12) <= 1e-6
    assert abs(
        float(translation["elasticity_ci_high"])
        - float(translation["ci_high"]) / log_ratio
    ) / max(abs(float(translation["elasticity_ci_high"])), 1e-12) <= 1e-6


def test_weekly_gap_file():
    weekly = pd.read_csv(TABLES / "did_weekly.csv")
    assert len(weekly) == 50
    assert weekly["week"].tolist() == list(range(53, 103))
    pre = weekly.loc[weekly["week"].between(53, 78), "gap_vs_pre"]
    assert abs(float(pre.mean())) <= 1e-10
