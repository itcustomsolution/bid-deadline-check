# Changelog

## 0.2.0rc1 (unreleased candidate, 2026-10-16; not published)

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
