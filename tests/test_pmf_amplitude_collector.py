"""Tests for the Amplitude Export collector — fixtures only, never the live API.

A synthetic export ZIP (gzipped NDJSON) is run through the collector and into the
PMF store, covering: entry-event filtering, field normalization, timezone-correct
event_time, window exclusion (delegated to the store), and idempotent re-ingest.
"""

from __future__ import annotations

import gzip
import io
import json
import os
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pmf_os.collectors import amplitude  # noqa: E402
from pmf_os.collectors.amplitude import (  # noqa: E402
    AmplitudeAuthError,
    fetch_signup_events,
    is_cohort_entry,
)
from pmf_os.store import PmfStore  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
MIGRATION = REPO_ROOT / "migrations" / "0005_pmf_cohort_os.sql"
WINDOW_START = "2026-06-11T00:00:00-07:00"
WINDOW_END = "2026-06-13T23:59:59-07:00"


def _raw_events() -> list[dict]:
    return [
        {  # in-window entry, full identity + properties
            "event_type": "onboarding_step_completed",
            "event_properties": {"step_name": "phone_number_submitted"},
            "event_time": "2026-06-11 10:15:00.123456",
            "insert_id": "ins-1",
            "user_id": "2714",
            "amplitude_id": 111,
            "user_properties": {"gp:first_name": "Asha", "gp:email": "asha@example.com", "gp:phone_number": "+15551234567"},
        },
        {  # in-window entry, amplitude_id only (user_id not assigned yet, no props)
            "event_type": "onboarding_step_completed",
            "event_properties": {"step_name": "phone_number_submitted"},
            "event_time": "2026-06-12 09:00:00",
            "insert_id": "ins-2",
            "amplitude_id": 222,
        },
        {  # non-entry onboarding step -> filtered out
            "event_type": "onboarding_step_completed",
            "event_properties": {"step_name": "otp_verified"},
            "event_time": "2026-06-11 10:16:00",
            "insert_id": "ins-3",
            "amplitude_id": 111,
        },
        {  # different event type -> filtered out
            "event_type": "credgpt_message_sent",
            "event_time": "2026-06-11 11:00:00",
            "insert_id": "ins-4",
            "user_id": "2714",
        },
        {  # entry but OUTSIDE the signup window -> the store must exclude it
            "event_type": "onboarding_step_completed",
            "event_properties": {"step_name": "phone_number_submitted"},
            "event_time": "2026-06-20 09:00:00",
            "insert_id": "ins-5",
            "amplitude_id": 333,
        },
    ]


def _export_zip(events: list[dict]) -> bytes:
    ndjson = "\n".join(json.dumps(e) for e in events).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("645917/2026-06-11/0.json.gz", gzip.compress(ndjson))
    return buf.getvalue()


def _fake_fetcher(events: list[dict]):
    blob = _export_zip(events)
    captured: dict[str, str] = {}

    def fetch(start_t: str, end_t: str) -> bytes:
        captured["start_t"] = start_t
        captured["end_t"] = end_t
        return blob

    fetch.captured = captured  # type: ignore[attr-defined]
    return fetch


def _store() -> PmfStore:
    db = str(Path(tempfile.mkdtemp(prefix="pmf_amp_")) / "alaska_pmf.db")
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    store = PmfStore(db)
    store.create_cohort(
        cohort_id="pmf-amp",
        name="Amp Test",
        signup_window_start=WINDOW_START,
        signup_window_end=WINDOW_END,
        activate=True,
    )
    return store


def test_is_cohort_entry():
    raw = _raw_events()
    assert is_cohort_entry(raw[0]) is True
    assert is_cohort_entry(raw[2]) is False  # otp_verified
    assert is_cohort_entry(raw[3]) is False  # different event type


def test_fetch_filters_to_entry_events_and_normalizes():
    fetch = _fake_fetcher(_raw_events())
    events = fetch_signup_events(WINDOW_START, WINDOW_END, export_fetcher=fetch)

    # only the three phone_number_submitted events survive; others are dropped
    assert [e["event_id"] for e in events] == ["ins-1", "ins-2", "ins-5"]

    first = events[0]
    assert first["user_id"] == "2714"
    assert first["amplitude_id"] == "111"
    assert first["user_properties"]["gp:email"] == "asha@example.com"
    # event_time normalized to explicit UTC (10:15 Pacific PDT -> 17:15 UTC)
    assert first["event_time"] == "2026-06-11T17:15:00+00:00"

    second = events[1]
    assert second["user_id"] is None  # user_id is not assigned at signup
    assert second["amplitude_id"] == "222"

    # the export was requested padded (at least a day before the window start)
    assert fetch.captured["start_t"] <= "20260610T00"


def test_ingest_excludes_out_of_window_and_is_idempotent():
    store = _store()
    fetch = _fake_fetcher(_raw_events())
    events = fetch_signup_events(WINDOW_START, WINDOW_END, export_fetcher=fetch)

    result = store.ingest_signup_events("pmf-amp", events)
    assert result["ingested"] == 2  # ins-1, ins-2 are in-window
    assert result["excluded"] == 1  # ins-5 (2026-06-20) is outside the window
    assert result["excluded_by_reason"].get("outside_signup_window") == 1
    assert {u["user_key"] for u in store.list_users("pmf-amp")} == {"user:2714", "amp:222"}

    # re-ingesting identical events dedups (idempotent intake)
    store.ingest_signup_events("pmf-amp", events)
    assert len(store.list_users("pmf-amp")) == 2


def test_iter_export_events_handles_bare_gzip_fallback():
    ndjson = (json.dumps(_raw_events()[0]) + "\n").encode("utf-8")
    out = list(amplitude.iter_export_events(gzip.compress(ndjson)))
    assert len(out) == 1
    assert out[0]["insert_id"] == "ins-1"


def test_auth_header_requires_credentials():
    saved = {k: os.environ.pop(k, None) for k in ("AMPLITUDE_API_KEY", "AMPLITUDE_SECRET_KEY")}
    try:
        raised = False
        try:
            amplitude._auth_header()
        except AmplitudeAuthError:
            raised = True
        assert raised
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


if __name__ == "__main__":
    import subprocess

    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-q"]))
