"""r6, independent review round 1 (kofi, BLOCK): each input below is the reviewer's own synthetic probe or a direct
variant. UNSAFE inputs gave strict exit 0, or kept the old proposal cutoff actionable, on f16da2e; they must now need
review and hold the old cutoff. CONTROLS are the reviewer probes that read cleanly by design (exact standard clause
text, a directly negated change with nothing contrasting it, a correct weekday) and must stay READ."""
import io
import json
import time

import pytest

from bid_deadline_check import analyze
from bid_deadline_check.cli import main
from bid_deadline_check.core import _iana_zones

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


UNSAFE = [
    # 1. a dated amendment of no known kind
    "The deadline is extended to November 12, 2026 at 5:00 PM ET.",
    "New date: November 12, 2026 at 5:00 PM ET.",
    "Amendment 0002 extends it to November 12, 2026 at 5:00 PM ET.",
    "Last day to submit: November 12, 2026 at 5:00 PM ET.",
    # 2. cancellations a hedge word used to hide
    "Effective May 1, 2026, the solicitation is cancelled.",
    "Because funding could not be secured, this solicitation is cancelled.",
    "Solicitation No. W912-26-R-0001 has been cancelled.",
    "The Government has cancelled this solicitation.",
    "The agency withdrew the RFP.",
    "RFP cancelled.",
    "The acquisition has been cancelled.",
    "NOTICE OF CANCELLATION",
    "This RFP is closed.",
    # 3. a negated change that its sentence contrasts or shifts
    "The proposal due date is not extended by one week but by two weeks.",
    "The closing date is not postponed but cancelled.",
    "The proposal due date is not changed; it is one week later.",
    "The proposal due date will not be extended by more than a week.",
    "The proposal due date will not be extended, only shortened.",
    # 5. label, status and schedule forms
    "| Proposal Due | Cancelled |",
    "Proposal due date: withdrawn.",
    "Proposal due date (cancelled).",
    "Proposal due date: T.B.D.",
    "Proposal due date: pending",
    "Proposal due date: N/A",
    "Proposals are no longer accepted.",
    "Proposals: no longer accepted.",
    "Proposals will no longer be accepted.",
    "No proposals will be accepted.",
    "Responses are no longer required.",
    "The Government will not accept proposals on November 5, 2026.",
    "The schedule is extended by two weeks.",
    "The procurement timeline slips two weeks.",
    "The site visit and all subsequent dates are postponed.",
    "The deadline is now Friday.",
    "Submit proposals by Thanksgiving.",
    "The proposal due date is shortened by two days.",
    "Disregard the proposal due date.",
    "Remove the proposal due date.",
    "The closing date is null and void.",
    "The proposal due date is waived.",
    "The proposal due date is\n\nextended by one week.",
    "(Postponed.)",
    "Last day to submit: 12-NOV-2026",
    "Bid opening: 12-NOV-2026 2:00 PM ET",
    # 7. former or quoted dates
    "Proposals were due November 5, 2026 at 5:00 PM ET.",
    "Proposal Due Date | Was: November 5, 2026 5:00 PM ET",
    "Until this amendment, the closing date was November 5, 2026 at 5:00 PM ET.",
    "Amendment 0001 read: proposals due November 5, 2026 at 5:00 PM ET.",
    "The RFP states: proposals due November 5, 2026 at 5:00 PM ET.",
    # 8. a stated interruption triggers the emergency extension
    "Normal Government processes were interrupted on November 5, 2026.",
    "An emergency has occurred.",
    "If no time is specified in the solicitation, the time for receipt is 4:30 p.m., local time, for the designated "
    "Government office on the date that offers or revisions are due. It is extended one week.",
]


@pytest.mark.parametrize("line", UNSAFE)
def test_r6r1_unresolved_wording_holds_the_old_cutoff(line):
    rc, rep = strict_json(BASE + OLD + line)
    assert rc == 2, line
    props = [d for d in rep["deadlines"] if d["kind"] == "proposal_due"]
    assert props and all(d["status"] == "needs_review" for d in props), rep["deadlines"]


@pytest.mark.parametrize("text", [
    "By 3:00 PM ET, proposals are due November 5, 2026 at 5:00 PM ET.",
    "At 3:00 PM ET proposals are due on November 5, 2026 at 5:00 PM ET.",
    "Proposals (3:00 PM ET) are due November 5, 2026 at 5:00 PM ET.",
    "Offers must arrive by 4:00 PM MT, 4:00 PM PT on November 5, 2026.",
    "All deadlines are Central Time.\n" + OLD,
    "Times in this RFP are Central Time.\n" + OLD,
    "Unless otherwise stated, deadlines are in Central Time.\n" + OLD,
    OLD + 'Note: "ET" in this RFP means Central Time.',
    "Proposals due Fri, November 5, 2026 at 5:00 PM ET.",  # November 5, 2026 is a Thursday
])
def test_r6r1_times_zones_and_weekdays_that_cannot_be_acted_on(text):
    rc, rep = strict_json(BASE + text)
    assert rc == 2
    props = [d for d in rep["deadlines"] if d["kind"] == "proposal_due"]
    assert props and all(d["status"] == "needs_review" for d in props), rep["deadlines"]


# Reviewer probes that read cleanly while the negation exemption existed; it was removed, so they need review again
# (false failures, on purpose).
NEGATED = [
    OLD + "The proposal due date is not changed.",
    OLD + "The proposal due date will not be extended again.",
    OLD + "The closing time will NOT be EXTENDED for traffic delays.",
    OLD + "The closing time will not\nbe extended for traffic delays.",
]


@pytest.mark.parametrize("text", NEGATED)
def test_r6r1_a_negated_change_needs_review(text):
    assert strict_json(BASE + text)[0] == 2


CONTROLS = [
    OLD + "If no time is specified in the solicitation, the time for receipt is 4:30  p.m., local time, for the designated "
          "Government office on the date that offers or revisions are due.",
    "Proposals due Friday, November 6, 2026 at 5:00 PM ET.",
    "Proposals due Thu, November 5, 2026 at 5:00 PM ET.",
    "Proposals: briefing at 9:00 AM ET, due November 5, 2026 at 5:00 PM ET.",
]


@pytest.mark.parametrize("text", CONTROLS)
def test_r6r1_controls_stay_read(text):
    rc, rep = strict_json(BASE + text)
    assert rc == 0, (rep["warnings"], rep["needs_review"])


def test_r6r1_zone_statements_times_deadlines_stay_linear():
    # 4: one ambiguity per deadline, however many zone statements; at most 50 statements are listed one by one
    deadlines = "".join(f"Proposal {i} due November 5, 2026 at 5:00 PM ET.\n" for i in range(400))
    text = BASE + deadlines + "All times are Central Time.\n" * 2000
    t0 = time.perf_counter()
    r = analyze(text)
    assert time.perf_counter() - t0 < 10
    assert all(sum(a.startswith("zone_conflict") for a in d.ambiguities) <= 1 for d in r.deadlines)
    assert sum(1 for n in r.needs_review if n["reason"] == "zone_statement") <= 51


@pytest.mark.skipif(not _iana_zones(), reason="no zone database on this system (Windows without tzdata): zone_unverified instead")
def test_r6r1_an_unknown_iana_name_is_invalid_where_a_zone_database_exists():
    rc, rep = strict_json(BASE + "Proposals due November 5, 2026 at 17:00 America/Not_A_Zone.")
    (d,) = [d for d in rep["deadlines"] if d["kind"] == "proposal_due"]
    assert "zone_invalid" in d["ambiguities"] and rc == 2
