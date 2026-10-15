# bid-deadline-check

Read a government solicitation (RFP, RFQ, IFB; PDF or text) and get back:

- **Deadlines** with date, time and **timezone**: questions due, proposal due, site visit, intent to bid, orals
- **Page limits** per volume
- **Format rules**: font, margins, paper size, spacing, file format
- **Forms and clauses**: SF-1449, SF-33, SF-30, FAR 52.xxx, DFARS 252.xxx
- **Sections and volumes** referenced (L, M, Volume I/II/III)
- Every **"shall / must"** requirement aimed at the offeror
- A **compliance checklist** (text, JSON, CSV or Markdown)
- **Warnings** for what's missing: no proposal due date, a time with no timezone, no page limits

It is deterministic: regex and rules only. No LLM, no network, nothing leaves your machine.

## Quickstart

```bash
pip install "git+https://github.com/itcustomsolution/bid-deadline-check#egg=bid-deadline-check[pdf]"
# (PyPI release coming soon: pip install "bid-deadline-check[pdf]")

bid-deadline-check solicitation.pdf
bid-deadline-check solicitation.pdf -f csv > compliance-matrix.csv
bid-deadline-check solicitation.txt -f md
bid-deadline-check solicitation.txt -f json
```

Example output (from `tests/fixtures/rfp_sample.txt`, a synthetic RFP):

```
DEADLINES
  [questions_due] October 20, 2026 2:00 PM Eastern Time  (line 6)
  [proposal_due] November 5, 2026 11:00 AM EDT  (line 7)
  [site_visit] 10/27/2026 10:00 AM local time  (line 8)
PAGE LIMITS
  Volume I Technical: 20 pages  (line 13)
  Volume II Past Performance: 10 pages  (line 14)
...
```

`--strict` exits with code 2 when there are warnings, so you can gate a script on it.

## Library

```python
from bid_deadline_check import analyze, read_document

report = analyze(read_document("solicitation.pdf"))
for d in report.deadlines:
    print(d.kind, d.date, d.time, d.timezone)
rows = report.checklist()   # list of dicts: id, category, item, line, done
```

## Scope and limits

- It finds what is written; it does not interpret it. Always read the solicitation and every amendment yourself. This is a checklist aid, not legal or contracting advice.
- Scanned PDFs without a text layer return no text. Run OCR first.
- Dates are reported as written; no timezone conversion.
- Out of scope: scoring, bid/no-bid, writing proposal content.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Fixtures are synthetic. Please don't add real solicitations that carry controlled or proprietary markings.

## License

MIT © IT Custom Solution
