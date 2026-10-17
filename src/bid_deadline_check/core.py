"""Rule-based extraction. No network, no LLM."""
from __future__ import annotations

import bisect
import calendar
import functools
import itertools
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

MONTHS = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
# A date's numbers must be whole: "111/05/2026" or "November 5, 20260" is not shortened into a valid-looking date.
# A date starts after a non-letter, non-digit, non-slash character, or glued to a word as a capital after a lowercase
# letter ("onNovember 5") or as a digit after a letter ("due11/05/2026"), or as the second ISO date of an interval
# ("2027-01-01/2027-06-30"). One gate in front of every form keeps the pattern from trying each month name inside
# each word.
_DATE_GATE = r"(?:(?<![A-Za-z\d/])|(?-i:(?<=[a-z])(?=[A-Z]))|(?<=[A-Za-z])(?=\d)|(?<=\d/)(?=\d{4}-))"  # last: ISO interval end
_NAMED_DATE = rf"{MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}|\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTHS}\s+\d{{4}}"
# A date running into letters ("November 5, 2026oops") is still read; the deadline is flagged date_glued_to_text.
DATE = (
    rf"{_DATE_GATE}(?:(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,?\s+)?"
    rf"(?:{_NAMED_DATE}|\d{{1,2}}/\d{{1,2}}/\d{{2,4}}(?!/)|\d{{4}}-\d{{2}}-\d{{2}})(?!\d)"
)
# Date-like tokens in an unsupported form are reported instead of silently skipped: too many digits, a digit glued to
# a month name ("5November 2026", "November5, 2026", "November 12th2026"), no space after the comma ("November 12,2026"),
# a letter typed for a digit ("2O26", "November l2, 2026", "11/O3/2026", "2O26-11-03"), dashed forms ("12-NOV-2026",
# "11-12-2026") and a two-digit year after a month name ("03 NOV 26").
_LETTER_YEAR = r"(?=[\dOoIl]{4}(?![A-Za-z\d]))(?!\d{4})[\dOoIl]{4}"
_HAS_LETTER = r"(?=[\dOoIl/\-]{0,9}[OoIl])"  # a letter within the token's ten characters; bounded, so runs stay linear
MALFORMED_DATE = (
    rf"{_DATE_GATE}(?:(?:\d{{3,}}/\d{{1,2}}/\d{{2,4}}|\d{{1,2}}/\d{{3,}}/\d{{2,4}}|\d{{1,2}}/\d{{1,2}}/\d{{5,}}"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTHS}\s+\d{{5,}}|{MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{5,}})(?![\d/])"
    rf"|{MONTHS}\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}(?!\d)|{MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,\d{{4}}(?!\d)"
    rf"|{MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)\d{{4}}(?!\d)"
    rf"|(?:{MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+|\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTHS}\s+|\d{{1,2}}/\d{{1,2}}/){_LETTER_YEAR}"
    rf"|{MONTHS}\s+(?=[\dOoIl]{{1,2}}(?![\w]))(?!\d{{1,2}}(?![\w]))[\dOoIl]{{1,2}},?\s+\d{{4}}(?!\d)"
    rf"|{_HAS_LETTER}[\dOoIl]{{4}}-[\dOoIl]{{2}}-[\dOoIl]{{2}}(?![\w-])|{_HAS_LETTER}[\dOoIl]{{1,2}}/[\dOoIl]{{1,2}}/[\dOoIl]{{2,4}}(?![\w/])"
    rf"|\d{{1,2}}-{MONTHS}-\d{{2,4}}(?![\w-])|\d{{1,2}}-\d{{1,2}}-\d{{4}}(?![\w-])|\d{{1,2}}\s+{MONTHS}\s+\d{{2}}(?![\w]))"
    # A digit glued to a month name, but not inside a longer token such as a part number ("47QTCA22D00MAR 2026").
    rf"|(?<![A-Za-z\d])\d{{1,2}}(?:st|nd|rd|th)?{MONTHS}\s*\d{{4}}(?!\d)"
)
# AM/PM must end at a token boundary: "17:00 America/New_York" is not "17:00 Am".
AMPM = r"(?:[ap]\.\s?m\.?|[ap]m)(?![a-z])"
TIME = (rf"(?<![\d:.])(?:\d{{1,2}}(?::\d{{2}}){{0,2}}\s*{AMPM}"
        rf"|\d{{3,4}}\s*(?:hours|hrs)\b"
        rf"|(?:12(?::00)?\s+)?noon\b"
        rf"|\d{{1,2}}:\d{{2}}(?::\d{{2}}(?:[.,]\d{{1,9}})?)?(?![\d:]))")
# Written cutoffs that are not clock times. They are preserved as written and flagged, never converted.
TIME_MARKER = r"\b(?:midnight|EOD|COB|EOB|end of (?:the )?(?:business )?day|close of (?:the )?business(?: day)?|end of business)\b"
# Longer forms first, so "UTC-04:00" is never reported as "UTC" and IANA names are kept whole.
# A zone must end at a token boundary, so "UTC+05:300" or a four-part IANA name never becomes a shorter valid one.
TZ = (r"\b(?:Africa|America|Antarctica|Arctic|Asia|Atlantic|Australia|Europe|Indian|Pacific|Etc)/[A-Za-z][A-Za-z0-9_+\-]{0,30}(?:/[A-Za-z][A-Za-z0-9_+\-]{0,30})?(?![A-Za-z0-9_+\-/])"
      r"|\b(?:UTC|GMT)\s?[+\u2212-]\s?\d{1,2}(?::?\d{2})?(?![\d:])"
      r"|\b(?:Eastern|Central|Mountain|Pacific|Alaska|Hawaii)(?:\s+(?:Standard|Daylight|Prevailing))?\s+Time\b"
      r"|(?-i:\b(?:E|C|M|P|AK|H)[SD]?T\b)|\b(?:UTC|GMT)\b(?!\s?[+\u2212-]\s?\d)|\bZulu\b|\blocal time\b")

# Whole words only: "registered", "conference call", "questionnaire", "offeror" and "disclosing" name no kind.
DEADLINE_KINDS = [
    ("registration", r"\bregistration\b|\bregister\b|\bregistered\s+(?:in|with|on)\s+SAM"),
    ("site_visit", r"\bsite visits?\b|\bpre-?(?:proposal|bid|quote|solicitation)\s+(?:conference|meeting)s?\b|\bpre-?bid\b|\bpre-?quote\b"
                   r"|\bindustry days?\b|\bconferences?\b(?!\s+calls?\b)"),
    ("intent_to_bid", r"\bintent to (?:bid|propose)\b|\bnotice of intent\b"),
    ("orals", r"\boral presentations?\b|\borals\b"),
    ("questions_due", r"(?<!answers to )(?<!answer to )\bquestions?\b|\binquir(?:y|ies|e|es)\b|\bclarifications?\b|\bRFI responses?\b"),
    ("revised_proposal_due", r"\bfinal proposal revisions?\b|\brevised proposals?\b|\bfinal revised\b|\bbest and final\b|\bBAFOs?\b|\bFPRs?\b"),
    ("proposal_due", r"\bproposals?\b|\bquotes?\b|\bquotations?\b|\boffers?\b|\bbids?\b|\bresponses?\b|\bsubmissions?\b"
                     r"|\bapplications?\b|\bclosing\b|\bdue date\b|\b(?:RFQ|RFP|IFB|solicitation)\b[^.;]{0,20}?\bcloses?\b"),
]
EVENT_KINDS = ("site_visit", "orals")
# Kinds that name something other than what is submitted; a clause can mention one while setting a submission deadline.
CONTEXT_KINDS = ("registration", "site_visit", "intent_to_bid", "orals")
SUBMISSION_KINDS = ("questions_due", "revised_proposal_due", "proposal_due")
SUBMIT_VERB = re.compile(r"\b(?:submit\w*|due)\b", re.I)

