"""Regressions for the independent review of 2026-10-16 (KB-01..KB-17). Case texts are the reviewer's
synthetic inputs (review/kofi-bid/cases*.json), copied verbatim."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bid_deadline_check import analyze, core

CASES = {
    'doc1_amendment_realistic': 'AMENDMENT 0002 TO SOLICITATION 47QSMA-26-R-0001\nThe purpose of this amendment is to extend the proposal due date.\nQuestions due: October 20, 2026 2:00 PM ET.\nThe proposal due date of November 5, 2026 at 5:00 PM ET is no longer in effect; offerors registered in SAM.gov shall submit proposals by November 19, 2026 at 5:00 PM ET.\nTechnical proposal must not exceed 20 pages.',
    'n10_no_longer_in_effect': 'B+The proposal due date of November 5, 2026 at 5:00 PM ET is no longer in effect; a new date will be provided by amendment.',
    'n11_no_longer_applicable': 'B+The proposal due date of November 5, 2026 at 5:00 PM ET is no longer applicable.',
    'n12_suspended': 'B+The proposal due date of November 5, 2026 at 5:00 PM ET is suspended until further notice.',
    'n13_hereby_removed': 'B+The proposal due date of November 5, 2026 at 5:00 PM ET is hereby removed; offerors will be notified of the new date.',
    'n14_extended_indefinitely': 'B+The proposal due date of November 5, 2026 at 5:00 PM ET is extended indefinitely.',
    'n15_will_not_be_required': 'B+Proposals due November 5, 2026 at 5:00 PM ET will no longer be required; this requirement is being resolicited.',
    'k03_registered_sam': 'B+Offerors registered in SAM.gov shall submit proposals by November 5, 2026 at 5:00 PM ET.',
    'k06_registered_with_cover': 'Offer Due Date: November 5, 2026 5:00 PM ET.\nQuestions due October 1, 2026 at 10:00 AM ET.\nTechnical proposal must not exceed 20 pages.\nOfferors registered in SAM.gov shall submit proposals by November 12, 2026 at 5:00 PM ET.',
    'c02_k05_control_other_date': 'Offer Due Date: November 5, 2026 5:00 PM ET.\nQuestions due October 1, 2026 at 10:00 AM ET.\nTechnical proposal must not exceed 20 pages.\nOfferors who attended industry day must submit proposals by November 12, 2026 at 5:00 PM ET.',
    'k02_industry_day_proposals': 'B+Offerors who attended industry day must submit proposals by November 5, 2026 at 5:00 PM ET.',
    'doc3_section_l_conference': 'Questions due: October 20, 2026 2:00 PM ET.\nOffer Due Date: November 5, 2026 5:00 PM ET.\nTechnical proposal must not exceed 20 pages.\nQuestions raised during the conference call must be submitted in writing by October 27, 2026 at 2:00 PM ET.',
    'doc2_cover_page_caps': 'SOLICITATION 47QSMA-26-R-0001\nQUESTIONS DUE\nOctober 20, 2026 at 2:00 PM ET\nPROPOSAL DUE DATE\nNovember 5, 2026 at 5:00 PM ET\nTechnical proposal must not exceed 20 pages.',
    's06_sentence_above_date': 'Questions due October 1, 2026 at 10:00 AM ET.\nTechnical proposal must not exceed 20 pages.\nProposals are due no later than the date and time below.\nNovember 5, 2026 at 5:00 PM ET',
    's05_heading_above_date': 'Questions due October 1, 2026 at 10:00 AM ET.\nTechnical proposal must not exceed 20 pages.\nPROPOSAL DUE DATE\nNovember 5, 2026 at 5:00 PM ET',
    'b04_sf1449_block8': 'B+8. OFFER DUE DATE/LOCAL TIME\n11/05/2026 1700',
    'b05_caps_date_line': 'B+Proposals due\nNOVEMBER 5, 2026 AT 5:00 PM ET',
    'd10_caps_continuation_deadline': 'B+Proposals must be received no later than\n5:00 PM EST, NOVEMBER 5, 2026',
    'd15_crlf': 'Questions due October 1, 2026 at 10:00 AM ET.\r\nTechnical proposal must not exceed 20 pages.\r\nProposals due\r\nNovember 5, 2026\r\nat 5:00 PM ET.',
    'r10_wrap_paren_a': 'BC+The offeror shall provide\n(a) a technical approach and (b) a staffing plan.',
    'r11_wrap_volume': 'BC+The offeror shall submit the technical approach in\nVolume I and the price in Volume II.',
    's03_caps_form_line': 'BC+The offeror shall complete and return\nSF-1449\nwith the proposal.',
    'a01_rm_bldg': 'B+The offeror shall deliver proposals to Rm. 101, Bldg. 5 by November 5, 2026 at 5:00 PM ET.',
    'a02_ste': 'B+Proposals shall be delivered to 100 Example Ave., Ste. 1402 by November 5, 2026 at 5:00 PM ET.',
    'd02_closes': 'B+This RFQ closes November 5, 2026 at 5:00 PM ET.',
    'e05_bid_opening': 'B+Bid opening: November 5, 2026 at 2:00 PM ET.',
    't01_12_noon': 'B+Proposals due November 5, 2026 at 12 noon ET.',
    't02_1200_noon': 'B+Proposals due November 5, 2026 at 12:00 noon Eastern Time.',
    't03_hrs_tz': 'B+Proposals due November 5, 2026 at 17:00 hrs ET.',
    't04_prevailing': 'B+Proposals due November 5, 2026 at 5:00 PM prevailing Eastern Time.',
    't06_time_then_on_or_before': 'B+Offers must be received at the address below by 2:00 PM local time on or before November 5, 2026.',
    't07_time_then_nlt': 'B+Proposals must be received by 5:00 PM ET no later than November 5, 2026.',
    't10_sharp': 'B+Proposals due November 5, 2026 at 5:00 PM sharp, Eastern Time.',
    'b03_table_due_time_col': 'B+Due Date: November 5, 2026 Due Time: 5:00 PM ET',
    'e01_dash_sep': 'B+Proposal due date: November 5, 2026 - 5:00 PM ET',
    'e03_pipe_sep': 'B+Proposals due | November 5, 2026 | 5:00 PM | ET',
    'e04_slash_sep': 'B+Proposals due November 5, 2026 / 5:00 PM ET.',
    'b01_from_until': 'B+Site visit November 5, 2026 from 9:00 AM until 11:00 AM ET; proposals due November 12, 2026 at 5:00 PM ET.',
    't05_range_tz': 'B+Site visit: November 5, 2026, 9:00 AM - 11:00 AM ET.\nProposals due November 12, 2026 at 5:00 PM ET.',
    'b14_received_after_only': 'Questions due October 1, 2026 at 10:00 AM ET.\nTechnical proposal must not exceed 20 pages.\nOffers received after November 5, 2026 at 5:00 PM ET will not be considered.',
    'b19_caps_5th': 'B+PROPOSALS DUE FEBRUARY 31ST, 2026 AT 5:00 PM ET.',
    'b09_date_fmt_dup': 'Questions due October 1, 2026 at 10:00 AM ET.\nTechnical proposal must not exceed 20 pages.\nOffer due date: 11/05/2026 5:00 PM ET.\nProposals are due November 5, 2026 at 5:00 PM ET.',
    'b10_tz_spelling_dup': 'Questions due October 1, 2026 at 10:00 AM ET.\nTechnical proposal must not exceed 20 pages.\nOffer due date: November 5, 2026 5:00 PM ET.\nProposals are due November 5, 2026 at 5:00 PM Eastern Time.',
    'd01_pop_after_due': 'B+Proposals are due November 5, 2026 at 5:00 PM ET for a period of performance of January 1, 2027 through December 31, 2027.',
    'k10_kind_from_after_questions': 'Offer Due Date: November 5, 2026 5:00 PM ET.\nTechnical proposal must not exceed 20 pages.\nNovember 5, 2026 at 5:00 PM ET is the deadline for proposals, and the questions period has closed.',
    'k04_questionnaire': 'Offer Due Date: November 5, 2026 5:00 PM ET.\nTechnical proposal must not exceed 20 pages.\nThe offeror shall complete the past performance questionnaire in Attachment 3 and submit it by November 5, 2026 at 5:00 PM ET.',
    'k07_answers_by': 'Offer Due Date: November 5, 2026 5:00 PM ET.\nTechnical proposal must not exceed 20 pages.\nAnswers to questions will be provided by October 25, 2026 at 5:00 PM ET.',
    'n01_not_accepted_by_fax': 'B+Offers will not be accepted by fax and are due November 5, 2026 at 5:00 PM ET.',
    'n02_not_due_until': 'B+Proposals are not due until November 5, 2026 at 5:00 PM ET.',
    'e06_unless_cancelled': 'B+Proposals due November 5, 2026 at 5:00 PM ET unless cancelled by amendment.',
    'a03_pm_dot_cancelled': 'B+Proposals remain due November 5, 2026 at 5:00 p.m. The site visit has been cancelled.',
    'b15_iana_space': 'B+Proposals due November 5, 2026 at 17:00 America/New York.',
    'e07_mt_tz_fp': 'B+Proposals due November 5, 2026 at 5:00 PM Mt. Vernon local time.',
    'e10_time_stolen_paren': 'B+Proposals due November 5, 2026 (5:00 PM ET on November 6, 2026 for hand-carried copies).',
    'd16_zero_width_space': 'B+Proposals due November 5, 2026 at 5:00\u200bPM ET.',
}
CHECKS = [
    ('doc1_amendment_realistic', "neg(r, 'November 5, 2026') and live(r, 'proposal_due') == [('November 19, 2026', '5:00 PM', 'ET')] and r.warnings"),
    ('n10_no_longer_in_effect', "neg(r, 'November 5, 2026')"),
    ('n11_no_longer_applicable', "neg(r, 'November 5, 2026')"),
    ('n12_suspended', "neg(r, 'November 5, 2026')"),
    ('n13_hereby_removed', "neg(r, 'November 5, 2026')"),
    ('n14_extended_indefinitely', "neg(r, 'November 5, 2026')"),
    ('n15_will_not_be_required', "neg(r, 'November 5, 2026')"),
    ('k03_registered_sam', "kinds(r) == ['proposal_due']"),
    ('k06_registered_with_cover', "any('2 different proposal due' in w for w in r.warnings)"),
    ('c02_k05_control_other_date', "any('2 different proposal due' in w for w in r.warnings)"),
    ('k02_industry_day_proposals', "kinds(r) == ['proposal_due']"),
    ('doc3_section_l_conference', "kinds(r)[-1] == 'questions_due'"),
    ('doc2_cover_page_caps', "live(r, 'questions_due') == [('October 20, 2026', '2:00 PM', 'ET')] and live(r, 'proposal_due') == [('November 5, 2026', '5:00 PM', 'ET')] and not r.warnings"),
    ('s06_sentence_above_date', "live(r, 'proposal_due') == [('November 5, 2026', '5:00 PM', 'ET')]"),
    ('s05_heading_above_date', "live(r, 'proposal_due') == [('November 5, 2026', '5:00 PM', 'ET')]"),
    ('b04_sf1449_block8', "live(r, 'proposal_due') == [('11/05/2026', None, None)]"),
    ('b05_caps_date_line', "live(r, 'proposal_due') == [('NOVEMBER 5, 2026', '5:00 PM', 'ET')]"),
    ('d10_caps_continuation_deadline', "live(r, 'proposal_due') == [('NOVEMBER 5, 2026', '5:00 PM', 'EST')]"),
    ('d15_crlf', "live(r, 'proposal_due') == [('November 5, 2026', '5:00 PM', 'ET')]"),
    ('r10_wrap_paren_a', "r.requirements and r.requirements[-1]['truncated']"),
    ('r11_wrap_volume', "r.requirements[-1]['truncated']"),
    ('s03_caps_form_line', "r.requirements[-1]['truncated']"),
    ('a01_rm_bldg', "kinds(r) == ['proposal_due']"),
    ('a02_ste', "kinds(r) == ['proposal_due']"),
    ('d02_closes', "kinds(r) == ['proposal_due']"),
    ('e05_bid_opening', "kinds(r) == ['proposal_due']"),
    ('t01_12_noon', "bound(r) == ('12 noon', 'ET')"),
    ('t02_1200_noon', "bound(r) == ('12:00 noon', 'Eastern Time')"),
    ('t03_hrs_tz', "bound(r) == ('17:00', 'ET')"),
    ('t04_prevailing', "bound(r) == ('5:00 PM', 'Eastern Time')"),
    ('t06_time_then_on_or_before', "bound(r) == ('2:00 PM', 'local time')"),
    ('t07_time_then_nlt', "bound(r) == ('5:00 PM', 'ET')"),
    ('t10_sharp', "bound(r) == ('5:00 PM', 'Eastern Time')"),
    ('b03_table_due_time_col', "bound(r) == ('5:00 PM', 'ET')"),
    ('e01_dash_sep', "bound(r) == ('5:00 PM', 'ET')"),
    ('e03_pipe_sep', "bound(r) == ('5:00 PM', 'ET')"),
    ('e04_slash_sep', "bound(r) == ('5:00 PM', 'ET')"),
    ('b01_from_until', "bound(r, 'site_visit') == ('9:00 AM', 'ET')"),
    ('t05_range_tz', "bound(r, 'site_visit') == ('9:00 AM', 'ET')"),
    ('b14_received_after_only', "'after_clause' in [d for d in r.deadlines if d.kind == 'proposal_due'][0].ambiguities"),
    ('b19_caps_5th', "'invalid_date' in r.deadlines[-1].ambiguities"),
    ('b09_date_fmt_dup', "not any('different proposal due' in w for w in r.warnings)"),
    ('b10_tz_spelling_dup', "not any('different proposal due' in w for w in r.warnings)"),
    ('d01_pop_after_due', 'len(r.deadlines) == 1'),
    ('k10_kind_from_after_questions', "kinds(r) == ['proposal_due', 'proposal_due']"),
    ('k04_questionnaire', "'questions_due' not in kinds(r)"),
    ('k07_answers_by', "'questions_due' not in kinds(r)"),
    ('n01_not_accepted_by_fax', "not neg(r, 'November 5, 2026')"),
    ('n02_not_due_until', "not neg(r, 'November 5, 2026')"),
    ('e06_unless_cancelled', "not neg(r, 'November 5, 2026')"),
    ('a03_pm_dot_cancelled', "not neg(r, 'November 5, 2026')"),
    ('b15_iana_space', "'timezone_unclear' in r.deadlines[-1].ambiguities"),
    ('e07_mt_tz_fp', "r.deadlines[-1].timezone != 'Mt'"),
    ('e10_time_stolen_paren', "[d.time for d in r.deadlines if d.date == 'November 5, 2026'] == [None]"),
    ('d16_zero_width_space', "bound(r) == ('5:00PM', 'ET')"),
]


def kinds(r):
    return [d.kind for d in r.deadlines]


def neg(r, date):
    return any(d.date == date and "negated_or_withdrawn" in d.ambiguities for d in r.deadlines)


def live(r, kind):
    return [(d.date, d.time, d.timezone) for d in r.deadlines if d.kind == kind and "negated_or_withdrawn" not in d.ambiguities]


def bound(r, kind="proposal_due"):
    d = [d for d in r.deadlines if d.kind == kind][-1]
    return d.time, d.timezone


@pytest.mark.parametrize("name, check", CHECKS, ids=[c[0] for c in CHECKS])
def test_reviewer_case(name, check):
    r = analyze(CASES[name])
    assert eval(check, {"r": r, "kinds": kinds, "neg": neg, "live": live, "bound": bound}), (r.deadlines, r.requirements, r.warnings)


def test_kb09_deadlines_are_capped_with_a_warning_and_bounded_work():
    r = analyze("due 2026-11-05 " * (core.MAX_DEADLINES + 500))
    assert len(r.deadlines) == core.MAX_DEADLINES
    assert any("extraction stopped" in w for w in r.warnings)


def _pdf(path):
    pypdf = pytest.importorskip("pypdf")
    w = pypdf.PdfWriter()
    w.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        w.write(f)
    return path


@pytest.mark.skipif(sys.platform == "win32", reason="no RLIMIT_CPU on Windows")
def test_kb10_worker_uses_a_lower_hard_cpu_limit_instead_of_crashing(tmp_path):
    pdf = _pdf(tmp_path / "blank.pdf")
    pkg = str(Path(core.__file__).resolve().parents[1])
    code = ("import sys, resource; resource.setrlimit(resource.RLIMIT_CPU, (30, 30)); sys.path.insert(0, sys.argv[1]); "
            "from bid_deadline_check.core import _pdf_worker; _pdf_worker(sys.argv[2:])")
    p = subprocess.run([sys.executable, "-I", "-B", "-c", code, pkg, str(pdf), "61", str(1 << 30), "1000", "5000000", "60"],
                       capture_output=True, text=True, timeout=60)
    out = __import__("json").loads(p.stdout)
    assert out["ok"] and out["limits"]["cpu_seconds"] == 30, p.stderr


def test_kb12_worker_never_imports_from_the_current_directory(tmp_path):
    pdf = _pdf(tmp_path / "blank.pdf")
    planted = tmp_path / "cwd" / "pypdf"
    planted.mkdir(parents=True)
    marker = tmp_path / "MARKER"
    (planted / "__init__.py").write_text(f"open({str(marker)!r}, 'w').write('planted')\n")
    env = {**os.environ, "PYTHONPATH": str(Path(core.__file__).resolve().parents[1]), "PYTHONDONTWRITEBYTECODE": "1"}
    p = subprocess.run([sys.executable, "-m", "bid_deadline_check.cli", str(pdf), "-f", "json"], cwd=tmp_path / "cwd",
                       env=env, capture_output=True, text=True, timeout=120)
    assert not marker.exists(), p.stdout + p.stderr
