"""Regressions for the independent audit of the r4 candidate (2026-10-17, R4-DL-1..R4-DL-3). Synthetic text only;
inputs are the audit's minimal cases (its receipt case names are given) or siblings, plus its controls. These close
the named forms only: a clean --strict result still never means every deadline was found or is right."""
import pytest

from bid_deadline_check import analyze
from bid_deadline_check.cli import main

BASE = "Questions due October 1, 2026 at 10:00 AM ET.\nTechnical proposal must not exceed 20 pages.\n"
OLD = "Proposals due November 5, 2026 at 5:00 PM ET.\n"


def strict(tmp_path, text):
    f = tmp_path / "rfp.txt"
    f.write_text(text)
    return main([str(f), "--strict", "-f", "json"])


def proposals(r):
    return [(d.date, d.time, d.timezone, d.ambiguities) for d in r.deadlines if d.kind == "proposal_due"]


# R4-DL-1: a day-first date with an ordinal suffix was never checked against the calendar.
@pytest.mark.parametrize("date", ["31st February 2026", "29th February 2026", "31st April 2026", "0th November 2026",
                                  "99th November 2026", "30th February 2028"])
def test_r4_dl_1_impossible_ordinal_dates_are_invalid(tmp_path, date):
    text = BASE + f"Proposals due {date} at 5:00 PM ET."
    assert any(d == date and "invalid_date" in a for d, t, z, a in proposals(analyze(text))), proposals(analyze(text))
    assert strict(tmp_path, text) == 2


@pytest.mark.parametrize("date", ["5th November 2026", "29th February 2028", "29 February 2028", "1st March 2027"])
def test_r4_dl_1_valid_ordinal_controls_stay_clean(tmp_path, date):
    assert strict(tmp_path, BASE + f"Proposals due {date} at 5:00 PM ET.") == 0


def test_r4_dl_1_ordinal_and_plain_forms_compare_equal(tmp_path):
    text = BASE + "Proposals due 5th November 2026 at 5:00 PM ET.\nProposals due November 5, 2026 at 5:00 PM ET."
    assert not any("different proposal due" in w for w in analyze(text).warnings)
    assert strict(tmp_path, text) == 0


# R4-DL-2: a malformed date beside a valid old cutoff disappeared and left the old cutoff clean.
@pytest.mark.parametrize("value", ["2026-11-005", "2026-111-05", "20260-11-05", "11/12/2026/2027", "November 12, 26",
                                   "November, 12, 2026", "12.11.2026", "2026/11/12", "2026.11.12"])
def test_r4_dl_2_malformed_second_deadline_is_reported(tmp_path, value):
    text = BASE + OLD + f"Proposals due {value} at 5:00 PM ET."
    r = analyze(text)
    assert any("date-like value" in w and "line 4" in w.lower() for w in r.warnings), r.warnings
    assert strict(tmp_path, text) == 2


@pytest.mark.parametrize("tail", [
    "Proposals must follow Section 3.4.1 and FAR 52.212-1.",
    "Refer to part number 2026-1145-AB and drawing 12.11.B.",
    "See paragraphs 1.2.3 through 1.2.10 of the statement of work.",
    "The contract number is 47QTCA-26-D-0001.",
])
def test_r4_dl_2_part_and_section_numbers_stay_clean(tmp_path, tail):
    assert strict(tmp_path, BASE + OLD + tail) == 0


# R4-DL-3: an offset followed by a fraction was cut to the shorter valid offset.
@pytest.mark.parametrize("tail", ["Proposals due November 5, 2026 at 17:00 UTC+05:30.5.",
                                  "Proposals due November 5, 2026 at 17:00 GMT+5.5.",
                                  "Proposals due 2026-11-05T17:00:00-04:00.5."])
def test_r4_dl_3_fractional_offset_is_unclear(tmp_path, tail):
    r = analyze(BASE + tail)
    assert any("timezone_unclear" in a for d, t, z, a in proposals(r)), proposals(r)
    assert strict(tmp_path, BASE + tail) == 2


@pytest.mark.parametrize("tail", ["Proposals due November 5, 2026 at 17:00 UTC+05:30.",
                                  "Proposals due November 5, 2026 at 17:00 GMT+5.",
                                  "Proposals due 2026-11-05T17:00:00-04:00.",
                                  "Proposals due November 5, 2026 at 17:00 UTC-04:00. 5 copies are required."])
def test_r4_dl_3_offset_before_sentence_end_stays_clean(tmp_path, tail):
    assert strict(tmp_path, BASE + tail) == 0
