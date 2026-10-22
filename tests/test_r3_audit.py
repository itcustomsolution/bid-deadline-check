"""Regressions for the independent audit of the r3 candidate (2026-10-17, R3-DL-1..R3-DL-3). Synthetic text only;
each input is the audit's reproduction (its receipt case ids are named) or a sibling of it, plus the audit's own
controls, which must keep passing. A clean --strict result still never means no amendment changed a deadline."""
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


# R3-DL-1: change wording the tool did not know left only the old cutoff, with no warning.
@pytest.mark.parametrize("tail", [
    "The closing time is altered to 3:00 PM ET.",                              # independent_time_altered
    "The proposal due date is brought forward by two days.",                   # independent_brought_forward
    "All prior closing times are revoked; closing time is 3:00 PM ET.",        # independent_revoked_clock
    "The proposal due date is rescinded pending a new amendment.",
    "The closing date is adjusted by one week.",
    "The proposal due date is accelerated by two days.",
    "The proposal due date is suspended pending resolution of a protest.",     # r3c fresh case F04
    "The proposal due date slides one week to accommodate the site visit.",    # r3c fresh case F07
])
def test_r3_dl_1_more_change_verbs_leave_the_old_cutoff_unresolved(tmp_path, tail):
    r = analyze(BASE + COMPLETE + tail)
    assert ("November 5, 2026", "5:00 PM", "ET", []) in proposals(r)  # the old cutoff is still reported
    assert any("change" in w for w in r.warnings), r.warnings
    assert strict(tmp_path, BASE + COMPLETE + tail) == 2


def test_r3_dl_1_generic_deadline_adjusted_to_a_date_is_a_replacement(tmp_path):
    text = BASE + COMPLETE + "The deadline is adjusted to November 12, 2026 at 5:00 PM ET."
    r = analyze(text)
    assert any(d.date == "November 12, 2026" and "replaces_earlier_date" in d.ambiguities for d in r.deadlines)
    assert strict(tmp_path, text) == 2


@pytest.mark.parametrize("tail", [
    "No alteration to the closing time is authorized.",                         # independent_no_alteration_control
    "The proposal deadline is unchanged at November 5, 2026 at 5:00 PM ET.",    # independent_unchanged_control
    "Offerors may adjust their technical approach before the proposal due date.",
    "Pricing adjustments are due with the proposal.",
])
def test_r3_dl_1_controls_stay_clean(tmp_path, tail):
    assert strict(tmp_path, BASE + COMPLETE + tail) == 0


# R3-DL-2: an announcement timestamp became a clean proposal cutoff.
@pytest.mark.parametrize("tail", [
    "The proposal due date was publicized October 2, 2026 at 5:00 PM ET.",                  # independent_issue_publicized
    "The notice about the proposal due date was delivered October 2, 2026 at 5:00 PM ET.",  # independent_notice_delivered
    "The proposal due date was communicated to offerors October 2, 2026 at 5:00 PM ET.",
    "The proposal due date was advertised October 2, 2026 at 5:00 PM ET.",
    "The proposal due date was made public on October 2, 2026 at 5:00 PM ET.",
])
def test_r3_dl_2_announcement_timestamps_are_flagged(tmp_path, tail):
    r = analyze(BASE + tail)
    assert all("issue_date_possible" in a for d, t, z, a in proposals(r) if d == "October 2, 2026"), proposals(r)
    assert strict(tmp_path, BASE + tail) == 2


@pytest.mark.parametrize("tail, date", [
    ("Amendment 0004 issued October 2, 2026 at 5:00 PM ET sets the proposal due date to November 12, 2026 at 5:00 PM ET.",
     "November 12, 2026"),                                                                   # issuance_then_due_control
    ("Proposals must be delivered by November 5, 2026 at 5:00 PM ET.", "November 5, 2026"),
    ("Proposals are due and must be delivered by November 5, 2026 at 5:00 PM ET.", "November 5, 2026"),
    ("Proposals are due, signed and dated, by November 5, 2026 at 5:00 PM ET.", "November 5, 2026"),  # independent_signed_dated_control
])
def test_r3_dl_2_submission_controls_stay_clean(tmp_path, tail, date):
    r = analyze(BASE + tail)
    assert any(d == date and a == [] for d, t, z, a in proposals(r)), proposals(r)
    assert strict(tmp_path, BASE + tail) == 0


