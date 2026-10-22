# Changelog

## 0.2.0rc7 (unreleased candidate, 2026-10-18; not published; 0.2.0rc6 and earlier are frozen)

**Breaking:** READ is allow-list based (the owner's choice B). Every sentence must be positively recognized, or it is
a review item (`not_recognized`, with a `detail`) that holds every deadline, so `--strict` exits 2 on almost every real
solicitation.

- A sentence holding a date, time or zone is recognized only if it holds one complete deadline in a fixed form whose
  label names that deadline's kind. Any other sentence is recognized only if it matches a closed whole-sentence
  template (see the last two items; the first candidate used a word list instead, which the code reviews broke and
  which is removed). Non-ASCII letters, look-alikes and invisible characters, a 12-hour time without AM or PM in a
  deadline, and sentences cut at a statement edge are not recognized. Standard FAR receipt clauses, the checked SF-30 "is not extended" line, a
  few fixed rule sentences, a matching late-receipt rule and an "All times are <zone>" statement are recognized whole.
- The 41 wordings 0.2.0rc6 recorded as read cleanly (40 in its tests, one in its release notes) are caught and are
  ordinary tests, each required to produce a review item on its own lines.
- r6's specific reasons are listed before allow-list items, overflow counts are reported separately, and a deadline
  carries one `not_recognized:N` code after its other reasons.
- Earlier test texts that read cleanly and now need review (76, see below); they are strict expected failures listed with their exact
  items in `tests/r7_false_failures.json`. `tests/conftest.py` fails one if its items change or if it also fails with
  the allow-list switched off. Their text and assertions are unchanged.
- The first code review (BLOCK) found inputs that read READ although they change the deadline; each is now a test.
- After the second code review (BLOCK) and the Two-Round Stop, the owner chose closed templates: a plain sentence is
  recognized only if it matches one of a short list of whole-sentence templates (page limits, submission method,
  questions, format, identification, volume list, headings). The open vocabulary is removed. Addresses are an email
  address or a bare host name with no digit, path or listed stem; a bare "Due date:" label is not a proposal deadline;
  ASCII control characters and line separators other than newline and carriage return are reviewed; only "or" may
  follow a standard clause. The second review's inputs are tests; 76 earlier test texts are listed false failures.
- After the third code review (BLOCK) and the owner's approval of one more corrective round (source prepared, not yet
  tested or reviewed): proposal labels and kind nouns are only proposals, offers, quotes, quotations and bids
  ("responses", "submissions", "applications" and a bare "Closing date:" are not); "will be" is not in the deadline
  forms ("must be delivered" still is); "Price", "Past Performance", "Technical Approach" and volume lines are no longer templates;
  headings and the volume-list opener count only as a whole statement; omission marks ("...", "[...]", "* * *") and
  literal template slots ("<A>", "<D>", "<T>", "<Z>") are not recognized; a punctuation-only sentence is recognized
  only as a table or separator rule; characters are checked on each raw line before whitespace is collapsed or
  zero-width characters removed (so U+001F, Unicode spaces and zero-width characters are reviewed). The third
  review's inputs are regression tests.

## 0.2.0rc6 (unreleased candidate, 2026-10-17; not published; 0.2.0rc5 and earlier were audited and are frozen)

**Breaking:** every report has an `outcome` (`read` or `needs_review`) and a `needs_review` list; deadlines carry
`status` and `review`; `--strict` exits 2 unless the outcome is READ, so it fails on more documents; text output
starts with an `OUTCOME:` line.

