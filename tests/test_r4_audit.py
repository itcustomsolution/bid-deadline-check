"""Regressions for the independent audit of the r4 candidate (2026-10-17, R4-DL-1..R4-DL-3). Synthetic text only;
inputs are the audit's minimal cases (its receipt case names are given) or siblings, plus its controls. These close
the named forms only: a clean --strict result still never means every deadline was found or is right."""
import pytest

from bid_deadline_check import analyze
from bid_deadline_check.cli import main

BASE = "Questions due October 1, 2026 at 10:00 AM ET.\nTechnical proposal must not exceed 20 pages.\n"
OLD = "Proposals due November 5, 2026 at 5:00 PM ET.\n"


def strict(tmp_path, text):
    f = tmp_path / "rfp.txt"
    f.write_text(text)
    return main([str(f), "--strict", "-f", "json"])


def proposals(r):
    return [(d.date, d.time, d.timezone, d.ambiguities) for d in r.deadlines if d.kind == "proposal_due"]


# R4-DL-1: a day-first date with an ordinal suffix was never checked against the calendar.
@pytest.mark.parametrize("date", ["31st February 2026", "29th February 2026", "31st April 2026", "0th November 2026",
                                  "99th November 2026", "30th February 2028"])
def test_r4_dl_1_impossible_ordinal_dates_are_invalid(tmp_path, date):
    text = BASE + f"Proposals due {date} at 5:00 PM ET."
    assert any(d == date and "invalid_date" in a for d, t, z, a in proposals(analyze(text))), proposals(analyze(text))
    assert strict(tmp_path, text) == 2


@pytest.mark.parametrize("date", ["5th November 2026", "29th February 2028", "29 February 2028", "1st March 2027"])
def test_r4_dl_1_valid_ordinal_controls_stay_clean(tmp_path, date):
    assert strict(tmp_path, BASE + f"Proposals due {date} at 5:00 PM ET.") == 0


def test_r4_dl_1_ordinal_and_plain_forms_compare_equal(tmp_path):
    text = BASE + "Proposals due 5th November 2026 at 5:00 PM ET.\nProposals due November 5, 2026 at 5:00 PM ET."
    assert not any("different proposal due" in w for w in analyze(text).warnings)
    assert strict(tmp_path, text) == 0


# R4-DL-2: a malformed date beside a valid old cutoff disappeared and left the old cutoff clean.
@pytest.mark.parametrize("value", ["2026-11-005", "2026-111-05", "20260-11-05", "11/12/2026/2027", "November 12, 26",
                                   "November, 12, 2026", "12.11.2026", "2026/11/12", "2026.11.12"])
def test_r4_dl_2_malformed_second_deadline_is_reported(tmp_path, value):
    text = BASE + OLD + f"Proposals due {value} at 5:00 PM ET."
    r = analyze(text)
    assert any("date-like value" in w and "line 4" in w.lower() for w in r.warnings), r.warnings
    assert strict(tmp_path, text) == 2


@pytest.mark.parametrize("tail", [
    "Proposals must follow Section 3.4.1 and FAR 52.212-1.",
    "Refer to part number 2026-1145-AB and drawing 12.11.B.",
    "See paragraphs 1.2.3 through 1.2.10 of the statement of work.",
    "The contract number is 47QTCA-26-D-0001.",
])
def test_r4_dl_2_part_and_section_numbers_stay_clean(tmp_path, tail):
    assert strict(tmp_path, BASE + OLD + tail) == 0


# R4-DL-3: an offset followed by a fraction was cut to the shorter valid offset.
@pytest.mark.parametrize("tail", ["Proposals due November 5, 2026 at 17:00 UTC+05:30.5.",
                                  "Proposals due November 5, 2026 at 17:00 GMT+5.5.",
                                  "Proposals due 2026-11-05T17:00:00-04:00.5."])
def test_r4_dl_3_fractional_offset_is_unclear(tmp_path, tail):
    r = analyze(BASE + tail)
    assert any("timezone_unclear" in a for d, t, z, a in proposals(r)), proposals(r)
    assert strict(tmp_path, BASE + tail) == 2


@pytest.mark.parametrize("tail", ["Proposals due November 5, 2026 at 17:00 UTC+05:30.",
                                  "Proposals due November 5, 2026 at 17:00 GMT+5.",
                                  "Proposals due 2026-11-05T17:00:00-04:00.",
                                  "Proposals due November 5, 2026 at 17:00 UTC-04:00. 5 copies are required."])
