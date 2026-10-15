import json
from pathlib import Path

from bid_deadline_check import analyze
from bid_deadline_check.cli import main

FX = Path(__file__).parent / "fixtures"


def rep(name):
    return analyze((FX / name).read_text())


def test_deadlines():
    r = rep("rfp_sample.txt")
    by = {d.kind: d for d in r.deadlines}
    q = by["questions_due"]
    assert q.date == "October 20, 2026" and q.time == "2:00 PM" and q.timezone == "Eastern Time"
    p = by["proposal_due"]
    assert p.date == "November 5, 2026" and p.time == "11:00 AM" and p.timezone == "EDT"
    assert by["site_visit"].timezone == "local time"


def test_page_limits():
    r = rep("rfp_sample.txt")
    got = {(p.pages, p.applies_to) for p in r.page_limits}
    assert (20, "Volume I Technical") in got
    assert (10, "Volume II Past Performance") in got


def test_forms_sections_volumes():
    r = rep("rfp_sample.txt")
    assert {"SF-1449", "SF-30", "FAR 52.212-3", "DFARS 252.204-7012"} <= set(r.forms)
    assert r.forms.count("SF-1449") == 1
    assert {"L", "M"} <= set(r.sections)
    assert any(v.startswith("Volume III") for v in r.volumes)


def test_format_rules_and_requirements():
    r = rep("rfp_sample.txt")
    rules = {f["rule"] for f in r.format_rules}
    assert {"font", "margins", "paper", "file_format", "spacing"} <= rules
    assert any("UEI and CAGE" in q["text"] for q in r.requirements)


def test_warnings_minimal():
    r = rep("rfq_minimal.txt")
    d = r.deadlines[0]
    assert d.kind == "proposal_due" and d.date == "2026-12-01" and d.time == "1500 hours"
    assert any("no timezone" in w for w in r.warnings)
    assert any("questions-due" in w for w in r.warnings)
    assert any("page limits" in w for w in r.warnings)


def test_clean_doc_has_no_deadline_warnings():
    r = rep("rfp_sample.txt")
    assert not any("No proposal" in w or "questions-due" in w for w in r.warnings)


def test_checklist_ids_and_deterministic():
    a = rep("rfp_sample.txt").checklist()
    b = rep("rfp_sample.txt").checklist()
    assert a == b and a[0]["id"] == "C001" and all(not c["done"] for c in a)


def test_cli_json(capsys):
    assert main([str(FX / "rfp_sample.txt"), "-f", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["checklist"] and data["deadlines"]


def test_cli_csv_md_text(capsys):
    main([str(FX / "rfp_sample.txt"), "-f", "csv"])
    assert capsys.readouterr().out.startswith("id,category,item,line,done")
    main([str(FX / "rfp_sample.txt"), "-f", "md"])
    assert "| C001 |" in capsys.readouterr().out
    main([str(FX / "rfp_sample.txt")])
    assert "DEADLINES" in capsys.readouterr().out


def test_cli_strict_exit(capsys):
    assert main([str(FX / "rfq_minimal.txt"), "--strict"]) == 2


def test_pdf(tmp_path):
    from pypdf import PdfWriter
    import pytest
    pytest.importorskip("pypdf")
    # Build a tiny PDF with text via reportlab-free approach: skip if no writer support for text
    w = PdfWriter()
    w.add_blank_page(612, 792)
    f = tmp_path / "blank.pdf"
    with open(f, "wb") as fh:
        w.write(fh)
    from bid_deadline_check import read_document
    assert read_document(f).strip() == ""


def test_dash_page_limit_and_application_due_with_label_above():
    from bid_deadline_check import analyze
    r = analyze("• Page Limit – Technical Proposal: 20 pages\nApplications must be received no later than\n30 October 2026 at 5:00 PM Eastern Time\n")
    assert [p.pages for p in r.page_limits] == [20]
    assert any(d.kind == "proposal_due" and d.timezone for d in r.deadlines)
