"""r6, independent review round 2 (kofi, BLOCK on 21e9ca1): FIXED are the reviewer's numbered findings, which must now
need review and hold the old cutoff; CONTROLS read cleanly and must stay READ (some were false holds in 21e9ca1).
KNOWN_MISSES are further reviewer probes that still read cleanly. They are recorded here, with their exact text, as
strict expected failures: they are unresolved, not waived, and this file fails if one of them starts to be caught, so
the README's list of known misses has to be updated with it. Two corrective rounds have run; the remaining misses are
the reason strict mode is not a deadline or amendment safety gate (see README, "What --strict means")."""
import io
import json

import pytest

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


def held(text):
    rc, rep = strict_json(BASE + text)
    props = [d for d in rep["deadlines"] if d["kind"] == "proposal_due"]
    return rc == 2 and bool(props) and all(d["status"] == "needs_review" for d in props)


FAR_EMERGENCY = ("If an emergency or unanticipated event interrupts normal Government processes so that offers cannot be received "
                 "at the Government office designated for receipt of offers by the exact time specified in the solicitation, and "
                 "urgent Government requirements preclude amendment of the solicitation or other notice of an extension of the "
                 "closing date, the time specified for receipt of offers will be deemed to be extended to the same time of day "
                 "specified in the solicitation on the first work day on which normal Government processes resume.")

FIXED = [
    OLD + "The proposal due date is not extended, and offerors are given three additional days.",
    OLD + "The closing date is not changed. Offerors are granted an additional 48 hours to submit proposals.",
    "The proposal due date is no longer November 5, 2026 at 5:00 PM ET.",
    "The proposal due date is not November 5, 2026 at 5:00 PM ET, as previously stated.",
    OLD + "Amendment 0003 cancels Solicitation No. 123 in its entirety.",
    OLD + "The agency cancels RFP 2026-01.",
    OLD + "Cancellation of Solicitation W912DY-26-R-0001.",
    OLD + "No proposals will be accepted in response to this notice.",
    OLD + "Offers will not be accepted at this time.",
    OLD + "Proposals will no longer be accepted from any offeror.",
    OLD + "References to ET in this solicitation mean Central Time.",
    OLD + "ET, as used herein, means Central Time.",
    OLD + "All times listed are Central Time (for example, 10:00 AM CT).",
    OLD + "Offerors now have until November 12, 2026 at 5:00 PM ET.",
    "Proposals in response to this call are due at 3:00 PM ET, November 5, 2026 (5:00 PM ET portal).",
    # caught by e62299f and lost to f16da2e's negation exemption, which 31fb7b5 removes
    OLD + "The proposal due date will not be extended. Offerors have an additional week.",
    # caught by 21e9ca1 and lost to narrowings in 1ecec0c, which the next commit undoes (review of the final delta)
    OLD + FAR_EMERGENCY + " Normal Government processes resume on Monday.",
    OLD + FAR_EMERGENCY + " Normal Government processes will resume on Monday, November 9, 2026.",
    OLD + FAR_EMERGENCY + " Government processes resumed today.",
    OLD + "Electronic and paper proposals will no longer be accepted.",
    OLD + "Hard-copy and electronic proposals will not be accepted.",
    OLD + "Paper proposals will no longer be accepted.",
    OLD + "Electronic proposals will no longer be accepted.",
    OLD + "All times in this solicitation are local time at the delivery site in Phoenix, Arizona.",
]


@pytest.mark.parametrize("text", FIXED)
def test_r6r2_reviewer_findings_hold_the_old_cutoff(text):
    assert held(text)


CONTROLS = [
    OLD + "Late proposals will not be accepted.",
    OLD + "Oral proposals will not be accepted.",
    OLD + "Faxed proposals will not be accepted.",
    OLD + "No proposals will be accepted by fax.",
    OLD + "If an emergency or unanticipated event interrupts normal Government processes so that offers cannot be received "
          "at the Government office designated for receipt of offers by the exact time specified in the solicitation, and urgent "
          "Government requirements preclude amendment of the solicitation or other notice of an extension of the closing date, "
          "the time specified for receipt of offers will be deemed to be extended to the same time of day specified in the "
          "solicitation on the first work day on which normal Government processes resume.",
    OLD + "If no time is specified in the solicitation, the time for receipt is 4:30\np.m., local time, for the designated "
          "Government office on the date that offers or revisions are due.",
    OLD + "The Government reserves the right to cancel this solicitation.",
    OLD + "The Government may cancel this solicitation at any time.",
    OLD + "All proposals must be received by the deadline.",
]


