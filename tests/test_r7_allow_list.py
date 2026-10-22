"""r7 (owner's choice B, 2026-10-18): READ is allow-list based. Every sentence must be positively recognized, or the run
needs review (reason not_recognized) and every deadline is held. UNSAFE cases here read cleanly on r6 5df6397 and must
need review on r7 with an item on the probe's own lines and the proposal cutoff held. Guards check that the base text
still reads cleanly, that each plain-sentence template reads and an altered one does not, and that no recognizing
pattern has a wildcard."""
import io
import json
import re

import pytest

import bid_deadline_check.core as core
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


def held_on_probe(text, base=BASE):
    """Strict exit 2, every deadline held (an unrecognized sentence holds them all) and a review item on the probe's own
    lines (after BASE and OLD)."""
    rc, rep = strict_json(base + text)
    first = base.count("\n") + (1 if text.startswith(OLD) else 0) + 1
    last = (base + text).rstrip("\n").count("\n") + 1
    on_probe = any(n["line"] <= last and n["end_line"] >= first for n in rep["needs_review"])
    return rc == 2 and bool(rep["deadlines"]) and all(d["status"] == "needs_review" for d in rep["deadlines"]) and on_probe


# Guards: the base texts read cleanly, so a probe can only be caught by its own line.
@pytest.mark.parametrize("text", [BASE + OLD, OLD + BASE, BASE.replace("\n", " ") + OLD])
def test_r7_base_texts_read_cleanly(text):
    rc, rep = strict_json(text)
    assert rc == 0 and rep["outcome"] == "read" and rep["needs_review"] == [], rep["needs_review"]


@pytest.mark.parametrize("text", [BASE, OLD])
def test_r7_base_lines_have_no_allow_list_item(text):
    assert not [n for n in core.analyze(text).needs_review if n["reason"] == "not_recognized"]


UNSAFE = [
    # found by the reviewer's rerun on r6's final commit and recorded in r6's LIMITATIONS, not in r6's test file
    OLD + "Offers will not be accepted before the issuance of Amendment 0004.",
    # the plan review's wordings with no word from the dropped relevance list (r7 checks every sentence)
    OLD + "The 5 above should read 12.",
    OLD + "The fifth becomes the twelfth.",
    OLD + "Refer to the attached letter.",
    OLD + "Las propuestas vencen el 12 de noviembre de 2026.",
    # word order and kind: a questions deadline named as the proposal deadline; a lot-specific reference
    "Questions due October 1, 2026 at 10:00 AM ET is the proposal due date.",
    OLD + "Lot 1 proposals are due by the closing date of the amendment.",
    # spans must not hide a change
    OLD + "Page limit - disregard the proposal due date above, it is void: 20 pages.",
    OLD + "Questions due October 1, 2026 at 10:00 AM ET; proposals received after 10:00 AM ET will be rejected.",
    "Proposals due November 5, 2026 at 5:00 PM ET, or 12NOV26 for Lot 2.",
    OLD + "Proposals shall be submitted to https://example.gov/new-deadline.",
    OLD + "Proposals shall be submitted to proposals-extended@example.gov.",
    # contractions, months written as words, a second value in a deadline sentence
    OLD + "Offerors can't submit proposals.",
    OLD + "Proposals won't be accepted.",
    OLD + "Proposals shall be submitted in May.",
    "Proposals due November 5, 2026 at 5:00 PM ET or November 12, 2026 at 5:00 PM ET.",
    "Proposals due November 5, 2026 at 5:00 PM ET and 6:00 PM CT.",
    "Proposals due November 5, 2026 at 5:00 PM ET for Lot 1.",
    # plain wording with no procurement words
    OLD + "Offerors get more time.",
    OLD + "The old date is off.",
    OLD + "This notice is no longer live.",
    OLD + "The window stays open longer.",
    OLD + "Everything above is void.",
    OLD + "See the attached schedule.",
    OLD + "Proposals are welcome for another fortnight.",
]


def _u(*codes):
    return "".join(map(chr, codes))