FORMS = [
    r"SF[- ]?(?:18|26|30|33|252|255|294|295|330|1442|1449|LLL)\b",
    r"DD[- ]?(?:Form\s*)?(?:254|1423|2345)\b",
    r"OF[- ]?(?:17|347)\b",
    r"FAR\s+52\.\d{3}-\d{1,3}",
    r"DFARS\s+252\.\d{3}-\d{4}",
]
SECTION = r"\b(?:Section|SECTION)\s+([A-M])\b"
VOLUME = r"\bVolume\s+(?:[IVX]+|\d+)\b(?:\s*[-\u2013:(]\s*([A-Z][A-Za-z /&]{2,40}))?"
PAGE_LIMIT = [
    r"(?:shall|must|will)\s+not\s+exceed\s+(\w{1,20}(?:\s*\(\d+\))?)\s+(?:\(\d+\)\s+)?pages?",
    r"(?:limited|limit)\s+to\s+(\w{1,20}(?:\s*\(\d+\))?)\s+(?:\(\d+\)\s+)?pages?",
    r"(?:maximum|max\.?)\s+(?:of\s+)?(\w{1,20}(?:\s*\(\d+\))?)\s+(?:\(\d+\)\s+)?pages?",
    r"(?<!\d)(\d{1,4})[- ]page\s+(?:limit|maximum)",  # bounded + left-anchored: no O(n^2) on digit runs
    r"page\s+limit(?:s|ation)?\s*[\u2013\u2014:-]\s*(?:[^:]{0,60}:\s*)?(\w{1,20}(?:\s*\(\d+\))?)\s+(?:\(\d+\)\s+)?pages?",
]
FORMAT_RULES = [
    ("font", r"(?:\d{1,2}[- ]?(?:point|pt)\b[^.\n]{0,40}font|font[^.\n]{0,40}\d{1,2}[- ]?(?:point|pt)\b|Times New Roman|Arial|Calibri)"),
    ("margins", r"\d(?:\.\d+)?[- ]?inch(?:es)?\s+margins?|margins?\s+of\s+(?:at least\s+)?\d(?:\.\d+)?"),
    ("paper", r"8[.\u00bd]?5?\s*(?:x|by)\s*11"),
    ("file_format", r"\b(?:PDF|\.pdf|Microsoft Word|\.docx?|Excel|\.xlsx)\b(?:\s+format)?"),
    ("spacing", r"(?:single|double|1\.5)[- ]spaced"),
]
SHALL = re.compile(r"[^.;\n]*\b(?:shall|must|is required to|are required to)\b[^.;\n]*[.;]?", re.I)  # reference only
SHALL_WORD = re.compile(r"\b(?:shall|must|is required to|are required to)\b", re.I)
REQUIREMENT_SUBJECT = re.compile(r"\b(offeror|contractor|quoter|vendor|proposal|response|submission|bidder)", re.I)
MAX_REQUIREMENT_TEXT = 1000  # longer requirement sentences are reported as flagged excerpts, never silently cut
EXCERPT_BEFORE = 200
EXCERPT_AFTER = 600
MAX_DEADLINE_CONTEXT = 300   # characters of clause text kept on each side of a deadline
MAX_STATEMENT_LINES = 25     # wrapped lines joined into one statement, at most
MAX_STATEMENT_CHARS = 6000
SUBJECT_BEFORE = 200  # page-limit subject is looked up in a window around the match
SUBJECT_AFTER = 60
MAX_INPUT_BYTES = 50 * 1024 * 1024
MAX_TEXT_CHARS = 5_000_000
MAX_PDF_PAGES = 1000
PDF_TIME_BUDGET_S = 60.0
PDF_MEMORY_LIMIT_BYTES = 1024 * 1024 * 1024
SUBJECT_RE = re.compile(r"(Volume\s+[IVX\d]{1,6}[^,.;]{0,60}?|Technical[^,.;]{0,60}?|Past Performance[^,.;]{0,60}?|Management[^,.;]{0,60}?|Price[^,.;]{0,60}?|Cost[^,.;]{0,60}?|White paper|Executive Summary|proposal|response|quote)\s+(?:shall|must|will|is|are|limited|\()", re.I)

DATE_RE = re.compile(DATE, re.I)
MALFORMED_DATE_RE = re.compile(MALFORMED_DATE, re.I)
DATE_START = re.compile(rf"\s*(?:{DATE})", re.I)
MAX_DEADLINES = 2000      # per document; beyond this extraction stops and says so
MAX_OTHER_TIMES = 5       # other times recorded per deadline
MAX_MALFORMED_WARNINGS = 50  # date-like values reported one by one; the rest are counted
MAX_REQUIREMENTS = 10000
TIME_RE = re.compile(rf"{TIME}|{TIME_MARKER}", re.I)
MARKER_RE = re.compile(TIME_MARKER, re.I)
TZ_RE = re.compile(TZ, re.I)
# What may sit between a date and its own time ("November 5, 2026 at 5:00 PM"), and a time and its zone.
# Separators and words that may sit between a date and its own time, and a time and its zone. Each is one regex
# with the time or zone it leads to, so a word that is also part of a zone ("local time") can backtrack.
_GAP_DATE_TIME = (r"[ \t,\-\u2013/|]*(?:(?:(?:at|by|before|until|on or before|no later than|not later than|NLT|prior to"
                  r"|from|beginning at|starting at)\b|@|(?:due\s+)?time\s*:)[ \t,]*)?\(?[ \t]*")
_GAP_TIME_TZ = (rf"[ \t,|/]*(?:(?:hrs|hours|sharp|prevailing|local)\b[ \t,]*)*"
                rf"(?:(?:-|\u2013|to|until|through)[ \t]*(?:{TIME})[ \t,]*)?\(?[ \t]*")
TIME_AFTER = re.compile(rf"{_GAP_DATE_TIME}(?P<time>{TIME}|{TIME_MARKER})", re.I)
TZ_AFTER = re.compile(rf"{_GAP_TIME_TZ}(?P<tz>{TZ})", re.I)
# A zone written directly after a date that has no time of its own. The time-range gap above is not allowed here, so
# "November 5, 2026 to 5:00 PM ET on November 12" does not lend the second date's zone to the first.
TZ_ONLY_AFTER = re.compile(rf"[ \t,|/]*(?:(?:prevailing|local)\b[ \t,]*)*\(?[ \t]*(?P<tz>{TZ})", re.I)
# A time (and zone) written immediately before its date: "by 11:00 AM EDT on November 5, 2026".
TIME_BEFORE_DATE = re.compile(rf"(?P<time>{TIME}|{TIME_MARKER})(?:{_GAP_TIME_TZ}(?P<tz>{TZ})\)?)?[ \t,]*"
                              rf"(?:on or before|no later than|not later than|by|on|of)?[ \t,]*$", re.I)
ISO_TIME = re.compile(r"T(\d{2}:\d{2}(?::\d{2}(?:[.,]\d{1,9})?)?)(Z|[+\u2212-]\d{2}:?\d{2})?(?![\d:])")
STRONG_TRIGGER = re.compile(r"\b(?:due|deadline|no later than|not later than|NLT|closing|closes|close[sd]?|on or before|cut-?off)\b", re.I)
WEAK_TRIGGER = re.compile(r"\b(?:submit(?:ted)?|received|delivered|by|before|prior to|opening)\b", re.I)
ISSUANCE = re.compile(r"\b(?:issued|issue date|posted|released|published|dated|amend(?:ed|ment)|modified|effective|as of|awarded|signed)\b", re.I)
# Issue or announcement words that may sit between a deadline word and a date that is not a deadline. Broader than
# ISSUANCE, which also decides whether a date is skipped; "signed and dated" describes the submission, not an issue.
# Announcement verbs count only in the past passive ("the due date was publicized <date>", "notice ... was delivered
# <date>"), so "as advertised", "will be made public" and "must have been delivered by <date>" stay deadlines. A fixed
# list: other announcement wording is not read.
ISSUE_AFTER = re.compile(rf"{ISSUANCE.pattern}|\b(?:sent|distributed|announced|went out|mailed|e-?mailed|circulated|transmitted)\b"
                         r"|\b(?:was|were|has\s+been|had\s+been|(?<!must )(?<!should )(?<!shall )(?<!will )(?<!may )(?<!to )have\s+been)"
                         r"\s+(?:\w+\s+)?(?:publici[sz]ed|advertised|broadcast|communicated|made\s+public|delivered|conveyed|disclosed"
                         r"|notified|provided|shared|faxed)\b", re.I)
SIGNED_AND_DATED = re.compile(r"\bsigned\s+and\s+dated\b|\bdated\s+and\s+signed\b", re.I)
EFFECTIVE_END = re.compile(r"\b(?:effective|as of)\b[\s,:]*$", re.I)
AFTER_WORD = re.compile(r"\bafter\b", re.I)
# Before the date; only counts when no due/deadline wording follows it ("will not be accepted by fax and are due").
NEGATION = re.compile(r"\b(?:not|no longer|never)\s+(?:be\s+)?(?:due\b(?!\s+until)|required|accepted|held)\b", re.I)
WITHDRAWN = re.compile(r"\b(?:withdrawn|cancel+ed|rescinded|revoked|superseded|postponed|deleted|suspended|voided|vacated|struck|resolicited)\b", re.I)
# After the date: "<date> is no longer in effect", "<date> is hereby removed", "<date> has been extended to ...".
VOIDED_AFTER = re.compile(r"\b(?:no longer|not\s+(?:be\s+)?(?:in effect|applicable|valid|required)"
                          r"|(?:is|are|was|were|has been|have been|will be|hereby)\s+(?:\w+\s+)?(?:extended|changed|revised|replaced|moved"
                          r"|removed|amended|void)|resolicit\w*)\b", re.I)
