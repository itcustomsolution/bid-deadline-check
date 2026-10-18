# bid-deadline-check

Read a government solicitation (RFP, RFQ, IFB; PDF or text) and get back:

- **Deadlines** with date, time and **timezone exactly as written**: questions due, proposal due,
  revised/final proposals, registration, site visit, intent to bid, orals. Each date is bound only to
  the time and zone written with it, several deadlines on one line are all kept, and anything
  unresolved (no time, no zone, "EOD", "midnight", an impossible date, a date described as withdrawn,
  cancelled, superseded or no longer in effect, a date taken from a "received after" clause) is flagged
- An **outcome**, READ or NEEDS REVIEW, and each sentence about a deadline that could not be resolved
  (a change with no new date read, a cancellation, TBD, a date form it does not read), with its exact
  text and a reason. A deadline that such a sentence may change is marked not actionable as stated
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
OUTCOME: NEEDS REVIEW (0 unresolved deadline sentence(s), 3 warning(s))
DEADLINES
  [questions_due] October 20, 2026 2:00 PM Eastern Time  (line 6)
  [proposal_due] November 5, 2026 11:00 AM EDT  (line 7)
  [site_visit] 10/27/2026 10:00 AM local time  (line 8)  CHECK: zone_unanchored  NOT ACTIONABLE AS STATED: needs review
  [registration] 10/23/2026 (no time) (no timezone)  (line 8)  CHECK: no_time  NOT ACTIONABLE AS STATED: needs review
PAGE LIMITS
  Volume I Technical: 20 pages  (line 13)
  Volume II Past Performance: 10 pages  (line 14)
...
WARNINGS
  ! Deadline on line 8: "local time" names no place; confirm the zone.
  ! Deadline on line 8 has a date but no time of day; confirm the cutoff time.
  ! Requirement on line 9 is long or continues past a parsing bound; the checklist shows an excerpt. Read lines 9-9.
