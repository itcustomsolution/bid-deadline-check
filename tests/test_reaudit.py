"""Regressions for the independent re-audit of 2026-10-17 (RBD-1..RBD-5). Synthetic text only; the inputs are the
re-audit's minimal reproductions, plus controls that must keep passing."""
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


# RBD-1: a from/to amendment keeps both dates, marks the old one superseded and the new one as a replacement.
@pytest.mark.parametrize("verb", ["is extended from", "has been changed from", "is moved from", "is postponed from"])
def test_rbd1_from_to_amendment(tmp_path, verb):
    text = BASE + f"The proposal due date {verb} November 5, 2026 at 5:00 PM ET to November 12, 2026 at 5:00 PM ET."
    assert proposals(analyze(text)) == [("November 5, 2026", "5:00 PM", "ET", ["negated_or_withdrawn"]),
                                        ("November 12, 2026", "5:00 PM", "ET", ["replaces_earlier_date"])]
    assert strict(tmp_path, text) == 2


def test_rbd1_extended_to_without_from():
    r = analyze(BASE + "The proposal due date of November 5, 2026 at 5:00 PM ET is extended to November 12, 2026 at 5:00 PM ET.")
    assert proposals(r) == [("November 5, 2026", "5:00 PM", "ET", ["negated_or_withdrawn"]),
                            ("November 12, 2026", "5:00 PM", "ET", ["replaces_earlier_date"])]


def test_rbd1_period_of_performance_range_is_not_an_amendment():
    r = analyze(BASE + COMPLETE + "The period of performance runs from January 1, 2027 to December 31, 2027.")
    assert proposals(r) == [("November 5, 2026", "5:00 PM", "ET", [])]
    assert r.warnings == []


# RBD-2: another clock time in the same sentence is attached to the deadline and fails strict.
@pytest.mark.parametrize("text, other", [
    ("Proposals due November 5, 2026 at 5:00 PM ET, changed to 6:00 PM ET.", "6:00 PM ET"),
    ("Proposals due November 5, 2026 at 5:00 PM ET for electronic copies and 3:00 PM ET for hand delivery.", "3:00 PM ET"),
    ("Proposals due November 5, 2026 at 5:00 PM ET; revised proposals at 6:00 PM ET.", "6:00 PM ET"),
])
def test_rbd2_other_times_in_the_sentence_are_flagged(tmp_path, text, other):
    r = analyze(BASE + text)
    assert proposals(r) == [("November 5, 2026", "5:00 PM", "ET", [f"other_time:{other}"])]
    assert any(other in w for w in r.warnings)
    assert strict(tmp_path, BASE + text) == 2


def test_rbd2_times_already_bound_or_in_another_sentence_are_not_extra():
    for text in ("Site visit November 5, 2026 from 9:00 AM until 11:00 AM ET; proposals due November 12, 2026 at 5:00 PM ET.",
                 "Site visit: November 5, 2026, 9:00 AM - 11:00 AM ET.\nProposals due November 12, 2026 at 5:00 PM ET.",
                 "Proposals due November 12, 2026 at 5:00 PM ET. The office opens at 9:00 AM.",
                 "Proposals due November 12, 2026 at 17:00 UTC-04:00."):
        assert not any(a.startswith("other_time:") for d in analyze(BASE + text).deadlines for a in d.ambiguities), text


# RBD-3: seconds are part of the comparison.
def test_rbd3_seconds_distinguish_deadlines(tmp_path):
    text = BASE + "Proposals due November 5, 2026 at 17:00:01 ET.\nProposals due November 5, 2026 at 17:00:59 ET."
    assert any("2 different proposal due" in w for w in analyze(text).warnings)
    assert strict(tmp_path, text) == 2
    same = BASE + "Proposals due November 5, 2026 at 17:00:01 ET.\nProposals due November 5, 2026 at 5:00:01 PM ET."
    assert analyze(same).warnings == []


# RBD-4: an obligation cut by a colon-led list or a blank line is an excerpt, never a complete requirement.
@pytest.mark.parametrize("tail, text", [
    ("The offeror shall submit the following:\n(a) a signed certification.", "The offeror shall submit the following:"),
    ("The offeror shall:\n(a) a signed certification.", "The offeror shall:"),
    ("The offeror shall provide all\n\na certification before award.", "The offeror shall provide all"),
])
def test_rbd4_interrupted_obligations_are_flagged(tmp_path, tail, text):
    r = analyze(BASE + COMPLETE + tail)
    req = [q for q in r.requirements if q["text"].startswith(text[:15])]
    assert req and req[0]["truncated"] is True and req[0]["text"].startswith(text)
    assert any("Requirement on line" in w for w in r.warnings)
    assert strict(tmp_path, BASE + COMPLETE + tail) == 2


