"""Monthly life table and 12-month value per subscriber."""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

CONTRIBUTION_PER_MONTH = 11
HAZARD_MONTHS = 11

# Months 1..11 crossed with subscribers, then grouped to a life table.
# Month k hazard = cancels after k paid months / subscribers whose follow-up
# reaches month k. Below 30 people at risk, the hazard is unknown.
LIFE_TABLE_SQL = """
WITH months AS (
    SELECT generate_series::INTEGER AS month
    FROM generate_series(1, 11)
),
subscribers AS (
    SELECT channel, months_paid, cancelled
    FROM read_parquet(?)
),
exposure AS (
    SELECT
        subscribers.channel,
        months.month,
        CASE
            WHEN subscribers.months_paid >= months.month + 1
              OR (subscribers.cancelled AND subscribers.months_paid = months.month)
            THEN 1
            ELSE 0
        END AS at_risk_flag,
        CASE
            WHEN subscribers.cancelled AND subscribers.months_paid = months.month
            THEN 1
            ELSE 0
        END AS cancel_flag
    FROM subscribers
    CROSS JOIN months
)
SELECT
    channel,
    month,
    SUM(at_risk_flag)::BIGINT AS at_risk,
    SUM(cancel_flag)::BIGINT AS cancels,
    CASE
        WHEN SUM(at_risk_flag) >= 30
        THEN SUM(cancel_flag)::DOUBLE / SUM(at_risk_flag)
        ELSE NULL
    END AS hazard,
    SUM(at_risk_flag) >= 30 AS estimated
FROM exposure
GROUP BY channel, month
ORDER BY channel, month
"""


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _tables_dir() -> Path:
    return project_root() / "outputs" / "tables"


def life_table(subscribers_path: Path | None = None) -> pd.DataFrame:
    """Build the life table with DuckDB and save outputs/tables/life_table.csv."""
    path = subscribers_path or project_root() / "data" / "subscribers.parquet"
    connection = duckdb.connect()
    try:
        frame = connection.execute(LIFE_TABLE_SQL, [str(path)]).df()
    finally:
        connection.close()

    frame["channel"] = frame["channel"].astype(str)
    frame["month"] = frame["month"].astype(int)
    frame["at_risk"] = frame["at_risk"].astype(int)
    frame["cancels"] = frame["cancels"].astype(int)
    frame["hazard"] = frame["hazard"].astype(float)
    frame["estimated"] = frame["estimated"].astype(bool)
    frame = frame.sort_values(["channel", "month"]).reset_index(drop=True)

    out = _tables_dir()
    out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out / "life_table.csv", index=False)
    return frame


def _bounds(life: pd.DataFrame, channel: str, month: int) -> tuple[float, float]:
    """Lowest and highest estimated hazard for this month among other channels."""
    others = life.loc[
        (life["channel"] != channel)
        & (life["month"] == month)
        & life["estimated"].astype(bool),
        "hazard",
    ].astype(float)
    if others.empty:
        raise ValueError(f"no estimated hazard for month {month} outside {channel}")
    return float(others.min()), float(others.max())


def _survival(hazards: np.ndarray) -> np.ndarray:
    """S(1) = 1 and S(k) = S(k-1) * (1 - hazard of month k-1) for k = 2..12."""
    survival = np.empty((hazards.shape[0], HAZARD_MONTHS + 1), dtype=float)
    survival[:, 0] = 1.0
    for month in range(HAZARD_MONTHS):
        survival[:, month + 1] = survival[:, month] * (1.0 - hazards[:, month])
    return survival


def _bootstrap(
    life: pd.DataFrame, n_draws: int, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    channels = sorted(life["channel"].unique())
    draw_frames: list[pd.DataFrame] = []
    summary_rows: list[dict] = []

    for channel in channels:
        rows = life.loc[life["channel"] == channel].sort_values("month")
        months = [int(month) for month in rows["month"].tolist()]
        if months != list(range(1, HAZARD_MONTHS + 1)):
            raise ValueError(f"{channel} is missing hazard months")

        hazards = np.empty((n_draws, HAZARD_MONTHS), dtype=float)
        unknown_months: list[int] = []
        for month, at_risk, hazard, estimated in zip(
            rows["month"].to_numpy(),
            rows["at_risk"].to_numpy(),
            rows["hazard"].to_numpy(),
            rows["estimated"].to_numpy(),
            strict=True,
        ):
            month = int(month)
            if bool(estimated):
                draws = rng.binomial(int(at_risk), float(hazard), size=n_draws)
                hazards[:, month - 1] = draws / float(at_risk)
            else:
                unknown_months.append(month)

        # One uniform per draw, shared by every unknown month of this channel.
        if unknown_months:
            u = rng.random(n_draws)
            for month in unknown_months:
                low, high = _bounds(life, channel, month)
                hazards[:, month - 1] = low + u * (high - low)

        survival = _survival(hazards)
        value = CONTRIBUTION_PER_MONTH * survival.sum(axis=1)
        draw_frames.append(
            pd.DataFrame(
                {
                    "channel": channel,
                    "draw": np.arange(1, n_draws + 1, dtype=np.int64),
                    "V": value,
                }
            )
        )

        part = rows
        row = {
            "channel": channel,
            "months_estimated": int(part["estimated"].sum()),
            "months_unknown": int((~part["estimated"]).sum()),
            "V_p5": float(np.quantile(value, 0.05)),
            "V_median": float(np.quantile(value, 0.50)),
            "V_p95": float(np.quantile(value, 0.95)),
        }
        for month in range(1, HAZARD_MONTHS + 2):
            row[f"s{month}"] = float(np.median(survival[:, month - 1]))
        summary_rows.append(row)

    draws = pd.concat(draw_frames, ignore_index=True)
    summary = pd.DataFrame(summary_rows)
    return draws, summary


def value_draws(
    n_draws: int = 2000,
    seed: int = 2026,
    life: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Bootstrap V and save the draw file and the value summary."""
    if life is None:
        life = life_table()
    draws, summary = _bootstrap(life, n_draws=n_draws, seed=seed)
    out = _tables_dir()
    out.mkdir(parents=True, exist_ok=True)
    draws.to_parquet(out / "value_draws.parquet", index=False)
    summary.to_csv(out / "value_summary.csv", index=False)
    return draws


def main() -> None:
    life = life_table()
    value_draws(life=life)
    summary = pd.read_csv(_tables_dir() / "value_summary.csv")
    with pd.option_context(
        "display.max_columns",
        30,
        "display.width",
        220,
        "display.float_format",
        lambda value: f"{value:.4f}",
    ):
        print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
