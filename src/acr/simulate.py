"""Simulate weekly channel data and subscribers for the coffee retailer.

The planted values are written to data/truth.json for the tests.
Analysis code must never read that file.
"""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

N_WEEKS = 156
FIRST_WEEK = date(2023, 1, 2)
DECISION_DATE = date(2025, 12, 29)
CONTRIBUTION_PER_MONTH = 11
MONTH_DAYS = 30.4375
SPEND_SHOCK_SD = 0.05
DID_FIRST_WEEK = 79
DID_LAST_WEEK = 90
DID_SPEND_MULTIPLIER = 1.5
TRUE_ELASTICITY = 0.5

CHANNELS: list[dict] = [
    {
        "channel": "paid_search",
        "A": 150,
        "S": 4250,
        "phi": 0.3,
        "sigma_e": 0.04,
        "p1": 0.30,
        "h": 0.06,
        "variable_cost_per_signup": 15,
        "fixed_monthly_cost": 2000,
        "launch_week": 1,
        "intended_call": "FUND",
    },
    {
        "channel": "paid_social",
        "A": 120,
        "S": 6850,
        "phi": 0.3,
        "sigma_e": 0.04,
        "p1": 0.45,
        "h": 0.09,
        "variable_cost_per_signup": 15,
        "fixed_monthly_cost": 3000,
        "launch_week": 1,
        "intended_call": "CUT",
    },
    {
        "channel": "affiliate",
        "A": 80,
        "S": 3485,
        "phi": 0.3,
        "sigma_e": 0.04,
        "p1": 0.50,
        "h": 0.12,
        "variable_cost_per_signup": 35,
        "fixed_monthly_cost": 1500,
        "launch_week": 1,
        "intended_call": "CUT",
    },
    {
        "channel": "referral",
        "A": 60,
        "S": 595,
        "phi": 0.3,
        "sigma_e": 0.04,
        "p1": 0.20,
        "h": 0.03,
        "variable_cost_per_signup": 30,
        "fixed_monthly_cost": 800,
        "launch_week": 1,
        "intended_call": "FUND",
    },
    {
        "channel": "direct_mail",
        "A": 40,
        "S": 1855,
        "phi": 0.0,
        "sigma_e": 0.35,
        "p1": 0.35,
        "h": 0.07,
        "variable_cost_per_signup": 15,
        "fixed_monthly_cost": 1000,
        "launch_week": 1,
        "intended_call": "HOLD",
    },
    {
        "channel": "podcast",
        "A": 30,
        "S": 1465,
        "phi": 0.5,
        "sigma_e": 0.08,
        "p1": 0.30,
        "h": 0.07,
        "variable_cost_per_signup": 15,
        "fixed_monthly_cost": 1000,
        "launch_week": 143,
        "intended_call": "HOLD",
    },
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def seasonal_index() -> np.ndarray:
    """Seasonal index s(p) for p = 0..51. The mean is exactly 1."""
    p = np.arange(52, dtype=float)
    g = 0.10 * np.cos(2.0 * math.pi * p / 52.0)
    g = g + 0.15 * ((p >= 46.0) & (p <= 51.0))
    g = g + 0.08 * (p <= 2.0)
    raw = np.exp(g)
    return raw / raw.mean()


def cumulative_active_months(p1: float, h: float, k: int) -> float:
    """Expected active months in the first k months, for k >= 1."""
    total = 1.0
    factor = 1.0
    for _ in range(k - 1):
        total += (1.0 - p1) * factor
        factor *= 1.0 - h
    return total


def channel_truth(spec: dict) -> dict:
    p1 = float(spec["p1"])
    h = float(spec["h"])
    annual_signups = int(spec["A"]) * 52
    annual_cost = (
        52 * int(spec["S"])
        + annual_signups * int(spec["variable_cost_per_signup"])
        + 12 * int(spec["fixed_monthly_cost"])
    )
    active_12 = cumulative_active_months(p1, h, 12)
    value = CONTRIBUTION_PER_MONTH * active_12
    cost_per_signup = annual_cost / annual_signups
    payback: int | str = "over 12 months"
    for k in range(1, 13):
        covered = CONTRIBUTION_PER_MONTH * cumulative_active_months(p1, h, k)
        if covered >= cost_per_signup:
            payback = k
            break
    phi = float(spec["phi"])
    sigma_e = float(spec["sigma_e"])
    sigma_u = sigma_e / math.sqrt(1.0 - phi * phi)
    return {
        "channel": spec["channel"],
        "A": int(spec["A"]),
        "S": int(spec["S"]),
        "phi": phi,
        "sigma_e": sigma_e,
        "sigma_u": sigma_u,
        "p1": p1,
        "h": h,
        "variable_cost_per_signup": int(spec["variable_cost_per_signup"]),
        "fixed_monthly_cost": int(spec["fixed_monthly_cost"]),
        "launch_week": int(spec["launch_week"]),
        "E": active_12,
        "V": value,
        "annual_signups": annual_signups,
        "annual_cost": annual_cost,
        "R": annual_signups * value / annual_cost,
        "net": annual_signups * value - annual_cost,
        "payback_month": payback,
        "intended_call": spec["intended_call"],
    }


def build_truth(seed: int) -> dict:
    return {
        "seed": int(seed),
        "decision_date": DECISION_DATE.isoformat(),
        "n_weeks": N_WEEKS,
        "first_week_start": FIRST_WEEK.isoformat(),
        "contribution_per_month": CONTRIBUTION_PER_MONTH,
        "month_length_days": MONTH_DAYS,
        "spend_shock_sd": SPEND_SHOCK_SD,
        "did_weeks": [DID_FIRST_WEEK, DID_LAST_WEEK],
        "did_spend_multiplier": DID_SPEND_MULTIPLIER,
        "did_true_log_effect": TRUE_ELASTICITY * math.log(DID_SPEND_MULTIPLIER),
        "true_elasticity": TRUE_ELASTICITY,
        "seasonal": {
            "period": 52,
            "cos_weight": 0.10,
            "high_season_weight": 0.15,
            "high_season_p": [46, 51],
            "early_weight": 0.08,
            "early_p_max": 2,
        },
        "channels": [channel_truth(spec) for spec in CHANNELS],
    }


def _draw_noise(rng: np.random.Generator, phi: float, sigma_e: float) -> np.ndarray:
    sigma_u = sigma_e / math.sqrt(1.0 - phi * phi)
    noise = np.empty(N_WEEKS, dtype=float)
    noise[0] = rng.normal(0.0, sigma_u)
    innovations = rng.normal(0.0, sigma_e, size=N_WEEKS - 1)
    for i in range(N_WEEKS - 1):
        noise[i + 1] = phi * noise[i] + innovations[i]
    return noise


def _simulate_channel(
    spec: dict,
    rng: np.random.Generator,
    seasonal: np.ndarray,
    week_starts: list[date],
    next_id: int,
) -> tuple[pd.DataFrame, pd.DataFrame | None, int]:
    name = spec["channel"]
    level = float(spec["A"])
    base_spend = float(spec["S"])
    phi = float(spec["phi"])
    sigma_e = float(spec["sigma_e"])
    p1 = float(spec["p1"])
    hazard = float(spec["h"])
    launch = int(spec["launch_week"])

    sigma_u = sigma_e / math.sqrt(1.0 - phi * phi)
    noise = _draw_noise(rng, phi, sigma_e)

    weeks = np.arange(launch, N_WEEKS + 1)
    kept = weeks - 1
    shock = rng.normal(0.0, SPEND_SHOCK_SD, size=len(weeks))
    raw_spend = base_spend * np.exp(shock)
    if name == "paid_social":
        bumped = (weeks >= DID_FIRST_WEEK) & (weeks <= DID_LAST_WEEK)
        raw_spend = np.where(bumped, raw_spend * DID_SPEND_MULTIPLIER, raw_spend)
    spend = np.rint(raw_spend).astype(np.int64)

    period = (weeks - 1) % 52
    mu = level * seasonal[period] * np.sqrt(spend / base_spend)
    lam = mu * np.exp(noise[kept] - (sigma_u ** 2) / 2.0)
    signups = rng.poisson(lam).astype(np.int64)

    weekly = pd.DataFrame(
        {
            "channel": name,
            "week": weeks.astype(int),
            "week_start": [week_starts[int(t) - 1] for t in weeks],
            "spend": spend,
            "signups": signups,
        }
    )

    n = int(signups.sum())
    if n == 0:
        return weekly, None, next_id

    week_index = np.repeat(np.arange(len(weeks)), signups)
    day_offset = rng.integers(0, 7, size=n)
    retain = rng.random(size=n)
    paid_months = np.ones(n, dtype=np.int64)
    geometric_rows = retain >= p1
    n_geometric = int(geometric_rows.sum())
    if n_geometric:
        paid_months[geometric_rows] = 1 + rng.geometric(hazard, size=n_geometric)

    base_dates = np.array(
        [week_starts[int(t) - 1] for t in weeks],
        dtype="datetime64[D]",
    )
    signup = base_dates[week_index] + day_offset.astype("timedelta64[D]")
    day_count = (np.datetime64(DECISION_DATE, "D") - signup).astype(np.int64)
    m_obs = np.floor(day_count / MONTH_DAYS).astype(np.int64)
    months_paid = np.minimum(paid_months, m_obs + 1)
    cancelled = paid_months <= m_obs

    subscribers = pd.DataFrame(
        {
            "subscriber_id": np.arange(next_id, next_id + n, dtype=np.int64),
            "channel": name,
            "signup_date": signup,
            "months_paid": months_paid,
            "cancelled": cancelled.astype(bool),
        }
    )
    return weekly, subscribers, next_id + n


def generate(seed: int = 2026, output_dir: Path | None = None) -> Path:
    """Write the simulated files. Uses one numpy generator for the whole run."""
    out = Path(output_dir) if output_dir is not None else project_root() / "data"
    out.mkdir(parents=True, exist_ok=True)

    truth = build_truth(seed)
    seasonal = seasonal_index()
    week_starts = [FIRST_WEEK + timedelta(days=7 * (t - 1)) for t in range(1, N_WEEKS + 1)]

    rng = np.random.default_rng(seed)
    weekly_parts: list[pd.DataFrame] = []
    subscriber_parts: list[pd.DataFrame] = []
    next_id = 1
    for spec in CHANNELS:
        weekly, subscribers, next_id = _simulate_channel(
            spec, rng, seasonal, week_starts, next_id
        )
        weekly_parts.append(weekly)
        if subscribers is not None:
            subscriber_parts.append(subscribers)

    weekly = pd.concat(weekly_parts, ignore_index=True)
    if subscriber_parts:
        subscribers = pd.concat(subscriber_parts, ignore_index=True)
    else:
        subscribers = pd.DataFrame(
            columns=["subscriber_id", "channel", "signup_date", "months_paid", "cancelled"]
        )

    costs = pd.DataFrame(
        {
            "channel": [spec["channel"] for spec in CHANNELS],
            "variable_cost_per_signup": [
                spec["variable_cost_per_signup"] for spec in CHANNELS
            ],
            "fixed_monthly_cost": [spec["fixed_monthly_cost"] for spec in CHANNELS],
            "contribution_per_month": CONTRIBUTION_PER_MONTH,
        }
    )

    weekly.to_csv(out / "weekly_channel.csv", index=False)
    subscribers.to_parquet(out / "subscribers.parquet", index=False)
    costs.to_csv(out / "channel_costs.csv", index=False)
    with (out / "truth.json").open("w", encoding="utf-8") as handle:
        json.dump(truth, handle, indent=2)
        handle.write("\n")
    return out


def main() -> None:
    written = generate(seed=2026)
    print(f"Wrote simulated data to {written}")


if __name__ == "__main__":
    main()
