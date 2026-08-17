"""Cost-benefit draws, FUND/CUT/HOLD calls, and the budget scenario."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

CONTRIBUTION_PER_MONTH = 11


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _tables_dir() -> Path:
    return project_root() / "outputs" / "tables"


def _call_from_r(r_p5: float, r_p95: float) -> str:
    if r_p5 >= 1.0:
        return "FUND"
    if r_p95 < 1.0:
        return "CUT"
    return "HOLD"


def _payback_month(survival: np.ndarray, cost_per_signup: float) -> int | str:
    cumulative = 0.0
    for month in range(1, 13):
        cumulative += float(survival[month - 1])
        if CONTRIBUTION_PER_MONTH * cumulative >= cost_per_signup:
            return month
    return "over 12 months"


def _value_from_hazards(hazards: np.ndarray) -> float:
    survival = np.empty(12, dtype=float)
    survival[0] = 1.0
    for month in range(11):
        survival[month + 1] = survival[month] * (1.0 - hazards[month])
    return CONTRIBUTION_PER_MONTH * float(survival.sum())


def _is_estimated(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower().isin(["true", "1", "1.0"])


def _breakeven_churn(
    life: pd.DataFrame,
    channel: str,
    breakeven_v: float,
) -> tuple[float | None, float | None, float | None]:
    """Solve for one shared unknown-month hazard that hits break-even V."""
    part = life.loc[life["channel"] == channel].sort_values("month")
    estimated = _is_estimated(part["estimated"])
    unknown_months = part.loc[~estimated, "month"].astype(int).tolist()
    if not unknown_months:
        return None, None, None

    hazards = np.full(11, np.nan, dtype=float)
    for _, row in part.loc[estimated].iterrows():
        hazards[int(row["month"]) - 1] = float(row["hazard"])

    other = life.loc[
        (life["channel"] != channel)
        & _is_estimated(life["estimated"])
        & life["month"].isin(unknown_months),
        "hazard",
    ].astype(float)
    lowest = float(other.min()) if len(other) else None
    highest = float(other.max()) if len(other) else None

    def value_at(churn: float) -> float:
        draw = hazards.copy()
        for month in unknown_months:
            draw[month - 1] = churn
        return _value_from_hazards(draw)

    # Higher churn lowers V. Bracket the root.
    low, high = 0.0, 0.999999
    v_low = value_at(low)
    v_high = value_at(high)
    if breakeven_v >= v_low:
        return 0.0, lowest, highest
    if breakeven_v <= v_high:
        return high, lowest, highest

    for _ in range(80):
        mid = 0.5 * (low + high)
        if value_at(mid) > breakeven_v:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high), lowest, highest


def decide(
    tables_dir: Path | None = None,
    data_dir: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tables = tables_dir or _tables_dir()
    data = data_dir or project_root() / "data"

    forecast_paths = pd.read_parquet(tables / "forecast_paths.parquet")
    value_draws = pd.read_parquet(tables / "value_draws.parquet")
    forecast_summary = pd.read_csv(tables / "forecast_summary.csv")
    value_summary = pd.read_csv(tables / "value_summary.csv")
    life_table = pd.read_csv(tables / "life_table.csv")
    did = pd.read_csv(tables / "did_translation.csv").iloc[0]
    costs = pd.read_csv(data / "channel_costs.csv")

    elasticity = float(did["elasticity"])
    planned = forecast_summary.set_index("channel")["planned_weekly_spend"].astype(float)
    values = value_summary.set_index("channel")
    cost_map = costs.set_index("channel")

    channels = sorted(planned.index.tolist())
    decision_rows: list[dict] = []
    hold_rows: list[dict] = []
    r_parts: list[pd.DataFrame] = []
    channel_draws: dict[str, dict[str, np.ndarray]] = {}

    for channel in channels:
        paths = (
            forecast_paths.loc[forecast_paths["channel"] == channel]
            .sort_values("draw")
            .reset_index(drop=True)
        )
        values_ch = (
            value_draws.loc[value_draws["channel"] == channel]
            .sort_values("draw")
            .reset_index(drop=True)
        )
        if not paths["draw"].equals(values_ch["draw"]):
            raise ValueError(f"draw ids do not align for {channel}")

        n_draws = paths["total_signups"].to_numpy(dtype=float)
        v_draws = values_ch["V"].to_numpy(dtype=float)
        weekly_spend = float(planned.loc[channel])
        variable_cost = float(cost_map.loc[channel, "variable_cost_per_signup"])
        fixed_monthly = float(cost_map.loc[channel, "fixed_monthly_cost"])

        cost_draws = 52.0 * weekly_spend + n_draws * variable_cost + 12.0 * fixed_monthly
        r_draws = n_draws * v_draws / cost_draws
        net_draws = n_draws * v_draws - cost_draws
        cost_per_signup_draws = cost_draws / n_draws

        r_p5 = float(np.percentile(r_draws, 5))
        r_median = float(np.percentile(r_draws, 50))
        r_p95 = float(np.percentile(r_draws, 95))
        net_p5 = float(np.percentile(net_draws, 5))
        net_median = float(np.percentile(net_draws, 50))
        net_p95 = float(np.percentile(net_draws, 95))
        signups_median = float(np.percentile(n_draws, 50))
        cost_median = float(np.percentile(cost_draws, 50))
        cost_per_signup = float(np.percentile(cost_per_signup_draws, 50))
        v_median = float(values.loc[channel, "V_median"])

        call = _call_from_r(r_p5, r_p95)
        survival = values.loc[channel, [f"s{k}" for k in range(1, 13)]].to_numpy(
            dtype=float
        )
        payback = _payback_month(survival, cost_per_signup)
        marginal = (
            elasticity
            * signups_median
            * (v_median - variable_cost)
            / (52.0 * weekly_spend)
        )

        decision_rows.append(
            {
                "channel": channel,
                "call": call,
                "signups_median": signups_median,
                "V_median": v_median,
                "cost_median": cost_median,
                "cost_per_signup": cost_per_signup,
                "R_p5": r_p5,
                "R_median": r_median,
                "R_p95": r_p95,
                "net_p5": net_p5,
                "net_median": net_median,
                "net_p95": net_p95,
                "payback_month": payback,
                "marginal_return_per_dollar": marginal,
            }
        )
        r_parts.append(
            pd.DataFrame(
                {
                    "channel": channel,
                    "draw": paths["draw"].to_numpy(dtype=np.int64),
                    "R": r_draws,
                    "net": net_draws,
                }
            )
        )
        channel_draws[channel] = {
            "n": n_draws,
            "v": v_draws,
            "weekly_spend": np.full_like(n_draws, weekly_spend),
            "variable_cost": variable_cost,
            "fixed_monthly": fixed_monthly,
            "net": net_draws,
            "cost": cost_draws,
        }

        if call == "HOLD":
            months_unknown = int(values.loc[channel, "months_unknown"])
            breakeven_signups_per_week = (
                (52.0 * weekly_spend + 12.0 * fixed_monthly)
                / (v_median - variable_cost)
                / 52.0
            )
            breakeven_v = cost_median / signups_median
            churn, lowest, highest = _breakeven_churn(
                life_table, channel, breakeven_v
            )
            hold_rows.append(
                {
                    "channel": channel,
                    "months_unknown": months_unknown,
                    "signups_per_week_median": signups_median / 52.0,
                    "signups_per_week_p5": float(np.percentile(n_draws, 5)) / 52.0,
                    "signups_per_week_p95": float(np.percentile(n_draws, 95)) / 52.0,
                    "breakeven_signups_per_week": breakeven_signups_per_week,
                    "V_median": v_median,
                    "V_p5": float(values.loc[channel, "V_p5"]),
                    "V_p95": float(values.loc[channel, "V_p95"]),
                    "breakeven_V": breakeven_v,
                    "breakeven_churn_unknown_months": churn,
                    "lowest_other_churn": lowest,
                    "highest_other_churn": highest,
                }
            )

    decisions = pd.DataFrame(decision_rows)
    decisions = decisions.sort_values("net_median", ascending=False).reset_index(
        drop=True
    )
    decisions.insert(0, "rank", np.arange(1, len(decisions) + 1))

    hold_detail = pd.DataFrame(hold_rows)
    if len(hold_detail):
        order = decisions.loc[decisions["call"] == "HOLD", "channel"].tolist()
        hold_detail["channel"] = pd.Categorical(
            hold_detail["channel"], categories=order, ordered=True
        )
        hold_detail = hold_detail.sort_values("channel").reset_index(drop=True)
        hold_detail["channel"] = hold_detail["channel"].astype(str)

    r_draws_frame = pd.concat(r_parts, ignore_index=True)

    fund_channels = decisions.loc[decisions["call"] == "FUND", "channel"].tolist()
    cut_channels = decisions.loc[decisions["call"] == "CUT", "channel"].tolist()
    freed = float(sum(52.0 * float(planned.loc[ch]) for ch in cut_channels))
    fund_weekly_total = float(sum(float(planned.loc[ch]) for ch in fund_channels))

    budget_rows: list[dict] = []
    redirect_extra_by_draw: np.ndarray | None = None

    for channel in fund_channels:
        old_weekly = float(planned.loc[channel])
        share = old_weekly / fund_weekly_total if fund_weekly_total else 0.0
        new_weekly = old_weekly + (freed / 52.0) * share
        draws = channel_draws[channel]
        n_old = draws["n"]
        v = draws["v"]
        variable_cost = draws["variable_cost"]
        fixed_monthly = draws["fixed_monthly"]
        ratio = new_weekly / old_weekly
        n_new = n_old * (ratio**elasticity)
        net_old = n_old * v - (52.0 * old_weekly + n_old * variable_cost + 12.0 * fixed_monthly)
        net_new = n_new * v - (52.0 * new_weekly + n_new * variable_cost + 12.0 * fixed_monthly)
        extra_net = net_new - net_old
        extra_signups = n_new - n_old
        if redirect_extra_by_draw is None:
            redirect_extra_by_draw = extra_net.copy()
        else:
            redirect_extra_by_draw = redirect_extra_by_draw + extra_net
        budget_rows.append(
            {
                "channel": channel,
                "current_weekly_spend": old_weekly,
                "new_weekly_spend": new_weekly,
                "extra_signups_median": float(np.percentile(extra_signups, 50)),
                "extra_net_median": float(np.percentile(extra_net, 50)),
                "extra_net_p5": float(np.percentile(extra_net, 5)),
                "extra_net_p95": float(np.percentile(extra_net, 95)),
            }
        )

    stop_cut = -float(
        decisions.loc[decisions["call"] == "CUT", "net_median"].sum()
    )
    if redirect_extra_by_draw is None:
        redirect_p5 = np.nan
        redirect_p95 = np.nan
        redirect_reported = 0.0
    else:
        redirect_p5 = float(np.percentile(redirect_extra_by_draw, 5))
        redirect_p95 = float(np.percentile(redirect_extra_by_draw, 95))
        # Keep the identity required by the tests: summary medians add.
        redirect_reported = float(
            sum(row["extra_net_median"] for row in budget_rows)
        )
    cut_and_redirect = stop_cut + redirect_reported

    budget_rows.extend(
        [
            {
                "channel": "stop_cut_channels",
                "current_weekly_spend": np.nan,
                "new_weekly_spend": np.nan,
                "extra_signups_median": np.nan,
                "extra_net_median": stop_cut,
                "extra_net_p5": np.nan,
                "extra_net_p95": np.nan,
            },
            {
                "channel": "redirect_to_fund_channels",
                "current_weekly_spend": np.nan,
                "new_weekly_spend": np.nan,
                "extra_signups_median": np.nan,
                "extra_net_median": redirect_reported,
                "extra_net_p5": redirect_p5,
                "extra_net_p95": redirect_p95,
            },
            {
                "channel": "cut_and_redirect",
                "current_weekly_spend": np.nan,
                "new_weekly_spend": np.nan,
                "extra_signups_median": np.nan,
                "extra_net_median": cut_and_redirect,
                "extra_net_p5": np.nan,
                "extra_net_p95": np.nan,
            },
        ]
    )
    budget = pd.DataFrame(budget_rows)

    tables.mkdir(parents=True, exist_ok=True)
    decisions.to_csv(tables / "decisions.csv", index=False)
    hold_detail.to_csv(tables / "hold_detail.csv", index=False)
    budget.to_csv(tables / "budget_scenario.csv", index=False)
    r_draws_frame.to_parquet(tables / "r_draws.parquet", index=False)
    return decisions, hold_detail, budget, r_draws_frame


def main() -> None:
    decisions, _, budget, _ = decide()
    with pd.option_context(
        "display.max_columns",
        30,
        "display.width",
        220,
        "display.float_format",
        lambda value: f"{value:.4f}",
    ):
        print(decisions.to_string(index=False))
        print()
        print(budget.to_string(index=False))


if __name__ == "__main__":
    main()