def test_r4_dl_3_offset_before_sentence_end_stays_clean(tmp_path, tail):
    assert strict(tmp_path, BASE + tail) == 0


# R4-SC-01 (GHSA-5hx5-vpf9-5wcv): pypdf below 6.21.1 passes /DCTDecode image data to Pillow without a format
# restriction, in its image conversion. The tool reads PDFs only through extract_text(); this checks that its text path
# never calls the conversion, for a page that draws a non-JPEG /DCTDecode image and holds an inline /DCT image, while
# pypdf's own image API on the same page does (the control). It shows the path is not reached for this file, not that
# no PDF can reach it; the floor is raised regardless.
def test_r4_sc_01_pdf_text_path_does_not_convert_images(tmp_path):
    import json, subprocess, sys
    from pathlib import Path
    root = Path(__file__).resolve().parent
    p = subprocess.run([sys.executable, "-I", str(root / "probes/pypdf_reachability.py"), str(root.parent / "src"), str(tmp_path)],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-500:]
    res = json.loads(p.stdout.strip().splitlines()[-1])
    assert res["text_found"]
    assert res["calls_during_text_extraction"] == {"xobj_to_image": 0, "Image.open": 0}
    assert res["calls_after_images_control"]["xobj_to_image"] >= 1, "the control must reach the conversion"
    assert res["calls_after_images_control"]["Image.open"] >= 1, "the control must reach Pillow's open"


# Internal r5 review (KR5-01..05, review/r5-kofi/REPORT.md). These fail on the r5 commit 54808d0, except the controls.
@pytest.mark.parametrize("value", ["November,12,2026", "November , 12, 2026", "Nov-12-2026", "11/05/2026/11/12/2026"])
def test_kr5_01_more_malformed_dates_are_reported(tmp_path, value):
    text = BASE + OLD + f"Proposals due {value} at 5:00 PM ET."
    assert any("date-like value" in w and "line 4" in w.lower() for w in analyze(text).warnings), analyze(text).warnings
    assert strict(tmp_path, text) == 2


# Control: r5 reported these through the broad forms that KR5-02 narrows; on a line with a deadline word they still are.
@pytest.mark.parametrize("value", ["2026-11-5", "2026/1/15", "2026.11.5"])
def test_kr5_02_control_one_digit_year_first_dates_on_a_deadline_line(tmp_path, value):
    assert strict(tmp_path, BASE + OLD + f"Proposals due {value} at 5:00 PM ET.") == 2


def test_kr5_01_day_month_comma_year_is_read(tmp_path):
    r = analyze(BASE + OLD + "Proposals due 12 November, 2026 at 5:00 PM ET.")
    assert ("12 November, 2026", "5:00 PM", "ET") in [(d, t, z) for d, t, z, a in proposals(r)]
    assert strict(tmp_path, BASE + "Proposals due Thursday, 5 November, 2026 at 5:00 PM ET.") == 0


@pytest.mark.parametrize("tail", ["Site visits are held on November 3, 10 and 17, 2026.",
                                  "Oral presentations are scheduled for May 4, 11 and 18.",
                                  "Install IntelliJ IDEA 2024.1.2 or later.", "Tableau v2023.3.1 is required.",
                                  "Solicitation No. 2026-100-001 applies.", "Refer to RFP 2026-1-05 for scope.",
                                  "Bid No. 2025-12-1 covers road salt.", "Paragraph L.3.2.2019 applies.",
                                  "Statute 2001.3.1 applies.", "Use release 2024.10.1."])
def test_kr5_02_identifiers_and_lists_are_not_malformed_dates(tmp_path, tail):
    assert strict(tmp_path, BASE + OLD + tail) == 0


def test_kr5_03_month_matched_only_by_case_folding_fails_closed(tmp_path):
    text = BASE + "Proposals due ſeptember 5, 2026 at 5:00 PM ET."
    assert any("invalid_date" in a for d, t, z, a in proposals(analyze(text))), proposals(analyze(text))
    assert strict(tmp_path, text) == 2


def test_kr5_04_zone_name_with_fraction_is_unclear(tmp_path):
    text = BASE + "Proposals due November 5, 2026 at 17:00 Etc/GMT+5.5."
    assert any("timezone_unclear" in a for d, t, z, a in proposals(analyze(text))), proposals(analyze(text))
    assert strict(tmp_path, text) == 2
    assert strict(tmp_path, BASE + "Proposals due November 5, 2026 at 17:00 Etc/GMT+5.") == 0
