"""Adversarial regressions from the 2026-10 security audit."""
import csv
import io
import time

from bid_deadline_check import analyze
from bid_deadline_check.cli import main


def test_exploit_redos_long_unpunctuated_line_is_fast():
    # Previously O(n^2): a 100 KB line without '.' or ';' took minutes.
    t = time.time()
    analyze("the offeror shall " + "word " * 20000)
    analyze("Technical " * 20000 + " limited to 10 pages")
    assert time.time() - t < 5


def test_requirements_unchanged_by_sentence_split():
    r = analyze("The offeror shall submit Volume I. The contractor must not exceed 10 pages; vendor notes")
    texts = [x["text"] for x in r.requirements]
    assert texts == ["The offeror shall submit Volume I.", "The contractor must not exceed 10 pages;"]


def test_exploit_csv_formula_injection_neutralized(tmp_path, capsys):
    f = tmp_path / "rfp.txt"
    f.write_text('=HYPERLINK("http://evil/x","click") the offeror shall comply with everything here.\n'
                 '@SUM(1+1) contractor shall also comply with this requirement.\n')
    # 1) prove the malicious text actually reaches the checklist (otherwise the escaping check is vacuous)
    items = [c["item"] for c in analyze(f.read_text()).checklist()]
    assert any(i.startswith("=HYPERLINK") for i in items), items
    assert any(i.startswith("@SUM") for i in items), items
    # 2) and that every such cell is prefixed in the CSV output
    main([str(f), "-f", "csv"])
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert any(r["item"].startswith("'=HYPERLINK") for r in rows)
    assert any(r["item"].startswith("'@SUM") for r in rows)
    for row in rows:
        for v in row.values():
            assert not (v or "").startswith(("=", "+", "-", "@", "\t", "\r")), v


def test_markdown_escapes_html(tmp_path, capsys):
    f = tmp_path / "rfp.txt"
    f.write_text("The offeror shall <img src=x onerror=alert(1)> comply with all instructions.\n")
    main([str(f), "-f", "md"])
    assert "<img" not in capsys.readouterr().out


def test_exploit_page_limit_digit_run_is_linear():
    # PAGE_LIMIT "(\d+)[- ]page" was O(n^2) on long digit runs (40 KB of digits ~ 10 s).
    t = time.time()
    analyze("1" * 40000)
    analyze("maximum of " + "9" * 40000)
    assert time.time() - t < 2


def test_page_limit_still_found():
    r = analyze("The Technical Volume is limited to 20 pages. A 15-page limit applies to Past Performance.")
    assert sorted(p.pages for p in r.page_limits) == [15, 20]


def test_iter_sentences_matches_split_and_is_single_pass():
    from bid_deadline_check.core import iter_sentences
    s = "a. b; c. no end"
    assert list(iter_sentences(s)) == ["a.", " b;", " c.", " no end"]
    assert "".join(iter_sentences("x" * 100000)) == "x" * 100000


def test_subject_found_from_context_beyond_2000_chars():
    line = ("filler " * 400) + "Volume II Past Performance shall not exceed 10 pages"
    assert len(line) > 2000
    r = analyze(line)
    assert r.page_limits and r.page_limits[0].applies_to.startswith("Volume II")


def test_subject_far_before_match_is_not_used():
    line = "Volume I Technical shall be clear. " + ("filler " * 100) + "The total must not exceed 30 pages"
    r = analyze(line)
    assert r.page_limits[0].applies_to == "unspecified"


def test_stdin_is_bounded(monkeypatch):
    import pytest
    from bid_deadline_check import core
    monkeypatch.setattr(core, "MAX_INPUT_BYTES", 10)
    assert core.read_stdin_bounded(io.BytesIO(b"0123456789")) == "0123456789"
    with pytest.raises(SystemExit):
        core.read_stdin_bounded(io.BytesIO(b"0123456789A"))


class _Page:
    def __init__(self, text, delay=0.0):
        self.text, self.delay = text, delay

    def extract_text(self):
        if self.delay:
            time.sleep(self.delay)
        return self.text


class _Reader:
    def __init__(self, pages):
        self.pages = pages


def test_pdf_page_text_and_time_limits(monkeypatch):
    import pytest
    from bid_deadline_check import core
    monkeypatch.setattr(core, "MAX_PDF_PAGES", 3)
    with pytest.raises(SystemExit, match="pages"):
        core._bounded_pdf_text(_Reader([_Page("x")] * 4))
    monkeypatch.setattr(core, "MAX_TEXT_CHARS", 10)
    with pytest.raises(SystemExit, match="characters"):
        core._bounded_pdf_text(_Reader([_Page("123456"), _Page("789012")]))
    monkeypatch.setattr(core, "MAX_TEXT_CHARS", 10_000)
    monkeypatch.setattr(core, "PDF_TIME_BUDGET_S", 0.05)
    with pytest.raises(SystemExit, match="exceeded"):
        core._bounded_pdf_text(_Reader([_Page("a", 0.06), _Page("b"), _Page("c")]))
    assert core._bounded_pdf_text(_Reader([_Page("a"), _Page("b")])) == "a\nb"
