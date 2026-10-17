# Changelog

## 0.2.0rc3 (unreleased candidate, 2026-10-17; not published; 0.2.0rc1 of 2026-10-16 and 0.2.0rc2 of 2026-10-17 were the independently audited candidates)

**Breaking:** deadline extraction output changes (more deadlines, new kinds `registration` and
`revised_proposal_due`, new `Deadline.end_line` and `Deadline.ambiguities`, `text` is now the clause around the
date), `--strict` fails on more unresolved cases, requirements carry `end_line` and `truncated`, Python 3.10 or
later is required, and the PDF extra needs pypdf 6.21.0 or later.

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
- BD-5: pypdf floor raised to 6.21.0. PDFs are parsed by default in a separate process with a wall-clock stop, a
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
  without trailing zeros (R2-DL-3); a date glued to letters ("November 5, 2026oops"), a digit glued to a month name
  and a year typed with a letter are reported as date-like values instead of being read as clean dates (R2-DL-4);
  a clause with change wording, a deadline word and a time but no date warns (it may also fire beside a dated
  deadline, as in "; revised proposals at 6:00 PM ET").
