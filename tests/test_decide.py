"""Recovery and consistency checks for the cost-benefit decisions."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs" / "tables"


def _planted() -> dict[str, dict]:
    payload = json.loads((ROOT / "data" / "truth.json").read_text(encoding="utf-8"))
    return {row["channel"]: row for row in payload["channels"]}


def _recompute_channel_metrics(channel: str) -> dict[str, float]:
    paths = (
        pd.read_parquet(TABLES / "forecast_paths.parquet")
        .loc[lambda frame: frame["channel"] == channel]
        .sort_values("draw")
    )
    values = (
        pd.read_parquet(TABLES / "value_draws.parquet")
        .loc[lambda frame: frame["channel"] == channel]
        .sort_values("draw")
    )
    planned = float(
        pd.read_csv(TABLES / "forecast_summary.csv")
        .set_index("channel")
        .loc[channel, "planned_weekly_spend"]
    )
    costs = pd.read_csv(ROOT / "data" / "channel_costs.csv").set_index("channel")
    variable_cost = float(costs.loc[channel, "variable_cost_per_signup"])
    fixed_monthly = float(costs.loc[channel, "fixed_monthly_cost"])

    n_draws = paths["total_signups"].to_numpy(dtype=float)
    v_draws = values["V"].to_numpy(dtype=float)
    cost_draws = 52.0 * planned + n_draws * variable_cost + 12.0 * fixed_monthly
    r_draws = n_draws * v_draws / cost_draws
    net_draws = n_draws * v_draws - cost_draws
    return {
        "R_p5": float(np.percentile(r_draws, 5)),
        "R_median": float(np.percentile(r_draws, 50)),
        "R_p95": float(np.percentile(r_draws, 95)),
        "net_median": float(np.percentile(net_draws, 50)),
    }


def test_calls_match_intended_calls():
    decisions = pd.read_csv(TABLES / "decisions.csv")
    planted = _planted()
    for _, row in decisions.iterrows():
        assert row["call"] == planted[row["channel"]]["intended_call"]


def test_calls_match_the_percentile_rule():
    decisions = pd.read_csv(TABLES / "decisions.csv")
    for _, row in decisions.iterrows():
        if row["R_p5"] >= 1.0:
            expected = "FUND"
        elif row["R_p95"] < 1.0:
            expected = "CUT"
        else:
            expected = "HOLD"
        assert row["call"] == expected


def test_r_draws_match_decisions():
    draws = pd.read_parquet(TABLES / "r_draws.parquet")
    decisions = pd.read_csv(TABLES / "decisions.csv")
    assert (draws.groupby("channel").size() == 2000).all()
    for _, row in decisions.iterrows():
        channel = row["channel"]
        recomputed = _recompute_channel_metrics(channel)
        for key in ("R_p5", "R_median", "R_p95", "net_median"):
            got = float(row[key])
            want = recomputed[key]
            denom = max(abs(want), 1e-12)
            assert abs(got - want) / denom <= 1e-9, (channel, key, got, want)


def test_rank_follows_net_median():
    decisions = pd.read_csv(TABLES / "decisions.csv")
    nets = decisions["net_median"].tolist()
    assert nets == sorted(nets, reverse=True)
    assert decisions["rank"].tolist() == list(range(1, len(decisions) + 1))


def test_hold_breakeven_churn_lies_in_the_other_channel_range():
    hold = pd.read_csv(TABLES / "hold_detail.csv")
    for _, row in hold.iterrows():
        if int(row["months_unknown"]) == 0:
            assert pd.isna(row["breakeven_churn_unknown_months"])
            assert pd.isna(row["lowest_other_churn"])
            assert pd.isna(row["highest_other_churn"])
            continue
        churn = float(row["breakeven_churn_unknown_months"])
        low = float(row["lowest_other_churn"])
        high = float(row["highest_other_churn"])
        assert low <= churn <= high, (row["channel"], low, churn, high)


def test_budget_scenario_adds_up():
    decisions = pd.read_csv(TABLES / "decisions.csv")
    budget = pd.read_csv(TABLES / "budget_scenario.csv")
    summary = budget.set_index("channel")
    stop = float(summary.loc["stop_cut_channels", "extra_net_median"])
    redirect = float(summary.loc["redirect_to_fund_channels", "extra_net_median"])
    combined = float(summary.loc["cut_and_redirect", "extra_net_median"])
    assert abs(combined - (stop + redirect)) <= 1e-9

    fund = decisions.loc[decisions["call"] == "FUND", "channel"].tolist()
    cut = decisions.loc[decisions["call"] == "CUT", "channel"].tolist()
    planned = (
        pd.read_csv(TABLES / "forecast_summary.csv")
        .set_index("channel")["planned_weekly_spend"]
        .astype(float)
    )
    fund_rows = budget.loc[budget["channel"].isin(fund)]
    freed = float(sum(52.0 * planned.loc[ch] for ch in cut))
    old_fund = float(sum(52.0 * planned.loc[ch] for ch in fund))
    new_fund = float((fund_rows["new_weekly_spend"] * 52.0).sum())
    assert abs(new_fund - (old_fund + freed)) / max(old_fund + freed, 1e-12) <= 1e-9
