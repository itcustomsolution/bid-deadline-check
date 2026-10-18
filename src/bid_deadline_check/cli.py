"""Command line: bid-deadline-check FILE [--format text|json|csv|md]."""
from __future__ import annotations

import argparse
import csv
import json
import sys

from . import __version__
from .core import analyze, read_document, read_stdin_bounded


def render_text(rep) -> str:
    out = [f"OUTCOME: {'READ' if rep.outcome == 'read' else 'NEEDS REVIEW'}"
           + ("" if rep.outcome == "read" else f" ({len(rep.needs_review)} unresolved deadline sentence(s), {len(rep.warnings)} warning(s))")]
    if rep.needs_review:
        out.append("NEEDS REVIEW (read these in the source; no deadline was read from them)")
        for n in rep.needs_review:
            where = f"line {n['line']}" + (f"-{n['end_line']}" if n["end_line"] != n["line"] else "")
            out.append(f"  ? [{n['reason']}] {where}: " + n["text"].replace("\n", " / "))
    out.append("DEADLINES")
    out += [f"  [{d.kind}] {d.date} {d.time or '(no time)'} {d.timezone or '(no timezone)'}  (line {d.line})"
            + (f"  CHECK: {', '.join(d.ambiguities)}" if d.ambiguities else "")
            + ("" if d.status == "actionable" else "  NOT ACTIONABLE AS STATED: needs review") for d in rep.deadlines] or ["  none found"]
    out.append("PAGE LIMITS")
    out += [f"  {p.applies_to}: {p.pages} pages  (line {p.line})" for p in rep.page_limits] or ["  none found"]
    out.append("FORMAT RULES")
    out += [f"  {f['rule']}: {f['text']}  (line {f['line']})" for f in rep.format_rules] or ["  none found"]
    out.append("FORMS / CLAUSES: " + (", ".join(rep.forms) or "none found"))
    out.append("SECTIONS: " + (", ".join(rep.sections) or "none found"))
    out.append("VOLUMES: " + (", ".join(rep.volumes) or "none found"))
    excerpts = sum(1 for q in rep.requirements if q.get("truncated"))
    out.append(f"REQUIREMENTS (shall/must): {len(rep.requirements)}" + (f" ({excerpts} shown as excerpts; read the source lines)" if excerpts else ""))
    if rep.warnings:
        out.append("WARNINGS")
        out += [f"  ! {w}" for w in rep.warnings]
    return "\n".join(out)


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """Neutralize spreadsheet formula injection (CWE-1236): solicitation text is untrusted."""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def render_md(rep) -> str:
    rows = ["| ID | Category | Item | Line | Done |", "|---|---|---|---|---|"]
    rows += [f"| {c['id']} | {c['category']} | {c['item'].replace('|', '/').replace('<', '&lt;').replace('>', '&gt;')} | {c['line'] or ''} | [ ] |" for c in rep.checklist()]
    return "# Compliance checklist\n\n" + "\n".join(rows) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="bid-deadline-check", description="Extract deadlines, page limits, forms and a compliance checklist from a solicitation (PDF or text).")
    ap.add_argument("file", help="solicitation .pdf or .txt/.md ('-' for stdin)")
    ap.add_argument("--format", "-f", choices=["text", "json", "csv", "md"], default="text")
    ap.add_argument("--strict", action="store_true",
                    help="exit 2 unless the outcome is READ (no check fired and every deadline is actionable); exit 2 means "
                         "NEEDS REVIEW. READ means only that none of the implemented checks fired (see README, 'What --strict "
                         "means'); it does not prove every deadline was found or is correct")
    ap.add_argument("--version", action="version", version=__version__)
    a = ap.parse_args(argv)
    try:
        text = read_stdin_bounded(getattr(sys.stdin, "buffer", sys.stdin)) if a.file == "-" else read_document(a.file)
    except OSError as e:
        print(f"bid-deadline-check: cannot read {a.file}: {e.strerror or e}", file=sys.stderr)
        return 1
    rep = analyze(text)
    if a.format == "json":
        print(json.dumps({**rep.to_dict(), "checklist": rep.checklist()}, indent=2))
    elif a.format == "csv":
        w = csv.DictWriter(sys.stdout, fieldnames=["id", "category", "item", "line", "done"])
        w.writeheader()
        w.writerows({k: csv_safe(v) for k, v in row.items()} for row in rep.checklist())
    elif a.format == "md":
        print(render_md(rep))
    else:
        print(render_text(rep))
    return 2 if a.strict and rep.outcome != "read" else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
