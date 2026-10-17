"""Rule-based extraction. No network, no LLM."""
from __future__ import annotations

import calendar
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

MONTHS = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
DATE = (
    rf"(?:(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,?\s+)?"
    rf"(?:{MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}"
    rf"|\d{{1,2}}\s+{MONTHS}\s+\d{{4}}"
    rf"|\d{{1,2}}/\d{{1,2}}/\d{{2,4}}"
    rf"|\d{{4}}-\d{{2}}-\d{{2}})"
)
# AM/PM must end at a token boundary: "17:00 America/New_York" is not "17:00 Am".
AMPM = r"(?:[ap]\.\s?m\.?|[ap]m)(?![a-z])"
TIME = (rf"(?<![\d:.])(?:\d{{1,2}}(?::\d{{2}}){{0,2}}\s*{AMPM}"
        rf"|\d{{3,4}}\s*(?:hours|hrs)\b"
        rf"|\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?![\d:])"
        rf"|noon\b)")
# Written cutoffs that are not clock times. They are preserved as written and flagged, never converted.
TIME_MARKER = r"\b(?:midnight|EOD|COB|EOB|end of (?:the )?(?:business )?day|close of (?:the )?business(?: day)?|end of business)\b"
# Longer forms first, so "UTC-04:00" is never reported as "UTC" and IANA names are kept whole.
TZ = (r"\b(?:Africa|America|Antarctica|Arctic|Asia|Atlantic|Australia|Europe|Indian|Pacific|Etc)/[A-Za-z][A-Za-z0-9_+\-]{0,30}(?:/[A-Za-z][A-Za-z0-9_+\-]{0,30})?"
      r"|\b(?:UTC|GMT)\s?[+\u2212-]\s?\d{1,2}(?::?\d{2})?(?!\d)"
      r"|\b(?:Eastern|Central|Mountain|Pacific|Alaska|Hawaii)(?:\s+(?:Standard|Daylight|Prevailing))?\s+Time\b"
      r"|\b(?:E|C|M|P|AK|H)[SD]?T\b|\b(?:UTC|GMT)\b(?!\s?[+\u2212-]\s?\d)|\bZulu\b|\blocal time\b")

