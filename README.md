# bid-deadline-check

Read a government solicitation (RFP, RFQ, IFB; PDF or text) and get back:

- **Deadlines** with date, time and **timezone exactly as written**: questions due, proposal due,
  revised/final proposals, registration, site visit, intent to bid, orals. Each date is bound only to
  the time and zone written with it, several deadlines on one line are all kept, and anything
  unresolved (no time, no zone, "EOD", "midnight", an impossible date, a withdrawn date) is flagged
- **Page limits** per volume
- **Format rules**: font, margins, paper size, spacing, file format
- **Forms and clauses**: SF-1449, SF-33, SF-30, FAR 52.xxx, DFARS 252.xxx
- **Sections and volumes** referenced (L, M, Volume I/II/III)
- **"Shall / must" sentences** aimed at the offeror, found by keyword rules, including sentences
  wrapped across lines. Up to 1000 characters they are kept whole; longer ones are shown as flagged
  excerpts with their source lines, never silently cut
- A **compliance checklist** (text, JSON, CSV or Markdown)
- **Warnings** for what is missing or needs a human check

It is deterministic: regex and rules only. No LLM, no network, nothing leaves your machine.

## Quickstart

```bash
pip install "bid-deadline-check[pdf]"

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
  [registration] 10/23/2026 (no time) (no timezone)  (line 8)  CHECK: no_time
PAGE LIMITS
  Volume I Technical: 20 pages  (line 13)
  Volume II Past Performance: 10 pages  (line 14)
...
WARNINGS
  ! Deadline on line 8 has a date but no time of day; confirm the cutoff time.
```

## What `--strict` means

`--strict` exits with code 2 when any warning fired, and 0 otherwise. Exit 0 means only that none of
the implemented checks fired:

- a proposal due date and a questions-due date were found (and neither is negated or withdrawn);
- every extracted deadline has a valid calendar date, a clock time (or "noon") and a timezone, all
  bound to the same clause, with no "EOD"/"midnight"/close-of-business marker and no two-digit year;
- no kind of deadline has two different values (for example an amended due date);
- no requirement was reported as an excerpt;
- page limits were found; and
- the input decoded without replacement characters.

It does **not** mean that every deadline or requirement in the document was found, that the extracted
values are what the agency intended, that a timezone is valid, or that a submission would be timely.
Read the solicitation and every amendment yourself.

## Library

```python
from bid_deadline_check import analyze, read_document

report = analyze(read_document("solicitation.pdf"))
for d in report.deadlines:
    print(d.kind, d.date, d.time, d.timezone, d.line, d.ambiguities)
rows = report.checklist()   # list of dicts: id, category, item, line, done
```

`Deadline` has `kind`, `date`, `time`, `timezone`, `line`, `text` (the clause around the date),
`end_line` and `ambiguities` (codes: `no_time`, `no_timezone`, `time_marker:<text>`, `invalid_date`,
`invalid_time`, `two_digit_year`, `negated_or_withdrawn`, `context_truncated`,
`statement_split_at_limit`). Each requirement is `{"text", "line", "end_line", "truncated"}`.

## Scope and limits

- It finds what is written; it does not interpret it. This is a checklist aid, not legal or
  contracting advice.
- Dates and times are reported as written. There is no timezone conversion, no daylight-saving
  validation (a winter date marked "EDT" passes), no holiday or next-business-day logic, and no
  judgement of whether a submission is on time. Numeric dates such as `10/05/2026` are not
  re-ordered; two-digit years are flagged.
- Signed UTC/GMT offsets (`UTC-04:00`), ISO offsets (`2026-11-05T17:00:00-04:00`) and IANA names
  (`America/New_York`) are kept exactly; IANA names are not checked against a timezone database.
- Rules are keyword based. Obligations phrased without "shall", "must" or "is/are required to", or not
  naming an offeror, contractor, quoter, vendor, bidder, proposal, response or submission, are not
  listed. Wrapped lines are joined into one statement for at most 25 lines or 6000 characters; text
  cut at that bound is flagged.
- Scanned PDFs without a text layer return no text. Run OCR first.
- Limits: files and stdin over 50 MB are refused. PDFs over 1000 pages or over 5 million extracted
  characters are refused (checked between pages). By default PDFs are parsed in a separate Python
  process that is stopped after 65 s of wall-clock time and limited to 61 s of CPU time; where the
  operating system allows it (normally Linux) its address space is also limited to 1 GiB. macOS does
  not allow that memory limit (measured), and Windows has no CPU limit, so there only the wall-clock
  stop applies. `read_document(path, isolate=False)` parses in-process with between-page checks only,
  which do not bound a single slow page. Requires pypdf 6.21.0 or later.
- CSV output prefixes cells that start with `=`, `+`, `-`, `@`, tab or CR with `'`. This is a common
  mitigation for formula injection; it is not tested against any particular spreadsheet application.
- Output contains solicitation text. Treat it as untrusted data if another program or an AI assistant
  reads it.
- Out of scope: scoring, bid/no-bid, writing proposal content.

## Development

This candidate was verified locally with CPython 3.10, 3.11, 3.12 and 3.14 on macOS (arm64), from source
and from the built wheel. Python 3.13, Linux and Windows were not run locally. The pull-request workflow
is configured for Python 3.10, 3.12 and 3.14 on Linux, plus Python 3.14 on macOS; configured jobs are not
executed by this change. Python 3.10 reached end of life on 2026-10-01 and remains the declared minimum.

```bash
python -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r requirements/build.txt -r requirements/test.txt
pip install --no-deps --no-build-isolation -e .
pytest
```

Fixtures are synthetic. Please don't add real solicitations that carry controlled or proprietary markings.

## License

MIT © IT Custom Solution
