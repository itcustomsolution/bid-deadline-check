"""r7: the clean texts that the allow-list (owner's choice B) now sends to review are strict expected failures, listed with
their exact not_recognized items in r7_false_failures.json. A listed test passes only while it still fails with an
AssertionError and records exactly those items; a different item, or none, is reported as a failure."""
import json
from pathlib import Path

import pytest

import bid_deadline_check.core as core

_TABLE = {r["nodeid"]: [tuple(x) for x in r["not_recognized"]]
          for r in json.loads((Path(__file__).with_name("r7_false_failures.json")).read_text())["false_failures"]}
_seen: dict = {"items": None}
_orig = core._unrecognized


def _recording(st, ds, spans):
    items = _orig(st, ds, spans)
    if _seen["items"] is not None:
        _seen["items"].update((it["line"], it["detail"]) for it in items)
    return items


def pytest_configure(config):
    for want in _TABLE.values():
        for _line, detail in want:  # a flip caused only by allowed words would be a bug, not an expected failure
            if " " not in detail and detail.lower() in core.ALLOWED_WORDS:
                raise pytest.UsageError(f"r7_false_failures.json lists an allowed word as the reason: {detail}")


def pytest_collection_modifyitems(items):
    for item in items:
        if item.nodeid in _TABLE:
            reason = "; ".join(d for _, d in _TABLE[item.nodeid])
            item.add_marker(pytest.mark.xfail(strict=True, raises=AssertionError, reason=f"option B, not recognized: {reason}"))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    want = _TABLE.get(item.nodeid)
    if want is None:
        yield
        return
    core._unrecognized, _seen["items"] = _recording, set()
    try:
        outcome = yield
    finally:
        core._unrecognized, got = _orig, _seen["items"]
        _seen["items"] = None
    if sorted(got) != sorted(want):
        outcome.force_exception(RuntimeError(f"r7 expected-failure reason changed: expected {sorted(want)}, got {sorted(got)}"))
