"""Tests for lib/rrule_helper.py."""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add lib/ to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))

from rrule_helper import next_fire_time, validate_rrule, describe_rrule


def test_validate_valid_rrule():
    valid, err = validate_rrule('FREQ=WEEKLY;BYDAY=FR;BYHOUR=17')
    assert valid, f"Expected valid, got error: {err}"
    assert err == ''


def test_validate_invalid_rrule():
    valid, err = validate_rrule('NOT_A_RULE')
    assert not valid
    assert err != ''


def test_next_fire_weekly_friday_5pm():
    # Anchor: Monday May 19, 2026 at 10:00 UTC
    anchor = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    nxt = next_fire_time('FREQ=WEEKLY;BYDAY=FR;BYHOUR=17;BYMINUTE=0', after=anchor)
    # Should be Friday May 22, 2026 at 17:00 UTC
    assert nxt.weekday() == 4  # Friday
    assert nxt.hour == 17
    assert nxt.minute == 0
    assert nxt.date() == datetime(2026, 5, 22).date()


def test_next_fire_daily():
    anchor = datetime(2026, 5, 19, 10, 0, 0, tzinfo=timezone.utc)
    nxt = next_fire_time('FREQ=DAILY;BYHOUR=9', after=anchor)
    # Should be next day at 9:00 UTC
    assert nxt.date() == (anchor + timedelta(days=1)).date()
    assert nxt.hour == 9


def test_describe_weekly_friday():
    desc = describe_rrule('FREQ=WEEKLY;BYDAY=FR;BYHOUR=17')
    assert 'Friday' in desc
    assert '17:00' in desc


def test_describe_daily():
    desc = describe_rrule('FREQ=DAILY;BYHOUR=9')
    assert 'every day' in desc
    assert '09:00' in desc


def test_next_fire_default_after_is_now():
    # When `after` is omitted, default to now UTC. The returned datetime
    # must be strictly in the future relative to call time.
    before_call = datetime.now(timezone.utc)
    nxt = next_fire_time('FREQ=DAILY;BYHOUR=23;BYMINUTE=59')
    after_call = datetime.now(timezone.utc)
    assert nxt > before_call, "next_fire should be after now"
    # Sanity: within the next 24 hours (daily rule at 23:59)
    assert (nxt - after_call).total_seconds() < 24 * 3600 + 60


def test_next_fire_no_future_occurrence_raises():
    # COUNT=1 with DTSTART in the past, anchor set after the single
    # occurrence — should exhaust the rule and raise ValueError.
    far_future = datetime(2030, 1, 1, tzinfo=timezone.utc)
    try:
        next_fire_time('FREQ=DAILY;COUNT=1', after=far_future)
    except ValueError as e:
        assert 'no future occurrence' in str(e).lower()
        return
    assert False, "Expected ValueError when RRULE has no future occurrence"


def test_describe_monthly():
    # Monthly branch — was previously untested.
    desc = describe_rrule('FREQ=MONTHLY;BYHOUR=10')
    assert 'every month' in desc
    assert '10:00' in desc


def test_describe_multi_day_weekly_with_minute():
    # Multi-day weekly + minute precision — the realistic case for
    # "reminder Monday/Wednesday/Friday at 9:30".
    desc = describe_rrule('FREQ=WEEKLY;BYDAY=MO,WE,FR;BYHOUR=9;BYMINUTE=30')
    assert 'Monday' in desc
    assert 'Wednesday' in desc
    assert 'Friday' in desc
    assert '09:30' in desc


def test_describe_no_freq_key():
    # Defensive: an RRULE with no FREQ key should not produce "every unknown".
    desc = describe_rrule('BYHOUR=10')
    assert 'unknown' in desc.lower()
    # Should not start with "every " when freq is genuinely missing
    assert not desc.startswith('every '), \
        f"Expected graceful unknown phrasing, got: {desc}"


if __name__ == '__main__':
    # Run all tests
    import inspect
    test_funcs = [obj for name, obj in inspect.getmembers(sys.modules[__name__])
                  if inspect.isfunction(obj) and name.startswith('test_')]
    failed = 0
    for fn in test_funcs:
        try:
            fn()
            print(f'PASS: {fn.__name__}')
        except AssertionError as e:
            print(f'FAIL: {fn.__name__}: {e}')
            failed += 1
        except Exception as e:
            print(f'ERROR: {fn.__name__}: {type(e).__name__}: {e}')
            failed += 1
    print(f'\n{len(test_funcs) - failed}/{len(test_funcs)} passed')
    sys.exit(1 if failed else 0)