- R5-DL-UNSAFE: a sentence that names a deadline and changes, cancels, suspends, negates or defers it, or gives a
  time or date this tool does not read, is no longer silently ignored when an earlier cutoff was recognized. It is
  listed for review with its exact source text and a reason code, and every deadline it may change is marked not
  actionable as stated. Covers imperative changes ("Alter the closing time"), "reopens", relative shifts ("one week
  later than stated"), checked SF-30 boxes, TBD, "until further notice", "proposals will be accepted until",
  `2026.11.5`, `20261112` and `2026 11 12`.
- Zones: IANA names are checked against the zone database (`zone_invalid`, `zone_unverified`); offsets outside
  UTC-12:00 to UTC+14:00 or with odd minutes are invalid; a second zone for one time is `zone_conflict`; "local
  time" is `zone_unanchored`; a statement setting the zone for all times is reviewed against each deadline.
- Dates: a written weekday that does not match the date and years outside 1900 to 2100 are flagged; "was
  publicized", "were notified" and similar announcement wording before a date is `issue_date_possible`.
- Unchanged FAR 52.212-1 and 52.215-1 receipt clauses are not reviewed when they match the published text exactly;
  any alteration is reviewed.
- Second change, informed by the one run of the first held-out set on the first r6 commit (so that set is no longer
  independent for this change): a cancelled, withdrawn, paused or draft solicitation holds every deadline
  (`solicitation_cancelled_or_draft`); corrections ("should read", "is corrected to") are reviewed; "on hold", "paused",
  TBA schedules and TBD table rows are reviewed; a deadline quoted from or labeled as an earlier text is
  `quoted_or_former`; a time paired with another zone before the date is `other_time`; zone statements that change the
  zone or use "Time zone for all deadlines:" are read; a kind withdrawn in one place holds the same cutoff elsewhere;
  generic deadline words in a review item hold the proposal deadline; hard copies name a proposal submission. A
  directly negated change verb was no longer a change (removed again later in this release), and more page-limit
  phrasings are read.
- Independent review round 1 (BLOCK) fixes: a dated change of no known kind ("The deadline is extended to <date>",
  "New date:", "extends it to", "Last day to submit:") is read as a proposal deadline of uncertain kind; solicitation
  cancellation is no longer hidden by a month named May, "could" or "No."; a negated change that its sentence
  contrasts or shifts is a change again (a regression in the second change); zone statements are compared with every
  deadline at once (memory had grown with statements times deadlines); label, status, pending, N/A, "no longer
  accepted", schedule-wide changes (`schedule_changed`), pronoun and bare changes, holidays and weekday words, former
  and quoted dates, paired and earlier times, more zone statement forms, abbreviated weekdays and a stated emergency
  are reviewed.
- Independent review round 2 (BLOCK) fixes: extra time granted ("given three additional days"), a negated date ("is no
  longer <date>"), cancellation without a determiner and "Cancellation of Solicitation ...", "not accepted" without a
  lateness or method qualifier (and no longer held when an adjective such as "Late" or "Faxed" names only some
  proposals), zone redefinitions with "mean" and commas, zone statements that give an example time, "now have until
  <date>", "call" no longer an event, the exact FAR emergency clause and the wrapped default-time clause read cleanly.
  32 further reviewer wordings still read cleanly (40 after the review of the final delta); after two corrective rounds they are recorded as known misses
  (strict expected failures in tests/test_r6_review_round2.py), not waived.
- The negated-change exemption added in the second change is removed: with the real change in the next sentence
  ("The proposal due date will not be extended. Offerors have an additional week.") it made a case read cleanly that
  rc5 and the first r6 commit caught. Negated changes need review again (false failures, on purpose).
- Review of the final delta: three narrowings in the round-2 fixes are undone because they lost cases 21e9ca1 caught
  ("processes resume" without a date after a FAR emergency clause; "Electronic and paper proposals will no longer be
  accepted"; "local time" dropped from every zone statement). An unaltered standard clause is not read as a zone
  statement. Eight further wordings that read cleanly ("will not be accepted by any means", "is no longer 5:00 PM ET on
  <date>") are recorded as known misses, now 40.
- Evaluation: the development cases used while writing this change are frozen with labels, reasons and sources,
  and an independently prepared held-out set was sealed before any run, then a second one before the final run; results
  are in the release package. The
  earlier candidates were tuned on the cases they were evaluated on, and this candidate was developed on the
  development set, so its development results are not an independent measure.

## 0.2.0rc5 (unreleased candidate, 2026-10-17; not published; 0.2.0rc1 of 2026-10-16 and 0.2.0rc2 to 0.2.0rc4 of 2026-10-17 were the independently audited candidates)

**Breaking:** deadline extraction output changes (more deadlines, new kinds `registration` and
`revised_proposal_due`, new `Deadline.end_line` and `Deadline.ambiguities`, `text` is now the clause around the
date), `--strict` fails on more unresolved cases, requirements carry `end_line` and `truncated`, Python 3.10 or
later is required, and the PDF extra needs pypdf 6.21.1 or later.

- BD-1: each date is bound only to the time and timezone written with it in the same clause. Issue dates, briefing
  times and the next line's event are never borrowed; several deadlines on one line are all reported.
- BD-2: signed UTC/GMT offsets, ISO 8601 offsets and IANA zone names are preserved exactly; AM/PM must end at a
  token boundary (`17:00 America/New_York` is no longer `17:00 Am`).
- BD-3: EOD, midnight, close of business and `12:00 AM` are kept as written and flagged; no hour is invented.
  Impossible dates and clock times, two-digit years, negated or withdrawn deadlines, missing times and conflicting
  values of one deadline kind are flagged. `--strict` exit 0 now has a documented meaning (README).
- BD-4: requirement sentences wrapped across lines are joined; sentences are no longer split at abbreviations or
  inside numbers like `52.212-1`; requirements up to 1000 characters are kept whole and longer ones are reported as
  flagged excerpts with source lines instead of being cut or dropped.
- BD-5: pypdf floor raised to 6.21.0 (6.21.1 since 0.2.0rc5, GHSA-5hx5-vpf9-5wcv). PDFs are parsed by default in a separate process with a wall-clock stop, a
  CPU-time limit and, where the OS allows it, a memory limit. `read_document(path, isolate=False)` keeps the old
  in-process behavior.
- A missing or unreadable input file is a one-line error (exit 1) instead of a traceback; text containing U+FFFD
  replacement characters is flagged.
- Build and test inputs are hash-pinned in `requirements/`; CI matrix restored for Python 3.10/3.12/3.14 on Linux
  and 3.14 on macOS.
- Local verification of this candidate (2026-10-16): CPython 3.10, 3.11, 3.12 and 3.14 on macOS (arm64), from source
  and from the built wheel. Python 3.13, Linux and Windows were not run; no hosted CI run exists for it.
- Independent review fixes: a date followed by "is no longer in effect", "is suspended", "is hereby removed",
  "has been extended" and similar is flagged `negated_or_withdrawn`, while "unless cancelled" and "are not due until"
  are not; kind words match whole words and a submission outranks a context word ("registered in SAM.gov",
  "industry day"), so an amended due date is no longer hidden under another kind; a capitals label or a sentence on
  the line above a date labels it again (cover pages, SF-1449 block 8); a date-only line ends its statement; a
  requirement interrupted by a list item or heading is flagged; "received after <date>" is reported with
  `after_clause`; "12 noon", "hrs", "prevailing", "sharp", ranges, "Due Time:", dashes, slashes, pipes and
  "on or before" no longer break time or zone binding; "FEBRUARY 31ST" is flagged; duplicates written in different
  formats ("11/05/2026", "ET" / "Eastern Time") are one deadline; "Mt." is not a zone and "America/New York" is
  flagged; `context_truncated` no longer warns; deadlines and requirements are capped per document and extraction
  is lazy (5 MB of dated text: 98 MB and 2.4 s, was about 600 MB and 10.5 s); the PDF worker adopts a lower hard
  CPU limit and never imports from the current directory.
- Independent re-audit fixes (2026-10-17): an "extended/changed/moved/postponed from <old> to <new>" or "<old> is
  extended to <new>" amendment reports both dates, the old one `negated_or_withdrawn` and the new one
  `replaces_earlier_date` (RBD-1); another clock time in a deadline's sentence ("changed to 6:00 PM ET", "3:00 PM ET
  for hand delivery", after a semicolon) is recorded as `other_time:<text>` and warns (RBD-2); duplicate comparison
  includes seconds (RBD-3); an obligation interrupted by a colon-led list or a blank line is flagged as an excerpt
  (RBD-4); dates and zones must be whole tokens, so `111/05/2026`, `20260`, `UTC+05:300` and four-part IANA names
  are flagged instead of shortened into valid-looking values (RBD-5). A later date in a triggered clause that has
  its own time is reported (for example a hand-carried-copy cutoff in parentheses).
- r2 review fixes (kofi, 2026-10-17): an amendment with the time written before each date ("from 5:00 PM ET on
  November 5, 2026 to 5:00 PM ET on November 12, 2026") reports both dates, and a date with no time of its own no
  longer borrows the next date's zone (KR2-01); "is extended to <date>" and "is changed to read: <date>" mark a
  replacement even when no earlier date is in the sentence (KR2-07); `noon`, `1700 hours` and `5:00 PM` again compare
  equal to the clock forms (KR2-02, a regression in the first r2 commit); a heading followed by a blank line no longer
  makes the next requirement an excerpt: a blank line is a cut only after an obligation, a comma or a word that
  cannot end a sentence (KR2-03); a restated equal time and an "NNN hours" duration are not other times (KR2-04); a
  dated event admitted only by its own time is reported as `other` with `kind_uncertain` instead of inheriting the
  deadline's kind, and a leading label is no longer read through the colon of "5:00" (KR2-05); date boundaries look
  only at digits, so a date glued to a word is read again, and "5th November 2026" is read (KR2-06, KR2-09);
  date-like warnings are capped at 50 plus a count (KR2-08). The README lists known strict false positives.
- Final verification residuals (kofi, 2026-10-17): "extended to <date>" with no earlier date is a replacement only
  when the sentence names a date, time, receipt, deadline, submission, solicitation, Q&A or any deadline kind word
  ("the question period is extended to ..." warns; "the period of performance may be extended to ..." does not), and
  "this amendment extends ... to <date>" is no longer skipped as an issuance date (pre-existing); "changed to read as follows:" is recognized; a clock time after "for" or "within" is an
  other time again (only a three-digit hours form is treated as a duration); a time-less date keeps a zone written
  after "prevailing" or "local".
- r2 audit fixes (2026-10-17, pre-existing on rc1 and rc2): "changed from the current date of <old> to <new>",
  "the extension of the due date from <old> to <new>" and "was previously <old>; it is now <new>" report both
  dates (R2-DL-1), and any other date in a sentence with change wording that is not read as a deadline is named as
  `unread_date:<text>` and warns; a date written after an issue or amendment word that follows the deadline words
  ("the proposal due date was issued <date>") is flagged `issue_date_possible` (R2-DL-2); fractional seconds compare
  without trailing zeros (R2-DL-3); a date glued to letters ("November 5, 2026oops") is still read but flagged
  `date_glued_to_text` (R2-DL-4), and a digit glued to a month name or a year typed with a letter is reported as a
  date-like value;
  a clause with change wording, a deadline word and a time but no date warns (it may also fire beside a dated
  deadline, as in "; revised proposals at 6:00 PM ET").
- r3 review fixes (kofi, 2026-10-17): the dateless-time check is replaced by a fail-closed clause check: a clause
  that names a deadline and uses change wording, with no date read as a replacement, warns, so a revision with no
  readable date, a new date in the next sentence or an unread form, and time-only changes ("vice", "in place of",
  ", not 5:00 PM ET", "on the original due date", "shifts to") fail `--strict`; "Proposal due date from <old> to
  <new>" and "FROM: ... TO: ..." with no verb, "extended until", "slipped to" and "shifts from ... to" are read as
  amendments; "previously", "now" and "(was ...)" mark dates only when they lead directly to them, so "As previously
  announced, proposals are due" and "now accepting proposals due by" read cleanly; the FAR late-receipt sentence no
  longer warns; "now <date>" takes a kind only from its own sentence and the check is linear again (it was quadratic
  on long sentences, new in this candidate); issue words "sent", "distributed", "announced", "went out" and others
  flag a possible issue date, but "signed and dated" does not; a date after "effective" in a change sentence is
  named as an unread date; fractions are read in non-ISO times and with a decimal comma; more date-like forms are
  reported (`November 12,2026`, `12-NOV-2026`, `11-12-2026`, `03 NOV 26`, letters for digits), and a date followed
  by `_` is flagged; a digit glued to a month name inside a part number is no longer reported.
- r3 second review round (kofi): the dateless-time check is restored beside the clause check (verb forms of change
  words or "now", a deadline word and a clock time, no date), so "Proposals must now be received by 3:00 PM ET" and
  "The closing hour is changed to 3:00 PM ET" fail `--strict` again; "will now be accepted until <date>" is a
  replacement again; a letter-for-digit pattern that rescanned long runs of dashes is bounded (it was quadratic, new
  in this candidate). The README lists the revision forms both checks still miss and the hedged sentences they flag.
- r3 audit fixes (2026-10-17): verb forms of alter, adjust, accelerate, revoke, rescind and suspend, "slid",
  "slide", "slides" or "sliding" before a shift ("slides two weeks", "slides back"), and "brought/brings ...
  forward" are change words, so "The closing time is altered to 3:00 PM ET." beside an old cutoff fails
  `--strict` (R3-DL-1); announcement wording between a deadline word and a date ("was publicized", "notice ... was
  delivered", "was communicated", "was made public", and after the r4 review also conveyed, disclosed, notified,
  provided, shared and faxed, in the past passive only) flags `issue_date_possible` (R3-DL-2); a zone followed by a letter,
  digit or `_` (`17:00:00Zdraft`, `UTC+05:30junk`) is flagged with the new code `timezone_glued_to_text`
  (R3-DL-3). A test fixture now uses a synthetic address.
- r4 audit fixes (2026-10-17): a day-first ordinal date is checked against the calendar ("31st February 2026" is
  `invalid_date`), and an extracted date that cannot be checked fails closed (R4-DL-1); more malformed forms of the
  supported dates are reported as date-like values (`2026-11-005`, `20260-11-05`, `2026/11/12`, `12.11.2026`,
  `11/12/2026/2027`, `November 12, 26`, `November, 12, 2026`) (R4-DL-2); a UTC/GMT or ISO offset followed by a
  fraction is flagged `timezone_unclear` instead of being shortened (R4-DL-3). The pdf and dev extras need pypdf
  6.21.1 or later, the first release with the fix for GHSA-5hx5-vpf9-5wcv; this tool's text path does not reach the
  affected image conversion (R4-SC-01). README says only the first zone written for a time is read and that
  `--strict` is an extraction aid, not a safety gate. After the internal r5 review (KR5-01..05): the new malformed forms report fewer
  solicitation, bid, version and paragraph numbers and lists of days (an ISO form needs exactly one component of the
  wrong length, year-first forms a two-digit month and day, or one of the listed deadline words on the same line for a
  one-digit one); README lists the numbers still reported and the forms no longer screened;
  "12 November, 2026" is read as a date, and "November,12,2026", "Nov-12-2026" and a date followed by more slash parts
  are reported; a month name matched only by case folding ("ſeptember") is `invalid_date` instead of raising; a zone
  name followed by a fraction ("Etc/GMT+5.5") is `timezone_unclear`.
