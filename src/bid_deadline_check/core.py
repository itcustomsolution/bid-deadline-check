"""Rule-based extraction. No network, no LLM."""
from __future__ import annotations

import re
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
TIME = r"\d{1,2}(?::\d{2})?\s*(?:[ap]\.?m\.?|AM|PM)|\d{3,4}\s*(?:hours|hrs)|noon|\d{1,2}:\d{2}"
TZ = (r"\b(?:Eastern|Central|Mountain|Pacific|Alaska|Hawaii)(?:\s+(?:Standard|Daylight|Prevailing))?\s+Time\b"
      r"|\b(?:E|C|M|P|AK|H)[SD]?T\b|\bUTC\b|\bGMT\b|\bZulu\b|\blocal time\b")

DEADLINE_KINDS = [
    ("site_visit", r"site visit|pre-?proposal conference|pre-?bid"),
    ("intent_to_bid", r"intent to (?:bid|propose)|notice of intent"),
    ("orals", r"oral presentation"),
    ("questions_due", r"question|inquir|clarification|RFI response"),
    ("proposal_due", r"proposal|quote|quotation|offer|bid|response|submission|application|closing|due date"),
]

FORMS = [
    r"SF[- ]?(?:18|26|30|33|252|255|294|295|330|1442|1449|LLL)\b",
    r"DD[- ]?(?:Form\s*)?(?:254|1423|2345)\b",
    r"OF[- ]?(?:17|347)\b",
    r"FAR\s+52\.\d{3}-\d{1,3}",
    r"DFARS\s+252\.\d{3}-\d{4}",
]
SECTION = r"\b(?:Section|SECTION)\s+([A-M])\b"
VOLUME = r"\bVolume\s+(?:[IVX]+|\d+)\b(?:\s*[-–:(]\s*([A-Z][A-Za-z /&]{2,40}))?"
PAGE_LIMIT = [
    r"(?:shall|must|will)\s+not\s+exceed\s+(\w+(?:\s*\(\d+\))?)\s+(?:\(\d+\)\s+)?pages?",
    r"(?:limited|limit)\s+to\s+(\w+(?:\s*\(\d+\))?)\s+(?:\(\d+\)\s+)?pages?",
    r"(?:maximum|max\.?)\s+(?:of\s+)?(\w+(?:\s*\(\d+\))?)\s+(?:\(\d+\)\s+)?pages?",
    r"(\d+)[- ]page\s+(?:limit|maximum)",
    r"page\s+limit(?:s|ation)?\s*[\u2013\u2014:-]\s*(?:[^:]{0,60}:\s*)?(\w+(?:\s*\(\d+\))?)\s+(?:\(\d+\)\s+)?pages?",
]
FORMAT_RULES = [
    ("font", r"(?:\d{1,2}[- ]?(?:point|pt)\b[^.\n]{0,40}font|font[^.\n]{0,40}\d{1,2}[- ]?(?:point|pt)\b|Times New Roman|Arial|Calibri)"),
    ("margins", r"\d(?:\.\d+)?[- ]?inch(?:es)?\s+margins?|margins?\s+of\s+(?:at least\s+)?\d(?:\.\d+)?"),
    ("paper", r"8[.½]?5?\s*(?:x|by)\s*11"),
    ("file_format", r"\b(?:PDF|\.pdf|Microsoft Word|\.docx?|Excel|\.xlsx)\b(?:\s+format)?"),
    ("spacing", r"(?:single|double|1\.5)[- ]spaced"),
]
SHALL = re.compile(r"[^.;\n]*\b(?:shall|must|is required to|are required to)\b[^.;\n]*[.;]?", re.I)

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
            add("deadline", f"{d.kind.replace('_', ' ')}: {when}", d.line)
        for p in self.page_limits:
            add("page_limit", f"{p.applies_to}: max {p.pages} pages", p.line)
        for f in self.format_rules:
            add("format", f"{f['rule']}: {f['text']}", f["line"])
        for f in self.forms:
            add("form", f"Complete / acknowledge {f}")
        for v in self.volumes:
            add("volume", f"Include {v}")
        for r in self.requirements:
            add("requirement", r["text"], r["line"])
        return rows


