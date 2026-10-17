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


# R2-DL-2: an issue or amendment date written after the deadline words is not reported as a clean deadline.
@pytest.mark.parametrize("tail", [
    "Amendment 0004 for the proposal due date was issued October 2, 2026 at 5:00 PM ET.",
    "The amendment changing the proposal deadline was posted October 2, 2026 at 5:00 PM ET.",
    "The notice about the closing date was released October 2, 2026 at 5:00 PM ET.",
])
def test_r2_dl_2_an_issue_date_after_deadline_words_is_flagged(tmp_path, tail):
    r = analyze(BASE + tail)
    assert not any(d.kind == "proposal_due" and not d.ambiguities for d in r.deadlines)
    assert strict(tmp_path, BASE + tail) == 2


def test_r2_dl_2_issued_then_sets_the_due_date_control(tmp_path):
    text = BASE + "Amendment 0004 issued October 2, 2026 at 5:00 PM ET sets the proposal due date to November 12, 2026 at 5:00 PM ET."
    assert proposals(analyze(text)) == [("November 12, 2026", "5:00 PM", "ET", [])]
    assert strict(tmp_path, text) == 0


def test_r2_dl_2_issue_words_before_the_deadline_words_are_not_flagged(tmp_path):
    text = BASE + "As amended, proposals are due November 12, 2026 at 5:00 PM ET."
    assert proposals(analyze(text)) == [("November 12, 2026", "5:00 PM", "ET", [])]
    assert strict(tmp_path, text) == 0


OLD = ("November 5, 2026", "5:00 PM", "ET", ["negated_or_withdrawn"])
NEW = ("November 12, 2026", "5:00 PM", "ET", ["replaces_earlier_date"])


# R2-DL-1: these revision wordings returned only the old date, unflagged, and --strict returned 0.
@pytest.mark.parametrize("tail", [
    "The proposal deadline is changed from the current date of November 5, 2026 at 5:00 PM ET to November 12, 2026 at 5:00 PM ET.",
    "The extension of the proposal due date from November 5, 2026 at 5:00 PM ET to November 12, 2026 at 5:00 PM ET is authorized.",
    "The proposal deadline was previously November 5, 2026 at 5:00 PM ET; it is now November 12, 2026 at 5:00 PM ET.",
    "The proposal due date is moved from its original date of November 5, 2026 at 5:00 PM ET to November 12, 2026 at 5:00 PM ET.",
])
def test_r2_dl_1_both_dates_of_a_revision_are_read(tmp_path, tail):
    assert proposals(analyze(BASE + tail)) == [OLD, NEW]
    assert strict(tmp_path, BASE + tail) == 2


# Any other date in a sentence that changes something, and that was not read as a deadline, is named in a warning,
# so a revision worded in a way this tool does not read never leaves a clean checklist.
@pytest.mark.parametrize("tail", [
    "The proposal deadline is reset from November 5, 2026 at 5:00 PM ET to November 12, 2026 at 5:00 PM ET.",
    "Proposals due November 5, 2026 at 5:00 PM ET are updated to the new date, November 12, 2026.",
])
def test_r2_dl_1_an_unread_date_in_a_change_sentence_is_named(tmp_path, tail):
    r = analyze(BASE + tail)
    assert any("November 12, 2026" in w and "not read as a deadline" in w for w in r.warnings), r.warnings
    assert strict(tmp_path, BASE + tail) == 2


@pytest.mark.parametrize("tail", [
    "Proposals due November 5, 2026 at 5:00 PM ET for performance from January 1, 2027 to December 31, 2027.",
    "Amendment 0004 issued October 2, 2026 at 5:00 PM ET sets the proposal due date to November 5, 2026 at 5:00 PM ET.",
])
def test_r2_dl_1_other_dates_in_a_plain_deadline_sentence_are_not_flagged(tmp_path, tail):
    r = analyze(BASE + tail)
    assert proposals(r) == [("November 5, 2026", "5:00 PM", "ET", [])]
    assert strict(tmp_path, BASE + tail) == 0


# A sentence that changes a deadline's clock time without giving a date fails --strict; nothing in it is a deadline
# this tool can place, so the original deadline must not look final.
@pytest.mark.parametrize("tail", [
    "The closing time is revised from 5:00 PM ET to 3:00 PM ET.",
    "The closing time is now 3:00 PM ET.",
    "The time for receipt of offers is changed to 3:00 PM ET.",
    "The proposal due time is moved to COB.",
])
def test_a_time_only_revision_fails_strict(tmp_path, tail):
    text = BASE + COMPLETE + tail
    assert any("change wording and a time but no date" in w for w in analyze(text).warnings)
    assert strict(tmp_path, text) == 2


@pytest.mark.parametrize("tail", [
    "The reading room is open from 9:00 AM to 5:00 PM ET.",
    "Late offers are handled within 120 hours of the deadline.",
])
def test_a_time_without_change_wording_is_not_a_revision(tmp_path, tail):
    assert strict(tmp_path, BASE + COMPLETE + tail) == 0


def test_time_only_revision_warnings_are_capped():
    from bid_deadline_check import core
    r = analyze(BASE + COMPLETE + "The closing time is now 3:00 PM ET.\n" * 80)
    listed = [w for w in r.warnings if w.startswith("Line ") and "change wording and a time but no date" in w]
    assert len(listed) == core.MAX_MALFORMED_WARNINGS
    assert any(w.startswith("30 more clauses") for w in r.warnings)
