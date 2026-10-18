"""r7 (owner's choice B, 2026-10-18): READ is allow-list based. Every sentence must be positively recognized, or the run
needs review (reason not_recognized) and every deadline is held. UNSAFE cases here read cleanly on r6 5df6397 and must
need review on r7 with an item on the probe's own lines and the proposal cutoff held. Guards check that the base text
still reads cleanly, that the vocabulary avoids the time, status and change lexicons and that no blanking pattern has a
wildcard."""
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
    assert n["line"] == 4 and n["text"] == "Refer to the attached letter." and n["detail"] == "Refer"


BANNED = """not no never none nor neither nothing without unless if except however but otherwise only same cannot can't
won't don't now still new revised original former previous was were had been before after until later earlier prior
extend extended change changed cancel cancelled postpone postponed void valid active open closed hold more extra another
additional one two three four five six seven eight nine ten first second third above below today tomorrow""".split()


def test_r7_vocabulary_invariant():
    bad = [w for w in core.ALLOWED_WORDS if core.TIME_LEXICON.fullmatch(w) or core.STATUS_LEXICON.fullmatch(w) or w in BANNED]
    assert bad == []
    assert not any(core.TIME_LEXICON.fullmatch(w) is None and core.STATUS_LEXICON.fullmatch(w) is None for w in BANNED)


def test_r7_tokenizer_keeps_contractions_whole():
    assert core._words_ok("Offerors can't") == "can't"
    assert core._words_ok("the offeror's proposal") is None
    assert core._words_ok("submit proposals in May") == "May"


def _strip(src: str) -> str:
    """The pattern source without escapes and character classes, where a wildcard would show."""
    src = re.sub(r"\\.", "", src)
    return re.sub(r"\[[^\]]*\]", "", src)


def test_r7_no_wildcards_in_recognizing_patterns():
    pats = [*core.BLANK_SPANS, core.ADDRESS, *core.PAGE_SPANS, core.DEADLINE_REF, core.LATE_RESTATE, core.ZONE_FORM,
            *core.RULE_SENTENCES, *(rx for k in core._KIND_LABEL for rx in core._deadline_forms(k))]
    for rx in pats:
        src = rx.pattern
        assert "\\S" not in src and "[^" not in src and "\\w*" not in src and "\\w+" not in src, src[:80]
        assert "." not in _strip(src), src[:80]


def test_r7_a_sentence_cut_by_a_list_line_is_not_judged_in_pieces():
    rep = core.analyze(BASE + OLD + "Proposals shall be submitted to the\n(1) contracting officer.")
    cut = [n for n in rep.needs_review if n["reason"] == "not_recognized" and n["detail"].startswith("cut by")]
    assert [n["line"] for n in cut] == [4, 5]