CONDITIONAL = re.compile(r"\b(?:unless|if|in the event)\b.*", re.I | re.S)
# Something written where a zone would be, in a form TZ does not accept ("UTC+05:300", "America/A/B/C/D").
TZ_LIKE = re.compile(r"[ \t,(]*(?:(?:UTC|GMT)\s?[+\u2212-]\s?\d|(?:Africa|America|Antarctica|Arctic|Asia|Atlantic|Australia|Europe|Indian|Pacific|Etc)/)", re.I)
# Amendments: "extended from <old> to <new>", "<old> is extended to <new>", "changed to <new>".
# Verb forms only. "slide" counts only before a shift ("slides one week", "slides back"), so presentation slides do not.
_MORE_CHANGE = (r"(?:alter(?:s|ed|ing)|adjust(?:s|ed|ing)|accelerat(?:es|ed|ing)|revok(?:es|ed|ing)|rescind(?:s|ed|ing)"
                r"|suspend(?:s|ed|ing)|slid(?:ing)?|slides?\s+(?:back|forward|out|by\s+(?:one|two|three|a|\d)|(?:one|two|three|a)\s+(?:week|day|month)|\d)"
                r"|br(?:ought|ings|inging)\s+(?:\w+\s+){0,5}?forward)\b")
CHANGE_VERB = rf"\b(?:(?:extend|extens|chang|mov|postpon|revis|amend|reschedul|delay|advanc|push|slip|shift)\w*|{_MORE_CHANGE})\b"
# What names a deadline: "proposal due date", "closing time", "deadline", "time for receipt", "proposals are now due",
# an SF form block.
DEADLINE_NOUN = (r"\b(?:(?:proposal|offer|quote|quotation|bid|response|submission|question|application|closing|receipt)s?"
                 r"\s+(?:due\s+)?(?:date|time|deadline)s?|due\s+(?:date|time)s?|deadlines?|(?:date\s+and\s+)?time\s+(?:for|of)\s+receipt"
                 r"|block\s+\d{1,2}|(?:proposals?|offers?|quotes?|quotations?|bids?|responses?|submissions?|questions?|applications?)"
                 r"\s+(?:(?:are|is|will\s+be|shall\s+be|remains?|were|was)\s+)?(?:now\s+|originally\s+|still\s+)?due)\b")
# "from <date>", "from the current date of <date>", "from its original date of <date>"; never across a "to". The
# "from" may follow a change verb or directly a deadline noun ("Proposal due date FROM: <old> TO: <new>").
_UP_TO_DATE = r"(?:(?!\bto\b)[^.;\d]){0,40}$"
FROM_BEFORE = re.compile(rf"(?:{CHANGE_VERB}[^.;]{{0,60}}?|{DEADLINE_NOUN}[\s:,\-]*)\bfrom\b{_UP_TO_DATE}", re.I)
# "The deadline was previously <date>; it is now <date>", "originally due <date>", "(formerly <date>)", "(was <date>)".
# Only short connecting words may follow, so "as previously announced, proposals are due <date>" is not withdrawn.
PREVIOUS_BEFORE = re.compile(r"(?:\b(?:previously|formerly|originally)(?:\s+(?:was|were|been|is|set|scheduled|due|for|at|on|of|as))*"
                             r"|\(\s*was)[\s,:]*$", re.I)
NOW_BEFORE = re.compile(r"\bnow(?:\s+(?:be|being|due|set|scheduled|extended|changed|moved|accept|accepted|received?|submitted"
                        r"|proposals?|offers?|quotes?|bids?|responses?|submissions?|on|for|at|by|until|through|reads?))*[\s,:]*$", re.I)
# A sentence that changes something: any other date in it that is not read as a deadline is named in a warning.
CHANGE_WORDS = re.compile(rf"{CHANGE_VERB}|\b(?:now|previously|formerly|originally|instead|in lieu|replac\w*|supersed\w*"
                          rf"|reset|updat\w*|correct\w*|modif\w*|new)\b", re.I)
_TO = r"\b(?:to|until|till|through)(?:\s+read(?:\s+as\s+follows)?)?[\s:]*$"
TO_BEFORE = re.compile(rf"(?:{CHANGE_VERB}[^.;]{{0,60}}?)?{_TO}", re.I)
CHANGE_TO_BEFORE = re.compile(rf"{CHANGE_VERB}[^.;]{{0,60}}?{_TO}", re.I)
# Fail-closed: a sentence that names a deadline (DEADLINE_NOUN) and uses change wording, but in which no date was read
# as a replacement, is reported, so a revision worded in a way this tool does not read cannot leave a clean checklist.
# Verb forms only ("revisions", "amendments" and "revised proposals" name things, not changes).
_DATE_NEXT = r"(?=\d|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))"
CHANGE_TERM = re.compile(
    r"\b(?:extend(?:s|ed|ing)?|extension|chang(?:es|ed|ing)|mov(?:es|ed|ing)|postpon(?:es|ed|ing|ement)"
    r"|revis(?:es|ing)|revised(?!\s+(?:proposals?|offers?|quotes?|quotations?|bids?|submissions?))|(?<!as )amend(?:s|ed|ing)"
    r"|reschedul(?:es|ed|ing)|delay(?:ed|ing)|advanc(?:es|ed|ing)|push(?:es|ed|ing)|slip(?:s|ped|ping)?|shift(?:s|ed|ing)?"
    rf"|{_MORE_CHANGE}"
    r"|substitut(?:e|es|ed|ing)|replac(?:es|ed|ing)|reset|updated|modif(?:ies|ied|ying)|correct(?:ed|ing)|delet(?:e|es|ed|ing)"
    r"|insert(?:s|ed|ing)?|supersed(?:es|ed|ing)|vice|instead\s+of|in\s+(?:place|lieu)\s+of|rather\s+than|formerly|originally"
    r"|no\s+longer\s+(?:applies|apply|valid|in\s+effect|required)|until\s+further\s+notice"
    r"|previously(?!\s+(?:announced|stated|noted|indicated|advised|posted|published|mentioned|discussed|described|registered|submitted|provided))"
    r"|original\s+(?:\w+\s+)?(?:date|time|deadline)|same\s+(?:\w+\s+)?(?:date|day)\s+(?:but|at|with)"
    r"|(?:old|new)\s*:|new\s+(?:\w+\s+)?(?:date|deadline|time)|now\s+(?:reads?|due|set|scheduled|closes?|ends?)\b"
    rf"|now\s+{_DATE_NEXT})|\(\s*was\b|,\s*not\s+{_DATE_NEXT}", re.I)
NOUN_THEN_FROM = re.compile(rf"{DEADLINE_NOUN}[\s:,\-]*from\b", re.I)
# A clause with no date that changes a clock time: change wording (or "now"), a deadline hint and a clock time. Verb
# forms only, so the FAR late-receipt text ("offers or revisions are due") and "New offerors must register by" pass.
TIME_CHANGE = re.compile(rf"{CHANGE_TERM.pattern}|\bnow\b", re.I)
DEADLINE_NOUN_RE = re.compile(DEADLINE_NOUN, re.I)
# "is extended to <date>" with no earlier date in the clause is an amendment of a deadline only when the sentence says
# what changed ("This date", "receipt of Offers", "the response period", "the question period", any deadline kind
# word, "changed to read"), not "the period of performance may be extended". Fail-closed: a validity change that names
# offers still warns.
CHANGE_HINT = re.compile(r"\b(?:dates?|hours?|times?|receipt|due|deadline|closing|responses?|proposals?|offers?|quotes?|quotations?"
                         r"|submissions?|solicitations?|RFP|RFQ|IFB)\b|\bQ\s*&\s*A\b|\bto\s+read\b", re.I)
SENTENCE_END = re.compile(r"[.!?]")
ZERO_WIDTH = re.compile("[\u200b-\u200d\u2060\ufeff]")
KIND_RES = [(k, re.compile(p, re.I)) for k, p in DEADLINE_KINDS]
LIST_MARKER = re.compile(r"\s*(?:[A-Z]{1,3}\.\d+(?:\.\d+)*\b|\d+(?:\.\d+)*[.)]\s|\(?[a-zA-Z0-9]{1,3}\)\s|[\u2022\u25cf\u25aa*\u2013-]\s|(?:SECTION|Section|ARTICLE|Article|PART|Part|VOLUME|Volume)\b)")
TERMINAL = re.compile(r"[.;!?][\"')\]]*$")
BOUNDARY = re.compile(r"[.;!?]")
NEXT_CAPITAL = re.compile(r"\s+(?=[A-Z])")
DOTTED_ABBREV = re.compile(r"(?:[A-Za-z]\.)+[A-Za-z]$")
ABBREVIATIONS = frozenset(
    "no nos inc corp co ltd llc dept sec sect para art vol vols fig st mr mrs ms dr approx vs attn ref pg pp ch govt "
    "rm bldg ste ave blvd rd hwy fl flr div encl exh jr sr hon gen col lt capt maj sgt ft "
    "jan feb mar apr jun jul aug sep sept oct nov dec".split())