def read_document(path: str | Path) -> str:
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:  # pragma: no cover
            raise SystemExit("PDF input needs pypdf: pip install 'bid-deadline-check[pdf]'") from e
        try:
            return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
        except Exception as e:
            raise SystemExit(f"Could not read {p} as a PDF ({e}). Is it really a PDF? Some sites return an HTML page instead.") from e
    return p.read_text(encoding="utf-8", errors="replace")


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


def analyze(text: str) -> Report:
    r = Report()
    lines = text.splitlines()
    date_re, time_re, tz_re = re.compile(DATE, re.I), re.compile(TIME, re.I), re.compile(TZ, re.I)

    for i, raw in enumerate(lines, 1):
        # look at this line plus the next one so "due ... \n October 1, 2026" still matches
        ctx = _norm_ws(raw + " " + (lines[i] if i < len(lines) else ""))
        line = _norm_ws(raw)
        if not line:
            continue

        dm = date_re.search(line)
        # PDF tables often put the label on the line above the date
        prev = _norm_ws(lines[i - 2]) if i > 1 and not date_re.search(lines[i - 2]) else ""
        if dm and re.search(r"due|deadline|no later than|NLT|submit|received|closing|close|by\s", prev + " " + line, re.I):
            kind = "other"
            pre = prev + " " + line[: dm.start()] + " " + line
            for k, pat in DEADLINE_KINDS:
                if re.search(pat, pre, re.I):
                    kind = k
                    break
            after = ctx[ctx.find(dm.group(0)) :] if dm.group(0) in ctx else ctx
            tm = time_re.search(line) or time_re.search(after[:80])
            tz = tz_re.search(line) or tz_re.search(after[:120])
            r.deadlines.append(Deadline(kind, _norm_ws(dm.group(0)), _norm_ws(tm.group(0)) if tm else None,
                                        _norm_ws(tz.group(0)) if tz else None, i, line[:240]))

        for pat in PAGE_LIMIT:
            for m in re.finditer(pat, line, re.I):
                n = _num(m.group(1))
                if n:
                    subj = re.search(r"(Volume\s+[IVX\d]+[^,.;]*?|Technical[^,.;]*?|Past Performance[^,.;]*?|Management[^,.;]*?|Price[^,.;]*?|Cost[^,.;]*?|White paper|Executive Summary|proposal|response|quote)\s+(?:shall|must|will|is|are|limited|\()", line, re.I)
                    r.page_limits.append(PageLimit(n, _norm_ws(subj.group(1)) if subj else "unspecified", i, line[:240]))

        for name, pat in FORMAT_RULES:
            if re.search(pat, line, re.I) and re.search(r"shall|must|required|use|submit|format|font|margin|page", line, re.I):
                r.format_rules.append({"rule": name, "text": line[:200], "line": i})

        for pat in FORMS:
            r.forms += [_norm_ws(m.group(0)).upper().replace("SF ", "SF-").replace("OF ", "OF-") for m in re.finditer(pat, line, re.I)]
        r.sections += [m.group(1) for m in re.finditer(SECTION, line)]
        r.volumes += [_norm_ws(m.group(0)) for m in re.finditer(VOLUME, line)]

    for i, raw in enumerate(lines, 1):
        for m in SHALL.finditer(raw):
            s = _norm_ws(m.group(0))
            if len(s) > 25 and re.search(r"\b(offeror|contractor|quoter|vendor|proposal|response|submission|bidder)", s, re.I):
                r.requirements.append({"text": s[:300], "line": i})

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

    kinds = {d.kind for d in r.deadlines}
    if "proposal_due" not in kinds:
        r.warnings.append("No proposal due date found. Check Section L, the SF-1449/SF-33 cover page, and amendments.")
    if "questions_due" not in kinds:
        r.warnings.append("No questions-due date found.")
    for d in r.deadlines:
        if d.time and not d.timezone:
            r.warnings.append(f"Deadline on line {d.line} has a time but no timezone.")
    if not r.page_limits:
        r.warnings.append("No page limits found.")
    return r
