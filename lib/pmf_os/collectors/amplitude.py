"""Amplitude Export collector for PMF cohort intake.

Pulls raw `onboarding_step_completed` / `phone_number_submitted` events for a
cohort's signup window via the Amplitude Export API (`/api/2/export`) and
normalizes them into the event shape `PmfStore.ingest_signup_events` consumes.

Design notes (see workspace/references/amplitude-api-reference.md):
- Auth = HTTP Basic `base64(AMPLITUDE_API_KEY:AMPLITUDE_SECRET_KEY)`.
- The Export API returns a ZIP of gzipped NDJSON; one JSON event per line.
- Cohort entry = event_type `onboarding_step_completed` with event property
  `step_name == "phone_number_submitted"`.
- At this onboarding step `gp:user_id` is usually NOT assigned yet (it lands
  after Spinwheel), so signup events are keyed off `amplitude_id`; the BON
  `user_id` is resolved later in the User 360 enrichment phase. Raw exports also
  often omit `user_properties` — that is expected and handled downstream.
- The HTTP fetch is injectable (`export_fetcher`) so tests use fixtures.
"""

from __future__ import annotations

import base64
import gzip
import io
import json
import os
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

AMPLITUDE_EXPORT_URL = "https://amplitude.com/api/2/export"
COHORT_ENTRY_EVENT = "onboarding_step_completed"
COHORT_ENTRY_STEP = "phone_number_submitted"

# Amplitude Export `start`/`end` params are expressed in the PROJECT timezone.
PROJECT_TZ = "America/Los_Angeles"
# CALIBRATION (verify on first live run): raw-export `event_time` is treated as
# PROJECT_TZ here, per Amplitude's documented export convention. If a spot-check
# shows Amplitude is returning UTC in this field, flip EVENT_TIME_TZ to "UTC".
# A wrong value silently shifts cohort membership at the day boundary, so this
# is the one thing to confirm against a real export before trusting intake.
EVENT_TIME_TZ = PROJECT_TZ

# (start_t, end_t) hour-granular strings "YYYYMMDDTHH" -> raw export bytes (zip).
ExportFetcher = Callable[[str, str], bytes]

# Event Segmentation API — used to count a user's CredGPT messages as the
# activation-signal fallback when User 360 chat comes back thin/empty.
AMPLITUDE_SEGMENTATION_URL = "https://amplitude.com/api/2/events/segmentation"
CREDGPT_MESSAGE_EVENT = "credgpt_message_sent"
# (e_json, start_YYYYMMDD, end_YYYYMMDD) -> parsed segmentation response dict.
SegmentationFetcher = Callable[[str, str, str], "dict[str, Any]"]


class AmplitudeAuthError(RuntimeError):
    """Raised when Amplitude credentials are missing."""


def _auth_header() -> str:
    key = os.environ.get("AMPLITUDE_API_KEY")
    secret = os.environ.get("AMPLITUDE_SECRET_KEY")
    if not key or not secret:
        raise AmplitudeAuthError("AMPLITUDE_API_KEY and AMPLITUDE_SECRET_KEY must be set for live Amplitude export")
    token = base64.b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _to_segmentation_date(value: str) -> str:
    """Coerce an ISO/date string to the YYYYMMDD (project tz) the API expects."""
    text = str(value).strip()
    # A bare calendar date (YYYY-MM-DD) is already the intended day — don't tz-shift it.
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text.replace("-", "")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return text.replace("-", "")[:8]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(PROJECT_TZ)).strftime("%Y%m%d")


def _live_segmentation_fetch(e_json: str, start: str, end: str, *, timeout: float = 60.0) -> "dict[str, Any]":
    import urllib.parse
    import urllib.request

    qs = urllib.parse.urlencode({"e": e_json, "m": "totals", "start": start, "end": end, "i": "30"})
    url = f"{AMPLITUDE_SEGMENTATION_URL}?{qs}"
    request = urllib.request.Request(url, headers={"Authorization": _auth_header()})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read())