```

## What `--strict` means

Every run reports an outcome: **READ** or **NEEDS REVIEW** (`outcome` in JSON, the first line of text output).
`--strict` exits 2 unless the outcome is READ, and 1 when the input cannot be read. READ means only that none of the
implemented checks fired:

- a proposal due date and a questions-due date were found, neither negated or withdrawn, and page limits were found;
- every extracted deadline has a valid calendar date in 1900 to 2100 whose weekday, if written, matches; a clock time
  (or "noon"); and one valid zone (an IANA name the zone database knows, or a UTC offset from UTC-12:00 to
  UTC+14:00), all bound to the same clause, with no "EOD", "midnight" or close-of-business marker, no two-digit year
  and no second, different zone written for the same time ("3:00 PM PST / 3:00 PM EST", "4:00 PM MT, 4:00 PM PT"),
  and no other clock time in the sentence, also before the date ("By 3:00 PM ET, proposals are due ... at 5:00 PM
  ET"; a time named for a briefing or other event just before it, or across a ";", does not count);
- no deadline is flagged as withdrawn, superseded, paused or on hold, as replacing an earlier date ("New date:"), as
  quoted from or labeled as an earlier text ("the RFP stated:", "Amendment 0001 read:", "former deadline", "Original
  Proposal Due", "Proposals were due", "Was:"), as possibly an issue or announcement date, as of uncertain kind (a date
  that names a deadline or a submission but no kind is read as a proposal deadline of uncertain kind, so it conflicts
  with an old cutoff), as sharing its sentence with another clock time or an unread date, as taken from a "received
  after" clause, or as of uncertain kind;
- no kind of deadline has two different values, and none is withdrawn or quoted from an earlier text in one place
  and written as current in another;
- no sentence about a deadline was left unresolved (the review items below), and no unsupported date form was found;
- every deadline is actionable; and
- the input decoded without replacement characters, and extraction did not stop at its per-document limits.

NEEDS REVIEW lists each unresolved candidate in `needs_review` with its first and last line, a reason code and its
exact source text (up to 600 characters). Each deadline carries `status`: `actionable`, or `needs_review` with the
reasons in `review`. A deadline is held (not actionable as stated) when it has any of the flags above, when another
value of its kind conflicts with it or is withdrawn, or when an unresolved item names its kind, names no kind at all,
or uses a generic deadline word ("the deadline", "the closing date"), so a
recognized old cutoff is never presented as actionable while a change to it is unresolved. The text output prints
these as "NOT ACTIONABLE AS STATED"; the checklist (`md`, `csv`) lists the review items first.

| Reason code | A sentence that names a deadline and ... |
|---|---|
| `solicitation_cancelled_or_draft` | (any sentence) cancels, withdraws, suspends, closes or puts on hold the whole solicitation or acquisition ("RFP cancelled.", "The agency withdrew the RFP.", "NOTICE OF CANCELLATION"), or marks it as a draft, notional or not yet requested; every deadline is held. "whether", "if" or "in the event" just before it, or a reserved right ("the right to cancel this solicitation"), does not count |
| `schedule_changed` | (any sentence) changes the schedule, the timeline or all dates at once ("The schedule is extended by two weeks", "all subsequent dates are postponed", "The timeline slips two weeks"); every deadline is held |
| `change_not_read` | changes it (a change verb that is not directly negated, "shortened", "waived", an imperative such as "Alter the closing time" or "Disregard the proposal due date", "reopens", "is now", "one week later than stated", a checked SF-30 "[X] is extended") with no replacement date read; also any sentence that corrects an earlier text ("should read", "is corrected to", "typographical error") and gives a date or time, a "New date:" label or "extends it to <date>", a change whose subject is only a pronoun ("It is extended one week"), a sentence that begins with the change ("extended by one week." after a blank line, "(Postponed.)"), and a stated interruption or emergency that triggers the FAR emergency extension |
| `deadline_cancelled_or_suspended` | cancels, withdraws, rescinds, revokes, suspends or postpones it |
| `deadline_to_be_determined` | says it is TBD, T.B.D., to be determined, pending, N/A or will be set later (also in a table row, "Revised Proposal Due \| TBD"); also any sentence saying the schedule, timeline or dates are TBD or TBA |
| `deadline_negated` | says it is no longer due, no longer applies, or that proposals are no longer (or not) accepted or required, or that no proposals will be accepted |
| `time_without_date` | gives a clock time but no date that was read (a restatement of a time already read in the same statement is not one) |
| `date_not_read_as_deadline` | contains a date that was not read as a deadline and is not an issue date |
| `unread_date_value` | contains a date-like value this tool does not read ("2026.11.5", "20261112", "2026 11 12", "Friday", "tomorrow", "next week", "Thanksgiving", "end of month") |
| `zone_statement` | sets, changes or redefines the zone for all times ("All times are Central Time, not Eastern Time", "Times in this RFP are Central Time", "deadlines are in Central Time", "All times are changed from Eastern Time to Central Time", "Time zone for all deadlines: Mountain", "\"ET\" in this RFP means Central Time") in a way that conflicts with a deadline's zone or rules one out. A deadline gets one conflict code however many statements there are, and at most 50 statements are listed one by one |
| `unsupported_date_form` | (any line) holds one of the screened malformed forms listed below |

What names a deadline: the deadline words "due", "deadline", "closing", "close date", "cut-off", "no later than",
"not later than", "NLT", "on or before"; "receipt of offers" (proposals, bids, quotes, responses); "time" or "date"
"for receipt"; "submission", "proposal", "offer" or "response" followed by date, time, deadline, window or period;
"period" or "window for submission"; "submit ... proposals" (offers, bids, quotes, responses); and "proposals"
(offers, bids, quotes, responses) followed within three words by a form of accept, receive, submit, deliver or "due".
A sentence without any of these is not reviewed.

It does **not** mean that every deadline or requirement in the document was found, that the extracted values are what
the agency intended, or that a submission would be timely. `--strict` is an extraction aid, not a deadline or amendment
safety gate. Read the solicitation and every amendment yourself.

## Supported scope

- Dates read: a month name first ("November 12, 2026", "Nov. 12, 2026", "November 12th, 2026", "November 12 2026"),
  day first ("12 November 2026", "12th Nov. 2026", "12 November, 2026"), `11/12/2026` (month first), `2026-11-12`,
  each with an optional weekday ("Thursday, November 12, 2026"); `11/12/26` is read and flagged as a two-digit year.
- Times read: "5:00 PM", "5 p.m.", "17:00", "17:00:30", "1700 hours", "noon"; markers such as "close of business" are
  kept and flagged. Zones read: ET/EST/EDT and the other US abbreviations, "Eastern Time" and the other US names,
  UTC/GMT with or without an offset, ISO 8601 offsets, "Z", "Zulu", IANA names, and "local time" (flagged).
- screened, and reported as unsupported date forms: `111/05/2026`,
  `5November 2026`, `November 12,2026`, `12-NOV-2026`, `11-12-2026`, `Nov-12-2026`, `03 NOV 26`,
  `November 12, 26` (not when the two-digit year is followed by a comma, a letter, a digit, `_`, a dot and a digit,
  or "and", "or", "through", "thru", "to", "&", "-" or an en dash, as in "November 3, 10 and 17", "November 12, 26,
  5:00 PM" or "November 12, 26 - 5:00 PM"), `November, 12, 2026` and `November,12,2026`, an ISO date with exactly one
  component of the wrong length (`2026-11-005`, `2026-111-05`, `20260-11-05`; not `2026-111-005`), a year-first date
  with `.` whose month (01 to 12) and day (01 to 31) have two digits each (`2026.11.12`; not `2026.13.05`), a
  year-first date with `/` whose day has two to four digits, whatever its values (`2026/11/12`, `2026/13/05` and
  `3026/11/12`, through the `111/05/2026` form), a year-first date with a one-digit month or day (`2026-11-5`,
  `2026/11/5`, `2026.1.15`) only on a line that itself contains "due", "deadline", "no later than", "not later than", "NLT",
  "closing", "closes", "close", "closed", "on or before" or "cut-off" (so not "received by 2026-11-5", and not when
  that word ends the previous line), `12.11.2026` (not directly after a letter, digit, `_` or dot), a date followed by
  more slash parts (`11/12/2026/2027`), or a letter typed for a digit as in `2O26` or `November l2, 2026`. Only these
  forms are screened, and in the ISO forms, the dotted forms and the one-digit form the year must look like 19xx or
  20xx; other forms,
  such as `12.11.26`, are not, and one of them beside a valid deadline disappears. No deadline's date or zone runs into the text after it
  (`November 5, 2026x` and `November 5, 2026_draft` are read as November 5 and flagged; `17:00:00Zdraft` and
  `UTC+05:30junk` are read as `Z` and `UTC+05:30` and flagged);
- Standard clause text that names a deadline and a time without changing it is not reviewed when it matches the
  published text exactly (case and spacing aside, including across a line wrap): FAR 52.212-1(f)(1) and
  52.215-1(c)(3)(i) (default time for receipt), 52.212-1(f)(2)(i)(A) and 52.215-1(c)(3)(ii)(A)(1) (electronic
  commerce receipt), 52.212-1(f)(4) and 52.215-1(c)(3)(iv) (emergency extension), as published on acquisition.gov
  (52.212-1 SEP 2023, 52.215-1 NOV 2021). Any other wording, an altered time, an added change or a negation is
  reviewed like any other sentence.
- Not in scope: converting zones (two notations of one moment, "17:00 UTC-4 (ET)", need review), holidays and
  business days, deadlines stated relative to another event ("30 days after award"), text that is not English,
  scanned PDFs without a text layer, and tables whose cells are split across lines in an order that separates a label
  from its date.

A change verb directly negated ("is not changed", "will not be extended", "There is no change to the closing date") is
not a change, unless the negation leaves room for one ("beyond <date>", "by more than a week", "except") or anything in
its sentence contrasts with or shifts it ("but", "instead", "only", "now", "later", "until", a ";"). Hard, paper, printed
and physical copies name a proposal submission, so a separate hard-copy deadline conflicts with the electronic one.

Known false failures (NEEDS REVIEW although nothing is wrong): the same time restated in another zone or notation
("5:00 PM ET (2:00 PM PT)", "17:00 UTC-4 (ET)"); office hours in a deadline's sentence; numbers written like a
screened date form (`Version 1.2.2026`, "In May, 12 2026 vehicles were inspected", `2026-111-05`, `JUN-12-1234`, and
on a deadline line `RFP 2026-1-05`); a validity or performance-period change in a sentence that names a deadline;
hedged, conditional or hypothetical sentences that name a deadline and use change wording ("Requests for extension
of the proposal due date will not be granted", "Proposals may be modified or withdrawn at any time before the closing
date", "The County may extend the deadline by addendum"); a zone written as "Eastern" alone, "Arizona time" or
"Atlantic Standard Time" (no zone is read); a deadline with no zone in a document whose zone statement sets one (the
statement is not applied); a four-digit time without "hours" ("by 1600 CST"); dates written in words or as
`14-JAN-2027`; a notice of intent to bid or a second round of questions read as a second deadline of the same kind; a standard clause in any wording other than the published one; and an announcement verb in a deadline's
clause ("Questions are due as communicated..." stays READ only because "as" marks a reference).

Known misses (READ although a careful reader would not act): a deadline date that has already passed (the tool does
not know today's date); a change sentence that uses none of the deadline words above; a change or new deadline written in a date form outside both lists; a change stated only by reference
("see Amendment 0003 for the new date") with no change word; and any wording this rule-based tool has not been
written for. The measured rates on the development cases and on an independent held-out set are in the release
package, not here, because they describe one evaluation, not a guarantee.

## Library

```python
from bid_deadline_check import analyze, read_document

