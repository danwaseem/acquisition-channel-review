"""Charts from existing analysis tables. No new results, no planted file."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

BG = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"
BLUE = "#2a78d6"
BAND_80 = "#9ec5f4"
BAND_90 = "#cde2fb"
COMPARE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
CALL_COLOR = {"FUND": "#0ca30c", "HOLD": "#fab219", "CUT": "#d03b3b"}
POSITIVE = "#0ca30c"
NEGATIVE = "#d03b3b"

CHANNEL_LABEL = {
    "paid_search": "Paid search",
    "paid_social": "Paid social",
    "affiliate": "Affiliate",
    "referral": "Referral",
    "direct_mail": "Direct mail",
    "podcast": "Podcast",
}
METHOD_LABEL = {
    "snaive": "Seasonal naive",
    "fourier": "Harmonic regression",
    "fourier_spend": "Harmonic regression + spend",
    "short_history": "Short history",
}
VARIANT_ORDER = ["snaive", "fourier", "fourier_spend"]
VARIANT_LABEL = {
    "snaive": "Seasonal naive",
    "fourier": "Harmonic regression",
    "fourier_spend": "Harmonic regression + spend",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _figures_dir() -> Path:
    return project_root() / "outputs" / "figures"


def _tables_dir() -> Path:
    return project_root() / "outputs" / "tables"


def money_k(value: float) -> str:
    """Format dollars as $223k with a thousands-style compact label."""
    signed = "-" if value < 0 else ""
    amount = abs(value) / 1000.0
    if amount >= 100:
        text = f"{amount:,.0f}"
    elif amount >= 10:
        text = f"{amount:,.0f}"
    else:
        text = f"{amount:,.1f}"
    return f"{signed}${text}k"


def channel_name(channel: str) -> str:
    return CHANNEL_LABEL.get(channel, channel.replace("_", " ").title())


def apply_style(
    ax: plt.Axes, *, horizontal: bool = False, size_boost: int = 0
) -> None:
    """Shared look used by every chart."""
    ax.set_facecolor(BG)
    ax.figure.set_facecolor(BG)
    ax.tick_params(colors=MUTED, labelsize=9 + size_boost)
    ax.xaxis.label.set_color(MUTED)
    ax.yaxis.label.set_color(MUTED)
    ax.xaxis.label.set_size(10 + size_boost)
    ax.yaxis.label.set_size(10 + size_boost)
    ax.title.set_color(INK)
    ax.title.set_size(13 + size_boost)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)
    ax.set_axisbelow(True)
    if horizontal:
        ax.xaxis.grid(True, color=GRID, linewidth=0.8)
        ax.yaxis.grid(False)
    else:
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
        ax.xaxis.grid(False)


def _save(fig: plt.Figure, path: Path, dpi: int = 200) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)


def _rank_order(decisions: pd.DataFrame) -> list[str]:
    return decisions.sort_values("rank")["channel"].tolist()


def chart_forecast_by_channel(tables: Path, figures: Path) -> Path:
    decisions = pd.read_csv(tables / "decisions.csv")
    methods = pd.read_csv(tables / "forecast_summary.csv").set_index("channel")["method"]
    weekly = pd.read_csv(
        project_root() / "data" / "weekly_channel.csv", parse_dates=["week_start"]
    )
    forecast = pd.read_csv(tables / "forecast_weekly.csv", parse_dates=["week_start"])
    order = _rank_order(decisions)
    start = pd.Timestamp("2025-12-29")

    fig, axes = plt.subplots(3, 2, figsize=(12, 7), dpi=200)
    axes_flat = axes.ravel()
    for idx, channel in enumerate(order):
        ax = axes_flat[idx]
        apply_style(ax)
        hist = weekly.loc[weekly["channel"] == channel].sort_values("week_start")
        fut = forecast.loc[forecast["channel"] == channel].sort_values("week_start")
        ax.fill_between(
            fut["week_start"],
            fut["p5"],
            fut["p95"],
            color=BAND_90,
            linewidth=0,
            label="90% band" if idx == 0 else None,
        )
        ax.fill_between(
            fut["week_start"],
            fut["p10"],
            fut["p90"],
            color=BAND_80,
            linewidth=0,
            label="80% band" if idx == 0 else None,
        )
        ax.plot(
            hist["week_start"],
            hist["signups"],
            color=BLUE,
            linewidth=1.5,
            label="Actual" if idx == 0 else None,
        )
        ax.plot(
            fut["week_start"],
            fut["median"],
            color=BLUE,
            linewidth=2.0,
            linestyle="--",
            label="Forecast median" if idx == 0 else None,
        )
        ax.axvline(start, color=MUTED, linewidth=1.0)
        method = METHOD_LABEL.get(str(methods.loc[channel]), str(methods.loc[channel]))
        ax.set_title(f"{channel_name(channel)} · {method}", fontsize=11, color=INK)
        ax.set_ylim(bottom=0)
        if idx % 2 == 0:
            ax.set_ylabel("Weekly signups", color=MUTED, fontsize=10)

    handles = [
        Line2D([0], [0], color=BLUE, linewidth=1.5, label="Actual"),
        Line2D([0], [0], color=BLUE, linewidth=2.0, linestyle="--", label="Forecast median"),
        Patch(facecolor=BAND_80, edgecolor="none", label="80% band"),
        Patch(facecolor=BAND_90, edgecolor="none", label="90% band"),
        Line2D(
            [0],
            [0],
            color=MUTED,
            linewidth=1.0,
            label="Forecast starts (2025-12-29)",
        ),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=5,
        frameon=False,
        fontsize=9,
        bbox_to_anchor=(0.5, 0.01),
    )
    fig.suptitle(
        "Weekly signups: history and 2026 forecast",
        color=INK,
        fontsize=13,
        y=0.98,
    )
    fig.subplots_adjust(left=0.07, right=0.98, top=0.90, bottom=0.10, hspace=0.45, wspace=0.22)
    path = figures / "forecast_by_channel.png"
    _save(fig, path, dpi=200)
    return path


def chart_backtest_error(tables: Path, figures: Path) -> Path:
    summary = pd.read_csv(tables / "backtest_summary.csv")
    channels = sorted(summary["channel"].unique())
    # Keep a stable readable order by mean chosen MAPE ascending? Spec says per channel.
    # Use alphabetical for grouping clarity unless rank preferred. Spec: grouped horizontal bars
    # per channel for the 3 variants. I'll order channels alphabetically for the chart labels.
    channels = sorted(channels)
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=200)
    apply_style(ax, horizontal=True)

    y_positions = np.arange(len(channels))
    height = 0.22
    # Higher y is drawn higher on the panel, so reverse the variant offset
    # to put Seasonal naive at the top of each group.
    for v_idx, variant in enumerate(VARIANT_ORDER):
        offsets = y_positions + (1 - v_idx) * height
        values = []
        chosen_flags = []
        for channel in channels:
            row = summary.loc[
                (summary["channel"] == channel) & (summary["variant"] == variant)
            ].iloc[0]
            values.append(float(row["mean_mape"]))
            chosen_flags.append(bool(row["chosen"]))
        bars = ax.barh(
            offsets,
            values,
            height=height,
            color=COMPARE[v_idx],
            label=VARIANT_LABEL[variant],
            linewidth=0,
        )
        for bar, chosen, value in zip(bars, chosen_flags, values, strict=True):
            if chosen:
                ax.text(
                    value + 0.4,
                    bar.get_y() + bar.get_height() / 2,
                    "chosen",
                    va="center",
                    ha="left",
                    color=INK,
                    fontsize=8,
                )

    ax.set_yticks(y_positions)
    ax.set_yticklabels([channel_name(ch) for ch in channels], color=MUTED)
    ax.set_xlabel("Mean weekly MAPE (%)")
    ax.set_title("Back-test error by forecast method (lower is better)")
    ax.set_xlim(left=0)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.02),
        ncol=3,
        frameon=False,
        fontsize=9,
    )
    fig.subplots_adjust(left=0.18, right=0.96, top=0.88, bottom=0.28)
    path = figures / "backtest_error.png"
    _save(fig, path)
    return path


def chart_backtest_bands(tables: Path, figures: Path) -> Path:
    summary = pd.read_csv(tables / "backtest_summary.csv")
    metrics = pd.read_csv(tables / "backtest_metrics.csv")
    chosen = summary.loc[summary["chosen"], ["channel", "variant"]]
    channels = sorted(chosen["channel"].unique())
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=200)
    apply_style(ax, horizontal=True)

    for idx, channel in enumerate(channels):
        variant = chosen.loc[chosen["channel"] == channel, "variant"].iloc[0]
        rows = metrics.loc[
            (metrics["channel"] == channel) & (metrics["variant"] == variant)
        ]
        errors = rows["total_pct_error"].to_numpy(dtype=float)
        ax.hlines(idx, errors.min(), errors.max(), color=MUTED, linewidth=1.5)
        ax.scatter(errors, np.full(len(errors), idx), color=BLUE, s=28, zorder=3)

    ax.axvline(0, color=MUTED, linewidth=1.2)
    ax.set_yticks(range(len(channels)))
    ax.set_yticklabels([channel_name(ch) for ch in channels], color=MUTED)
    ax.set_xlabel("13-week total error (%)")
    ax.set_title("Error on 13-week totals across 4 held-out quarters")
    fig.subplots_adjust(left=0.18, right=0.96, top=0.88, bottom=0.14)
    path = figures / "backtest_bands.png"
    _save(fig, path)
    return path


def chart_did_gap(tables: Path, figures: Path, *, deck: bool = False) -> Path:
    weekly = pd.read_csv(tables / "did_weekly.csv", parse_dates=["week_start"])
    did = pd.read_csv(tables / "did_translation.csv").iloc[0]
    weekly = weekly.sort_values("week_start")
    y = (np.exp(weekly["gap_vs_pre"]) - 1.0) * 100.0
    effect = float(did["effect_pct"])
    ci_low = (np.exp(float(did["ci_low"])) - 1.0) * 100.0
    ci_high = (np.exp(float(did["ci_high"])) - 1.0) * 100.0
    window_start = pd.Timestamp("2024-07-01")
    window_end = pd.Timestamp("2024-09-16")
    boost = 2 if deck else 0

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=200)
    apply_style(ax, size_boost=boost)
    ax.axvspan(window_start, window_end, color="#e8e7e3", linewidth=0)
    ax.plot(weekly["week_start"], y, color=BLUE, linewidth=2.0)
    ax.axhline(0, color=MUTED, linewidth=1.0)
    ax.fill_between(
        [window_start, window_end],
        [ci_low, ci_low],
        [ci_high, ci_high],
        color=BAND_80,
        alpha=0.7,
        linewidth=0,
    )
    ax.hlines(effect, window_start, window_end, color=INK, linewidth=2.0)
    y_top = float(y.max()) + 15.0
    ax.set_ylim(top=y_top)
    label_box = dict(facecolor=BG, alpha=0.9, edgecolor="none")
    ax.text(
        window_start + pd.Timedelta(days=2),
        y_top - 3.0,
        "Paid social budget +51%",
        color=MUTED,
        fontsize=9 + boost,
        va="top",
        zorder=5,
        bbox=label_box,
    )
    ax.text(
        window_start + pd.Timedelta(days=2),
        ci_low - 1.5,
        "Estimated effect +19%",
        color=INK,
        fontsize=9 + boost,
        va="top",
        zorder=5,
        bbox=label_box,
    )
    if deck:
        ax.set_ylabel("Paid social vs other channels (%)")
    else:
        ax.set_ylabel("Paid social signups vs other channels (% vs normal)")
        ax.set_title("What the paid social budget increase did")
    fig.subplots_adjust(
        left=0.12,
        right=0.97,
        top=0.96 if deck else 0.88,
        bottom=0.14,
    )
    out_dir = figures / "deck" if deck else figures
    path = out_dir / "did_gap.png"
    _save(fig, path)
    return path


def chart_ratio_ranges(tables: Path, figures: Path, *, deck: bool = False) -> Path:
    decisions = pd.read_csv(tables / "decisions.csv").sort_values("rank")
    boost = 2 if deck else 0
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=200)
    apply_style(ax, horizontal=True, size_boost=boost)
    y = np.arange(len(decisions))[::-1]
    for idx, (_, row) in enumerate(decisions.iterrows()):
        color = CALL_COLOR[row["call"]]
        ypos = y[idx]
        ax.hlines(ypos, row["R_p5"], row["R_p95"], color=color, linewidth=4)
        ax.scatter([row["R_median"]], [ypos], color=INK, s=28, zorder=3)
        ax.text(
            float(row["R_p95"]) + 0.04,
            ypos,
            row["call"],
            va="center",
            ha="left",
            color=INK,
            fontsize=9 + boost,
        )
    ax.axvline(1.0, color=MUTED, linewidth=1.2, linestyle="--")
    ax.set_yticks(y)
    ax.set_yticklabels(
        [channel_name(ch) for ch in decisions["channel"]], color=MUTED
    )
    ax.set_ylim(-0.75, float(y.max()) + 0.45)
    ax.text(
        1.02,
        -0.55,
        "Break-even within 12 months",
        color=MUTED,
        fontsize=8 + boost,
        va="bottom",
        ha="left",
        bbox=dict(facecolor=BG, alpha=0.9, edgecolor="none"),
    )
    ax.set_xlabel("12-month value per $1 spent (5% to 95% range)")
    if not deck:
        ax.set_title("How sure we are about each channel")
    fig.subplots_adjust(
        left=0.18,
        right=0.92,
        top=0.96 if deck else 0.88,
        bottom=0.14,
    )
    out_dir = figures / "deck" if deck else figures
    path = out_dir / "ratio_ranges.png"
    _save(fig, path)
    return path


def chart_net_contribution(tables: Path, figures: Path, *, deck: bool = False) -> Path:
    decisions = pd.read_csv(tables / "decisions.csv").sort_values("rank")
    boost = 2 if deck else 0
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=200)
    apply_style(ax, horizontal=True, size_boost=boost)
    y = np.arange(len(decisions))[::-1]
    colors = [CALL_COLOR[call] for call in decisions["call"]]
    ax.barh(y, decisions["net_median"], color=colors, height=0.62, linewidth=0)
    ax.hlines(
        y,
        decisions["net_p5"],
        decisions["net_p95"],
        color=INK,
        linewidth=1.4,
        zorder=3,
    )
    gap = 12000.0
    label_x = []
    for idx, (_, row) in enumerate(decisions.iterrows()):
        xpos = max(0.0, float(row["net_p95"])) + gap
        label_x.append(xpos)
        ax.text(
            xpos,
            y[idx],
            f"{money_k(float(row['net_median']))}  {row['call']}",
            va="center",
            ha="left",
            color=INK,
            fontsize=8 + boost,
        )
    ax.axvline(0, color=MUTED, linewidth=1.2)
    ax.set_yticks(y)
    ax.set_yticklabels(
        [channel_name(ch) for ch in decisions["channel"]], color=MUTED
    )
    left = float(min(decisions["net_p5"].min(), decisions["net_median"].min(), 0.0))
    right = float(max(label_x) + 90000.0)
    ax.set_xlim(left - 10000.0, right)
    ax.xaxis.set_major_formatter(
        plt.FuncFormatter(lambda value, _pos: "$0" if abs(value) < 0.5 else money_k(value))
    )
    ax.set_xlabel("12-month net contribution ($k)")
    if not deck:
        ax.set_title("Expected 12-month net contribution by channel")
    fig.subplots_adjust(
        left=0.18,
        right=0.97,
        top=0.96 if deck else 0.88,
        bottom=0.14,
    )
    out_dir = figures / "deck" if deck else figures
    path = out_dir / "net_contribution.png"
    _save(fig, path)
    return path


def chart_retention_curves(tables: Path, figures: Path) -> Path:
    decisions = pd.read_csv(tables / "decisions.csv").sort_values("rank")
    values = pd.read_csv(tables / "value_summary.csv").set_index("channel")
    order = _rank_order(decisions)
    months = np.arange(1, 13)
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=200)
    apply_style(ax)

    for idx, channel in enumerate(order):
        color = COMPARE[idx]
        survival = values.loc[channel, [f"s{k}" for k in range(1, 13)]].to_numpy(
            dtype=float
        )
        pct = survival * 100.0
        if channel == "podcast":
            ax.plot(months[:3], pct[:3], color=color, linewidth=2.0, solid_capstyle="round")
            ax.plot(
                months[2:],
                pct[2:],
                color=color,
                linewidth=2.0,
                linestyle="--",
                solid_capstyle="round",
            )
        else:
            ax.plot(months, pct, color=color, linewidth=2.0, label=channel_name(channel))
        ax.text(
            12.15,
            pct[-1],
            channel_name(channel),
            color=INK,
            fontsize=8,
            va="center",
        )

    ax.set_xlim(1, 13.8)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Month")
    ax.set_ylabel("Still active (%)")
    ax.set_title("Share of subscribers still active, months 1 to 12")
    ax.text(
        1.05,
        8,
        "Podcast: months 3 to 12 estimated from other channels (range rule)",
        color=MUTED,
        fontsize=8,
    )
    handles = [
        Line2D([0], [0], color=COMPARE[i], linewidth=2.0, label=channel_name(ch))
        for i, ch in enumerate(order)
    ]
    ax.legend(handles=handles, frameon=False, fontsize=8, loc="upper right")
    fig.subplots_adjust(left=0.10, right=0.88, top=0.88, bottom=0.14)
    path = figures / "retention_curves.png"
    _save(fig, path)
    return path


def waterfall_segments(
    steps: list[tuple[str, float]],
) -> list[tuple[str, float, float]]:
    """Turn ordered (label, change) steps into (label, start, end) bars.

    The first bar starts at 0. Each later step bar continues the running
    total. The last bar is the Net change total from 0 to that final total.
    """
    if not steps:
        return []
    segments: list[tuple[str, float, float]] = []
    running = 0.0
    last_index = len(steps) - 1
    for idx, (label, change) in enumerate(steps):
        if idx == last_index:
            segments.append((label, 0.0, running))
        else:
            start = running
            end = running + float(change)
            segments.append((label, start, end))
            running = end
    return segments


def chart_budget_change(tables: Path, figures: Path) -> Path:
    budget = pd.read_csv(tables / "budget_scenario.csv").set_index("channel")
    decisions = pd.read_csv(tables / "decisions.csv")
    fund = decisions.loc[decisions["call"] == "FUND", "channel"].tolist()

    steps: list[tuple[str, float]] = [
        (
            "Stop paid social and affiliate",
            float(budget.loc["stop_cut_channels", "extra_net_median"]),
        )
    ]
    for channel in fund:
        steps.append(
            (channel_name(channel), float(budget.loc[channel, "extra_net_median"]))
        )
    steps.append(
        ("Net change", float(budget.loc["cut_and_redirect", "extra_net_median"]))
    )
    segments = waterfall_segments(steps)

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=200)
    apply_style(ax)
    width = 0.62
    half = width / 2.0
    x = np.arange(len(segments))

    for idx, (label, start, end) in enumerate(segments):
        bottom = min(start, end)
        height = abs(end - start)
        if label == "Net change":
            color = BLUE
        elif end > start:
            color = POSITIVE
        else:
            color = NEGATIVE
        ax.bar(
            x[idx],
            height,
            bottom=bottom,
            color=color,
            width=width,
            linewidth=0,
        )
        if idx < len(segments) - 1:
            ax.plot(
                [x[idx] + half, x[idx + 1] - half],
                [end, end],
                color=MUTED,
                linewidth=1.0,
            )
        change = end - start
        ax.text(
            x[idx],
            max(start, end) + 4000.0,
            money_k(change),
            ha="center",
            va="bottom",
            color=INK,
            fontsize=9,
        )

    ax.axhline(0, color=MUTED, linewidth=1.0)
    ax.set_xticks(x)
    ax.set_xticklabels([label for label, _start, _end in segments], color=MUTED, fontsize=9)
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda value, _pos: "$0" if abs(value) < 0.5 else money_k(value))
    )
    ax.set_ylabel("Change in 12-month net contribution ($k)")
    ax.set_title("If the freed budget moved all at once (DiD elasticity assumed)")
    fig.subplots_adjust(left=0.14, right=0.97, top=0.88, bottom=0.18)
    path = figures / "budget_change.png"
    _save(fig, path)
    return path


def make_all_charts(
    tables_dir: Path | None = None,
    figures_dir: Path | None = None,
) -> list[Path]:
    tables = tables_dir or _tables_dir()
    figures = figures_dir or _figures_dir()
    figures.mkdir(parents=True, exist_ok=True)
    (figures / "deck").mkdir(parents=True, exist_ok=True)
    paths = [
        chart_forecast_by_channel(tables, figures),
        chart_backtest_error(tables, figures),
        chart_backtest_bands(tables, figures),
        chart_did_gap(tables, figures),
        chart_ratio_ranges(tables, figures),
        chart_net_contribution(tables, figures),
        chart_retention_curves(tables, figures),
        chart_budget_change(tables, figures),
        chart_did_gap(tables, figures, deck=True),
        chart_ratio_ranges(tables, figures, deck=True),
        chart_net_contribution(tables, figures, deck=True),
    ]
    return paths


def main() -> None:
    paths = make_all_charts()
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
