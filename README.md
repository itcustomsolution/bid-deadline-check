# bid-deadline-check

Read a government solicitation (RFP, RFQ, IFB; PDF or text) and get back:

- **Deadlines** with date, time and **timezone exactly as written**: questions due, proposal due,
  revised/final proposals, registration, site visit, intent to bid, orals. Each date is bound only to
  the time and zone written with it, several deadlines on one line are all kept, and anything
  unresolved (no time, no zone, "EOD", "midnight", an impossible date, a date described as withdrawn,
  cancelled, superseded or no longer in effect, a date taken from a "received after" clause) is flagged
- **Page limits** per volume
- **Format rules**: font, margins, paper size, spacing, file format
- **Forms and clauses**: SF-1449, SF-33, SF-30, FAR 52.xxx, DFARS 252.xxx
- **Sections and volumes** referenced (L, M, Volume I/II/III)
- **"Shall / must" sentences** aimed at the offeror, found by keyword rules, including sentences
  wrapped across lines. Up to 1000 characters they are kept whole; longer ones, and sentences interrupted
  by a list-item or heading line, are shown as flagged excerpts with their source lines
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
  bound to the same clause, with no "EOD"/"midnight"/close-of-business marker and no two-digit year,
  and none is flagged as withdrawn or superseded, as replacing an earlier date, as possibly an issue
  date, as sharing its sentence with another clock time or with a date not read as a deadline in a
  sentence that changes something, as taken from a "received after" clause, as of uncertain kind, or as
  having an unclear or unsupported timezone;
- no kind of deadline has two different values (for example an amended due date);
- no requirement was reported as an excerpt;
- page limits were found;
- no date-like value was found in a form the tool does not read (for example `111/05/2026`,
  `5November 2026`, `November 12,2026`, `12-NOV-2026`, `11-12-2026`, `03 NOV 26`, or a letter typed for a
  digit as in `2O26` or `November l2, 2026`), and no deadline's date or zone runs into the text after it
  (`November 5, 2026x` and `November 5, 2026_draft` are read as November 5 and flagged; `17:00:00Zdraft` and
  `UTC+05:30junk` are read as `Z` and `UTC+05:30` and flagged);