def fetch_message_count(
    user_id: str | int,
    window_start: str,
    window_end: str,
    *,
    segmentation_fetcher: SegmentationFetcher | None = None,
) -> int:
    """Total CredGPT messages a user sent in the window (activation fallback).

    Uses the Event Segmentation API (gp:user_id filter, m=totals) — the canonical
    engagement metric — when User 360 chat is thin/empty. Note this is a raw
    message count (greetings included), so it's an activation proxy, not the
    greeting-filtered "meaningful" count we get from User 360 turn text.
    """
    fetcher = segmentation_fetcher or _live_segmentation_fetch
    definition = {
        "event_type": CREDGPT_MESSAGE_EVENT,
        "filters": [
            {
                "subprop_key": "gp:user_id",
                "subprop_op": "is",
                "subprop_type": "user",
                "subprop_value": [str(user_id)],
            }
        ],
    }
    data = fetcher(json.dumps(definition), _to_segmentation_date(window_start), _to_segmentation_date(window_end))
    series = ((data or {}).get("data") or {}).get("series") or []
    if not series:
        return 0
    return int(sum(v for v in series[0] if isinstance(v, (int, float))))


def _live_export_fetch(start_t: str, end_t: str, *, timeout: float = 420.0) -> bytes:
    # Imported lazily so the module (and CLI) load without network deps present.
    import urllib.request

    url = f"{AMPLITUDE_EXPORT_URL}?start={start_t}&end={end_t}"
    request = urllib.request.Request(url, headers={"Authorization": _auth_header()})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (trusted host)
        return response.read()


def _iter_ndjson(data: bytes) -> Iterator[dict[str, Any]]:
    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def iter_export_events(blob: bytes) -> Iterator[dict[str, Any]]:
    """Yield each raw event dict from an Amplitude export payload.

    Handles the normal case (ZIP of gzipped NDJSON files) and the fallback of a
    single gzip or plain NDJSON stream.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        try:
            yield from _iter_ndjson(gzip.decompress(blob))
        except (OSError, EOFError):
            yield from _iter_ndjson(blob)
        return
    with archive:
        for name in archive.namelist():
            raw = archive.read(name)
            try:
                data = gzip.decompress(raw)
            except (OSError, EOFError):
                data = raw
            yield from _iter_ndjson(data)


def is_cohort_entry(raw: dict[str, Any]) -> bool:
    if raw.get("event_type") != COHORT_ENTRY_EVENT:
        return False
    props = raw.get("event_properties") or {}
    return props.get("step_name") == COHORT_ENTRY_STEP


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_event_time(raw_event_time: Any) -> str | None:
    """Return an explicit UTC ISO timestamp the PMF store can parse precisely."""
    if not raw_event_time:
        return None
    text = str(raw_event_time).strip()
    if text.endswith("Z") or "+" in text[10:]:
        return text  # already carries an explicit offset; trust it
    naive_part = text.replace("T", " ").split(".")[0]
    try:
        naive = datetime.strptime(naive_part, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return text  # let the store's parse_dt make a best effort
    localized = naive.replace(tzinfo=ZoneInfo(EVENT_TIME_TZ))
    return localized.astimezone(timezone.utc).isoformat()


def normalize_signup_event(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Map a raw export event to the `upsert_signup_user` shape, or None."""
    if not is_cohort_entry(raw):
        return None
    return {
        "event_type": raw.get("event_type"),
        "step_name": COHORT_ENTRY_STEP,
        "event_time": _normalize_event_time(raw.get("event_time") or raw.get("client_event_time")),
        "event_id": _str_or_none(raw.get("insert_id") or raw.get("uuid") or raw.get("$insert_id")),
        "user_id": _str_or_none(raw.get("user_id")),  # usually absent at this step
        "amplitude_id": _str_or_none(raw.get("amplitude_id")),
        "user_properties": raw.get("user_properties") or {},
    }


def _parse_window(value: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_export_t(dt_utc: datetime, *, tz: str = PROJECT_TZ) -> str:
    return dt_utc.astimezone(ZoneInfo(tz)).strftime("%Y%m%dT%H")


def fetch_signup_events(
    window_start: str,
    window_end: str,
    *,
    export_fetcher: ExportFetcher | None = None,
    pad_days: int = 1,
) -> list[dict[str, Any]]:
    """Fetch + normalize cohort-entry signup events for the window.

    Over-fetches by `pad_days` on each side (timezone / day-boundary safety); the
    PMF store applies the exact tz-aware window check and idempotent dedup on
    ingest, so over-fetching is harmless and never drops a boundary signup.
    """
    fetcher = export_fetcher or _live_export_fetch
    start_dt = _parse_window(window_start) - timedelta(days=pad_days)
    end_dt = _parse_window(window_end) + timedelta(days=pad_days)
    blob = fetcher(_to_export_t(start_dt), _to_export_t(end_dt))
    events: list[dict[str, Any]] = []
    for raw in iter_export_events(blob):
        normalized = normalize_signup_event(raw)
        if normalized is not None:
            events.append(normalized)
    return events
