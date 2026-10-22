"""r6: an unresolved deadline sentence must never leave a recognized old cutoff looking clean. Each unsafe case below gave
strict exit 0 on frozen r5 (e06cf5e) with only the old cutoff; it must now give NEEDS REVIEW (strict exit 2), name the
sentence with a reason and its exact source text, and mark the old deadline as not actionable. The controls read
cleanly on r5 and must stay READ. Synthetic text only."""
import io
import json

import pytest

from bid_deadline_check import analyze
from bid_deadline_check.cli import main

BASE = "Questions due October 1, 2026 at 10:00 AM ET.\nTechnical proposal must not exceed 20 pages.\n"
OLD = "Proposals due November 5, 2026 at 5:00 PM ET.\n"


def cli(text, *args):
    import contextlib, sys
    old = sys.stdin
    sys.stdin = io.StringIO(text)
    try:
        with contextlib.redirect_stdout(io.StringIO()) as o:
            rc = main(["-", *args])
    finally:
        sys.stdin = old
    return rc, o.getvalue()


def strict_json(text):
    rc, out = cli(text, "--strict", "-f", "json")
    return rc, json.loads(out)


UNSAFE = [
    ("Receipt of offers is extended by one week.", "change_not_read"),
    ("Alter the closing time to 3:00 PM ET.", "change_not_read"),
    ("The proposal submission window reopens for one week.", "change_not_read"),
    ("Proposals are due one week later than stated in the RFP.", "change_not_read"),
    ("The hour and date specified for receipt of Offers [X] is extended, [ ] is not extended.", "change_not_read"),
    ("The proposal due date is postponed until further notice, and offerors may continue to submit questions.", "change_not_read"),
    ("The closing date is cancelled.", "deadline_cancelled_or_suspended"),
    ("Proposal submission is postponed until further notice.", "deadline_cancelled_or_suspended"),
    ("Offers due: TBD; a new date will be set by amendment.", "deadline_to_be_determined"),
    ("Proposals are not due on the previously stated date.", "deadline_negated"),
    ("Amendment 0004: submit proposals by 3:00 PM ET.", "time_without_date"),
    ("Proposals shall be delivered before 2026.11.5 at 5:00 PM ET.", "unread_date_value"),
    ("Proposals due 2026 11 12 at 5:00 PM ET.", "unread_date_value"),
    ("Proposals are due no later than\n2026-11-5 at 5:00 PM ET.", "unread_date_value"),
    ("All times stated in this solicitation are Central Time, not Eastern Time.", "zone_statement"),
]


@pytest.mark.parametrize("line,reason", UNSAFE)
def test_r6_unresolved_change_beside_an_old_cutoff_needs_review(line, reason):
    rc, rep = strict_json(BASE + OLD + line)
    assert rc == 2, rep["warnings"]
    assert rep["outcome"] == "needs_review"
    items = [n for n in rep["needs_review"] if n["reason"] == reason]
    assert items, rep["needs_review"]
    exact = "\n".join((BASE + OLD + line).splitlines()[items[0]["line"] - 1:items[0]["end_line"]])
    assert items[0]["text"] == exact
    old = [d for d in rep["deadlines"] if d["kind"] == "proposal_due" and d["date"] == "November 5, 2026"]
    assert old and all(d["status"] == "needs_review" for d in old), old


def test_r6_accepted_until_is_a_second_proposal_deadline():
    rc, rep = strict_json(BASE + OLD + "Proposals will be accepted until November 12, 2026 at 5:00 PM ET.")
    assert rc == 2
    props = [d for d in rep["deadlines"] if d["kind"] == "proposal_due"]
    assert {d["date"] for d in props} == {"November 5, 2026", "November 12, 2026"}
    assert all(d["status"] == "needs_review" and "conflicting_proposal_due" in d["review"] for d in props)


@pytest.mark.parametrize("tail,code", [
    ("17:00 UTC+99:99", "zone_invalid"), ("17:00 UTC+05:20", "zone_invalid"), ("17:00 America/Not_A_Zone", "zone_invalid"),
    ("5:00 PM local time", "zone_unanchored"), ("5:00 PM ET or CT", "zone_conflict:CT"),
    ("5:00 PM EST (Eastern Daylight Time)", "zone_conflict:Eastern Daylight Time"),
    ("17:00 America/New_York or America/Chicago", "zone_conflict:America/Chicago"),
])
def test_r6_zones_that_cannot_be_acted_on_need_review(tail, code):
    rc, rep = strict_json(BASE + f"Proposals due November 5, 2026 at {tail}.")
    assert rc == 2
    (d,) = [d for d in rep["deadlines"] if d["kind"] == "proposal_due"]
    assert code in d["ambiguities"] and d["status"] == "needs_review", d


@pytest.mark.parametrize("date,code", [("Friday, November 5, 2026", "weekday_mismatch"), ("November 5, 0000", "implausible_year")])
def test_r6_dates_that_cannot_be_right_need_review(date, code):
    rc, rep = strict_json(BASE + f"Proposals due {date} at 5:00 PM ET.")
    assert rc == 2
    (d,) = [d for d in rep["deadlines"] if d["kind"] == "proposal_due"]
    assert code in d["ambiguities"]