DEADLINE_KINDS = [
    ("registration", r"registration|register"),
    ("site_visit", r"site visit|pre-?proposal conference|pre-?bid|pre-?quote|industry day|conference"),
    ("intent_to_bid", r"intent to (?:bid|propose)|notice of intent"),
    ("orals", r"oral presentation|\borals\b"),
    ("questions_due", r"question|inquir|clarification|RFI response"),
    ("revised_proposal_due", r"final proposal revision|revised proposal|final revised|best and final|\bBAFOs?\b|\bFPRs?\b"),
    ("proposal_due", r"proposal|quote|quotation|offer|bid|response|submission|application|closing|due date"),
]
EVENT_KINDS = ("site_visit", "orals")

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
TIME_RE = re.compile(rf"{TIME}|{TIME_MARKER}", re.I)
MARKER_RE = re.compile(TIME_MARKER, re.I)
TZ_RE = re.compile(TZ, re.I)
# What may sit between a date and its own time ("November 5, 2026 at 5:00 PM"), and a time and its zone.
GAP_DATE_TIME = re.compile(r"[ \t,]*(?:(?:at|by|before|until|on or before|no later than|not later than|NLT|prior to|@)\b[ \t,]*)?\(?[ \t]*", re.I)
GAP_TIME_TZ = re.compile(r"[ \t,]*\(?[ \t]*")
# A time (and zone) written immediately before its date: "by 11:00 AM EDT on November 5, 2026".
TIME_BEFORE_DATE = re.compile(rf"(?P<time>{TIME}|{TIME_MARKER})(?:[ \t,]*\(?[ \t]*(?P<tz>{TZ})\)?)?[ \t,]*(?:on|of)?[ \t,]*$", re.I)
ISO_TIME = re.compile(r"T(\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?)(Z|[+\u2212-]\d{2}:?\d{2})?(?![\d:])")
STRONG_TRIGGER = re.compile(r"\b(?:due|deadline|no later than|not later than|NLT|closing|closes|close[sd]?|on or before|cut-?off)\b", re.I)
WEAK_TRIGGER = re.compile(r"\b(?:submit(?:ted)?|received|delivered|by)\b", re.I)
ISSUANCE = re.compile(r"\b(?:issued|issue date|posted|released|published|dated|amend(?:ed|ment)|modified|effective|as of|awarded|signed)\b", re.I)
AFTER_WORD = re.compile(r"\bafter\b", re.I)
NEGATION = re.compile(r"\b(?:not|no longer|never)\s+(?:be\s+)?(?:due|required|accepted|held)\b", re.I)  # before the date only
WITHDRAWN = re.compile(r"\b(?:withdrawn|cancel+ed|rescinded|superseded|postponed|deleted)\b", re.I)
KIND_RES = [(k, re.compile(p, re.I)) for k, p in DEADLINE_KINDS]
LIST_MARKER = re.compile(r"\s*(?:[A-Z]{1,3}\.\d+(?:\.\d+)*\b|\d+(?:\.\d+)*[.)]\s|\(?[a-zA-Z0-9]{1,3}\)\s|[\u2022\u25cf\u25aa*\u2013-]\s|(?:SECTION|Section|ARTICLE|Article|PART|Part|VOLUME|Volume)\b)")
TERMINAL = re.compile(r"[.;!?][\"')\]]*$")
BOUNDARY = re.compile(r"[.;!?]")
DOTTED_ABBREV = re.compile(r"(?:[A-Za-z]\.)+[A-Za-z]$")
ABBREVIATIONS = frozenset(
    "no nos inc corp co ltd llc dept sec sect para art vol vols fig st mr mrs ms dr approx vs attn ref pg pp ch govt "
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
    # invalid_time, two_digit_year, negated_or_withdrawn, context_truncated, statement_split_at_limit.
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
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
        limits["cpu_seconds"] = cpu_s
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
    allows it, an RLIMIT_AS memory limit. The parent's import path is passed explicitly, never the cwd."""
    timeout = PDF_TIME_BUDGET_S + 5
    paths = [x for x in sys.path if x]
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
        how = f"signal {-proc.returncode}" if proc.returncode < 0 else f"exit {proc.returncode}"
        raise PdfLimitError(f"PDF parsing stopped ({how}); a CPU or memory limit may have been reached.") from None
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

    def line_at(self, offset: int) -> int:
        n = self.starts[0][1]
        for off, line in self.starts:
            if off > offset:
                break
            n = line
        return n


def _statements(lines: list[str]) -> list[_Statement]:
    out: list[_Statement] = []
    cur: _Statement | None = None
    ends_sentence, carry = True, False
    for i, raw in enumerate(lines, 1):
        line = _norm_ws(raw)
        if not line:
            if cur:
                out.append(cur)
            cur, ends_sentence = None, True
            continue
        heading = line.isupper() and len(line) > 3
        if cur is not None:
            full = len(cur.starts) >= MAX_STATEMENT_LINES or len(cur.text) + 1 + len(line) > MAX_STATEMENT_CHARS
            if ends_sentence or heading or full or LIST_MARKER.match(raw):
                if full and not ends_sentence:  # cut mid-sentence: flag both sides
                    cur.forced, carry = True, True
                out.append(cur)
                cur = None
        if cur is None:
            cur, carry = _Statement(line, [(0, i)], forced=carry), False
        else:
            cur.starts.append((len(cur.text) + 1, i))
            cur.text += " " + line
        ends_sentence = heading or bool(TERMINAL.search(line))
    if cur:
        out.append(cur)
    return out


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


def _date_issues(date: str) -> list[str]:
    s = re.sub(r"^(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day,?\s+", "", date, flags=re.I)
    m = re.fullmatch(r"([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", s)
    if m:
        y, mo, d = int(m.group(3)), _MONTH_NUM[m.group(1)[:3].lower()], int(m.group(2))
    elif (m := re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})", s)):
        y, mo, d = int(m.group(3)), _MONTH_NUM[m.group(2)[:3].lower()], int(m.group(1))
    elif (m := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", s)):
        if len(m.group(3)) != 4:
            return ["two_digit_year"]
        y, mo, d = int(m.group(3)), int(m.group(1)), int(m.group(2))
    elif (m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)):
        y, mo, d = (int(x) for x in m.groups())
    else:
        return []
    if not (1 <= mo <= 12) or not (1 <= d <= calendar.monthrange(y, mo)[1]):
        return ["invalid_date"]
    return []


def _time_issues(t: str) -> list[str]:
    if MARKER_RE.fullmatch(t):
        return [f"time_marker:{t.lower()}"]
    if t.lower() == "noon":
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


def _bind_after(s: str, end: int, limit: int):
    """A time/marker and zone directly following a date. Returns (time, tz, end) using spans within limit."""
    if (iso := ISO_TIME.match(s, end, limit)):
        zone = iso.group(2)
        if not zone:
            g = GAP_TIME_TZ.match(s, iso.end(), limit)
            z = TZ_RE.match(s, g.end(), limit)
            return iso.group(1), z.group(0) if z else None, z.end() if z else iso.end()
        return iso.group(1), zone, iso.end()
    g = GAP_DATE_TIME.match(s, end, limit)
    t = TIME_RE.match(s, g.end(), limit)
    pos = t.end() if t else end
    g2 = GAP_TIME_TZ.match(s, pos, limit)
    z = TZ_RE.match(s, g2.end(), limit)
    if z:
        return (t.group(0) if t else None), z.group(0), z.end()
    return (t.group(0) if t else None), None, pos


