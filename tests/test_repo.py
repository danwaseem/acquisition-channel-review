"""Repo-wide checks for the README and tracked text."""

from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "outputs" / "tables"
EM_DASH = "\u2014"
SKIP_SUFFIXES = {".parquet", ".png", ".pptx", ".pdf", ".pyc"}
SKIP_NAMES = {"uv.lock"}


def _planted_effects_section() -> str:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(
        r"## Did the analysis find the planted effects\?\n\n(.*?)(?=\n## |\Z)",
        readme,
        flags=re.DOTALL,
    )
    assert match is not None, "planted-effects section missing from README"
    return match.group(1)


def _tracked_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    return [line for line in out.splitlines() if line]


def _is_text_path(path: Path) -> bool:
    if path.name in SKIP_NAMES:
        return False
    if path.suffix.lower() in SKIP_SUFFIXES:
        return False
    data = path.read_bytes()
    if b"\0" in data:
        return False
    return True


def test_readme_contains_each_channel_call_and_r_median():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    decisions = pd.read_csv(ROOT / "outputs" / "tables" / "decisions.csv")
    for _, row in decisions.iterrows():
        assert str(row["call"]) in readme
        assert f"{float(row['R_median']):.2f}" in readme


def test_tracked_text_has_no_em_dash():
    offenders: list[str] = []
    for rel in _tracked_files():
        path = ROOT / rel
        if not _is_text_path(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if EM_DASH in text:
            offenders.append(rel)
    assert offenders == []


def test_tracked_text_has_no_forbidden_editor_word():
    offenders: list[str] = []
    # Build the needle at runtime so this file does not contain the word itself.
    needle = "cur" + "sor"
    pattern = re.compile(needle, re.IGNORECASE)
    for rel in _tracked_files():
        path = ROOT / rel
        if path.name == "uv.lock":
            continue
        if not _is_text_path(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if pattern.search(text):
            offenders.append(rel)
    assert offenders == []


def test_interview_md_is_ignored_and_untracked():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "interview.md" in gitignore.splitlines()
    tracked = set(_tracked_files())
    assert "interview.md" not in tracked


def test_readme_image_paths_exist():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    paths = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", readme)
    missing = [path for path in paths if not (ROOT / path).exists()]
    assert missing == []


def test_readme_planted_effects_numbers_match_outputs():
    section = _planted_effects_section()
    planted = json.loads((ROOT / "data" / "truth.json").read_text(encoding="utf-8"))
    decisions = pd.read_csv(TABLES / "decisions.csv")
    did_main = pd.read_csv(TABLES / "did_results.csv")
    did_main = did_main.loc[did_main["test"] == "main"].iloc[0]
    translation = pd.read_csv(TABLES / "did_translation.csv").iloc[0]
    value = pd.read_csv(TABLES / "value_summary.csv")
    forecast = pd.read_csv(TABLES / "forecast_summary.csv")

    intended = {row["channel"]: row["intended_call"] for row in planted["channels"]}
    calls = decisions.set_index("channel")["call"].to_dict()
    n_match = sum(1 for channel, call in intended.items() if calls.get(channel) == call)
    assert n_match == 6
    assert f"All {n_match} fund, cut and hold calls match the planted answer." in section

    effect_pct = round(float(translation["effect_pct"]))
    true_pct = round((math.exp(float(planted["did_true_log_effect"])) - 1) * 100, 1)
    range_low = round((math.exp(float(did_main["ci_low"])) - 1) * 100)
    range_high = round((math.exp(float(did_main["ci_high"])) - 1) * 100)
    elasticity = round(float(translation["elasticity"]), 2)
    true_elasticity = f"{float(planted['true_elasticity']):.2f}"
    assert (
        f"The paid social effect came out at +{effect_pct}% (true +{true_pct}%). "
        f"The true value sits inside the likely range of {range_low}% to {range_high}%. "
        f"The implied response to spend was {elasticity} (true {true_elasticity})."
    ) in section

    true_v = {row["channel"]: float(row["V"]) for row in planted["channels"]}
    full_history = value.loc[value["months_unknown"] == 0]
    v_errors = [
        abs(float(row["V_median"]) - true_v[row["channel"]]) / true_v[row["channel"]] * 100
        for _, row in full_history.iterrows()
    ]
    v_within = round(max(v_errors), 1)
    assert (
        f"12-month value per subscriber came out within {v_within}% of the truth "
        "for every channel with full history."
    ) in section

    channel_truth = {row["channel"]: row for row in planted["channels"]}
    forecast_errors: list[float] = []
    for _, row in forecast.iterrows():
        truth = channel_truth[row["channel"]]
        expected = (
            float(truth["A"])
            * 52
            * math.sqrt(float(row["planned_weekly_spend"]) / float(truth["S"]))
        )
        forecast_errors.append(abs(float(row["total_median"]) - expected) / expected * 100)
        assert float(row["total_p5"]) <= expected <= float(row["total_p95"])
    forecast_within = round(max(forecast_errors))
    assert (
        f"2026 signup forecasts came out within {forecast_within}% of the true expected "
        "signups for every channel, and every true value sat inside its 90% range."
    ) in section

    assert "Tests check each of these, so a broken step fails the build." in section