def _is_boundary(s: str, i: int) -> bool:
    """True if the punctuation at s[i] ends a sentence or clause. ';' always does; '.' not after abbreviations."""
    c = s[i]
    if c == ";":
        return True
    j = i + 1
    while j < len(s) and s[j] in "\"')]":
        j += 1
    if j < len(s) and not s[j].isspace():
        return False  # "52.212-1", "a.m.,", "U.S.-based"
    if c != ".":
        return True
    tok = re.search(r"[A-Za-z.]{1,15}$", s[max(0, i - 15):i])
    word = tok.group(0) if tok else ""
    if word.lower() in ("a.m", "p.m"):  # "5:00 p.m. The site visit ..." ends a sentence; "5:00 p.m. Eastern Time" does not
        nxt = NEXT_CAPITAL.match(s, j)  # match at a position: never slice the rest of the text
        return bool(nxt) and not TZ_RE.match(s, nxt.end())
    return not (DOTTED_ABBREV.search(word) or word.lower() in ABBREVIATIONS)


def iter_sentences(line: str):
    """Yield sentences ending in '.', ';', '!' or '?' (delimiter kept); abbreviations and numbers do not split. O(n)."""
    pos = 0
    for m in BOUNDARY.finditer(line):
        if m.start() >= pos and _is_boundary(line, m.start()):
            yield line[pos:m.end()]
            pos = m.end()
    if pos < len(line):
        yield line[pos:]


NUMWORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty".split())}
NUMWORDS.update({"twenty-five": 25, "thirty": 30, "forty": 40, "fifty": 50})


@dataclass
class Deadline:
    kind: str
    date: str
    time: str | None
    timezone: str | None
    line: int
    text: str
    end_line: int | None = None
    # Codes for anything a reader must check: no_time, no_timezone, time_marker:<text>, invalid_date,
    # invalid_time, two_digit_year, negated_or_withdrawn, after_clause, kind_uncertain, timezone_unclear,
    # context_truncated (informational: only the excerpt was shortened), statement_split_at_limit, issue_date_possible,
    # replaces_earlier_date, other_time:<text>, unread_date:<text>, date_glued_to_text, timezone_glued_to_text.
    ambiguities: list[str] = field(default_factory=list)


@dataclass
class PageLimit:
    pages: int
    applies_to: str
    line: int
    text: str


@dataclass
class Report:
    deadlines: list[Deadline] = field(default_factory=list)
    forms: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    volumes: list[str] = field(default_factory=list)
    page_limits: list[PageLimit] = field(default_factory=list)
    format_rules: list[dict] = field(default_factory=list)
    requirements: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def checklist(self) -> list[dict]:
        """Flat compliance checklist rows: id, category, item, source line."""
        rows: list[dict] = []
        def add(cat, item, line=None):
            rows.append({"id": f"C{len(rows) + 1:03d}", "category": cat, "item": item, "line": line, "done": False})
        for d in self.deadlines:
            when = " ".join(x for x in (d.date, d.time, d.timezone) if x)
            check = f" [CHECK: {', '.join(d.ambiguities)}]" if d.ambiguities else ""
            add("deadline", f"{d.kind.replace('_', ' ')}: {when}{check}", d.line)
        for p in self.page_limits:
            add("page_limit", f"{p.applies_to}: max {p.pages} pages", p.line)
        for f in self.format_rules:
            add("format", f"{f['rule']}: {f['text']}", f["line"])
        for f in self.forms:
            add("form", f"Complete / acknowledge {f}")
        for v in self.volumes:
            add("volume", f"Include {v}")
        for r in self.requirements:
            prefix = f"[EXCERPT; read lines {r['line']}-{r['end_line']}] " if r.get("truncated") else ""
            add("requirement", prefix + r["text"], r["line"])
        return rows


def read_document(path: str | Path, *, isolate: bool = True) -> str:
    """Text of a .pdf (via pypdf) or a UTF-8 text file. PDFs are parsed in a bounded worker process by default."""
    p = Path(path)
    if p.stat().st_size > MAX_INPUT_BYTES:
        raise SystemExit(f"{p} is larger than {MAX_INPUT_BYTES // (1024 * 1024)} MB; refusing to parse it.")
    if p.suffix.lower() == ".pdf":
        if isolate:
            return _isolated_pdf_text(p)
        try:
            from pypdf import PdfReader
        except ImportError as e:  # pragma: no cover
            raise SystemExit("PDF input needs pypdf: pip install 'bid-deadline-check[pdf]'") from e
        try:
            return _bounded_pdf_text(PdfReader(str(p)))
        except PdfLimitError:
            raise
        except Exception as e:
            raise SystemExit(f"Could not read {p} as a PDF ({e}). Is it really a PDF? Some sites return an HTML page instead.") from e
    return p.read_text(encoding="utf-8", errors="replace")


class PdfLimitError(SystemExit):
    pass


def _bounded_pdf_text(reader) -> str:
    """Extract text with page, size and wall-clock limits. These are checked BETWEEN pages, so they do not
    bound work inside one parser call; the isolated worker (read_document's default) adds process limits."""
    import time
    start = time.monotonic()
    if len(reader.pages) > MAX_PDF_PAGES:
        raise PdfLimitError(f"PDF has {len(reader.pages)} pages; limit is {MAX_PDF_PAGES}.")
    parts, total = [], 0
    for pg in reader.pages:
        if time.monotonic() - start > PDF_TIME_BUDGET_S:
            raise PdfLimitError(f"PDF text extraction exceeded {PDF_TIME_BUDGET_S:.0f}s.")
        t = pg.extract_text() or ""
        total += len(t) + 1
        if total > MAX_TEXT_CHARS:
            raise PdfLimitError(f"PDF text exceeds {MAX_TEXT_CHARS} characters.")
        parts.append(t)
    return "\n".join(parts)


def _pdf_worker(argv: list[str]) -> int:
    """Child-process entry: apply OS limits to itself, extract, and print one JSON object."""
    global MAX_PDF_PAGES, MAX_TEXT_CHARS, PDF_TIME_BUDGET_S
    path, cpu_s, mem = argv[0], int(argv[1]), int(argv[2])
    MAX_PDF_PAGES, MAX_TEXT_CHARS, PDF_TIME_BUDGET_S = int(argv[3]), int(argv[4]), float(argv[5])
    limits = {"cpu_seconds": None, "address_space_bytes": None}
    try:
        import resource
        # A hard limit below ours (CI, containers, launchd) cannot be raised: use it instead of failing.
        hard = resource.getrlimit(resource.RLIMIT_CPU)[1]
        cpu = cpu_s if hard == resource.RLIM_INFINITY else min(cpu_s, hard)
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            limits["cpu_seconds"] = cpu
        except (ValueError, OSError):
            pass
        try:
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            limits["address_space_bytes"] = mem
        except (ValueError, OSError):
            pass  # e.g. macOS refuses RLIMIT_AS; only the wall clock and CPU limits apply there
    except ImportError:  # Windows: no resource module; only the parent's wall-clock kill applies
        pass
    try:
        from pypdf import PdfReader
    except ImportError:
        print(json.dumps({"ok": False, "kind": "missing_pypdf", "limits": limits}))
        return 0
    try:
        text = _bounded_pdf_text(PdfReader(path))
        print(json.dumps({"ok": True, "text": text, "limits": limits}))
    except PdfLimitError as e:
        print(json.dumps({"ok": False, "kind": "limit", "error": str(e), "limits": limits}))
    except MemoryError:
        print(json.dumps({"ok": False, "kind": "limit", "error": "PDF parsing exceeded the memory limit.", "limits": limits}))
    except Exception as e:  # malformed PDF
        print(json.dumps({"ok": False, "kind": "parse", "error": f"{type(e).__name__}: {e}", "limits": limits}))
    return 0


def _isolated_pdf_text(p: Path) -> str:
    """Parse in a separate interpreter (-I) with a wall-clock kill, an RLIMIT_CPU limit and, where the OS
    allows it, an RLIMIT_AS memory limit. The child gets this package's directory and the parent's import path
    without the current directory (which `python -m` puts first), so a pypdf planted there is not imported."""
    timeout = PDF_TIME_BUDGET_S + 5
    here = str(Path(__file__).resolve().parents[1])
    cwd = Path.cwd().resolve()
    paths = [here] + [x for x in sys.path if x and x != "." and Path(x).resolve() != cwd]
    code = ("import sys; sys.path[:0] = __import__('json').loads(sys.argv[1]); "
            "from bid_deadline_check.core import _pdf_worker; raise SystemExit(_pdf_worker(sys.argv[2:]))")
    args = [sys.executable, "-I", "-B", "-c", code, json.dumps(paths), str(p), str(int(PDF_TIME_BUDGET_S) + 1), str(PDF_MEMORY_LIMIT_BYTES),
            str(MAX_PDF_PAGES), str(MAX_TEXT_CHARS), str(PDF_TIME_BUDGET_S)]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise PdfLimitError(f"PDF parsing exceeded {timeout:.0f}s and was stopped.") from None
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        import signal
        if proc.returncode == -getattr(signal, "SIGXCPU", 24):
            raise PdfLimitError("PDF parsing exceeded its CPU time limit and was stopped.") from None
        if proc.returncode < 0:
            raise PdfLimitError(f"PDF parsing was stopped by signal {-proc.returncode}; a memory limit may have been reached.") from None
        raise SystemExit(f"The PDF worker failed (exit {proc.returncode}) before reporting a result; "
                         "run with isolate=False to see the error.") from None
    if result["ok"]:
        return result["text"]
    if result["kind"] == "missing_pypdf":
        raise SystemExit("PDF input needs pypdf: pip install 'bid-deadline-check[pdf]'")
    if result["kind"] == "limit":
        raise PdfLimitError(result["error"])
    raise SystemExit(f"Could not read {p} as a PDF ({result['error']}). Is it really a PDF? Some sites return an HTML page instead.")