# R3-DL-3: letters or digits glued to a zone were dropped and a shorter zone reported.
@pytest.mark.parametrize("tail, zone", [
    ("Proposals due 2026-11-05T17:00:00Zdraft.", "Z"),                          # independent_ISO_Z_suffix
    ("Proposals due 2026-11-05T17:00:00-04:00junk.", "-04:00"),                # independent_ISO_offset_suffix
    ("Proposals due November 5, 2026 at 17:00 UTC+05:30junk.", "UTC+05:30"),   # independent_UTC_letter_suffix
    ("Proposals due November 5, 2026 at 17:00 UTC-04:00_draft.", "UTC-04:00"),
])
def test_r3_dl_3_zone_glued_to_text_is_flagged(tmp_path, tail, zone):
    r = analyze(BASE + tail)
    assert any(z == zone and "timezone_glued_to_text" in a for d, t, z, a in proposals(r)), proposals(r)
    assert strict(tmp_path, BASE + tail) == 2


@pytest.mark.parametrize("tail", [
    "Proposals due 2026-11-05T17:00:00Z.",
    "Proposals due 2026-11-05T17:00:00-04:00, as stated in Block 8.",
    "Proposals due November 5, 2026 at 17:00 UTC+05:30.",
    "Proposals due November 5, 2026 (17:00 UTC-04:00).",
    "Proposals due November 5, 2026 at 5:00 PM ET.",
])
def test_r3_dl_3_zone_controls_stay_clean(tmp_path, tail):
    assert strict(tmp_path, BASE + tail) == 0


# r4 review (kofi): the r4 verb list missed "slid" and "brings ... forward"; "slides" the noun and some announcement
# words in ordinary text raised false alarms. The cases are the reviewer's.
@pytest.mark.parametrize("tail", [
    "The proposal due date slid by one week.",                                  # M01
    "Amendment 0002 brings the proposal due date forward by two days.",          # M18
    "The proposal due date slides back to November 3, 2026.",
    "The proposal due date slides two weeks.",                                  # round 2: plural units
    "The proposal due date slides three days.",
    "The proposal due date slides ten days.",
    "The proposal due date slides a full week.",
    "The proposal due date slides 7 days.",
    "The closing date is sliding by two business days.",
])
def test_r4_review_revisions_now_fail(tmp_path, tail):
    assert strict(tmp_path, BASE + COMPLETE + tail) == 2


@pytest.mark.parametrize("tail", [
    "The proposal due date was conveyed to offerors October 2, 2026 at 5:00 PM ET.",                       # S01
    "The notice of the proposal due date was provided to offerors October 2, 2026 at 5:00 PM ET.",         # S02
    "The proposal due date was shared with industry on October 2, 2026 at 5:00 PM ET.",                    # S03
    "The notice about the proposal due date was faxed October 2, 2026 at 5:00 PM ET.",                     # S05
    "The proposal due date was disclosed October 2, 2026 at 5:00 PM ET.",                                  # S07
])
def test_r4_review_announcement_siblings_are_flagged(tmp_path, tail):
    assert strict(tmp_path, BASE + tail) == 2


@pytest.mark.parametrize("tail", [
    "Presentation slides must be submitted with the proposal by the proposal due date.",                    # C01
    "Oral presentations are limited to 15 slides and will be scheduled after the closing date.",             # C02
    "Offerors are encouraged to bring forward any questions well before the question deadline.",             # C07
    "Submit presentation slides by the proposal due date.",
    "Registration fees follow a sliding scale and are due by the registration deadline.",   # round 2
    "Sliding doors at the loading dock are locked after the closing time.",
    "Presentation slides two through five must show the schedule; slides are due with the proposal.",
])
def test_r4_review_slides_and_bring_forward_controls_stay_clean(tmp_path, tail):
    assert strict(tmp_path, BASE + COMPLETE + tail) == 0


@pytest.mark.parametrize("tail, date", [
    ("The bid due date, as advertised in the legal notice, is November 5, 2026 at 5:00 PM ET.", "November 5, 2026"),        # C11
    ("Hand-carried proposals due under this RFQ must have been delivered to the mailroom by November 5, 2026 at 5:00 PM ET.",
     "November 5, 2026"),                                                                                                  # C13
    ("Proposals are due November 5, 2026 at 5:00 PM ET; bid tabulations will be made public after the bid due date.", "November 5, 2026"),
])
def test_r4_review_announcement_words_in_ordinary_text_stay_clean(tmp_path, tail, date):
    r = analyze(BASE + tail)
    assert any(d == date and a == [] for d, t, z, a in proposals(r)), proposals(r)
    assert strict(tmp_path, BASE + tail) == 0