def test_rbd4_finished_sentences_before_a_blank_line_are_not_flagged():
    r = analyze(BASE + COMPLETE + "The offeror shall provide a signed certification.\n\nThe contractor shall keep records.")
    assert [q["truncated"] for q in r.requirements] == [False, False, False]


# RBD-5: a malformed date or zone is flagged, never shortened into a valid-looking value.
@pytest.mark.parametrize("text", [
    "Proposals due 111/05/2026 at 5:00 PM ET.",
    "Proposals due by 5:00 PM ET on November 5, 20260.",
])
def test_rbd5_malformed_dates_are_not_shortened(tmp_path, text):
    r = analyze(BASE + text)
    assert proposals(r) == []
    assert any("date-like value" in w for w in r.warnings)
    assert strict(tmp_path, BASE + text) == 2


@pytest.mark.parametrize("zone", ["UTC+05:300", "UTC+05:30:15", "America/Argentina/Buenos_Aires/Other", "America/" + "A" * 40])
def test_rbd5_malformed_zones_are_not_shortened(tmp_path, zone):
    text = BASE + f"Proposals due November 5, 2026 at 17:00 {zone}."
    (d,) = [d for d in analyze(text).deadlines if d.kind == "proposal_due"]
    assert d.timezone is None and d.ambiguities == ["timezone_unclear"]
    assert strict(tmp_path, text) == 2


@pytest.mark.parametrize("zone", ["UTC-04:00", "GMT+05:30", "UTC+0530", "America/Argentina/Buenos_Aires", "America/New_York"])
def test_rbd5_supported_zones_are_kept_whole(zone):
    (d,) = [d for d in analyze(BASE + f"Proposals due November 5, 2026 at 17:00 {zone}.").deadlines if d.kind == "proposal_due"]
    assert (d.timezone, d.ambiguities) == (zone, [])


def test_rbd5_supported_dates_are_kept_whole():
    for date in ("11/05/2026", "2026-11-05", "November 5, 2026", "5 November 2026"):
        (d,) = [d for d in analyze(BASE + f"Proposals due {date} at 5:00 PM ET.").deadlines if d.kind == "proposal_due"]
        assert d.date == date
    assert proposals(analyze(BASE + "Proposals due 2026-11-05T17:00:00-04:00.")) == [("2026-11-05", "17:00:00", "-04:00", [])]


def test_rbd2_other_times_are_bounded_per_deadline():
    times = ", ".join(f"{h}:00 PM ET" for h in range(1, 10))
    (d,) = [d for d in analyze(BASE + f"Proposals due November 5, 2026 at 5:00 PM ET, or {times}.").deadlines if d.kind == "proposal_due"]
    assert sum(a.startswith("other_time:") for a in d.ambiguities) == 5


# r2 independent review (kofi, KR2-01 to KR2-09). Synthetic text only.
from bid_deadline_check import core  # module import, so these tests also run against earlier commits


def kinds(r):
    return [(d.kind, d.date, d.time, d.ambiguities) for d in r.deadlines if d.kind != "questions_due"]


@pytest.mark.parametrize("text", [
    "The due date for receipt of proposals is extended from 5:00 PM ET on November 5, 2026 to 5:00 PM ET on November 12, 2026.",
    "The proposal due date is extended from November 5, 2026 to 5:00 PM ET on November 12, 2026.",
])
def test_kr2_01_amendment_with_the_time_written_first(tmp_path, text):
    (old, new) = kinds(analyze(BASE + text))
    assert old[1] == "November 5, 2026" and "negated_or_withdrawn" in old[3]
    assert new[1:3] == ("November 12, 2026", "5:00 PM") and "replaces_earlier_date" in new[3]
    assert strict(tmp_path, BASE + text) == 2


def test_kr2_01_a_date_without_a_time_does_not_take_the_next_dates_zone():
    (old, _new) = [d for d in analyze(BASE + "The proposal due date is extended from November 5, 2026 to 5:00 PM ET on "
                                          "November 12, 2026.").deadlines if d.kind == "proposal_due"]
    assert (old.time, old.timezone) == (None, None)


@pytest.mark.parametrize("text", [
    "The hour and date specified for receipt of Offers is extended to 5:00 PM ET on November 12, 2026.",
    "This date is extended to November 12, 2026 at 5:00 PM ET.",
    "Block 8 of the SF-1449 is changed to read: November 12, 2026 at 5:00 PM ET.",
])
def test_kr2_07_an_amendment_naming_only_the_new_date_is_reported(tmp_path, text):
    r = analyze(BASE + COMPLETE + text)
    assert any(d.date == "November 12, 2026" and "replaces_earlier_date" in d.ambiguities for d in r.deadlines)
    assert strict(tmp_path, BASE + COMPLETE + text) == 2