def read_stdin_bounded(stream) -> str:
    data = stream.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise SystemExit(f"stdin is larger than {MAX_INPUT_BYTES // (1024 * 1024)} MB; refusing to parse it.")
    return data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data


def _num(tok: str) -> int | None:
    m = re.search(r"\((\d+)\)", tok)
    if m:
        return int(m.group(1))
    tok = tok.strip().lower()
    if tok.isdigit():
        return int(tok)
    return NUMWORDS.get(tok)


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _dedupe(seq):
    seen, out = set(), []
    for x in seq:
        k = x.upper().replace("-", " ") if isinstance(x, str) else x
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


@dataclass
class _Statement:
    """Physical lines joined while a line does not end a sentence (wrapped prose, label-above-date tables)."""
    text: str
    starts: list[tuple[int, int]]  # (offset in text, physical line number)
    forced: bool = False           # split because of the size bounds: content may continue across it
    open_start: bool = False       # begins mid-sentence after a list-marker or heading line split
    open_end: bool = False         # ends mid-sentence because the next line starts a list item or heading

    def line_at(self, offset: int) -> int:
        n = self.starts[0][1]
        for off, line in self.starts:
            if off > offset:
                break
            n = line
        return n


WHEN_REST = re.compile(r"[\s,@()\-\u2013/|]*(?:(?:at|by|on)\b[\s,@()\-\u2013/|]*)*", re.I)
# The next line carries on the date ("November 5, 2026" / "at 5:00 PM ET."): lower case, a joiner, a time or a zone.
CONTINUES = re.compile(rf"[a-z,@(]|(?i:{TIME})|(?i:{TZ})")


def _when_only(line: str) -> bool:
    """A short line holding only a date (with its time and zone), like the value under a label."""
    if len(line) > 120 or not DATE_RE.search(line):
        return False
    return WHEN_REST.fullmatch(TZ_RE.sub(" ", TIME_RE.sub(" ", DATE_RE.sub(" ", line)))) is not None


CUT_BEFORE_BLANK = re.compile(r"(?:,|\b(?:a|an|the|and|or|nor|of|to|for|in|on|at|by|with|from|as|all|any|each|that|which|than|if|is|are|be))\s*$", re.I)


def _statements(lines: list[str]):
    """Yields statements one at a time, so memory does not grow with the number of statements."""
    cur: _Statement | None = None
    ends_sentence, carry, opened = True, False, False
    for i, raw in enumerate(lines, 1):
        line = _norm_ws(raw)
        if not line:
            if cur:
                # A blank line inside a sentence (layout or PDF extraction): flag both sides. A heading without a full
                # stop ("Technical Approach", "Volume I - Technical") is not a cut; an obligation, a trailing comma or
                # a word that cannot end a sentence is.
                if not ends_sentence and (SHALL_WORD.search(cur.text) or CUT_BEFORE_BLANK.search(cur.text)):
                    cur.open_end, opened = True, True
                yield cur
            cur, ends_sentence = None, True
            continue
        heading = line.isupper() and len(line) > 3 and not DATE_RE.search(line)
        if cur is not None:
            full = len(cur.starts) >= MAX_STATEMENT_LINES or len(cur.text) + 1 + len(line) > MAX_STATEMENT_CHARS
            if ends_sentence or heading or full or LIST_MARKER.match(raw):
                if full and not ends_sentence:  # cut mid-sentence: flag both sides
                    cur.forced, carry = True, True
                elif not ends_sentence:  # a list item or heading interrupts a sentence, including one ending in ":"
                    cur.open_end, opened = True, True
                yield cur
                cur = None
        if cur is None:
            cur, carry, opened = _Statement(line, [(0, i)], forced=carry, open_start=opened), False, False
        else:
            cur.starts.append((len(cur.text) + 1, i))
            cur.text += " " + line
        # A capitals label directly above a date line ("PROPOSAL DUE DATE" / "November 5, 2026 at 5:00 PM ET")
        # is joined with it; a date-only line then ends the statement.
        nxt = _norm_ws(lines[i]) if i < len(lines) else ""
        label_above = heading and DATE_START.match(nxt) is not None
        value_line = _when_only(line) and not CONTINUES.match(nxt)
        ends_sentence = (heading and not label_above) or bool(TERMINAL.search(line)) or value_line
    if cur:
        yield cur


def _clauses(text: str) -> list[tuple[int, int]]:
    spans, pos = [], 0
    for m in BOUNDARY.finditer(text):
        if _is_boundary(text, m.start()):
            spans.append((pos, m.end()))
            pos = m.end()
    if pos < len(text):
        spans.append((pos, len(text)))
    return spans


_MONTH_NUM = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _date_parts(date: str):
    """(year, month, day) as written, "two_digit_year", or None if the form is not recognized."""
    s = re.sub(r"^(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,?\s+", "", date, flags=re.I)
    if (m := re.fullmatch(r"([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", s, re.I)):
        return int(m.group(3)), _MONTH_NUM[m.group(1)[:3].lower()], int(m.group(2))
    if (m := re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})", s, re.I)):
        return int(m.group(3)), _MONTH_NUM[m.group(2)[:3].lower()], int(m.group(1))
    if (m := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", s)):
        return "two_digit_year" if len(m.group(3)) != 4 else (int(m.group(3)), int(m.group(1)), int(m.group(2)))
    if (m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)):
        return tuple(int(x) for x in m.groups())
    return None


def _date_issues(date: str) -> list[str]:
    parts = _date_parts(date)
    if parts == "two_digit_year":
        return ["two_digit_year"]
    if parts is None:
        return []
    y, mo, d = parts
    if not (1 <= mo <= 12) or not (1 <= d <= calendar.monthrange(y, mo)[1]):
        return ["invalid_date"]
    return []


def _time_issues(t: str) -> list[str]:
    if MARKER_RE.fullmatch(t):
        return [f"time_marker:{t.lower()}"]
    if re.fullmatch(r"(?:12(?::00)?\s+)?noon", t, re.I):
        return []
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*([ap])?.*", t, re.I)
    if not m:
        return []
    h, mi, se, ap = int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0), m.group(4)
    if re.fullmatch(r"\d{3,4}\s*(?:hours|hrs)", t, re.I):
        h, mi = divmod(int(re.match(r"\d+", t).group(0)), 100)
    if mi > 59 or se > 59 or (ap and not 1 <= h <= 12) or (not ap and h > 23):
        return ["invalid_time"]
    if ap and h == 12 and mi == 0 and ap.lower() == "a":
        return ["time_marker:12:00 am (midnight)"]
    return []


def _kind(*texts: str) -> str | None:
    for t in texts:
        for k, rx in KIND_RES:
            if rx.search(t):
                return k
    return None


def _kind_first(text: str) -> str | None:
    """The kind named first in text that follows the date ("<date> is the deadline for proposals, and ...")."""
    found = [(m.start(), k) for k, rx in KIND_RES if (m := rx.search(text))]
    return min(found)[1] if found else None


def _bind_after(s: str, end: int, limit: int):
    """A time/marker and zone directly following a date. Returns (time, tz, end) using spans within limit."""
    if (iso := ISO_TIME.match(s, end, limit)):
        zone = iso.group(2)
        if not zone:
            z = TZ_AFTER.match(s, iso.end(), limit)
            return iso.group(1), z.group("tz") if z else None, z.end() if z else iso.end()
        return iso.group(1), zone, iso.end()
    t = TIME_AFTER.match(s, end, limit)
    pos = t.end() if t else end
    z = (TZ_AFTER if t else TZ_ONLY_AFTER).match(s, pos, limit)
    if z:
        return (t.group("time") if t else None), z.group("tz"), z.end()
    return (t.group("time") if t else None), None, pos


def _with_next(iterator):
    """(item, next item or None) pairs, consuming the iterator lazily."""
    cur = next(iterator, None)
    while cur is not None:
        nxt = next(iterator, None)
        yield cur, nxt
        cur = nxt


