"""Build the 5-slide stakeholder readout from existing result tables."""

from __future__ import annotations

import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

FIXED_DECK_TIME = datetime(2025, 12, 29, 0, 0, 0)
FIXED_ZIP_DATE = (2025, 12, 29, 0, 0, 0)

INK = RGBColor(0x0B, 0x0B, 0x0B)
MUTED = RGBColor(0x52, 0x51, 0x4E)
CARD_FILL = RGBColor(0xFC, 0xFC, 0xFB)
CARD_LINE = RGBColor(0xE4, 0xE3, 0xDF)
CALL_RGB = {
    "FUND": RGBColor(0x0C, 0xA3, 0x0C),
    "HOLD": RGBColor(0xFA, 0xB2, 0x19),
    "CUT": RGBColor(0xD0, 0x3B, 0x3B),
}

CHANNEL_LABEL = {
    "paid_search": "Paid search",
    "paid_social": "Paid social",
    "affiliate": "Affiliate",
    "referral": "Referral",
    "direct_mail": "Direct mail",
    "podcast": "Podcast",
}

FOOTER = (
    "Simulated data for a fictional coffee subscription. "
    "Decision date 2025-12-29."
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def channel_name(channel: str) -> str:
    return CHANNEL_LABEL.get(channel, channel.replace("_", " ").title())


def channel_in_sentence(channel: str, *, sentence_start: bool = False) -> str:
    name = channel_name(channel)
    if sentence_start or not name:
        return name
    return name[0].lower() + name[1:]


def money_k(value: float) -> str:
    signed = "-" if value < 0 else ""
    amount = abs(value) / 1000.0
    if amount >= 10:
        text = f"{amount:,.0f}"
    else:
        text = f"{amount:,.1f}"
    return f"{signed}${text}k"


def money_dollars(value: float) -> str:
    return f"${abs(value):,.0f}" if value >= 0 else f"-${abs(value):,.0f}"


def ratio_phrase(r_median: float) -> str:
    return f"${r_median:.2f} back per $1 within 12 months"


def pct_points(value: float) -> str:
    return f"{value:.0f}"


def pct_rate(value: float) -> str:
    return f"{value * 100:.1f}"


def _no_shadow(shape) -> None:
    shape.shadow.inherit = False


def _set_run_font(run, *, size: int, bold: bool = False, color: RGBColor = INK) -> None:
    run.font.name = "Calibri"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:latin", "a:cs", "a:ea"):
        node = rpr.find(qn(tag))
        if node is None:
            node = rpr.makeelement(qn(tag), {})
            rpr.append(node)
        node.set("typeface", "Calibri")


def _add_textbox(
    slide,
    left,
    top,
    width,
    height,
    text: str,
    *,
    size: int,
    bold: bool = False,
    color: RGBColor = INK,
    align=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
):
    box = slide.shapes.add_textbox(left, top, width, height)
    _no_shadow(box)
    frame = box.text_frame
    frame.word_wrap = True
    frame.auto_size = None
    try:
        frame._txBody.bodyPr.set(
            "anchor",
            {MSO_ANCHOR.TOP: "t", MSO_ANCHOR.MIDDLE: "ctr", MSO_ANCHOR.BOTTOM: "b"}[
                anchor
            ],
        )
    except Exception:
        pass
    frame.clear()
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    run = paragraph.add_run()
    run.text = text
    _set_run_font(run, size=size, bold=bold, color=color)
    return box


def _add_rich_textbox(
    slide,
    left,
    top,
    width,
    height,
    parts: list[tuple[str, bool]],
    *,
    size: int,
    color: RGBColor = INK,
):
    box = slide.shapes.add_textbox(left, top, width, height)
    _no_shadow(box)
    frame = box.text_frame
    frame.word_wrap = True
    frame.clear()
    paragraph = frame.paragraphs[0]
    paragraph.alignment = PP_ALIGN.LEFT
    for text, bold in parts:
        run = paragraph.add_run()
        run.text = text
        _set_run_font(run, size=size, bold=bold, color=color)
    return box


def _add_multiline(
    slide,
    left,
    top,
    width,
    height,
    lines: list[tuple[str, dict]],
):
    box = slide.shapes.add_textbox(left, top, width, height)
    _no_shadow(box)
    frame = box.text_frame
    frame.word_wrap = True
    frame.clear()
    for idx, (text, style) in enumerate(lines):
        paragraph = frame.paragraphs[0] if idx == 0 else frame.add_paragraph()
        paragraph.alignment = style.get("align", PP_ALIGN.LEFT)
        paragraph.space_after = Pt(style.get("space_after", 6))
        label = style.get("label")
        if label:
            run = paragraph.add_run()
            run.text = label
            _set_run_font(
                run,
                size=style.get("size", 16),
                bold=True,
                color=style.get("color", INK),
            )
            run = paragraph.add_run()
            run.text = text
            _set_run_font(
                run,
                size=style.get("size", 16),
                bold=False,
                color=style.get("color", INK),
            )
        else:
            run = paragraph.add_run()
            run.text = text
            _set_run_font(
                run,
                size=style.get("size", 16),
                bold=style.get("bold", False),
                color=style.get("color", INK),
            )
    return box


def _footer(slide, page: int, total: int = 5) -> None:
    _add_textbox(
        slide,
        Inches(0.5),
        Inches(7.05),
        Inches(10.5),
        Inches(0.35),
        FOOTER,
        size=10,
        color=MUTED,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    _add_textbox(
        slide,
        Inches(11.5),
        Inches(7.05),
        Inches(1.3),
        Inches(0.35),
        f"{page} / {total}",
        size=10,
        color=MUTED,
        align=PP_ALIGN.RIGHT,
        anchor=MSO_ANCHOR.MIDDLE,
    )


def _notes(slide, text: str) -> None:
    notes = slide.notes_slide
    frame = notes.notes_text_frame
    frame.clear()
    paragraph = frame.paragraphs[0]
    run = paragraph.add_run()
    run.text = text
    _set_run_font(run, size=12, color=INK)


def _title(slide, text: str) -> None:
    _add_textbox(
        slide,
        Inches(0.5),
        Inches(0.28),
        Inches(12.3),
        Inches(0.7),
        text,
        size=28,
        bold=True,
        color=INK,
        anchor=MSO_ANCHOR.MIDDLE,
    )


def _clear_auto_shape_style(shape) -> None:
    el = shape._element
    style = el.find(qn("p:style"))
    if style is not None:
        el.remove(style)


def _card(slide, left, top, width, height, call: str):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    _no_shadow(shape)
    _clear_auto_shape_style(shape)
    shape.fill.solid()
    shape.fill.fore_color.rgb = CARD_FILL
    shape.line.color.rgb = CARD_LINE
    shape.line.width = Pt(1)
    strip = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, left, top, width, Inches(0.12)
    )
    _no_shadow(strip)
    _clear_auto_shape_style(strip)
    strip.fill.solid()
    strip.fill.fore_color.rgb = CALL_RGB[call]
    strip.line.fill.background()
    return shape


def _load_inputs(root: Path) -> dict:
    tables = root / "outputs" / "tables"
    figures = root / "outputs" / "figures"
    decisions = pd.read_csv(tables / "decisions.csv").sort_values("rank")
    hold = pd.read_csv(tables / "hold_detail.csv")
    did = pd.read_csv(tables / "did_translation.csv").iloc[0]
    budget = pd.read_csv(tables / "budget_scenario.csv").set_index("channel")
    life = pd.read_csv(tables / "life_table.csv")
    weekly = pd.read_csv(root / "data" / "weekly_channel.csv", parse_dates=["week_start"])
    forecast = pd.read_csv(tables / "forecast_summary.csv").set_index("channel")
    return {
        "decisions": decisions,
        "hold": hold,
        "did": did,
        "budget": budget,
        "life": life,
        "weekly": weekly,
        "forecast": forecast,
        "figures": figures,
    }


def _channels_by_call(decisions: pd.DataFrame, call: str) -> list[str]:
    return decisions.loc[decisions["call"] == call, "channel"].tolist()


def build_deck(out_path: Path | None = None, root: Path | None = None) -> Path:
    root = root or project_root()
    data = _load_inputs(root)
    decisions = data["decisions"]
    hold = data["hold"]
    did = data["did"]
    budget = data["budget"]
    life = data["life"]
    weekly = data["weekly"]
    forecast = data["forecast"]
    figures = data["figures"]
    deck_figures = figures / "deck"

    by_channel = decisions.set_index("channel")
    fund = _channels_by_call(decisions, "FUND")
    cut = _channels_by_call(decisions, "CUT")
    hold_channels = _channels_by_call(decisions, "HOLD")

    freed = float(
        sum(52.0 * float(forecast.loc[ch, "planned_weekly_spend"]) for ch in cut)
    )
    stop_cut = float(budget.loc["stop_cut_channels", "extra_net_median"])

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    # Slide 1
    slide1 = prs.slides.add_slide(blank)
    _title(slide1, "Fund 2 channels, cut 2, hold 2 until we know more")
    cards = [
        ("FUND", fund),
        ("CUT", cut),
        ("HOLD", hold_channels),
    ]
    card_width = Inches(3.9)
    card_gap = Inches(0.25)
    card_left0 = Inches(0.5)
    card_top = Inches(1.15)
    card_height = Inches(2.4)
    for idx, (call, channels) in enumerate(cards):
        left = card_left0 + idx * (card_width + card_gap)
        _card(slide1, left, card_top, card_width, card_height, call)
        _add_textbox(
            slide1,
            left + Inches(0.18),
            card_top + Inches(0.22),
            card_width - Inches(0.36),
            Inches(0.35),
            call,
            size=18,
            bold=True,
            color=INK,
        )
        lines: list[tuple[str, dict]] = []
        for channel in channels:
            lines.append(
                (
                    channel_name(channel),
                    {"size": 20, "bold": True, "color": INK, "space_after": 2},
                )
            )
            lines.append(
                (
                    ratio_phrase(float(by_channel.loc[channel, "R_median"])),
                    {"size": 16, "color": MUTED, "space_after": 8},
                )
            )
        _add_multiline(
            slide1,
            left + Inches(0.18),
            card_top + Inches(0.6),
            card_width - Inches(0.36),
            Inches(1.7),
            lines,
        )

    referral_marginal = float(by_channel.loc["referral", "marginal_return_per_dollar"])
    search_marginal = float(by_channel.loc["paid_search", "marginal_return_per_dollar"])
    _add_rich_textbox(
        slide1,
        Inches(0.5),
        Inches(3.8),
        Inches(12.3),
        Inches(0.55),
        [
            ("Stopping paid social and affiliate frees ", False),
            (money_k(freed), True),
            (" a year and adds about ", False),
            (money_k(stop_cut), True),
            (" in 12-month profit.", False),
        ],
        size=18,
    )
    _add_rich_textbox(
        slide1,
        Inches(0.5),
        Inches(4.4),
        Inches(12.3),
        Inches(0.7),
        [
            ("Move the freed money in steps and test each step. ", False),
            ("Referral returns about ", False),
            (f"${referral_marginal:.2f}", True),
            (" per extra $1, paid search only about ", False),
            (f"${search_marginal:.2f}", True),
            (".", False),
        ],
        size=18,
    )
    _footer(slide1, 1)
    _notes(
        slide1,
        "This slide is the decision board. We pair 2,000 signup forecasts with "
        "2,000 customer-value draws for each channel, then look at the low and "
        "high ends of the value-to-cost ratio. We fund only when even the low end "
        "pays back within 12 months, and we cut only when even the high end fails. "
        "Signups come from a seasonal forecast in R with 2,000 simulated paths, "
        "chosen after a back-test on 4 held-out quarters. Value comes from a "
        "monthly retention life table. The budget line uses the measured response "
        "from the past paid social spend change as an assumption, not a promise.",
    )

    # Slide 2
    slide2 = prs.slides.add_slide(blank)
    _title(slide2, "Search and referral make money; social and affiliate lose it")
    pic = slide2.shapes.add_picture(
        str(deck_figures / "net_contribution.png"),
        Inches(0.4),
        Inches(1.15),
        width=Inches(8.6),
    )
    _no_shadow(pic)
    top = decisions.iloc[0]
    losers = decisions.loc[decisions["call"] == "CUT"]
    holders = decisions.loc[decisions["call"] == "HOLD"]
    combined_loss = -float(losers["net_median"].sum())
    bullets = [
        (
            f"{channel_in_sentence(str(top['channel']), sentence_start=True)} leads "
            f"at about {money_k(float(top['net_median']))} of 12-month profit.",
            {"size": 16, "color": INK, "space_after": 12},
        ),
        (
            f"{channel_in_sentence(str(losers.iloc[0]['channel']), sentence_start=True)} "
            f"and {channel_in_sentence(str(losers.iloc[1]['channel']))} lose about "
            f"{money_k(combined_loss)} combined.",
            {"size": 16, "color": INK, "space_after": 12},
        ),
        (
            f"{channel_in_sentence(str(holders.iloc[0]['channel']), sentence_start=True)} "
            f"and {channel_in_sentence(str(holders.iloc[1]['channel']))} sit close to "
            "zero, so we keep learning before we move them.",
            {"size": 16, "color": INK, "space_after": 12},
        ),
    ]
    _add_multiline(slide2, Inches(9.2), Inches(1.15), Inches(3.6), Inches(4.8), bullets)
    _footer(slide2, 2)
    _notes(
        slide2,
        "Net contribution is forecast 12-month signups times value per customer, "
        "minus media spend, variable signup costs, and fixed monthly fees. The "
        "bars show the middle of 2,000 paired draws. The whiskers show the low and "
        "high ends of that same set. The signup path comes from the chosen "
        "seasonal model in R, simulated 2,000 times after a 4-quarter back-test. "
        "Customer value comes from the retention life table with bootstrap draws. "
        "This ranking is what we use to talk about money, not just signups.",
    )

    # Slide 3
    slide3 = prs.slides.add_slide(blank)
    _title(slide3, "How sure we are about each channel")
    pic = slide3.shapes.add_picture(
        str(deck_figures / "ratio_ranges.png"),
        Inches(0.4),
        Inches(1.15),
        width=Inches(8.6),
    )
    _no_shadow(pic)
    hold_line = " and ".join(
        channel_in_sentence(ch, sentence_start=(i == 0))
        for i, ch in enumerate(hold_channels)
    )
    bullets3 = [
        (
            "Each line shows the likely range for the next 12 months.",
            {"size": 16, "color": INK, "space_after": 12},
        ),
        (
            "We fund a channel only if even the low end pays back.",
            {"size": 16, "color": INK, "space_after": 12},
        ),
        (
            "We cut a channel only if even the high end does not.",
            {"size": 16, "color": INK, "space_after": 12},
        ),
        (
            f"Lines that cross $1: not enough evidence yet. {hold_line}.",
            {"size": 16, "color": MUTED, "space_after": 8},
        ),
    ]
    _add_multiline(slide3, Inches(9.2), Inches(1.15), Inches(3.6), Inches(4.8), bullets3)
    _footer(slide3, 3)
    _notes(
        slide3,
        "The chart shows the 5th to 95th percentile of the value-to-cost ratio for "
        "each channel, with the middle marked as a dark point. The rule is simple: "
        "fund when the low end is at least $1.00 back per $1 spent, cut when the "
        "high end stays below $1.00, and hold when the range still crosses $1.00. "
        "Those draws come from pairing the R forecast paths with the retention "
        "bootstrap. No channel is moved on a single point estimate.",
    )

    # Slide 4
    slide4 = prs.slides.add_slide(blank)
    _title(slide4, "Spending more on paid social did not pay")
    pic = slide4.shapes.add_picture(
        str(deck_figures / "did_gap.png"),
        Inches(0.4),
        Inches(1.15),
        width=Inches(8.6),
    )
    _no_shadow(pic)
    spend_lift = (float(did["spend_ratio"]) - 1.0) * 100.0
    effect_pct = float(did["effect_pct"])
    ci_low_pct = (float(np.exp(float(did["ci_low"]))) - 1.0) * 100.0
    ci_high_pct = (float(np.exp(float(did["ci_high"]))) - 1.0) * 100.0
    extra_cost = float(did["cost_per_extra_signup"])
    normal_cost = float(did["avg_cost_per_signup_pre"])
    bullets4 = [
        (
            "In July to September 2024 we raised the paid social budget by "
            f"{pct_points(spend_lift)}%.",
            {"size": 16, "color": INK, "space_after": 12},
        ),
        (
            f"Signups rose about {pct_points(effect_pct)}% (likely range "
            f"{pct_points(ci_low_pct)}% to {pct_points(ci_high_pct)}%) compared "
            "with channels we did not change.",
            {"size": 16, "color": INK, "space_after": 12},
        ),
        (
            f"Each extra signup cost about {money_dollars(extra_cost)}, versus "
            f"{money_dollars(normal_cost)} for a normal signup.",
            {"size": 16, "color": INK, "space_after": 12},
        ),
    ]
    _add_multiline(slide4, Inches(9.2), Inches(1.15), Inches(3.6), Inches(4.8), bullets4)
    _footer(slide4, 4)
    _notes(
        slide4,
        "This slide is the past spend test. We compared paid social with paid "
        "search, affiliate, and referral before and during the budget increase, "
        "using channel and week fixed effects and Newey-West standard errors. A "
        "fake earlier event and a later reversal both show little lasting change. "
        "Signups rose, but each extra customer cost far more than a normal one, "
        "so the spend hike did not pay. That measured response is the assumption "
        "behind any later talk of moving budget into other channels.",
    )

    # Slide 5
    slide5 = prs.slides.add_slide(blank)
    _title(slide5, "Two channels we cannot call yet, and what would settle them")
    hold_width = Inches(5.9)
    hold_gap = Inches(0.35)
    hold_top = Inches(1.15)
    hold_height = Inches(3.5)
    hold_rows = [
        hold.loc[hold["channel"] == channel].iloc[0] for channel in hold_channels
    ]

    for idx, row in enumerate(hold_rows):
        channel = str(row["channel"])
        left = Inches(0.5) + idx * (hold_width + hold_gap)
        _card(slide5, left, hold_top, hold_width, hold_height, "HOLD")
        _add_textbox(
            slide5,
            left + Inches(0.2),
            hold_top + Inches(0.2),
            hold_width - Inches(0.4),
            Inches(0.35),
            f"HOLD  {channel_name(channel)}",
            size=18,
            bold=True,
        )
        if channel == "podcast":
            n_weeks = int((weekly["channel"] == "podcast").sum())
            estimated = life.loc[
                (life["channel"] == "podcast")
                & life["estimated"]
                .astype(str)
                .str.lower()
                .isin(["true", "1", "1.0"])
            ]
            months_estimated = int(len(estimated))
            first_signup = weekly.loc[
                weekly["channel"] == "podcast", "week_start"
            ].min()
            settle = (
                pd.Timestamp(first_signup) + pd.DateOffset(months=12)
            ).to_pydatetime()
            settle_label = settle.strftime("%B %Y")
            churn = float(row["breakeven_churn_unknown_months"])
            low = float(row["lowest_other_churn"])
            high = float(row["highest_other_churn"])
            lines = [
                (
                    f" launched {n_weeks} weeks before the decision date; we only "
                    f"have {months_estimated} months of customer history.",
                    {
                        "size": 16,
                        "color": INK,
                        "space_after": 8,
                        "label": "What we know:",
                    },
                ),
                (
                    " it pays back if monthly cancellations after month 2 stay at "
                    f"or below {pct_rate(churn)}%. Other channels range from "
                    f"{pct_rate(low)}% to {pct_rate(high)}%.",
                    {
                        "size": 16,
                        "color": INK,
                        "space_after": 8,
                        "label": "Break-even:",
                    },
                ),
                (
                    " 12 months of history for the first podcast customers, which "
                    f"we will have by {settle_label}.",
                    {
                        "size": 16,
                        "color": INK,
                        "space_after": 6,
                        "label": "What would settle it:",
                    },
                ),
            ]
        else:
            lines = [
                (
                    " signups swing a lot from week to week.",
                    {
                        "size": 16,
                        "color": INK,
                        "space_after": 8,
                        "label": "What we know:",
                    },
                ),
                (
                    " it needs about "
                    f"{round(float(row['breakeven_signups_per_week']))} signups a "
                    "week. We expect about "
                    f"{round(float(row['signups_per_week_median']))} (likely "
                    f"{round(float(row['signups_per_week_p5']))} to "
                    f"{round(float(row['signups_per_week_p95']))}).",
                    {
                        "size": 16,
                        "color": INK,
                        "space_after": 8,
                        "label": "Break-even:",
                    },
                ),
                (
                    " a holdout test, pausing mail in a random set of ZIP codes "
                    "for 8 to 12 weeks, or 2 more quarters of data.",
                    {
                        "size": 16,
                        "color": INK,
                        "space_after": 6,
                        "label": "What would settle it:",
                    },
                ),
            ]
        _add_multiline(
            slide5,
            left + Inches(0.2),
            hold_top + Inches(0.6),
            hold_width - Inches(0.4),
            Inches(2.25),
            lines,
        )

    closer = (
        "Also worth testing: how referral and paid search respond to more money. "
        "Our budget numbers assume they respond like paid social did."
    )
    _add_textbox(
        slide5, Inches(0.5), Inches(4.9), Inches(12.3), Inches(0.7), closer, size=16
    )
    _footer(slide5, 5)
    _notes(
        slide5,
        "Podcast is young, so most of its later cancel rates are filled in from "
        "the range of other channels. Direct mail is older but noisy, and its "
        "range still crosses break-even. The break-even lines come from the same "
        "cost and value math used in the decision step. Until those ranges settle, "
        "we keep current spend. Any big budget move into referral or paid search "
        "should be tested in steps, because the response size used in the scenario "
        "is borrowed from the paid social difference-in-differences result.",
    )

    out = Path(out_path) if out_path is not None else root / "deck" / "readout.pptx"
    out.parent.mkdir(parents=True, exist_ok=True)
    _set_fixed_core_properties(prs)
    _save_pptx_deterministic(prs, out)
    return out


def _set_fixed_core_properties(prs: Presentation) -> None:
    props = prs.core_properties
    props.author = "Danish Waseem"
    props.title = "Acquisition Channel Review"
    props.last_modified_by = "Danish Waseem"
    props.revision = 1
    props.created = FIXED_DECK_TIME
    props.modified = FIXED_DECK_TIME


def _save_pptx_deterministic(prs: Presentation, out_path: Path) -> None:
    """Save a pptx with fixed metadata timestamps and zip entry dates."""
    buffer = BytesIO()
    prs.save(buffer)
    buffer.seek(0)
    with zipfile.ZipFile(buffer, "r") as source:
        with zipfile.ZipFile(
            out_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as destination:
            for info in source.infolist():
                data = source.read(info.filename)
                entry = zipfile.ZipInfo(filename=info.filename, date_time=FIXED_ZIP_DATE)
                entry.compress_type = zipfile.ZIP_DEFLATED
                destination.writestr(entry, data)


def main() -> None:
    path = build_deck(project_root() / "deck" / "readout.pptx")
    print(path)


if __name__ == "__main__":
    main()