- no clause both names a deadline ("proposal due date", "closing time", "deadline", "time for receipt",
  "proposals are now due", an SF form block) and uses change wording ("extended", "postponed", "revised",
  "altered", "adjusted", "brought forward", "revoked", "suspended", "slides", "now <date or time>", "new date",
  "vice", "in place of", "rather than", ", not <date>", "(was <date>)", "formerly", "originally",
  "from ... to ...", and so on) without one of its dates being read as a
  replacement, and no clause without a date has change wording (or "now"), a deadline word and a clock
  time ("Proposals must now be received by 3:00 PM ET."). These two checks are what make a revision fail
  `--strict` when the tool cannot read it: a change with no date ("postponed until further notice"), a new
  date in a form it does not read, a new date in the next sentence, or a time-only change. They are
  keyword based, so they also miss revisions: a dateless change whose subject is not one of the deadline
  names above ("Receipt of offers is extended by one week.", "The submission window is extended by ten
  days.", "Closing extended one week."), an SF-30 Block 11 box checked as "[X] is extended", "due one week
  later", a time written without a change word ("Amendment 0004: submit proposals by 3:00 PM ET."), "Offers
  due: TBD", a zone change ("Central Time, not Eastern Time") and a new date stated without change wording
  ("Proposals will be accepted until November 12, 2026 at 5:00 PM ET." beside the old one) give `--strict` 0
  with only the old deadline, as does any other change verb the tool does not list. Of the last internal
  review's 10 fresh revision sentences, 3 still pass `--strict` (5 did before this release); of its 30
  harder revision sentences, 13 pass. Treat a clean `--strict` result as "no implemented check fired", never as
  "no amendment changed a deadline"; and
- the input decoded without replacement characters, and extraction did not stop at its per-document
  limits.

It does **not** mean that every deadline or requirement in the document was found, that the extracted
values are what the agency intended, that a timezone is valid, or that a submission would be timely.
Read the solicitation and every amendment yourself.

Known cases where `--strict` fails although nothing is wrong: the same time restated in another zone
("5:00 PM ET (2:00 PM PT)"), because the tool does not convert zones; office hours in the deadline's
sentence ("; hand-carried proposals are accepted between 8:00 AM and 4:00 PM ET"); and slash-separated part
or document numbers that look like dates (`123/45/6789`); a period-of-performance or validity change whose
sentence names a date, time, receipt, submission, solicitation or any deadline kind (offers, questions,
registration, site visit, and so on); an issue, amendment or announcement word between the deadline word and its
date ("due on the date stated in Amendment 0002, November 12, 2026", "the due date was communicated to offerors
on ..."); any other date in a deadline's sentence when that sentence
has change wording ("new", "now", "updated", "extended", and so on), such as a performance period in the same
sentence as an extended deadline; and any clause that names a deadline and uses change wording without a date read
as a replacement, including hedged or hypothetical sentences: "Requests for extension of the proposal due date will
not be granted", "The Government reserves the right to amend the solicitation and extend the proposal due date",
"Proposals may be modified or withdrawn at any time before the closing date", and the FAR 52.212-1(f)(4) emergency
sentence ("... the time specified for receipt of offers will be deemed to be extended ..."). A change that the tool cannot read is reported, not read: the warning
names its line, and the reader confirms the new date or time in the source. When a time-only change is written next
to a date, the old time may be the one reported (flagged as withdrawn or as another time). Dates after an issue
word ("issued", "posted", "dated", and so on) with no deadline word before them are skipped as issue dates and are
not named by the unread-date check, except after "effective" or "as of"; a clause that also names a deadline with
change wording is still reported by the clause check above.

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
`invalid_time`, `two_digit_year`, `negated_or_withdrawn`, `replaces_earlier_date` (the new date of an
"extended/changed/moved from ... to ..." or "... it is now <date>" amendment), `issue_date_possible` (an issue,
amendment or announcement word, such as "was publicized" or "was delivered", sits between the deadline word and the
date), `date_glued_to_text` (letters follow the date with no space, as in `2026at`), `timezone_glued_to_text`
(letters or digits follow the zone with no space, as in `17:00:00Zdraft` or `UTC+05:30junk`), `other_time:<text>` (another clock time in the same
sentence, at most five), `unread_date:<text>` (another date in a sentence with change wording that was not read as
a deadline, at most five), `after_clause`, `kind_uncertain`, `timezone_unclear` (a zone that may be cut
short or is in an unsupported form, such as `UTC+05:30:15`), `statement_split_at_limit`, and
`context_truncated`, which only says the `text` excerpt was shortened and raises no warning). Each requirement is `{"text", "line", "end_line", "truncated"}`.

## Scope and limits

- It finds what is written; it does not interpret it. This is a checklist aid, not legal or
  contracting advice.
- Dates and times are reported as written. There is no timezone conversion, no daylight-saving
  validation (a winter date marked "EDT" passes), no holiday or next-business-day logic, and no
  judgement of whether a submission is on time. Numeric dates such as `10/05/2026` are not
  re-ordered; two-digit years are flagged.
- Signed UTC/GMT offsets (`UTC-04:00`), ISO offsets (`2026-11-05T17:00:00-04:00`) and IANA names
  (`America/New_York`) are kept exactly; IANA names are not checked against a timezone database.
- Rules are keyword based and match whole words, so "registered", "conference call", "questionnaire"
  and "offeror" do not name a kind of deadline. When a clause names both a submission ("submit
  proposals") and something else ("industry day", "registration"), the submission wins. A date is
  bound to what is written with it in its own clause, or to a label on the line just above it.
  Obligations phrased without "shall", "must" or "is/are required to", or not naming an offeror,
  contractor, quoter, vendor, bidder, proposal, response or submission, are not listed. Wrapped lines
  are joined into one statement for at most 25 lines or 6000 characters; text cut at that bound, or
  interrupted by a list item or heading, is flagged.
- Scanned PDFs without a text layer return no text. Run OCR first.
- Limits: files and stdin over 50 MB are refused. At most 2000 deadlines and 10000 requirements are
  extracted per document; a warning says where extraction stopped. Measured on macOS (arm64), analysis
  needs up to about 23 MB of memory and 1.8 s per MB of text (20 MB: 456 MB and 11 s for dense dated
  text, 321 MB and 37 s for one-word lines), so a 50 MB input can need about 1.2 GB and 90 s.
- PDFs over 1000 pages or over 5 million extracted characters are refused (checked between pages). By
  default PDFs are parsed in a separate Python process that is stopped after 65 s of wall-clock time
  and limited to 61 s of CPU time (or the environment's hard CPU limit, if lower); where the operating
  system allows it (normally Linux) its address space is also limited to 1 GiB. macOS does not allow
  that memory limit (measured), and Windows has no CPU limit, so there only the wall-clock stop
  applies. The worker never imports from the current directory. A worker that crashes is reported as a
  failure, not as a limit. `read_document(path, isolate=False)` parses in-process with between-page
  checks only, which do not bound a single slow page. Requires pypdf 6.21.0 or later.
- CSV output prefixes cells that start with `=`, `+`, `-`, `@`, tab or CR with `'`. This is a common
  mitigation for formula injection; it is not tested against any particular spreadsheet application.
- Output contains solicitation text. Treat it as untrusted data if another program or an AI assistant
  reads it.
- Out of scope: scoring, bid/no-bid, writing proposal content.

## Development

The pull-request workflow is configured for Python 3.10, 3.12 and 3.14 on Linux, plus Python 3.14 on
macOS; configured jobs are not executed by this change. Python 3.10 reached end of life on 2026-10-01 and
remains the declared minimum.

```bash
python -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r requirements/build.txt -r requirements/test.txt
pip install --no-deps --no-build-isolation -e .
pytest
```

Fixtures are synthetic. Please don't add real solicitations that carry controlled or proprietary markings.

## License

MIT © IT Custom Solution