LIST_GAP = re.compile(r"[\s,;]*(?:(?:and|or|&)\b[\s,]*)?", re.I)
RANGE_WORDS = re.compile(r"\b(?:through|thru|to|until|from|period|performance|start|begin\w*|commenc\w*|award\w*|contract)\b|[-\u2013]", re.I)
ZONE_NAMES = {"eastern": "et", "central": "ct", "mountain": "mt", "pacific": "pt", "alaska": "akt", "hawaii": "ht"}


def _deadlines_in(st: _Statement, prev: str = "", limit: int = MAX_DEADLINES, issues: list[int] | None = None) -> list[Deadline]:
    """Deadlines in one statement. `prev` is the adjacent statement before it, used as the label of a date that
    begins this statement ("Proposals are due no later than the date and time below." / "November 5, ...").
    `issues`, when given, receives the line of each clause that appears to change a deadline without a date that
    was read as a replacement."""
    out: list[Deadline] = []
    starts: list[int] = []                 # date offset of each deadline in `out`
    consumed: list[tuple[int, int]] = []   # spans already bound to some date, as time or zone
    skipped: list[re.Match] = []           # dates not read as deadlines (issue dates excluded)
    s = st.text
    stopped = len(s)                       # where extraction stopped if the deadline limit was reached
    sent_ends = [m.start() for m in SENTENCE_END.finditer(s) if _is_boundary(s, m.start())]
    def same_sentence(a: int, b: int) -> bool:  # two offsets in one sentence; binary searches, never a rescan
        return bisect.bisect_left(sent_ends, a) == bisect.bisect_left(sent_ends, b)
    # "Proposals: briefing 9:00 AM ET; due November 5" -> the leading label names what is due (kind only).
    label = m.group(1) if (m := re.match(r"([^:;.]{1,60}):(?!\d)", s)) else ""  # not the colon of "5:00"
    for c0, c1 in _clauses(s):
        pairs = _with_next(DATE_RE.finditer(s, c0, c1))  # lazy, one date of lookahead: memory bounded by `limit`
        first = next(pairs, None)
        if first is None:
            continue
        # Per-clause first positions keep every per-date check O(1): no rescanning the clause prefix.
        trig = [m.end() for rx in (STRONG_TRIGGER, WEAK_TRIGGER) if (m := rx.search(s, c0, c1))]
        first_trigger = min(trig) if trig else None
        kind_ends = [(k, m.end()) for k, rx in KIND_RES if (m := rx.search(s, c0, c1))]
        prev_end = c0
        prev_kind = None        # kind of the previous deadline in this clause
        prev_superseded = False  # the previous date was the "from" side of an amendment
        for k, (dm, following) in enumerate(itertools.chain([first], pairs)):
            if len(out) >= limit:
                stopped = min(stopped, dm.start())
                break
            last = following is None
            region_start = prev_end
            nxt = c1 if last else following.start()
            time, tz, bind_end = _bind_after(s, dm.end(), nxt)
            zone_after = tz is not None  # the zone, if any, ends at bind_end
            unclear_zone = time is not None and tz is None and TZ_LIKE.match(s, bind_end, nxt) is not None
            # "November 5 (5:00 PM ET on November 6 ...)": that time is written for the next date, not this one.
            if time is not None and not last and re.fullmatch(r"[\s,]*(?:on|of)?[\s,]*", s[bind_end:nxt]):
                time, tz, bind_end, zone_after = None, None, dm.end(), False
            lead = dm.start()  # where this date's written time begins, when the time is written before the date
            if time is None:
                lo = max(prev_end, dm.start() - 80)
                b = TIME_BEFORE_DATE.search(s, lo, dm.start())
                if b:
                    time, tz = b.group("time"), b.group("tz") or tz
                    zone_after = zone_after and not b.group("tz")
                    consumed.append((b.start(), dm.start()))
                    lead = b.start()
            consumed.append((dm.start(), bind_end))
            region = s[prev_end:dm.start()]
            # "from 5:00 PM ET on November 5, 2026 to 5:00 PM ET on November 12": the amendment words sit before the
            # time. "is extended to November 12" marks a replacement even when it is the first date in the clause.
            # These patterns end at `lead` and span at most about 90 characters, so only the last 200 are searched.
            hp = max(prev_end, lead - 200)
            superseded = bool(FROM_BEFORE.search(s, hp, lead) or PREVIOUS_BEFORE.search(s, hp, lead))
            # "...; it is now <date>" replaces the deadline before it in the same sentence and takes its kind.
            now_repl = bool(NOW_BEFORE.search(s, hp, lead)) and bool(
                CHANGE_HINT.search(s, hp, lead) or _kind(s[hp:lead])
                or (out and same_sentence(starts[-1], dm.start())))
            replacement = bool((k > 0 and prev_superseded and TO_BEFORE.search(s, hp, lead))
                               or (CHANGE_TO_BEFORE.search(s, hp, lead)
                                   and (k > 0 or CHANGE_HINT.search(s, hp, lead) or _kind(s[hp:lead])))) or now_repl
            after = s[bind_end:nxt]
            strong = STRONG_TRIGGER.search(region)
            event = any(_kind(region) == ek for ek in EVENT_KINDS)
            skip = ISSUANCE.search(region) and not strong and not replacement  # "this amendment extends ... to <date>"
            # A later date in a triggered clause is a deadline only in a plain list ("by October 20, November 5 and ...").
            listed = (k > 0 and first_trigger is not None and first_trigger <= dm.start()
                      and (LIST_GAP.fullmatch(region) or ((_kind(region) or time is not None) and not RANGE_WORDS.search(region))))
            # Admitted only because it carries its own time ("..., with debriefings on December 1 at 10:00 AM"): it is
            # reported, but it does not inherit the clause's kind.
            by_time = (listed and not replacement and not LIST_GAP.fullmatch(region) and not _kind(region)
                       and not STRONG_TRIGGER.search(region) and not WEAK_TRIGGER.search(region))
            is_deadline = not skip and bool(
                strong or WEAK_TRIGGER.search(region) or event or listed or replacement
                or (last and (STRONG_TRIGGER.search(after) or _kind(after) in EVENT_KINDS) and not ISSUANCE.search(after)))
            labelled_by_prev = (not is_deadline and k == 0 and c0 == 0 and not region.strip() and prev
                                and (STRONG_TRIGGER.search(prev) or WEAK_TRIGGER.search(prev)) and not ISSUANCE.search(prev))
            is_deadline = is_deadline or bool(labelled_by_prev)
            prev_end = bind_end
            if not is_deadline:
                prev_superseded = False
                if not skip or EFFECTIVE_END.search(region):  # "..., effective <date>" in a change sentence is a new date
                    skipped.append(dm)
                continue
            line_start = max(off for off, _ in st.starts if off <= dm.start())
            local = s[max(line_start, region_start):dm.start()]
            earlier = next((kn for kn, end in kind_ends if end <= dm.start()), None)
            kind = ((prev_kind if replacement and prev_kind else None) or _kind(local, region) or (None if by_time else earlier)
                    or (out[-1].kind if now_repl and out and same_sentence(starts[-1], dm.start()) else None) or _kind_first(after) or _kind(label) or (_kind(prev) if labelled_by_prev else None) or "other")
            amb: list[str] = ["kind_uncertain"] if by_time else []
            # "Offerors registered in SAM.gov shall submit proposals by ...": the submission kind wins over a context
            # kind; if the context word is the one nearer the date, say the kind is uncertain.
            if kind in CONTEXT_KINDS and SUBMIT_VERB.search(region):
                ends = {kn: max(m.end() for m in rx.finditer(region)) for kn, rx in KIND_RES if rx.search(region)}
                sub = next((kn for kn in SUBMISSION_KINDS if kn in ends), None)
                if sub:
                    # Confident when the submission word is the subject (first) or the word nearest the date.
                    first = min((m.start(), kn) for kn, rx in KIND_RES if (m := rx.search(region)))[1]
                    if first != sub and ends[sub] < max(e for kn, e in ends.items() if kn in CONTEXT_KINDS):
                        amb.append("kind_uncertain")
                    kind = sub
            amb += _date_issues(_norm_ws(dm.group(0)))
            if re.match(r"[^\W\d]", s[dm.end():dm.end() + 1]) and not ISO_TIME.match(s, dm.end()):  # a letter or "_"
                amb.append("date_glued_to_text")  # "November 5, 2026oops": the date may be cut or mistyped
            if time is None:
                amb.append("no_time")
            else:
                amb += _time_issues(_norm_ws(time))
                if unclear_zone:
                    amb.append("timezone_unclear")  # a zone in a form this tool does not accept
                elif tz is None:
                    amb.append("no_timezone")
            negs = list(NEGATION.finditer(region))
            negated = bool(negs) and not STRONG_TRIGGER.search(region, negs[-1].end())
            plain_after = CONDITIONAL.sub("", after)  # "unless cancelled by amendment" does not withdraw it
            if superseded or negated or WITHDRAWN.search(region) or WITHDRAWN.search(plain_after) or VOIDED_AFTER.search(plain_after):
                amb.append("negated_or_withdrawn")
            if replacement:
                amb.append("replaces_earlier_date")
            elif strong and (iss := [m.start() for m in ISSUE_AFTER.finditer(SIGNED_AND_DATED.sub(lambda x: " " * len(x.group(0)), region))]) and \
                    iss[-1] > max(m.start() for m in STRONG_TRIGGER.finditer(region)):
                amb.append("issue_date_possible")  # "the proposal due date was issued <date>": the issue word is nearer
            prev_kind, prev_superseded = kind, "negated_or_withdrawn" in amb
            if AFTER_WORD.search(region) and not strong:
                amb.append("after_clause")  # "Offers received after <date> will not be considered"
            if tz and "/" in tz and re.match(r"\s+[A-Z][a-z]", s[bind_end:bind_end + 3]):
                amb.append("timezone_unclear")  # "America/New York"
            if tz and zone_after and re.match(r"\w", s[bind_end:bind_end + 1]):
                amb.append("timezone_glued_to_text")  # "17:00:00Zdraft", "UTC+05:30junk": the zone may be cut or mistyped
            lo, hi = max(c0, dm.start() - MAX_DEADLINE_CONTEXT), min(c1, bind_end + MAX_DEADLINE_CONTEXT)
            if lo > c0 or hi < c1:
                amb.append("context_truncated")
            if st.forced:
                amb.append("statement_split_at_limit")
            out.append(Deadline(kind, _norm_ws(dm.group(0)), _norm_ws(time) if time else None, _norm_ws(tz) if tz else None,
                                st.line_at(dm.start()), _norm_ws(s[lo:hi]), st.line_at(max(dm.start(), hi - 1)), amb))
            starts.append(dm.start())
    # Any other clock time in the same sentence after a deadline's date ("..., changed to 6:00 PM ET", "3:00 PM ET
    # for hand delivery") is attached to that deadline, so one time is never presented as the only cutoff.
    # Spans and starts are in text order, so each time is placed with two binary searches (linear overall).
    if out:
        span_starts = [a for a, _ in consumed]
        ends = sent_ends
        for t in TIME_RE.finditer(s, starts[0], stopped):
            j = bisect.bisect_right(span_starts, t.start()) - 1
            if (MARKER_RE.fullmatch(t.group(0)) or (j >= 0 and t.start() < consumed[j][1])
                    or re.search(r"(?:UTC|GMT)\s?[+\u2212-]\s?$", s[max(0, t.start() - 6):t.start()], re.I)):
                continue  # a written marker, already bound to a date, or the digits of a UTC/GMT offset
            i = bisect.bisect_left(starts, t.start()) - 1
            if i >= 0 and bisect.bisect_left(ends, starts[i]) == bisect.bisect_left(ends, t.start()):  # same sentence
                if sum(a.startswith("other_time:") for a in out[i].ambiguities) >= MAX_OTHER_TIMES:
                    continue  # a few are enough to send a reader to the source
                z = TZ_AFTER.match(s, t.end())
                same = (out[i].time is not None and _time_key(t.group(0)) == _time_key(out[i].time)
                        and (z is None or _zone_key(z.group("tz")) == _zone_key(out[i].timezone)))
                duration = DURATION_HOURS.fullmatch(t.group(0))
                if not same and not duration:
                    written = _norm_ws(t.group(0) + (" " + z.group("tz") if z else ""))
                    out[i].ambiguities.append(f"other_time:{written}")
        # A date that was not read as a deadline, in a sentence that changes something, is named on that sentence's
        # deadline: a revision worded in a way this tool does not read must not leave a clean checklist.
        changes: dict[int, bool] = {}  # sentence index -> has change wording, computed once per sentence
        for dm in skipped:
            p = dm.start()
            e = bisect.bisect_left(ends, p)
            a, b = (ends[e - 1] + 1 if e else 0), (ends[e] if e < len(ends) else len(s))
            i = bisect.bisect_left(starts, p) - 1
            if i < 0 or starts[i] < a:
                i += 1
            if i >= len(out) or not a <= starts[i] < b:
                continue
            if e not in changes:
                changes[e] = CHANGE_WORDS.search(s, a, b) is not None
            if changes[e] and sum(x.startswith("unread_date:") for x in out[i].ambiguities) < MAX_OTHER_TIMES:
                out[i].ambiguities.append(f"unread_date:{_norm_ws(dm.group(0))}")
    # Fail-closed: a clause that names a deadline and uses change wording, in which no date was read as a
    # replacement, is reported. One pass over the clauses (split at ";" as well as sentence ends, so a change to
    # something else in the next clause does not count); deadlines are found by binary search.
    if issues is not None:
        for pos, end in _clauses(s):
            if DEADLINE_NOUN_RE.search(s, pos, end) and (CHANGE_TERM.search(s, pos, end) or NOUN_THEN_FROM.search(s, pos, end)):
                lo, hi = bisect.bisect_left(starts, pos), bisect.bisect_left(starts, end)
                if not any("replaces_earlier_date" in out[i].ambiguities for i in range(lo, hi)):
                    lead = re.match(r"\s*", s[pos:pos + 200]).end()  # bounded: only leading spaces are skipped
                    issues.append(st.line_at(pos + lead))
    return out


