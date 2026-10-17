"""Regressions for kofi's review of r3 (2026-10-17). Synthetic text only. The inputs are the reviewer's own cases: a
revision or malformed date that must not leave a clean --strict result, ordinary solicitation text that must still
read cleanly, and wordings that are now read rather than only flagged."""
import time

import pytest

from bid_deadline_check import analyze
from bid_deadline_check.cli import main

BASE = "Questions due October 1, 2026 at 10:00 AM ET.\nTechnical proposal must not exceed 20 pages.\n"
COMPLETE = "Proposals due November 5, 2026 at 5:00 PM ET.\n"
O = BASE + COMPLETE
OLD, NEW = "November 5, 2026 at 5:00 PM ET", "November 12, 2026 at 5:00 PM ET"


def strict(tmp_path, text):
    f = tmp_path / "rfp.txt"
    f.write_text(text)
    return main([str(f), "--strict", "-f", "json"])


MUST_FAIL = {
    "A1_extended_by_one_week": O + "The proposal due date is extended by one week.",
    "A2_extended_by_7_days": O + "The proposal due date is extended by seven (7) calendar days.",
    "A3_postponed_indefinitely": O + "The proposal due date is postponed until further notice.",
    "A4_new_date_comma_no_space": O + "The proposal due date is changed to November 12,2026.",
    "A5_new_date_dod_dashes": O + "The proposal due date is changed to 12-NOV-2026.",
    "A6_new_date_us_dashes": O + "The proposal due date is changed to 11-12-2026.",
    "A7_new_date_ocr_day": O + "The proposal due date is extended to November l2, 2026.",
    "A8_new_date_ordinal_glued_year": O + "The proposal due date is extended to November 12th2026.",
    "B1_now_next_sentence": O + "Amendment 0003 changes the proposal due date. It is now November 12, 2026 at 5:00 PM ET.",
    "B2_new_date_next_sentence": O + "The proposal due date is extended. The new date is November 12, 2026 at 5:00 PM ET.",
    "B3_new_date_label_next_line": O + "The proposal due date is extended.\nNew date: November 12, 2026 at 5:00 PM ET.",
    "C1_deadline_extended_until": O + "The deadline has been extended until November 12, 2026 at 5:00 PM ET.",
    "C2_revised_deadline_is": O + "The revised deadline is November 12, 2026 at 5:00 PM ET.",
    "C3_new_deadline_is": O + "The new deadline is November 12, 2026 at 5:00 PM ET.",
    "D1_time_change_dated_amendment": O + "Amendment 0004, dated October 20, 2026, changes the closing time to 3:00 PM ET.",
    "D2_time_change_effective": O + "Effective October 20, 2026, the closing time is revised to 3:00 PM ET.",
    "D3_time_change_as_of": O + "As of October 20, 2026, proposals are now due at 3:00 PM ET.",
    "D4_time_change_ocr_day": BASE + "Proposals due November 5, 2026 at 5:00 PM ET are now due November l2, 2026 at 5:00 PM ET.",
    "E1_time_change_military_no_hours": O + "The closing time is changed to 1500 ET.",
    "F1_notice_sent": BASE + "The notice about the proposal due date was sent October 2, 2026 at 5:00 PM ET.",
    "F2_notice_distributed": BASE + "The proposal due date notice was distributed October 2, 2026 at 5:00 PM ET.",
    "F3_extension_announced": BASE + "The proposal deadline extension was announced October 2, 2026 at 5:00 PM ET.",
    "F4_amendment_went_out": BASE + "Amendment 0004 to the proposal due date went out on October 2, 2026 at 5:00 PM ET.",
    "G1_fraction_non_iso_distinct": BASE + "Proposals due November 5, 2026 at 17:00:01.1 ET.\nProposals due November 5, 2026 at 17:00:01.2 ET.",
    "G2_iso_comma_fraction": BASE + "Proposals due 2026-11-05T17:00:01,1Z.\nProposals due 2026-11-05T17:00:01,2Z.",
    "H1_glued_underscore": BASE + "Proposals due by 5:00 PM ET on November 5, 2026_draft.",
    "H2_iso_letter_year": O + "Site visit on 2O26-11-03 at 10:00 AM ET.",
    "H3_slash_letter_day": O + "Site visit on 11/O3/2026 at 10:00 AM ET.",
    "H4_dod_two_digit_year": O + "Site visit on 03 NOV 26 at 10:00 AM ET.",
    "Q1_now_kind_across_sentences": BASE.replace("\n", " ", 1) + COMPLETE + "Questions due October 1, 2026 at 10:00 AM ET. The deadline is now November 12, 2026 at 5:00 PM ET.",
    # batch 2: date revisions, both with and without the original deadline stated elsewhere
    **{f"{n}{suffix}": prefix + t for suffix, prefix in (("", O), ("_alone", BASE)) for n, t in {
        "R1_sf30_from_to_colons": f"Proposal due date FROM: {OLD} TO: {NEW}.",
        "R2_delete_insert": f'Delete "{OLD}" and insert "{NEW}" as the proposal due date.',
        "R3_deleted_replaced_by": f"The proposal due date of {OLD} is deleted and replaced by {NEW}.",
        "R4_in_place_of": f"Proposals are due {NEW} in place of {OLD}.",
        "R5_vice": f"Proposals due {NEW} vice {OLD}.",
        "R6_not_old": f"Proposals due {NEW}, not {OLD}.",
        "R7_rather_than": f"The proposal due date is {NEW} rather than {OLD}.",
        "R8_was_paren": f"Proposals due {NEW} (was {OLD}).",
        "R9_formerly_paren": f"Proposals due {NEW} (formerly {OLD}).",
        "R10_from_until": f"The proposal due date is extended from {OLD} until {NEW}.",
        "R11_pushed_back_from_to": f"The proposal due date has been pushed back from {OLD} to {NEW}.",
        "R12_old_new_labels": f"Proposal due date - Old: {OLD}; New: {NEW}.",
        "R13_originally_due": f"Proposals originally due {OLD} are due {NEW}.",
        "R14_slipped_to": f"The proposal due date of {OLD} has slipped to {NEW}.",
        "R15_substitute": f"Substitute {NEW} for {OLD} as the proposal due date.",
        "R16_shifted_from_to": f"The proposal due date shifts from {OLD} to {NEW}.",
        "R17_now_reads": f"The proposal due date, {OLD}, now reads {NEW}.",
        "R18_previous_due_date": f"The previous proposal due date of {OLD} no longer applies; the due date is {NEW}.",
        "S4_from_to_lowercase": f"Proposal due date from {OLD} to {NEW}.",
        "S5_closing_date_from_to": f"Closing date: from {OLD} to {NEW}.",
    }.items()},
    # batch 2: time-only changes
    "T1_vice_time": O + "The closing time shall be 3:00 PM ET vice 5:00 PM ET.",
    "T2_in_place_of_time": O + "Read 3:00 PM ET in place of 5:00 PM ET for the closing time.",
    "T3_not_time": O + "Proposals are due at 3:00 PM ET, not 5:00 PM ET.",
    "T4_original_date_new_time": O + "Proposals are due at 3:00 PM ET on the original due date.",
    "T5_same_date_earlier_time": O + "Proposals remain due on the same date but at 3:00 PM ET.",
    "T6_delete_insert_time": O + 'Delete "5:00 PM ET" and insert "3:00 PM ET" in Block 9.',
    "T7_hours_change": O + "The closing time is changed from 1700 hours to 1500 hours ET.",
    "T8_time_in_next_sentence": O + "The closing time is revised. Proposals are due at 3:00 PM ET.",
    "T9_shifted_time": O + "The closing time shifts to 3:00 PM ET.",
    "K5_effective_skipped_date": BASE + "Proposals due November 5, 2026 at 5:00 PM ET; this date is changed, effective November 12, 2026.",
}

