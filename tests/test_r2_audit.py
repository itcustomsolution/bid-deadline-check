"""Regressions for the independent audit of the r2 candidate (2026-10-17, R2-DL-1..R2-DL-4) and the pre-release
strict-mode gaps found while it ran. Synthetic text only; each input is the audit's reproduction or a sibling of it,
plus controls that must keep passing."""
import pytest

from bid_deadline_check import analyze
from bid_deadline_check.cli import main

BASE = "Questions due October 1, 2026 at 10:00 AM ET.\nTechnical proposal must not exceed 20 pages.\n"
COMPLETE = "Proposals due November 5, 2026 at 5:00 PM ET.\n"


def strict(tmp_path, text):
    f = tmp_path / "rfp.txt"
    f.write_text(text)
    return main([str(f), "--strict", "-f", "json"])


def proposals(r):
    return [(d.date, d.time, d.timezone, d.ambiguities) for d in r.deadlines if d.kind == "proposal_due"]


# R2-DL-3: one moment written with a different number of fractional digits is not two deadlines.
def test_r2_dl_3_trailing_fraction_zeros_are_the_same_moment(tmp_path):
    text = BASE + "Proposals due 2026-11-05T17:00:01.1Z.\nProposals due 2026-11-05T17:00:01.10Z."
    r = analyze(text)
    assert not any("different proposal due" in w for w in r.warnings)
    assert strict(tmp_path, text) == 0


def test_r2_dl_3_different_fractions_still_conflict(tmp_path):
    text = BASE + "Proposals due 2026-11-05T17:00:01.1Z.\nProposals due 2026-11-05T17:00:01.2Z."
    assert any("2 different proposal due" in w for w in analyze(text).warnings)
    assert strict(tmp_path, text) == 2


# R2-DL-4 and the strict gaps of the same class: a date glued to letters, a digit glued to a month name, or a year
# typed with a letter is never shortened into a clean date; it is reported as a date-like value instead.
@pytest.mark.parametrize("tail", [
    "Proposals due by 5:00 PM ET on November 5, 2026oops.",
    "Proposals due November 5, 2026oops at 5:00 PM ET.",
    "Proposals due by 5:00 PM ET on 5 November 2026x.",
    "Proposals due by 5:00 PM ET on 11/05/2026a.",
    "Proposals due 2026-11-05x at 5:00 PM ET.",
])
def test_r2_dl_4_letters_glued_after_a_date_are_not_a_clean_date(tmp_path, tail):
    r = analyze(BASE + tail)
    assert not any(d.kind == "proposal_due" and not d.ambiguities for d in r.deadlines)
    assert any("date-like value" in w for w in r.warnings)
    assert strict(tmp_path, BASE + tail) == 2


@pytest.mark.parametrize("tail", [
    "Site visit on 5November 2026 at 10:00 AM ET.",
    "Site visit on November5, 2026 at 10:00 AM ET.",
    "Site visit on November 3, 2O26 at 10:00 AM ET.",
    "Site visit on 3 November 2O26 at 10:00 AM ET.",
    "Site visit on 11/03/2O26 at 10:00 AM ET.",
])
def test_glued_month_and_letter_year_are_reported(tmp_path, tail):
    text = BASE + COMPLETE + tail
    assert any("date-like value" in w for w in analyze(text).warnings), tail
    assert strict(tmp_path, text) == 2


@pytest.mark.parametrize("tail, date", [
    ("Proposals due 2026-11-05T17:00Z.", "2026-11-05"),
    ("Proposals due 2026-11-05t17:00Z.", "2026-11-05"),
    ("Proposals due November 5, 2026, at 5:00 PM ET.", "November 5, 2026"),
    ("Proposals due November 5, 2026 (5:00 PM ET).", "November 5, 2026"),
    ("Proposals due onNovember 5, 2026 at 5:00 PM ET.", "November 5, 2026"),
])
def test_r2_dl_4_controls_still_read(tail, date):
    r = analyze(BASE + tail)
    assert [d.date for d in r.deadlines if d.kind == "proposal_due"] == [date]
    assert not any("date-like value" in w for w in r.warnings)