def _deadlines_in(st: _Statement) -> list[Deadline]:
    out: list[Deadline] = []
    s = st.text
    # "Proposals: briefing 9:00 AM ET; due November 5" -> the leading label names what is due (kind only).
    label = m.group(1) if (m := re.match(r"([^:;.]{1,60}):", s)) else ""
    for c0, c1 in _clauses(s):
        dates = [m for m in DATE_RE.finditer(s, c0, c1)]
        if not dates:
            continue
        # Per-clause first positions keep every per-date check O(1): no rescanning the clause prefix.
        trig = [m.end() for rx in (STRONG_TRIGGER, WEAK_TRIGGER) if (m := rx.search(s, c0, c1))]
        first_trigger = min(trig) if trig else None
        kind_ends = [(k, m.end()) for k, rx in KIND_RES if (m := rx.search(s, c0, c1))]
        prev_end = c0
        for k, dm in enumerate(dates):
            region_start = prev_end
            nxt = dates[k + 1].start() if k + 1 < len(dates) else c1
            time, tz, bind_end = _bind_after(s, dm.end(), nxt)
            if time is None:
                lo = max(prev_end, dm.start() - 80)
                b = TIME_BEFORE_DATE.search(s, lo, dm.start())
                if b:
                    time, tz = b.group("time"), b.group("tz") or tz
            region = s[prev_end:dm.start()]
            after = s[bind_end:nxt]
            strong = STRONG_TRIGGER.search(region)
            event = any(_kind(region) == ek for ek in EVENT_KINDS)
            skip = (ISSUANCE.search(region) or AFTER_WORD.search(region)) and not strong
            is_deadline = not skip and bool(
                strong or WEAK_TRIGGER.search(region) or event
                or (k > 0 and first_trigger is not None and first_trigger <= dm.start())
                or (k == len(dates) - 1 and (STRONG_TRIGGER.search(after) or _kind(after) in EVENT_KINDS) and not ISSUANCE.search(after)))
            prev_end = bind_end
            if not is_deadline:
                continue
            line_start = max(off for off, _ in st.starts if off <= dm.start())
            local = s[max(line_start, region_start):dm.start()]
            earlier = next((kn for kn, end in kind_ends if end <= dm.start()), None)
            kind = _kind(local, region) or earlier or _kind(after, label) or "other"
            amb: list[str] = []
            amb += _date_issues(_norm_ws(dm.group(0)))
            if time is None:
                amb.append("no_time")
            else:
                amb += _time_issues(_norm_ws(time))
                if tz is None:
                    amb.append("no_timezone")
            if NEGATION.search(region) or WITHDRAWN.search(region) or WITHDRAWN.search(after):
                amb.append("negated_or_withdrawn")
            lo, hi = max(c0, dm.start() - MAX_DEADLINE_CONTEXT), min(c1, bind_end + MAX_DEADLINE_CONTEXT)
            if lo > c0 or hi < c1:
                amb.append("context_truncated")
            if st.forced:
                amb.append("statement_split_at_limit")
            out.append(Deadline(kind, _norm_ws(dm.group(0)), _norm_ws(time) if time else None, _norm_ws(tz) if tz else None,
                                st.line_at(dm.start()), _norm_ws(s[lo:hi]), st.line_at(max(dm.start(), hi - 1)), amb))
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
        if len(s) <= 25 or not REQUIREMENT_SUBJECT.search(s):
            continue
        lead = len(sent) - len(sent.lstrip())
        at_cut = st.forced and (start == 0 or pos == len(st.text))
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


def _norm_key(d: Deadline) -> tuple:
    return (d.date.lower(), (d.time or "").lower().replace(" ", "").replace(".", ""), (d.timezone or "").lower())


def analyze(text: str) -> Report:
    r = Report()
    lines = text.splitlines()

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

    for st in _statements(lines):
        r.deadlines += _deadlines_in(st)
        r.requirements += _requirements_in(st)

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
            elif a == "context_truncated":
                r.warnings.append(f"Deadline on line {d.line}: surrounding text was shortened; read lines {d.line}-{d.end_line}.")
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
    if "\ufffd" in text:
        r.warnings.append("Input contains U+FFFD replacement characters (undecodable bytes or a lossy conversion); some text may be missing.")
    if not r.page_limits:
        r.warnings.append("No page limits found.")
    return r
