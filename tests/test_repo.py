"""Repo-wide checks for the README and tracked text."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EM_DASH = "\u2014"
SKIP_SUFFIXES = {".parquet", ".png", ".pptx", ".pdf", ".pyc"}
SKIP_NAMES = {"uv.lock"}


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