report = analyze(read_document("solicitation.pdf"))
for d in report.deadlines:
    print(d.kind, d.date, d.time, d.timezone, d.line, d.status, d.ambiguities)
for n in report.needs_review:  # unresolved deadline sentences: line, end_line, reason, text
    print(n["reason"], n["line"], n["text"])
print(report.outcome)       # "read" or "needs_review"
rows = report.checklist()   # list of dicts: id, category, item, line, done
```

`Report.outcome` is `read` or `needs_review` (see "What `--strict` means"); `Report.needs_review` lists the
unresolved sentences. `Deadline.status` is `actionable` or `needs_review`, and `Deadline.review` gives the reasons:
its own ambiguity codes, `conflicting_<kind>`, `line_<n>:<reason>` for a review item that may change it, and
`withdrawn_<kind>` when the same kind is withdrawn elsewhere, and `unlisted_review_items` when more than 50 items
were found.

`Deadline` has `kind`, `date`, `time`, `timezone`, `line`, `text` (the clause around the date),
`end_line` and `ambiguities` (codes: `no_time`, `no_timezone`, `time_marker:<text>`, `invalid_date`,
`invalid_time`, `quoted_or_former`, `implausible_year` (outside 1900 to 2100), `weekday_mismatch`, `two_digit_year`, `negated_or_withdrawn`, `replaces_earlier_date` (the new date of an
"extended/changed/moved from ... to ..." or "... it is now <date>" amendment), `issue_date_possible` (an issue,
amendment or announcement word, such as "was publicized" or "was delivered", sits between the deadline word and the
date), `date_glued_to_text` (letters follow the date with no space, as in `2026at`), `timezone_glued_to_text`
(letters or digits follow the zone with no space, as in `17:00:00Zdraft` or `UTC+05:30junk`), `other_time:<text>` (another clock time in the same
sentence, at most five), `unread_date:<text>` (another date in a sentence with change wording that was not read as
a deadline, at most five), `after_clause`, `kind_uncertain`, `timezone_unclear` (a zone that may be cut
short or is in an unsupported form, such as `UTC+05:30:15`), `zone_invalid`, `zone_unverified`, `zone_unanchored`,
`zone_conflict:<zone>`, `statement_split_at_limit`, and
`context_truncated`, which only says the `text` excerpt was shortened and raises no warning). Each requirement is `{"text", "line", "end_line", "truncated"}`.

## Scope and limits

- It finds what is written; it does not interpret it. This is a checklist aid, not legal or
  contracting advice.
- Dates and times are reported as written. There is no timezone conversion, no daylight-saving
  validation (a winter date marked "EDT" passes), no holiday or next-business-day logic, and no
  judgement of whether a submission is on time. Numeric dates such as `10/05/2026` are not
  re-ordered; two-digit years are flagged.
- Signed UTC/GMT offsets (`UTC-04:00`), ISO offsets (`2026-11-05T17:00:00-04:00`) and IANA names
  (`America/New_York`) are kept exactly. IANA names are checked against the zone database Python finds
  (`zone_invalid`; `zone_unverified` when there is none, which is usual on Windows without the `tzdata`
  package); offsets outside UTC-12:00 to UTC+14:00 or with minutes other than 00, 15, 30 or 45 are
  `zone_invalid`. An offset followed by a fraction (`UTC+05:30.5`, `GMT+5.5`, `-04:00.5`) is not shortened:
  it is flagged `timezone_unclear`. A second, different zone written for the same time (`5:00 PM ET or CT`,
  `5:00 PM EST (Eastern Daylight Time)`) is flagged `zone_conflict`, and "local time" is `zone_unanchored`.
  Zones are compared by name, not converted, so two notations of one moment also need review.
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
  extracted per document; a warning says where extraction stopped. At most 50 unresolved sentences are listed, each with up
  to 600 characters of its source text; a warning counts the rest. Measured on macOS (arm64) for this
  candidate on inputs up to 1 MB, analysis takes up to about 3.5 s per MB of text and grows linearly
  (about 31 to 75 MB peak memory at 1 MB, including 2000 deadlines followed by zone statements). Larger inputs were not measured for this candidate; the previous
  candidate needed 456 MB and 11 s for 20 MB of dense dated text and 321 MB and 37 s for 20 MB of one-word
  lines, so a 50 MB input should be expected to need more than a gigabyte and minutes.
- PDFs over 1000 pages or over 5 million extracted characters are refused (checked between pages). By
  default PDFs are parsed in a separate Python process that is stopped after 65 s of wall-clock time
  and limited to 61 s of CPU time (or the environment's hard CPU limit, if lower); where the operating
  system allows it (normally Linux) its address space is also limited to 1 GiB. macOS does not allow
  that memory limit (measured), and Windows has no CPU limit, so there only the wall-clock stop
  applies. The worker never imports from the current directory. A worker that crashes is reported as a
  failure, not as a limit. `read_document(path, isolate=False)` parses in-process with between-page
  checks only, which do not bound a single slow page. Requires pypdf 6.21.1 or later.
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