def _requirements_in(st: _Statement) -> list[dict]:
    out: list[dict] = []
    pos = 0
    for sent in iter_sentences(st.text):
        start, pos = pos, pos + len(sent)
        hits = list(SHALL_WORD.finditer(sent))
        if not hits:
            continue
        s = _norm_ws(sent)
        at_cut = ((st.forced and (start == 0 or pos == len(st.text))) or (st.open_start and start == 0)
                  or (st.open_end and pos == len(st.text)))
        if (len(s) <= 25 and not at_cut) or not REQUIREMENT_SUBJECT.search(s):
            continue
        lead = len(sent) - len(sent.lstrip())
        if len(s) <= MAX_REQUIREMENT_TEXT and not at_cut:
            out.append({"text": s, "line": st.line_at(start + lead), "end_line": st.line_at(start + len(sent.rstrip()) - 1), "truncated": False})
            continue
        # Too long (or possibly continued past a statement bound): one flagged excerpt per obligation word.
        windows: list[list[int]] = []
        for h in hits:
            lo, hi = max(0, h.start() - EXCERPT_BEFORE), min(len(sent), h.end() + EXCERPT_AFTER)
            if windows and lo <= windows[-1][1]:
                windows[-1][1] = max(windows[-1][1], hi)
            else:
                windows.append([lo, hi])
        for lo, hi in windows:
            text = _norm_ws(sent[lo:hi])
            out.append({"text": ("..." if lo > lead else "") + text + ("..." if hi < len(sent.rstrip()) else ""),
                        "line": st.line_at(start + lo), "end_line": st.line_at(start + hi - 1), "truncated": True})
    return out


# ponytail: "within 120 hours" is a duration, not a clock time; a three-digit military time ("900 hours") is also
# skipped. Add a context check if such times matter.
DURATION_HOURS = re.compile(r"\d{3}\s*(?:hours|hrs)", re.I)


@functools.lru_cache(maxsize=4096)
def _time_key(t: str | None):
    """Seconds after midnight as a string (one type for every form), so 17:00:01 and 5:00:01 PM compare equal,
    1700 hours, 5:00 PM and 17:00 compare equal, and 17:00:01 and 17:00:59 do not. A fraction is compared without its
    trailing zeros (01.1 and 01.10 are one moment); the dots of "p.m." are dropped, a decimal point is kept."""
    t = re.sub(r"\.(?!\d)", "", re.sub(r"(?<=\d),(?=\d)", ".", (t or "").lower())).strip()
    if re.fullmatch(r"(?:12(?::00)?\s+)?noon", t):
        return str(12 * 3600)
    if (m := re.fullmatch(r"(\d{3,4})\s*(?:hours|hrs)", t)):
        h, mi = divmod(int(m.group(1)), 100)
        return str(h * 3600 + mi * 60)
    if (m := re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(?::(\d{2}(?:\.\d+)?))?\s*([ap])?m?", t)):
        h, mi, se, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3) or "0", m.group(4)
        hour = (h % 12) + (12 if ap == "p" else 0) if ap else h
        whole, _, frac = se.partition(".")
        frac = frac.rstrip("0")
        return f"{hour * 3600 + mi * 60 + int(whole)}{'.' + frac if frac else ''}"
    return t


@functools.lru_cache(maxsize=1024)
def _zone_key(tz: str | None) -> str:
    """"ET" and "Eastern Time" compare equal; EST and EDT stay different."""
    zone = re.sub(r"\s+", " ", (tz or "").lower())
    if (m := re.fullmatch(r"(eastern|central|mountain|pacific|alaska|hawaii)(?: prevailing)? time", zone)):
        zone = ZONE_NAMES[m.group(1)]
    return zone


