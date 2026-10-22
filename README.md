# bid-deadline-check

Read a government solicitation (RFP, RFQ, IFB; PDF or text) and get back:

- **Deadlines** with date, time and **timezone exactly as written**: questions due, proposal due,
  revised/final proposals, registration, site visit, intent to bid, orals. Each date is bound only to
  the time and zone written with it, several deadlines on one line are all kept, and anything
  unresolved (no time, no zone, "EOD", "midnight", an impossible date, a date described as withdrawn,
  cancelled, superseded or no longer in effect, a date taken from a "received after" clause) is flagged
- An **outcome**, READ or NEEDS REVIEW. READ is allow-list based: every sentence must be in a form this tool
  recognizes. Each sentence that is not, and each sentence about a deadline that could not be resolved (a change with
  no new date read, a cancellation, TBD, a date form it does not read), is listed with its exact text and a reason,
  and the deadlines it may change are marked not actionable as stated
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

Abridged example output (from `tests/fixtures/rfp_sample.txt`, a synthetic RFP; most sentences of a real solicitation
are outside the recognized forms, so NEEDS REVIEW is the normal result). It was produced by an earlier 0.2.0rc7 build;
the counts and `detail` texts of the current candidate differ and are to be regenerated with the command above:

```
OUTCOME: NEEDS REVIEW (8 sentence(s) to review, 11 warning(s))
NEEDS REVIEW (read these in the source)
  ? [not_recognized] line 1: SOLICITATION NO. EXAMPLE-26-R-0001 (SYNTHETIC SAMPLE)  (not recognized: SYNTHETIC)
  ...
  ? [not_recognized] line 8: L.3 A pre-proposal conference (site visit) will be held 10/27/2026 at 10:00 AM local time; registration is due by 10/23/2026.  (not recognized: a deadline that is not complete)
  ...
  ? [not_recognized] line 21: The Government will evaluate proposals in accordance with Section M.  (not recognized: evaluate)
DEADLINES
  [questions_due] October 20, 2026 2:00 PM Eastern Time  (line 6)  NOT ACTIONABLE AS STATED: needs review
  [proposal_due] November 5, 2026 11:00 AM EDT  (line 7)  NOT ACTIONABLE AS STATED: needs review
  [site_visit] 10/27/2026 10:00 AM local time  (line 8)  CHECK: zone_unanchored  NOT ACTIONABLE AS STATED: needs review
  [registration] 10/23/2026 (no time) (no timezone)  (line 8)  CHECK: no_time  NOT ACTIONABLE AS STATED: needs review
PAGE LIMITS
...
```

## What `--strict` means

Every run reports an outcome: **READ** or **NEEDS REVIEW** (`outcome` in JSON, the first line of text output).
`--strict` exits 2 unless the outcome is READ, and 1 when the input cannot be read.

Since 0.2.0rc7, READ is **allow-list based**: every sentence of the input must be positively recognized (next
section), and in addition none of the checks below may fire. An unrecognized sentence is a review item with reason
`not_recognized`, its exact text and a `detail` saying what is not recognized (for most sentences, the sentence as it
was compared with the templates; otherwise the character, marker or deadline problem found), and it
holds **every** deadline, because the tool cannot tell which deadline it changes. The cost is deliberate: almost any
real solicitation, and most ordinary prose, needs review. READ is meant for short, plainly written deadline notices in
the supported forms; on anything else, NEEDS REVIEW is the expected result and says only that a person must read it.

### Recognized sentences (the allow-list)

A sentence is recognized only if one of these holds:

- it is, whole, an unaltered standard clause (below), the SF-30 Block 11 line checked "[X] is not extended", or one of
  the fixed rule sentences "Late (Oral, Verbal, Faxed, Facsimile, Telephonic, Telephone) proposals (offers, bids,
  quotes, quotations) will (shall) not be accepted (considered).", "No proposals
  will be accepted by fax (facsimile, telephone).", "The Government reserves the right to cancel this solicitation."
  and "The Government may cancel this solicitation at any time.";
- it is a late-receipt rule, whole, whose time equals that of a complete proposal deadline in the same statement,
  and whose zone, when it states one, equals that deadline's zone ("Proposals due November 5, 2026 at 5:00 PM ET; proposals received after 5:00 PM ET will be rejected."; on
  a line of its own it needs review);