MUST_PASS = {
    "P1_as_previously_announced": BASE + "As previously announced, proposals are due November 5, 2026 at 5:00 PM ET.",
    "P2_now_accepting": BASE + "The Government is now accepting proposals due by November 5, 2026 at 5:00 PM ET.",
    "P3_registration_now_open": O + "Registration is now open and closes October 20, 2026 at 5:00 PM ET.",
    "P4_far_52_212_1_late": O + "If no time is specified in the solicitation, the time for receipt is 4:30 p.m., local time, for the designated Government office on the date that offers or revisions are due.",
    "P5_far_52_215_1_late": O + "If no time is specified in the solicitation, the time for receipt is 4:30 p.m., local time, for the designated Government office on the date that proposal or revision is due.",
    "P6_extension_request_from": BASE + "Offerors requesting an extension from the Contracting Officer must submit proposals by November 5, 2026 at 5:00 PM ET.",
    "P7_signed_and_dated": BASE + "Proposals are due, signed and dated, by November 5, 2026 at 5:00 PM ET.",
    "P8_new_offerors_register": O + "New offerors must register by 5:00 PM ET.",
    "P9_part_number_month": O + "Provide part number 47QTCA22D00MAR 2026 kits.",
    "P10_plain_previously_registered": BASE + "Offerors previously registered must submit proposals by November 5, 2026 at 5:00 PM ET.",
    "P11_original_and_copies": O + "Submit one original and three copies of each proposal.",
    "P12_period_of_performance": BASE + "Proposals due November 5, 2026 at 5:00 PM ET for performance from January 1, 2027 to December 31, 2027.",
    "P13_issued_then_sets": BASE + "Amendment 0004 issued October 2, 2026 at 5:00 PM ET sets the proposal due date to November 5, 2026 at 5:00 PM ET.",
    "P14_acknowledge_amendments": O + "Offerors shall acknowledge receipt of all amendments to the solicitation.",
    "P15_method_change_other_clause": BASE + "Proposals due November 5, 2026 at 5:00 PM ET; the submission method is changed from paper to electronic.",
    "P16_revised_proposals_due": O + "Final revised proposals are due December 1, 2026 at 5:00 PM ET.",
    "P17_as_amended": BASE + "As amended, proposals are due November 5, 2026 at 5:00 PM ET.",
}