# The code review of 545a70a (kofi, BLOCK): each read READ there.
UNSAFE_CR1 = [
    # allowed words alone, or two kinds in one plain sentence
    OLD + "Proposals shall be submitted with the questions.",
    OLD + "The RFP will be posted on SAM.",
    OLD + "This solicitation is an RFI.",
    OLD + "The contract is signed.",
    OLD + "The evaluation of proposals is complete.",
    OLD + "Questions shall be submitted by the proposal due date.",
    # text that is not ASCII: full-width letters, another script, look-alike letters, an invisible character
    OLD + "This solicitation is " + _u(0xFF23, 0xFF21, 0xFF2E, 0xFF23, 0xFF25, 0xFF2C, 0xFF2C, 0xFF25, 0xFF24) + ".",
    OLD + _u(0x0421, 0x0440, 0x043E, 0x043A, 0x20, 0x043F, 0x043E, 0x0434, 0x0430, 0x0447, 0x0438, 0x20, 0x043F, 0x0440, 0x0435,
             0x0434, 0x043B, 0x043E, 0x0436, 0x0435, 0x043D, 0x0438, 0x0439, 0x20, 0x043F, 0x0440, 0x043E, 0x0434, 0x043B,
             0x0435, 0x043D) + ".",
    OLD + "Proposals are " + _u(0x0475, 0x043E, 0x0456, 0x0501) + ".",
    OLD + "Proposals shall be submitted with" + _u(0x2063) + "in the questions.",
    # words hidden in a solicitation number
    OLD + "This RFP is ON-HOLD-0004.",
    OLD + "This RFP is VOID-0004.",
    OLD + "Solicitation No. RESOLICITED-AS-W912-0005.",
    # a sentence split from the one it changes
    "Proposals due November 5, 2026 at 5:00 PM ET; or with the questions.",
    "Proposals due November 5, 2026 at 5:00 PM ET.\nOr with the questions.",
    OLD + "NO PROPOSALS WILL BE ACCEPTED BY FAX\nor at the portal.",
    # the month May, and a 12-hour time without AM or PM (the reviewer's note on r6 extraction)
    OLD + "Proposals shall be submitted in may.",
    OLD + "1. May is for proposals.",
    "Proposals due November 5, 2026 at 5:00 ET.",
    # found by the builder before the second review: a word taken for a list marker, a date inside an address
    OLD + "(no) Proposals shall be submitted electronically.",
    OLD + "Proposals shall be submitted at https://example.gov/20261112.",
]


@pytest.mark.parametrize("text", UNSAFE_CR1)
def test_r7_code_review_inputs_hold_the_cutoff_on_their_own_line(text):
    assert held_on_probe(text)


@pytest.mark.parametrize("text", UNSAFE)
def test_r7_unrecognized_wording_holds_the_cutoff_on_its_own_line(text):
    assert held_on_probe(text)


SUPPORTED = [  # clean forms the allow-list recognizes; each must stay READ
    "Proposal due date: November 5, 2026 at 5:00 PM ET.",
    "Proposals are due no later than 5:00 PM ET on November 5, 2026.",
    "Proposals must be received by November 5, 2026 at 5:00 PM ET.",
    "Offerors shall submit proposals by November 5, 2026 at 5:00 PM ET.",
    "| Proposals due | November 5, 2026 | 5:00 PM ET |",
    "PROPOSAL DUE DATE\nNovember 5, 2026 at 5:00 PM ET",
    "Proposals due November 5, 2026 at 5:00 PM ET (Eastern Time).",
    "Proposals due 2026-11-05T17:00:00-04:00.",
    "Proposals due November 5, 2026 at 5:00 PM ET.\nLate proposals will not be accepted.",
    "Proposals due November 5, 2026 at 5:00 PM ET; proposals received after 5:00 PM ET will be rejected.",
    "All times in this solicitation are Eastern Time.\nProposals due November 5, 2026 at 5:00 PM ET.",
    "Proposals due November 5, 2026 at 5:00 PM ET.\nProposals shall be submitted electronically to the contracting officer at co@example.gov.",
    "Proposals due November 5, 2026 at 5:00 PM ET.\nAll proposals must be received by the deadline.",
    "Proposals due November 5, 2026 at 5:00 PM ET.\nThe price proposal shall be submitted in Volume II.",
]