- it holds exactly one complete deadline (date, time and zone, nothing flagged) and, with that date, time and zone in
  place, is one of these forms, with a label that names that deadline's own kind: "<label> <when>." or "<label>:
  <when>" (also with "|" or "-" after the label), "<label> are (is, must be, shall be) due (submitted, received, delivered)
  [electronically | via email] [to <address>] [no later than | not later than | NLT | on or before | by | on] <when>.",
  "Offerors (quoters, vendors, bidders, respondents) must (shall) submit [their | all] <label> ... <when>.", a table
  row "| <label> | <date> | <time zone> |", a capitals label above a date line, and, for the proposal deadline, "[This]
  RFQ (RFP, IFB, solicitation) closes [on] <when>." For the proposal deadline <label> is proposal(s), offer(s),
  quote(s), quotation(s) or bid(s), optionally followed by "due date", "due", "deadline", "closing date" or "submission
  deadline", with an optional "the"; for questions, question(s), inquiry or inquiries; for the other kinds, their own
  names (site visit, pre-proposal conference, oral presentations, registration, notice of intent, final proposal
  revisions, BAFO, FPR, revised proposals). "Responses", "submissions", "applications" and a bare "Closing date:" or
  "Due date:" are not labels: they also name answers to questions, questionnaire returns and other events. Here <when> is the date with its time and zone in the usual orders (", at, @, |, -, /"
  between them; "hrs", "hours", "sharp" or "prevailing" before the zone; the zone repeated in parentheses; an ISO 8601
  date-time). Nothing else may remain in the sentence: no second date or time, no other zone, no "or", no lot. A
  deadline sentence is not subject to the lower-case and joining-word rule below (its form is fixed whole, and no form
  begins with a joining word);
- it is a zone statement "All times (in this solicitation) are <zone>." (r6 compares it with every deadline's zone);
- it has no date, time, zone or date-like value, does not begin in lower case or with a joining or condition word
  ("or", "and", "but", "if", "unless", ...), and, with a leading list marker set aside, matches one of these templates
  whole (case aside; `core.PLAIN_FORMS` and `core.LIST_FORMS`):
  - page limits: "<subject> shall (must) not exceed <n> pages.", "<subject> is (are) limited to <n> pages.",
    "<subject> page limit: <n> pages", where the subject is a proposal, volume, response, narrative or approach
    (optionally technical, price, cost, management, past performance or staffing) or "Volume I" to "Volume X" (or 1
    to 10) with an optional title, and <n> is a number of 1 to 3 digits, or one of the words one to twelve, fifteen,
    twenty, twenty-five, thirty, forty and fifty, with an optional "(1 to 3 digits)";
  - submission: "<proposals> shall (must) be submitted electronically (by email, via email) [to <address> | to the
    contracting officer [at <address>]].", "... be submitted in PDF format (as a single PDF file) [by email].", "... be
    submitted through <address>.", "Submit <proposals> [by email] to <address>.", "The technical (price, cost,
    management, past performance) proposal (volume) shall be submitted in (as) Volume <n>.", "All proposals shall
    (must) be received by the [proposal] deadline (due date, closing date).";
  - questions: "Questions shall (must) be submitted by email (via email, in writing) [to <address> | to the
    contracting officer [at <address>]].", "Questions shall (must) be directed to the contracting officer [at
    <address>].", "The offeror shall direct all questions to the point of contact.";
  - format: "Pages shall be 8.5 x 11 inches [with 1-inch margins].", "Text shall use [12-point] Times New Roman (Arial,
    Calibri) font[, single-spaced].", and "The offeror shall include its UEI and CAGE code on the cover page.";
  - headings and the volume-list opener, only as a whole statement (a line of their own, never beside another
    sentence): "The proposal (offer, quote) shall consist of the following volumes:", "Section A" to "Section M"
    (optionally "- Instructions to Offerors" or "- Evaluation Factors [for Award]"), "Instructions to Offerors",
    "Evaluation Factors", "Table of Contents", "Introduction", "Scope", "Submission Instructions", "Proposal Format".
    Headings that limit what follows to one part of the proposal ("Price", "Past Performance", "Technical Approach",
    "Volume II", "Volume II - Price") are not templates: a document that has one needs review.

  Here <proposals> is proposals, offers, quotes, quotations or bids (with an optional "all" or "the"), and
  <address> an email address or a bare host name (an optional "https://" or "www.", a name ending in .gov, .mil,
  .com, .org, .net or .us, and an optional "/"), with no digit, no path or query, and none of these stems anywhere
  inside it: time words (due, date, late, early, after, before, until, next, last, week, day, month, year, hour, time,
  now, ...), status and change words (cancel, void, extend, amend, amdt, postpon, clos, open, new, revis, chang, hold,
  pause, tbd, not, no, only, except, if, ...), event words (oral, present, visit, conferen, meet, award, notice, brief,
  ...) and month abbreviations (`core.ADDRESS_STEMS` has the full list). A volume or section and its title may be
  separated by "-", ":", an en dash or an em dash.
