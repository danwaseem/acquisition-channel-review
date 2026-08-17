"""Checks for the 5-slide stakeholder readout."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from pptx import Presentation

from acr.deck import (
    FOOTER,
    build_deck,
    channel_name,
    money_dollars,
    pct_points,
    pct_rate,
    ratio_phrase,
)

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs" / "tables"
EM_DASH = "\u2014"


def _slide_text(slide) -> str:
    chunks: list[str] = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            chunks.append(shape.text_frame.text)
    return "\n".join(chunks)


def _notes_text(slide) -> str:
    return slide.notes_slide.notes_text_frame.text


def _all_text(prs: Presentation) -> str:
    parts: list[str] = []
    for slide in prs.slides:
        parts.append(_slide_text(slide))
        parts.append(_notes_text(slide))
    return "\n".join(parts)


def test_deck_has_five_titled_slides_with_notes_and_footer(tmp_path: Path):
    out = tmp_path / "readout.pptx"
    build_deck(out)
    prs = Presentation(out)
    assert len(prs.slides) == 5
    for idx, slide in enumerate(prs.slides, start=1):
        text = _slide_text(slide)
        assert text.strip(), idx
        assert len(text.splitlines()[0].strip()) > 0
        notes = _notes_text(slide).strip()
        assert notes, idx
        assert FOOTER in text
        assert f"{idx} / 5" in text


def test_slide_one_shows_each_channel_ratio(tmp_path: Path):
    out = tmp_path / "readout.pptx"
    build_deck(out)
    prs = Presentation(out)
    text = _slide_text(prs.slides[0])
    decisions = pd.read_csv(TABLES / "decisions.csv")
    for _, row in decisions.iterrows():
        assert channel_name(str(row["channel"])) in text
        assert ratio_phrase(float(row["R_median"])) in text


def test_slide_four_and_five_show_key_formatted_numbers(tmp_path: Path):
    out = tmp_path / "readout.pptx"
    build_deck(out)
    prs = Presentation(out)
    did = pd.read_csv(TABLES / "did_translation.csv").iloc[0]
    slide4 = _slide_text(prs.slides[3])
    assert f"{pct_points(float(did['effect_pct']))}%" in slide4
    assert money_dollars(float(did["cost_per_extra_signup"])) in slide4

    hold = pd.read_csv(TABLES / "hold_detail.csv")
    slide5 = _slide_text(prs.slides[4])
    podcast = hold.loc[hold["channel"] == "podcast"].iloc[0]
    mail = hold.loc[hold["channel"] == "direct_mail"].iloc[0]
    assert f"{pct_rate(float(podcast['breakeven_churn_unknown_months']))}%" in slide5
    assert str(round(float(mail["breakeven_signups_per_week"]))) in slide5
    assert str(round(float(mail["signups_per_week_median"]))) in slide5
    assert str(round(float(mail["signups_per_week_p5"]))) in slide5
    assert str(round(float(mail["signups_per_week_p95"]))) in slide5


def test_slides_two_three_four_each_have_one_picture(tmp_path: Path):
    out = tmp_path / "readout.pptx"
    build_deck(out)
    prs = Presentation(out)
    for index in (1, 2, 3):
        pictures = [
            shape
            for shape in prs.slides[index].shapes
            if shape.shape_type is not None and shape.shape_type == 13
        ]
        assert len(pictures) == 1, index


def test_deck_has_no_em_dashes(tmp_path: Path):
    out = tmp_path / "readout.pptx"
    build_deck(out)
    prs = Presentation(out)
    text = _all_text(prs)
    assert EM_DASH not in text


def test_deck_auto_shapes_have_no_p_style(tmp_path: Path):
    out = tmp_path / "readout.pptx"
    build_deck(out)
    prs = Presentation(out)
    for idx, slide in enumerate(prs.slides, start=1):
        xml = slide._element.xml
        assert "<p:style>" not in xml, idx


def test_build_deck_is_byte_identical_across_runs(tmp_path: Path):
    first = tmp_path / "first.pptx"
    second = tmp_path / "second.pptx"
    build_deck(first)
    build_deck(second)
    assert first.read_bytes() == second.read_bytes()
