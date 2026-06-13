"""Tests for lib/sanitize.py — the shared C0/NUL stripper used by the parsers.

Stdlib only. Runnable directly:
    python3 tests/test_sanitize.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "lib"))

import sanitize  # noqa: E402


def test_nul_stripped_no_truncation():
    # The whole point: content after a NUL survives (no SQLite mid-word truncation).
    assert sanitize.clean("before\x00after") == "beforeafter"


def test_tab_newline_cr_preserved():
    assert sanitize.clean("a\tb\nc\rd") == "a\tb\nc\rd"


def test_other_c0_controls_stripped():
    assert sanitize.clean("x\x01\x07\x1fy") == "xy"


def test_none_passthrough():
    assert sanitize.clean(None) is None


def test_plain_text_unchanged():
    text = "let's ship — O'Brien said \"go\" | a|b"
    assert sanitize.clean(text) == text


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