- it is punctuation only and a table or separator rule ("---", "|---|---|"); other punctuation-only sentences
  ("( )", "* * *") need review.

There is no open vocabulary: the two code reviews of an earlier vocabulary-based version showed that ordinary words
could still move or qualify a submission ("Proposals shall be submitted with the questions.", "Proposals shall be
submitted at the presentation."), so the owner chose this closed list. A template with any word changed or added needs
review. Also unrecognized: a mark of omitted or struck text ("...", an ellipsis character, "[...]", "* * *") or a
literal template slot ("<A>", "<D>", "<T>", "<Z>") anywhere in a sentence; and, checked on each raw line before any
whitespace is collapsed or zero-width character removed, any non-ASCII character other than U+2018, U+2019, U+201C,
U+201D (typographic quotes), U+2013, U+2014 (en and em dash), U+2022, U+25CF, U+25AA (bullets), U+2026 (ellipsis,
itself an omission mark), U+00A7 (section sign), U+2713, U+2714 and U+2612 (check marks), which covers other scripts,
full-width and look-alike letters, Unicode spaces (U+00A0, U+1680, U+3000, ...), zero-width characters (U+200B to
U+200D, U+2060, a U+FEFF byte-order mark) and invisible format characters; an ASCII control character other than tab
(U+0000 to U+001F, including U+001F); a line separator other than a newline or carriage return
(`\x0b`, `\x0c`, `\x1c` to `\x1e`, U+0085, U+2028, U+2029: the line it ends is reviewed); a 12-hour clock time without AM or PM in a deadline ("5:00 ET"); and a sentence
at the edge of a statement cut by a size bound or by an interrupting list or heading line, unless it is a heading or
the volume-list opener standing as a whole statement and the cut is not a size bound. After an unaltered standard clause that ends "; or", that "or" alone is recognized.

The checks that still give their own reasons:

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
| `change_not_read` | changes it (a change verb, negated or not, "shortened", "waived", an imperative such as "Alter the closing time" or "Disregard the proposal due date", "reopens", "is now", "one week later than stated", a checked SF-30 "[X] is extended") with no replacement date read; also any sentence that corrects an earlier text ("should read", "is corrected to", "typographical error") and gives a date or time, a "New date:" label or "extends it to <date>", a change whose subject is only a pronoun ("It is extended one week"), a sentence that begins with the change ("extended by one week." after a blank line, "(Postponed.)"), and a stated interruption or emergency that triggers the FAR emergency extension |
| `deadline_cancelled_or_suspended` | cancels, withdraws, rescinds, revokes, suspends or postpones it |
| `deadline_to_be_determined` | says it is TBD, T.B.D., to be determined, pending, N/A or will be set later (also in a table row, "Revised Proposal Due \| TBD"); also any sentence saying the schedule, timeline or dates are TBD or TBA |
| `deadline_negated` | says it is no longer due, no longer applies, or that proposals are no longer (or not) accepted or required, or that no proposals will be accepted. Not counted: a qualifier right after it ("after", "later than", "past", "beyond", "before", "by", "through", "via", "unless", "if", "in paper", "electronically"), which over-matches ("by any means" is missed), or an adjective right before the noun that names only some proposals ("Late", "Oral", "Faxed", "Unsigned", "Incomplete"; not after "and" or "or") |
| `time_without_date` | gives a clock time but no date that was read (a restatement of a time already read in the same statement is not one) |
| `date_not_read_as_deadline` | contains a date that was not read as a deadline and is not an issue date |
| `unread_date_value` | contains a date-like value this tool does not read ("2026.11.5", "20261112", "2026 11 12", "Friday", "tomorrow", "next week", "Thanksgiving", "end of month") |
| `zone_statement` | sets, changes or redefines the zone for all times ("All times are Central Time, not Eastern Time", "Times in this RFP are Central Time", "deadlines are in Central Time", "All times are changed from Eastern Time to Central Time", "Time zone for all deadlines: Mountain", "\"ET\" in this RFP means Central Time") in a way that conflicts with a deadline's zone or rules one out. A deadline gets one conflict code however many statements there are, and at most 50 statements are listed one by one |
| `unsupported_date_form` | (any line) holds one of the screened malformed forms listed below |
| `not_recognized` | (any sentence, since 0.2.0rc7) is not one of the recognized forms above; `detail` says what is not recognized (usually the sentence as compared with the templates); every deadline is held, and each deadline carries one `not_recognized:N` code after its other reasons |

What names a deadline: the deadline words "due", "deadline", "closing", "close date", "cut-off", "no later than",
"not later than", "NLT", "on or before"; "receipt of offers" (proposals, bids, quotes, responses); "time" or "date"
"for receipt"; "submission", "proposal", "offer" or "response" followed by date, time, deadline, window or period;
"period" or "window for submission"; "submit ... proposals" (offers, bids, quotes, responses); and "proposals"
(offers, bids, quotes, responses) followed within three words by a form of accept, receive, submit, deliver or "due".
A sentence without any of these is not reviewed.

Every sentence is also checked against the allow-list above, whether or not it uses any of these words.

READ does **not** mean that every deadline or requirement in the document was found, that the extracted values are
what the agency intended, that the input is the whole solicitation with every amendment, or that a submission would be
timely. With the allow-list, READ is defensible only for input written entirely in the supported forms; the remaining
gaps are listed under "Known misses". Read the solicitation and every amendment yourself.

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

A change verb counts even when it is negated ("The proposal due date is not changed." needs review): an exemption for
negated changes was tried in this release and removed, because it could not be made safe when the real change is in the
next sentence ("... will not be extended. Offerors have an additional week."). Hard, paper, printed and physical copies
name a proposal submission, so a separate hard-copy deadline conflicts with the electronic one.

Known false failures (NEEDS REVIEW although nothing is wrong). Since 0.2.0rc7, every sentence outside the supported
forms, which is most ordinary prose: numbers written as words ("three volumes"), names ("Point of Contact: Jane Doe"),
counts ("5 copies"), "As amended, proposals are due ...", "As previously announced, ...", periods of performance,
award dates, office hours, version numbers, a label on one line with its date on the next sentence, and any plain
sentence that is not one of the templates. 76 earlier test texts that read cleanly before now need review; each is listed, with the exact
item it now produces, in `tests/r7_false_failures.json`. Also, from earlier releases: the same time restated in another zone or notation
("5:00 PM ET (2:00 PM PT)", "17:00 UTC-4 (ET)"); office hours in a deadline's sentence; numbers written like a
screened date form (`Version 1.2.2026`, "In May, 12 2026 vehicles were inspected", `2026-111-05`, `JUN-12-1234`, and
on a deadline line `RFP 2026-1-05`); a validity or performance-period change in a sentence that names a deadline; a negated change ("The proposal due date
is not changed.", "will not be extended for traffic delays");
hedged, conditional or hypothetical sentences that name a deadline and use change wording ("Requests for extension
of the proposal due date will not be granted", "Proposals may be modified or withdrawn at any time before the closing
date", "The County may extend the deadline by addendum"); a zone written as "Eastern" alone, "Arizona time" or
"Atlantic Standard Time" (no zone is read); a deadline with no zone in a document whose zone statement sets one (the
statement is not applied); a four-digit time without "hours" ("by 1600 CST"); dates written in words or as
`14-JAN-2027`; a notice of intent to bid or a second round of questions read as a second deadline of the same kind; a standard clause in any wording other than the published one; and an announcement verb in a deadline's
clause ("Questions are due as communicated..." stays READ only because "as" marks a reference).

Known misses (READ although a careful reader would not act). The 41 wordings that 0.2.0rc6 recorded as read cleanly
("The date above is no longer valid.", "Amendment 0002 grants a two-week extension.", "This RFP is no longer active.",
"Time Zone: Central", ...) are now caught and are ordinary tests. What the allow-list cannot see: a deadline date that
has already passed (the tool does not know today's date); an amendment that is not in the input; a supported-form
deadline that is itself wrong; and a change written entirely in the recognized forms above. The forms were reviewed
one by one and attacked in code review; every input found is now a test, and further ones may exist. The measured
rates on the development cases and on the
independent held-out sets are in the release package, not here, because they describe one evaluation, not a
guarantee.

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
  candidate on inputs up to 1 MB, analysis grows linearly and takes up to about 6 s per MB of text, with up to
  about 180 MB peak memory at 1 MB (the slowest and largest shapes found in review: a dense run of numbers; 2000
  deadlines followed by zone statements took 2.2 s and 58 to 75 MB). Larger inputs were not measured for this candidate; the previous
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