@pytest.mark.parametrize("line", [
    "The agency publicized the proposal due date on November 5, 2026 at 5:00 PM ET.",
    "Offerors were notified of the proposal due date on November 5, 2026 at 5:00 PM ET.",
    "The notice about the proposal due date was handed out November 5, 2026 at 5:00 PM ET.",
])
def test_r6_announcement_dates_are_not_presented_as_the_deadline(line):
    rc, rep = strict_json(BASE + line)
    assert rc == 2
    (d,) = [d for d in rep["deadlines"] if d["kind"] == "proposal_due"]
    assert "issue_date_possible" in d["ambiguities"] and d["status"] == "needs_review"


# Controls: ordinary text, references to a deadline, unaltered standard clauses and restatements stay READ.
CONTROLS = [
    OLD + "The hour and date specified for receipt of Offers [ ] is extended, [X] is not extended.",
    OLD + "Presentation slides must be submitted with the proposal by the proposal due date.",
    OLD + "Oral presentations are limited to 15 slides and will be scheduled after the closing date.",
    "Proposals due November 5, 2026 at 5:00 PM ET (Eastern Time).",
    "Proposals due November 5, 2026 at 5:00 PM ET; proposals received after 5:00 PM ET will be rejected.",
    "Proposals due November 5, 2026 at noon ET; proposals received after 1200 hours ET will be rejected.",
    "As previously announced, proposals are due November 5, 2026 at 5:00 PM ET.",
    "Proposals due November 5, 2026 at 17:00 America/Argentina/Buenos_Aires, local time.",
    OLD + "If no time is specified in the solicitation, the time for receipt is 4:30 p.m., local time, for the designated "
          "Government office on the date that offers or revisions are due.",
    OLD + "If it was transmitted through an electronic commerce method authorized by the solicitation, it was received at the "
          "initial point of entry to the Government infrastructure not later than 5:00 p.m. one working day prior to the date "
          "specified for receipt of offers; or",
]


@pytest.mark.parametrize("text", CONTROLS)
def test_r6_controls_stay_read(text):
    rc, rep = strict_json(BASE + text)
    assert rc == 0, rep["warnings"]
    # r5 has no outcome or status fields; these lines check them where they exist (they read cleanly on r5 too)
    assert rep.get("outcome", "read") == "read" and not rep.get("needs_review")
    assert all(d.get("status", "actionable") == "actionable" for d in rep["deadlines"])


@pytest.mark.parametrize("altered", [
    "If no time is specified in the solicitation, the time for receipt is 3:00 p.m., local time, for the designated "
    "Government office on the date that offers or revisions are due.",
    "If it was transmitted through an electronic commerce method authorized by the solicitation, it was received at the "
    "initial point of entry to the Government infrastructure not later than 5:00 p.m. two working days prior to the date "
    "specified for receipt of offers; or",
    "If no time is specified in the solicitation, the time for receipt is 4:30 p.m., local time, for the designated "
    "Government office on the date that offers or revisions are due; the closing time is now 3:00 PM ET.",
])
def test_r6_an_altered_standard_clause_is_reviewed(altered):
    rc, rep = strict_json(BASE + OLD + altered)
    assert rc == 2 and rep["needs_review"], rep["warnings"]


def test_r6_a_wrapped_standard_clause_still_reads():
    text = (BASE + OLD + "If no time is specified in the solicitation, the time for receipt is 4:30 p.m., local time,\n"
            "for the designated Government office on the date that offers or revisions are due.")
    assert strict_json(text)[0] == 0


def test_r6_exact_source_text_is_kept_with_its_spacing_and_line_breaks():
    text = BASE + OLD + "Receipt   of offers  is\n  extended by one week."
    rc, rep = strict_json(text)
    (item,) = [n for n in rep["needs_review"] if n["reason"] == "change_not_read"]
    assert item["text"] == "Receipt   of offers  is\n  extended by one week." and (item["line"], item["end_line"]) == (4, 5)


def test_r6_text_output_leads_with_the_outcome_and_holds_the_old_deadline():
    rc, out = cli(BASE + OLD + "The closing date is cancelled.", "--strict")
    assert rc == 2
    assert out.splitlines()[0].startswith("OUTCOME: NEEDS REVIEW")
    assert "deadline_cancelled_or_suspended" in out and "NOT ACTIONABLE AS STATED" in out
    rc, out = cli(BASE + OLD, "--strict")
    assert rc == 0 and out.splitlines()[0] == "OUTCOME: READ"


def test_r6_checklist_rows_carry_the_review_items():
    r = analyze(BASE + OLD + "The closing date is cancelled.")
    rows = r.checklist()
    assert rows[0]["category"] == "needs_review" and rows[0]["line"] == 4
    assert any("NOT ACTIONABLE" in row["item"] for row in rows if row["category"] == "deadline")


def test_r6_review_items_past_the_listing_cap_still_hold_every_deadline():
    filler = "".join(f"Section {i}: the questions due date is extended by one week.\n" for i in range(60))
    rc, rep = strict_json(BASE + filler + OLD)
    assert rc == 2 and len(rep["needs_review"]) == 50
    assert any("more sentences about a deadline" in w for w in rep["warnings"])
    assert all(d["status"] == "needs_review" for d in rep["deadlines"]), rep["deadlines"]