@pytest.mark.parametrize("text", SUPPORTED)
def test_r7_supported_forms_read(text):
    rc, rep = strict_json(BASE + text)
    assert rc == 0, rep["needs_review"]


def test_r7_one_code_per_deadline_after_the_r6_reasons():
    rep = core.analyze(BASE + OLD + "The proposal due date is postponed.\nRefer to the attached letter.\nSee the attached schedule.")
    (d,) = [d for d in rep.deadlines if d.kind == "proposal_due"]
    nr = [x for x in d.review if x.startswith("not_recognized:")]
    assert nr == ["not_recognized:3"] and d.review[-1] == "not_recognized:3"
    assert any(x.endswith(":change_not_read") for x in d.review[:-1])


def test_r7_r6_reasons_are_listed_before_allow_list_items():
    text = OLD + "Refer to the attached letter.\n" * 60 + "The proposal due date is postponed.\n"
    rep = core.analyze(BASE + text)
    assert rep.needs_review[0]["reason"] == "change_not_read"
    assert any(w.endswith("more sentences not in a recognized form are not listed.") for w in rep.warnings)


def test_r7_each_allow_list_item_names_what_is_not_recognized():
    rep = core.analyze(BASE + OLD + "Refer to the attached letter.")
    (n,) = [n for n in rep.needs_review if n["reason"] == "not_recognized"]
    assert n["line"] == 4 and n["text"] == "Refer to the attached letter."
    assert n["detail"] == "not a supported sentence form: Refer to the attached letter."


# The open vocabulary of 545a70a and bf0ad4a is gone (option 1 after the Two-Round Stop): plain sentences must match a
# closed template whole. These are code review round 2's inputs (kofi, BLOCK on bf0ad4a); each read READ there.
UNSAFE_CR2 = [
    "Proposals due November 5, 2026 at 5:00 PM ET. (or at the presentation.)",
    OLD + "NO PROPOSALS WILL BE ACCEPTED BY FAX\n(or at the portal.)",
    "Proposals due November 5, 2026 at 5:00 PM ET.\n- or at the presentation.",
    "Proposals due November 5, 2026 at 5:00 PM ET.\n" + _u(0x201C) + "Or at the presentation.",
    "Proposals due November 5, 2026 at 5:00 PM ET.\n" + _u(0x2014) + "or at the presentation.",
    "Proposals due November 5, 2026 at 5:00 PM ET.\n" + _u(0x2026) + "or at the presentation.",
    "Proposals due November 5, 2026 at 5:00 PM ET.\n" + _u(0x2022) + " or at the presentation.",
    OLD + "Proposals shall be submitted at the presentation.",
    OLD + "Questions shall be submitted at the presentation.",
    OLD + "Proposals shall be submitted at the pre bid.",
    OLD + "Proposals shall be submitted as presentations.",
    OLD + "All offerors have submitted proposals.",
    OLD + "This document is for information.",
    OLD + "Proposals shall be submitted in May, use the portal.",
    OLD + "Proposals shall be submitted at https://sam.gov/opp/duedatemovedtodecember.",
    OLD + "Proposals shall be submitted to rfpcancelled.gov.",
    OLD + "Proposals shall be submitted at https://sam.gov/opp/11.15.26.",
    OLD + "Proposals shall be submitted at https://sam.gov/opp/amdt004.",
    OLD + "The government can for" + _u(0) + "bid proposals.",
]


@pytest.mark.parametrize("text", UNSAFE_CR2)
def test_r7_code_review_round2_inputs_hold_the_cutoff_on_their_own_line(text):
    assert held_on_probe(text)


# The plan review of the templates (kofi, SAME PAGE WITH CHANGES): an address may be only an email address or a bare host
# name, with no digit, path, query or time, status or event stem inside it.
BAD_ADDRESSES = ["https://agency.gov/afterorals", "atthepresentation@agency.gov", "extraweek.agency.gov", "latebids@agency.gov",
                 "https://agency.gov/pushedtofriday", "notaccepted@agency.gov", "nextweek.gov", "onlyaftersitevisit@agency.gov",
                 "https://agency.gov/11-15", "https://agency.gov/11.15", "co1115@agency.gov", "https://agency.gov/?d=x",
                 "www.agency.gov/amendment"]


