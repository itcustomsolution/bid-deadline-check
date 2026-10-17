"""Regressions for the independent audit of the r2 candidate (2026-10-17, R2-DL-1..R2-DL-4) and the pre-release
strict-mode gaps found while it ran. Synthetic text only; each input is the audit's reproduction or a sibling of it,
plus controls that must keep passing."""
import pytest

from bid_deadline_check import analyze
from bid_deadline_check.cli import main

BASE = "Questions due October 1, 2026 at 10:00 AM ET.\nTechnical proposal must not exceed 20 pages.\n"
COMPLETE = "Proposals due November 5, 2026 at 5:00 PM ET.\n"


def strict(tmp_path, text):
    f = tmp_path / "rfp.txt"
    f.write_text(text)
    return main([str(f), "--strict", "-f", "json"])


def proposals(r):
    return [(d.date, d.time, d.timezone, d.ambiguities) for d in r.deadlines if d.kind == "proposal_due"]


# R2-DL-3: one moment written with a different number of fractional digits is not two deadlines.
def test_r2_dl_3_trailing_fraction_zeros_are_the_same_moment(tmp_path):
    text = BASE + "Proposals due 2026-11-05T17:00:01.1Z.\nProposals due 2026-11-05T17:00:01.10Z."
    r = analyze(text)
    assert not any("different proposal due" in w for w in r.warnings)
    assert strict(tmp_path, text) == 0


def test_r2_dl_3_different_fractions_still_conflict(tmp_path):
    text = BASE + "Proposals due 2026-11-05T17:00:01.1Z.\nProposals due 2026-11-05T17:00:01.2Z."
    assert any("2 different proposal due" in w for w in analyze(text).warnings)
    assert strict(tmp_path, text) == 2