@pytest.mark.parametrize("name", sorted(MUST_FAIL))
def test_a_revision_or_unreadable_date_never_gives_a_clean_strict_result(tmp_path, name):
    assert strict(tmp_path, MUST_FAIL[name]) == 2


@pytest.mark.parametrize("name", sorted(MUST_PASS))
def test_ordinary_text_still_reads_cleanly(tmp_path, name):
    r = analyze(MUST_PASS[name])
    assert r.warnings == [], r.warnings
    assert strict(tmp_path, MUST_PASS[name]) == 0


def proposals(text):
    return [(d.date, d.ambiguities) for d in analyze(text).deadlines if d.kind == "proposal_due"]


@pytest.mark.parametrize("tail", [f"Proposal due date FROM: {OLD} TO: {NEW}.", f"Proposal due date from {OLD} to {NEW}.",
                                  f"Closing date: from {OLD} to {NEW}.", f"The proposal due date is extended from {OLD} until {NEW}."])
def test_a_from_to_revision_without_a_verb_reads_both_dates(tail):
    assert proposals(BASE + tail) == [("November 5, 2026", ["negated_or_withdrawn"]), ("November 12, 2026", ["replaces_earlier_date"])]


def test_extended_until_is_a_replacement():
    r = analyze(O + "The deadline has been extended until November 12, 2026 at 5:00 PM ET.")
    assert any(d.date == "November 12, 2026" and "replaces_earlier_date" in d.ambiguities for d in r.deadlines)


def test_now_takes_the_kind_only_from_its_own_sentence():
    r = analyze(BASE.replace("\n", " ", 1) + COMPLETE + "Questions due October 1, 2026 at 10:00 AM ET. The deadline is now November 12, 2026 at 5:00 PM ET.")
    (d,) = [d for d in r.deadlines if d.date == "November 12, 2026"]
    assert d.kind != "questions_due"


def test_the_revision_warning_names_the_line_and_is_capped():
    from bid_deadline_check import core
    r = analyze(O + "The proposal due date is postponed until further notice.\n" * 80)
    listed = [w for w in r.warnings if w.startswith("Line ") and "appears to change a deadline" in w]
    assert len(listed) == core.MAX_MALFORMED_WARNINGS and listed[0].startswith("Line 4 ")
    assert any(w.startswith("30 more sentences") for w in r.warnings)


def test_now_scan_stays_linear():
    # kofi's generator: a deadline, many short sentences, then many "now <date>" phrases that are not deadlines.
    # The deadline's sentence does not end before the dots, so a rescan back to it is quadratic.
    def text(n):
        return "Proposals due November 5, 2026 at 5:00 PM ET " + "a.b " * n + ". " + "x now November 5, 2026 " * n
    t0 = time.perf_counter(); analyze(text(1000)); small = time.perf_counter() - t0
    t0 = time.perf_counter(); analyze(text(4000)); large = time.perf_counter() - t0
    assert large < 6 * small + 0.2, (small, large)  # four times the input: linear is about 4x, quadratic about 16x