@pytest.mark.parametrize("addr", BAD_ADDRESSES)
def test_r7_an_address_cannot_carry_a_change_in_a_plain_sentence(addr):
    assert held_on_probe(OLD + f"Proposals shall be submitted electronically to {addr}.")


@pytest.mark.parametrize("addr", BAD_ADDRESSES)
def test_r7_an_address_cannot_carry_a_change_in_a_deadline_sentence(addr):
    assert held_on_probe(f"Proposals shall be submitted to {addr} by November 5, 2026 at 5:00 PM ET.")


@pytest.mark.parametrize("heading", ["Price", "Past Performance"])
def test_r7_a_bare_due_date_label_is_not_a_proposal_deadline(heading):
    assert held_on_probe(f"{heading}\n\nDue date: November 15, 2026 at 5:00 PM ET.")


@pytest.mark.parametrize("code", [0x0B, 0x0C, 0x1C, 0x1D, 0x1E, 0x85, 0x2028, 0x2029])
def test_r7_a_line_separator_other_than_a_newline_is_reviewed(code):
    assert held_on_probe(OLD + "The government can for" + chr(code) + "bid proposals.")


def test_r7_only_or_follows_a_standard_clause():
    far = ("If it was transmitted through an electronic commerce method authorized by the solicitation, it was received at the "
           "initial point of entry to the Government infrastructure not later than 5:00 p.m. one working day prior to the date "
           "specified for receipt of offers; ")
    assert strict_json(BASE + OLD + far + "or")[0] == 0
    assert held_on_probe(OLD + far + "and")


@pytest.mark.parametrize("text", [  # each template, filled; each must read cleanly after the base text
    "Volume I Technical shall not exceed twenty (20) pages.",
    "Volume II Past Performance is limited to 10 pages.",
    "The technical narrative page limit: 30 pages",
    "Proposals must be submitted in PDF format by email.",
    "Offers shall be submitted through piee.eb.mil.",
    "Proposals must be submitted electronically to the contracting officer at co@example.gov.",
    "Submit quotes by email to co@example.gov.",
    "Questions must be submitted in writing to the contracting officer at co@example.gov.",
    "Questions shall be directed to the contracting officer.",
    "The offeror shall direct all questions to the point of contact.",
    "Pages shall be 8.5 x 11 inches with 1-inch margins.",
    "Text shall use 12-point Times New Roman font, single-spaced.",
    "The offeror shall include its UEI and CAGE code on the cover page.",
    "The proposal shall consist of the following volumes:",  # with a list after it, r6 flags the open requirement
    "Section L - Instructions to Offerors",
])
def test_r7_each_plain_template_reads(text):
    rc, rep = strict_json(BASE + OLD + text)
    assert rc == 0, rep["needs_review"]


@pytest.mark.parametrize("text", [  # a template with one word changed or added is not recognized
    "Volume I Technical shall not exceed twenty (20) pages, or thirty for Lot 2.",
    "Proposals must be submitted in PDF format by email only.",
    "Questions must be submitted in writing to the program office.",
    "The proposal shall consist of the following volumes: Volume I only.",
    "Section L - Instructions to Offerors (superseded)",
    "Technical proposal must not exceed later pages.",
])
def test_r7_an_altered_template_needs_review(text):
    assert held_on_probe(OLD + text)