def test_kr2_07_a_period_of_performance_change_is_not_a_deadline():
    r = analyze(BASE + COMPLETE + "The period of performance is extended from January 1, 2027 to June 30, 2027.")
    assert kinds(r) == [("proposal_due", "November 5, 2026", "5:00 PM", [])] and r.warnings == []


@pytest.mark.parametrize("a, b", [("noon", "12:00 PM"), ("1700 hours", "5:00 PM"), ("1700 hrs", "17:00"), ("12:00 noon", "noon")])
def test_kr2_02_one_moment_written_two_ways_is_not_a_conflict(a, b):
    r = analyze(BASE + f"Proposals due November 5, 2026 at {a} ET.\nProposals due November 5, 2026 at {b} ET.")
    assert r.warnings == []


@pytest.mark.parametrize("text", [
    "Section L - Instructions to Offerors\n\nThe offeror shall submit its proposal in three volumes.",
    "Technical Approach\n\nThe offeror shall describe its approach.",
    "Volume I - Technical\n\nThe offeror shall describe its approach.",
    "Point of Contact:\nJane Doe, Contracting Officer\n\nThe offeror shall direct all questions to the point of contact.",
    "Table of Contents\n\n1. Introduction\n2. Scope\n\nThe contractor shall provide all labor.",
])
def test_kr2_03_a_heading_and_a_blank_line_do_not_cut_the_next_requirement(tmp_path, text):
    r = analyze(BASE + COMPLETE + text)
    assert [q["truncated"] for q in r.requirements] == [False] * len(r.requirements)
    assert strict(tmp_path, BASE + COMPLETE + text) == 0


@pytest.mark.parametrize("tail", [
    "; proposals received after 5:00 PM ET will be rejected.",
    ", i.e., by 5:00 PM ET on that date.",
    " (1700 hours).",
    ". Late offers are handled within 120 hours of the deadline, see L.5.",
])
def test_kr2_04_a_restated_time_or_a_duration_is_not_another_cutoff(tail):
    r = analyze(BASE + "Proposals due November 5, 2026 at 5:00 PM ET" + tail)
    assert kinds(r) == [("proposal_due", "November 5, 2026", "5:00 PM", [])]


def test_kr2_04_a_time_in_another_zone_is_still_flagged():
    # Possibly the same moment, but the tool does not convert zones, so the reader is sent to the source.
    (d,) = kinds(analyze(BASE + "Proposals due November 5, 2026 at 5:00 PM ET (2:00 PM PT)."))
    assert d[3] == ["other_time:2:00 PM PT"]


def test_kr2_05_a_later_dated_event_does_not_inherit_the_deadline_kind():
    r = analyze(BASE + "Proposals due November 5, 2026 at 5:00 PM ET, with debriefings on December 1, 2026 at 10:00 AM ET.")
    assert kinds(r) == [("proposal_due", "November 5, 2026", "5:00 PM", []), ("other", "December 1, 2026", "10:00 AM", ["kind_uncertain"])]
    assert not any("different proposal due" in w for w in r.warnings)


@pytest.mark.parametrize("text, date", [
    ("Proposals due onNovember 5, 2026 at 5:00 PM ET.", "November 5, 2026"),
    ("Proposals due11/05/2026 at 5:00 PM ET.", "11/05/2026"),
    ("Proposals due x2026-11-05 at 5:00 PM ET.", "2026-11-05"),
    ("Proposals due 5th November 2026 at 5:00 PM ET.", "5th November 2026"),
])
def test_kr2_06_kr2_09_glued_and_ordinal_dates_are_read(text, date):
    assert [d.date for d in analyze(BASE + text).deadlines if d.kind == "proposal_due"] == [date]


def test_kr2_06_both_ends_of_an_iso_interval_are_dates():
    assert [m.group(0) for m in core.DATE_RE.finditer("2027-01-01/2027-06-30")] == ["2027-01-01", "2027-06-30"]


def test_kr2_08_malformed_date_warnings_are_capped():
    r = analyze(BASE + COMPLETE + "111/05/2026 " * 500)
    listed = [w for w in r.warnings if w.startswith("Line ") and "date-like value" in w]
    cap = getattr(core, "MAX_MALFORMED_WARNINGS", None)
    assert cap is not None and len(listed) == cap
    assert any(w.startswith(f"{500 - cap} more date-like values") for w in r.warnings)
