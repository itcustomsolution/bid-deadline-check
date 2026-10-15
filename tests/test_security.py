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
    f.write_text('=HYPERLINK("http://evil.example/x","click") the offeror shall comply with everything here.\n'
                 '@SUM(1+1) contractor shall also comply with this requirement.\n')
    main([str(f), "-f", "csv"])
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    for row in rows:
        for v in row.values():
            assert not (v or "").startswith(("=", "+", "-", "@")), v


def test_markdown_escapes_html(tmp_path, capsys):
    f = tmp_path / "rfp.txt"
    f.write_text("The offeror shall <img src=x onerror=alert(1)> comply with all instructions.\n")
    main([str(f), "-f", "md"])
    assert "<img" not in capsys.readouterr().out