# Code review round 3 (kofi, BLOCK on 32b64e8): each read READ there. Generic labels and scoping headings let another
# event's deadline, or one volume's, read as the proposal deadline; a heading split off by ";" scoped the deadline;
# omission marks and literal template slots read cleanly; characters were checked only after r6 normalized them.
UNSAFE_CR3 = [
    "Questions shall be directed to the contracting officer.\nResponses will be delivered via email by October 8, 2026 at 5:00 PM ET.",
    "Questions shall be submitted by email to the contracting officer.\nSubmissions due October 1, 2026 at 10:00 AM ET.",
    "Past Performance\n\nResponses due November 1, 2026 at 5:00 PM ET.",
    "PAST PERFORMANCE\nResponses due November 1, 2026 at 5:00 PM ET.",
    "Price\n\nClosing date: November 15, 2026 at 5:00 PM ET.",
    "Volume II - Price\n\nProposals due November 15, 2026 at 5:00 PM ET.",
    "Proposals due November 5, 2026 at 5:00 PM ET; Volume II - Price.",
    OLD + "[...]",
    OLD + "[" + _u(0x2026) + "]",
    OLD + "* * *",
    "Proposals must be received to <A> by November 5, 2026 at 5:00 PM ET.",
    OLD + "Proposals shall be submitted" + _u(0x1F) + "electronically.",
    OLD + "Proposals shall be submitted" + _u(0xA0) + "electronically.",
    OLD + "Proposals shall be submitted" + _u(0x1680) + "electronically.",
    OLD + "Proposals shall be submitted" + _u(0x3000) + "electronically.",
    OLD + "Proposals shall be submitted" + _u(0x200B) + " electronically.",
    # the builder's additions in the same classes
    "Technical Approach\n\nProposals due November 15, 2026 at 5:00 PM ET.",
    "Volume I\n\nProposals due November 15, 2026 at 5:00 PM ET.",
    "Section L; Proposals due November 5, 2026 at 5:00 PM ET.",
    "Applications due November 5, 2026 at 5:00 PM ET.",
    "Proposals will be delivered by November 5, 2026 at 5:00 PM ET.",
    "Proposals due November 5, 2026 at 5:00 PM ET.\nResponses shall be submitted by email to co@example.gov.",
    "Proposals due November 5, 2026 at 5:00 PM ET.\n( )",
]


@pytest.mark.parametrize("text", UNSAFE_CR3)
def test_r7_code_review_round3_inputs_hold_every_deadline_on_their_own_line(text):
    # NOT RUN when written (source-only preparation of round 4): expected to pass on the round-4 source, fail on 32b64e8.
    assert held_on_probe(text)


SUPPORTED_CR3 = [  # benign controls next to the round-3 changes; each must stay READ after the base text
    "Offers due November 5, 2026 at 5:00 PM ET.",
    "Proposal closing date: November 5, 2026 at 5:00 PM ET.",
    "Quotes must be received by November 5, 2026 at 5:00 PM ET.",
    "This RFQ closes November 5, 2026 at 5:00 PM ET.",
    "Section L - Instructions to Offerors\n\nProposals due November 5, 2026 at 5:00 PM ET.",
    "Proposals due November 5, 2026 at 5:00 PM ET.\n\n---",
    "Proposals due November 5, 2026 at 5:00 PM ET.\nProposals shall be submitted electronically to the contracting officer.",
    "Proposals due November 5, 2026 at 5:00 PM ET.\nVolume I Technical shall not exceed twenty (20) pages.",
]


@pytest.mark.parametrize("text", SUPPORTED_CR3)
def test_r7_round3_controls_still_read(text):
    # NOT RUN when written: expected rc 0 on the round-4 source.
    rc, rep = strict_json(BASE + text)
    assert rc == 0, rep["needs_review"]


def _strip(src: str) -> str:
    """The pattern source without escapes and character classes, where a wildcard would show."""
    src = re.sub(r"\\.", "", src)
    return re.sub(r"\[[^\]]*\]", "", src)


def test_r7_no_wildcards_in_recognizing_patterns():
    pats = [core.ADDRESS, core.ADDRESS_STEMS, *core.PLAIN_FORMS, *core.LIST_FORMS, core.LATE_RESTATE, core.ZONE_FORM,
            core.OMISSION, core.PLACEHOLDER, core.RULE_LINE,
            *core.RULE_SENTENCES, *(rx for k in core._KIND_LABEL for rx in core._deadline_forms(k))]
    for rx in pats:
        src = rx.pattern
        assert "\\S" not in src and "[^" not in src and "\\w*" not in src and "\\w+" not in src, src[:80]
        assert "." not in _strip(src), src[:80]


def test_r7_a_sentence_cut_by_a_list_line_is_not_judged_in_pieces():
    rep = core.analyze(BASE + OLD + "Proposals shall be submitted to the\n(1) contracting officer.")
    cut = [n for n in rep.needs_review if n["reason"] == "not_recognized" and n["detail"].startswith("cut by")]
    assert [n["line"] for n in cut] == [4, 5]