def _norm_key(d: Deadline) -> tuple:
    """Equal for the same moment written differently: "11/05/2026" and "November 5, 2026", "5 PM" and "17:00",
    "ET" and "Eastern Time". EST and EDT stay different."""
    parts = _date_parts(d.date)
    return (parts if isinstance(parts, tuple) else d.date.lower(), _time_key(d.time), _zone_key(d.timezone))


def analyze(text: str) -> Report:
    r = Report()
    lines = ZERO_WIDTH.sub("", text).splitlines()

    for i, raw in enumerate(lines, 1):
        line = _norm_ws(raw)
        if not line:
            continue

        for pat in PAGE_LIMIT:
            for m in re.finditer(pat, line, re.I):
                n = _num(m.group(1))
                if n:
                    window = line[max(0, m.start() - SUBJECT_BEFORE): m.end() + SUBJECT_AFTER]
                    subj = SUBJECT_RE.search(window)
                    r.page_limits.append(PageLimit(n, _norm_ws(subj.group(1)) if subj else "unspecified", i, line[:240]))

        for name, pat in FORMAT_RULES:
            if re.search(pat, line, re.I) and re.search(r"shall|must|required|use|submit|format|font|margin|page", line, re.I):
                r.format_rules.append({"rule": name, "text": line[:200], "line": i})

        for pat in FORMS:
            r.forms += [_norm_ws(m.group(0)).upper().replace("SF ", "SF-").replace("OF ", "OF-") for m in re.finditer(pat, line, re.I)]
        r.sections += [m.group(1) for m in re.finditer(SECTION, line)]
        r.volumes += [_norm_ws(m.group(0)) for m in re.finditer(VOLUME, line)]

    prev: _Statement | None = None
    capped = []
    revisions: list[int] = []  # lines of clauses that appear to change a deadline in a way that was not read
    for st in _statements(lines):
        pos = 0
        for sent in iter_sentences(st.text):
            start, pos = pos, pos + len(sent)
            if (TIME_CHANGE.search(sent) and (CHANGE_HINT.search(sent) or STRONG_TRIGGER.search(sent) or _kind(sent))
                    and not DATE_RE.search(sent) and any(not DURATION_HOURS.fullmatch(t.group(0)) for t in TIME_RE.finditer(sent))):
                revisions.append(st.line_at(start + len(sent) - len(sent.lstrip())))
        adjacent = prev is not None and prev.starts[-1][1] + 1 == st.starts[0][1] and len(prev.text) <= 200
        if len(r.deadlines) < MAX_DEADLINES:
            r.deadlines += _deadlines_in(st, prev.text if adjacent else "", MAX_DEADLINES - len(r.deadlines), revisions)
            if len(r.deadlines) >= MAX_DEADLINES:
                capped.append(f"More than {MAX_DEADLINES} dated deadlines; extraction stopped at line {st.line_at(0)}. Check the rest of the document.")
        if len(r.requirements) < MAX_REQUIREMENTS:
            r.requirements += _requirements_in(st)
            if len(r.requirements) >= MAX_REQUIREMENTS:
                del r.requirements[MAX_REQUIREMENTS:]
                capped.append(f"More than {MAX_REQUIREMENTS} requirements; extraction stopped at line {st.line_at(0)}. Check the rest of the document.")
        prev = st

    r.forms = sorted(_dedupe(r.forms))
    r.sections = sorted(set(r.sections))
    vols = _dedupe(r.volumes)
    r.volumes = [v for v in vols if not any(o != v and o.startswith(v + " ") for o in vols)]
    seen = set()
    fr = []
    for f in r.format_rules:
        if (f["rule"], f["line"]) not in seen:
            seen.add((f["rule"], f["line"]))
            fr.append(f)
    r.format_rules = fr

    live = [d for d in r.deadlines if "negated_or_withdrawn" not in d.ambiguities]
    kinds = {d.kind for d in live}
    if "proposal_due" not in kinds:
        r.warnings.append("No proposal due date found. Check Section L, the SF-1449/SF-33 cover page, and amendments.")
    if "questions_due" not in kinds:
        r.warnings.append("No questions-due date found.")
    for d in r.deadlines:
        for a in d.ambiguities:
            if a == "no_timezone":
                r.warnings.append(f"Deadline on line {d.line} has a time but no timezone.")
            elif a == "no_time":
                r.warnings.append(f"Deadline on line {d.line} has a date but no time of day; confirm the cutoff time.")
            elif a.startswith("time_marker:"):
                r.warnings.append(f"Deadline on line {d.line} uses \"{a.split(':', 1)[1]}\", which is not a specific clock time; confirm the exact cutoff and date boundary.")
            elif a == "invalid_date":
                r.warnings.append(f"Deadline on line {d.line}: \"{d.date}\" is not a valid calendar date.")
            elif a == "invalid_time":
                r.warnings.append(f"Deadline on line {d.line}: \"{d.time}\" is not a valid clock time.")
            elif a == "two_digit_year":
                r.warnings.append(f"Deadline on line {d.line}: \"{d.date}\" has a two-digit year.")
            elif a == "negated_or_withdrawn":
                r.warnings.append(f"Deadline on line {d.line} appears negated, withdrawn or superseded; confirm it still applies.")
            elif a == "after_clause":
                r.warnings.append(f"Deadline on line {d.line} comes from an \"after\" (lateness) clause; confirm the actual due date and time.")
            elif a == "kind_uncertain":
                r.warnings.append(f"Deadline on line {d.line} mentions more than one kind of event; confirm what is due on that date.")
            elif a == "timezone_unclear":
                r.warnings.append(f"Deadline on line {d.line}: timezone \"{d.timezone}\" may be cut short; read the source text." if d.timezone
                                  else f"Deadline on line {d.line}: the timezone is written in a form this tool does not support; read the source text.")
            elif a == "date_glued_to_text":
                r.warnings.append(f"Deadline on line {d.line}: \"{d.date}\" runs into the text after it; check the full date in the source.")
            elif a == "timezone_glued_to_text":
                r.warnings.append(f"Deadline on line {d.line}: timezone \"{d.timezone}\" runs into the text after it; check the full zone in the source.")
            elif a == "issue_date_possible":
                r.warnings.append(f"Deadline on line {d.line}: \"{d.date}\" follows an issue or amendment word; confirm it is a deadline and not the date the document was issued.")
            elif a == "replaces_earlier_date":
                r.warnings.append(f"Deadline on line {d.line} replaces an earlier date in the same sentence; confirm it against the amendment.")
            elif a.startswith("unread_date:"):
                r.warnings.append(f"Deadline on line {d.line}: the same sentence also gives the date \"{a.split(':', 1)[1]}\", which was not read as a deadline; confirm which date applies.")
            elif a.startswith("other_time:"):
                r.warnings.append(f"Deadline on line {d.line}: the same sentence also gives \"{a.split(':', 1)[1]}\"; confirm which time applies to what.")
            elif a == "statement_split_at_limit":
                r.warnings.append(f"Deadline on line {d.line} is in a very long unpunctuated passage; check the source text around it.")
    by_kind: dict[str, list[Deadline]] = {}
    for d in live:
        by_kind.setdefault(d.kind, []).append(d)
    for kind, ds in by_kind.items():
        if len({_norm_key(d) for d in ds}) > 1:
            where = ", ".join(str(d.line) for d in ds)
            r.warnings.append(f"Found {len(ds)} different {kind.replace('_', ' ')} deadlines (lines {where}); confirm which applies (amendments may change dates).")
    for q in r.requirements:
        if q["truncated"]:
            r.warnings.append(f"Requirement on line {q['line']} is long or continues past a parsing bound; the checklist shows an excerpt. Read lines {q['line']}-{q['end_line']}.")
    r.warnings += capped
    malformed = 0
    for i, raw in enumerate(lines, 1):
        for m in MALFORMED_DATE_RE.finditer(raw):
            malformed += 1
            if malformed <= MAX_MALFORMED_WARNINGS:
                r.warnings.append(f"Line {i} has a date-like value in a form this tool does not read (\"{_norm_ws(m.group(0))[:40]}\"); check it in the source.")
    if malformed > MAX_MALFORMED_WARNINGS:
        r.warnings.append(f"{malformed - MAX_MALFORMED_WARNINGS} more date-like values in unsupported forms are not listed.")
    revisions = list(dict.fromkeys(revisions))  # one warning per line, whichever check found it
    for i in revisions[:MAX_MALFORMED_WARNINGS]:
        r.warnings.append(f"Line {i} appears to change a deadline in a way this tool does not read; confirm the new date and time in the source.")
    if len(revisions) > MAX_MALFORMED_WARNINGS:
        r.warnings.append(f"{len(revisions) - MAX_MALFORMED_WARNINGS} more sentences that appear to change a deadline are not listed.")
    if "\ufffd" in text:
        r.warnings.append("Input contains U+FFFD replacement characters (undecodable bytes or a lossy conversion); some text may be missing.")
    if not r.page_limits:
        r.warnings.append("No page limits found.")
    return r
