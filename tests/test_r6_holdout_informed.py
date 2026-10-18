"""r6, second change: classes of wording found by the one run of holdout set v1 on e62299f (see the release package's
holdout contamination record). The sentences here are new synthetic text written for these tests, not copies of
holdout cases. UNSAFE cases gave strict exit 0, or kept the old cutoff actionable, on e62299f and on frozen r5
(e06cf5e); they must now need review and hold the old cutoff. FALSE_FAILURES were NEEDS REVIEW although nothing is
unresolved; they must now read. Controls must read on all three."""
import io
import json

import pytest

from bid_deadline_check import analyze
from bid_deadline_check.cli import main

BASE = "Questions due October 1, 2026 at 10:00 AM ET.\nTechnical proposal must not exceed 20 pages.\n"
OLD = "Proposals due November 5, 2026 at 5:00 PM ET.\n"


def strict_json(text):
    import contextlib, sys
    old = sys.stdin
    sys.stdin = io.StringIO(text)
    try:
        with contextlib.redirect_stdout(io.StringIO()) as o:
            rc = main(["-", "--strict", "-f", "json"])
    finally:
        sys.stdin = old
    return rc, json.loads(o.getvalue())


def held(rep, kind="proposal_due"):
    ds = [d for d in rep["deadlines"] if d["kind"] == kind]
    return bool(ds) and all(d.get("status") == "needs_review" for d in ds)


UNSAFE_ALL_HELD = [  # the whole solicitation is void or a draft: every deadline is held, questions too
    "RFQ 27-ZZ-003 has been withdrawn. No quotes will be accepted.",
    "Effective today, the Invitation for Bids is cancelled.",
    "This is a draft solicitation for industry comment only.",
    "The proposal due date shown above is notional.",
    "Offers are not being solicited at this time.",
    "The County is cancelling this RFP and will not make an award.",
]


@pytest.mark.parametrize("line", UNSAFE_ALL_HELD)
def test_r6b_void_or_draft_solicitation_holds_every_deadline(line):
    rc, rep = strict_json(BASE + OLD + line)
    assert rc == 2
    assert any(n["reason"] == "solicitation_cancelled_or_draft" for n in rep["needs_review"]), rep["needs_review"]
    assert held(rep) and held(rep, "questions_due"), rep["deadlines"]


UNSAFE = [  # (text after BASE, expected review reason or deadline code); the old cutoff must be held
    (OLD + "The bid deadline of November 5, 2026 at 5:00 PM ET is on hold pending a protest.", "negated_or_withdrawn"),
    (OLD + "Revised schedule: TBA.", "deadline_to_be_determined"),
    (OLD + "Final Proposal Due | TBD | TBD", "deadline_to_be_determined"),
    (OLD + "Line 4 of Amendment 0001 is corrected to November 12, 2026.", "change_not_read"),
    (OLD + "Amendment 0001 contained a clerical error in the time; it should read 3:00 PM.", "change_not_read"),
    ("The original RFP said: proposals due November 5, 2026 at 5:00 PM ET.", "quoted_or_former"),
    ("Former closing date: November 5, 2026 at 5:00 PM ET", "quoted_or_former"),
    ("Original Proposal Due | November 5, 2026 | 5:00 PM ET", "quoted_or_former"),
    ("Offers must arrive by 4:00 PM MT / 4:00 PM PT on November 5, 2026.", "other_time:4:00 PM MT"),
    ("Proposals due November 5, 2026 at 5:00 PM CT.\nAll times in this RFP are changed from Central Time to Mountain Time.",
     "zone_statement"),
    ("Time zone for every deadline: Mountain\nProposals due November 5, 2026 at 5:00 PM PT.", "zone_statement"),
    (OLD + "Hard copies are due by 2:00 PM ET on November 6, 2026.", "conflicting_proposal_due"),
    (OLD + "Revised deadline: November 19, 2026 1:30\nQuestions are due October 2, 2026 at 10:00 AM ET.", "change_not_read"),
    (OLD + "The closing date will not be extended beyond November 12, 2026.", "change_not_read"),
    (OLD + "The due date is not extended but is moved to the following week.", "change_not_read"),
]


@pytest.mark.parametrize("text,code", UNSAFE)
def test_r6b_unresolved_wording_holds_the_old_cutoff(text, code):
    rc, rep = strict_json(BASE + text)
    assert rc == 2
    reasons = {n["reason"] for n in rep["needs_review"]}
    codes = {a for d in rep["deadlines"] for a in d["ambiguities"] + d.get("review", [])}
    assert code in reasons or code in codes, (reasons, codes)
    assert held(rep), rep["deadlines"]


FALSE_FAILURES = [  # nothing is unresolved: these must read
    OLD + "The proposal due date is not changed.",
    OLD + "There is no change to the closing date.",
    OLD + "The closing time will not be extended for traffic delays.",
]


@pytest.mark.parametrize("text", FALSE_FAILURES)
def test_r6b_a_directly_negated_change_is_not_a_change(text):
    rc, rep = strict_json(BASE + text)
    assert rc == 0, (rep["warnings"], rep["needs_review"])


@pytest.mark.parametrize("limit", [
    "Volume I may not exceed 20 pages.", "The narrative is capped at 10 pages.", "Responses shall be no longer than 15 pages.",
    "Page Limit | 25 pages", "Maximum length: 12 pages.", "Bid narratives shall be no more than 6 pages.",
    "Responses should not exceed 12 pages.", "The page limitation of 30 pages for Volume I is unchanged.",
])
def test_r6b_page_limit_forms_are_read(limit):
    r = analyze(OLD + limit)
    assert r.page_limits, limit


CONTROLS = [
    OLD + "The site visit is cancelled.",
    OLD + "Bid Item 3 (extended warranty) is cancelled from the schedule.",
    "Proposals: briefing 9:00 AM ET; due November 5, 2026 at 5:00 PM ET.",
    "All times in this solicitation are Eastern Time.\n" + OLD,
    OLD + "Some vendors asked whether the RFP was withdrawn; it was not.",
    OLD + "The State reserves the right to cancel this solicitation at any time.",
    OLD + "If this solicitation is cancelled, all offerors will be notified.",
]


@pytest.mark.parametrize("text", CONTROLS)
def test_r6b_controls_stay_read(text):
    rc, rep = strict_json(BASE + text)
    assert rc == 0, (rep["warnings"], rep.get("needs_review"))


def test_r6b_hold_wording_applies_to_the_deadline_it_names():
    rc, rep = strict_json(BASE + OLD + "The pre-proposal conference on October 20, 2026 at 1:00 PM ET is on hold.")
    conf = [d for d in rep["deadlines"] if d["kind"] == "site_visit"]
    assert conf and "negated_or_withdrawn" in conf[0]["ambiguities"]
    assert all(d["status"] == "actionable" for d in rep["deadlines"] if d["kind"] == "proposal_due")


def test_r6b_a_question_word_alone_does_not_hide_a_cancellation():
    rc, rep = strict_json(BASE + OLD + "In response to questions received, the RFP is cancelled.")
    assert rc == 2 and any(n["reason"] == "solicitation_cancelled_or_draft" for n in rep["needs_review"])