@pytest.mark.parametrize("text", CONTROLS)
def test_r6r2_controls_stay_read(text):
    rc, rep = strict_json(BASE + text)
    assert rc == 0, (rep["warnings"], rep["needs_review"])


def test_r6r2_an_award_date_is_its_own_item_and_leaves_the_proposal_deadline_actionable():
    # Reported, as since r1, as a dated item without a time (so NEEDS REVIEW); it changes no submission deadline.
    rc, rep = strict_json(BASE + OLD + "Award is anticipated by December 15, 2026.")
    assert rc == 2 and all(d["status"] == "actionable" for d in rep["deadlines"] if d["kind"] == "proposal_due")


KNOWN_MISSES = [  # unresolved: each reads cleanly although a careful reader would not act on the old cutoff
    "Proposals due November 5, 2026 at 5:00 PM ET will not apply.",
    OLD + "The date above is no longer valid.",
    OLD + "That date has passed and a new one is coming.",
    OLD + "Offerors have one additional week to respond.",
    OLD + "An additional 14 calendar days is provided for proposal preparation.",
    OLD + "Proposal due date: see Amendment 0003.",
    OLD + "Offerors are given until close of business November 12, 2026.",
    OLD + "Amendment 0002 grants a two-week extension.",
    OLD + "The entire schedule slides one week.",
    OLD + "The proposal due date is ex-\ntended one week.",
    OLD + "The proposal due date is post-\nponed.",
    OLD + "The solicitation is can-\ncelled.",
    OLD + "The Government no longer has a requirement for these services.",
    OLD + "This requirement will not be awarded.",
    OLD + "No further proposals will be accepted.",
    OLD + "This notice serves to cancel the subject solicitation.",
    OLD + "This RFP is no longer active.",
    OLD + "The Government is cancelling the requirement.",
    OLD + "Proposal due date: to be advised.",
    OLD + "Proposal due date: will be posted in a future amendment.",
    OLD + "Proposal due date: [date]",
    OLD + "The proposal due date is under review.",
    OLD + "Proposals should not be submitted at this time.",
    OLD + "Ignore the November 5, 2026 date.",
    OLD + "The November 5 date was an error.",
    OLD + "The above proposal due date is incorrect.",
    OLD + "Proposals will not be considered until further notice.",
    OLD + "Eastern Time is not used in this RFP; Central Time governs.",
    OLD + "| Time Zone | Central |",
    OLD + "Time Zone: Central",
    OLD + "Unless otherwise noted, Central Time applies.",
    OLD + "Central Time governs all deadlines.",
    # found by the review of the final delta (not regressions; recorded, not fixed, after two corrective rounds)
    OLD + "Proposals will not be accepted by any means.",
    OLD + "Proposals will no longer be accepted by the Government.",
    OLD + "No proposals will be accepted by this office.",
    OLD + "Proposals will not be accepted before further notice.",
    OLD + "Proposals will not be accepted through the end of the fiscal year.",
    OLD + "No offers will be received via any method.",
    OLD + "The proposal due date is no longer 5:00 PM ET on November 5, 2026.",
    OLD + "The Government does not intend to award a contract under this notice.",
]


def held_on_probe(text):
    """As held(), and a review item lies on the probe's own lines (after BASE, and after OLD when the text starts with it),
    so an unrecognized line elsewhere cannot make the test pass (r7 plan review, finding 4)."""
    rc, rep = strict_json(BASE + text)
    first = BASE.count("\n") + (1 if text.startswith(OLD) else 0) + 1
    last = (BASE + text).rstrip("\n").count("\n") + 1
    return held(text) and any(n["line"] <= last and n["end_line"] >= first for n in rep["needs_review"])


@pytest.mark.parametrize("text", KNOWN_MISSES)
def test_r6r2_known_misses_are_caught_by_the_r7_allow_list(text):
    # r6 recorded these as strict expected failures (they read cleanly on 5df6397); r7's allow-list must catch each one.
    assert held_on_probe(text)
