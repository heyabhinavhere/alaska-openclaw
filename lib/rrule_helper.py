"""
RRULE helper for Alaska v2 scheduling engine.

Wraps python-dateutil's rrule module with a few helpers that handle
the specific cases Alaska needs:
- Compute next fire time after a given datetime
- Validate RRULE string syntax
- Format human-readable description (for confirmation messages)

Assumes the input RRULE string has NO embedded DTSTART — we synthesize
one from the `after` anchor at call time. All datetimes returned are
in UTC.
"""

# PEP 604 union syntax (`datetime | None`) requires Python 3.10+.
# The production image (1panel/openclaw:2026.3.13, node:24-bookworm) runs
# Python 3.11, so this is fine in prod. Adding the future import lets
# local-dev environments on Python 3.9 (e.g. macOS system python) import
# this module too — annotations become strings, evaluated lazily.
from __future__ import annotations

from datetime import datetime, timezone
from dateutil import rrule
from dateutil.parser import isoparse


def next_fire_time(rrule_str: str, after: datetime | None = None) -> datetime:
    """
    Compute the next firing time for an RRULE, after a given datetime.

    Args:
        rrule_str: an RRULE string, e.g. 'FREQ=WEEKLY;BYDAY=FR;BYHOUR=17'
        after: anchor datetime (default: now UTC)

    Returns:
        UTC datetime of next firing

    Raises:
        ValueError: if rrule_str is malformed
    """
    if after is None:
        after = datetime.now(timezone.utc)
    # rrulestr returns an rruleset / rrule; first occurrence after `after`
    rule = rrule.rrulestr(f"DTSTART:{after.strftime('%Y%m%dT%H%M%SZ')}\nRRULE:{rrule_str}")
    next_occurrence = rule.after(after, inc=False)
    if next_occurrence is None:
        raise ValueError(f"RRULE has no future occurrence after {after}: {rrule_str}")
    return next_occurrence


def validate_rrule(rrule_str: str) -> tuple[bool, str]:
    """
    Check if an RRULE string is syntactically valid.

    Returns:
        (is_valid, error_message_or_empty)
    """
    try:
        anchor = datetime.now(timezone.utc)
        rrule.rrulestr(f"DTSTART:{anchor.strftime('%Y%m%dT%H%M%SZ')}\nRRULE:{rrule_str}")
        return (True, "")
    except (ValueError, KeyError) as e:
        return (False, str(e))


def describe_rrule(rrule_str: str) -> str:
    """
    Return a human-readable description of an RRULE.
    Crude but useful for confirmation messages.

    Example: 'FREQ=WEEKLY;BYDAY=FR;BYHOUR=17' -> 'every Friday at 17:00 UTC'
    """
    parts = {}
    for kv in rrule_str.split(';'):
        if '=' in kv:
            k, v = kv.split('=', 1)
            parts[k] = v

    freq = parts.get('FREQ', '').lower()
    day_map = {'MO': 'Monday', 'TU': 'Tuesday', 'WE': 'Wednesday',
               'TH': 'Thursday', 'FR': 'Friday', 'SA': 'Saturday', 'SU': 'Sunday'}

    bits = []
    if freq == 'daily':
        bits.append('every day')
    elif freq == 'weekly':
        if 'BYDAY' in parts:
            days = [day_map.get(d, d) for d in parts['BYDAY'].split(',')]
            bits.append('every ' + ', '.join(days))
        else:
            bits.append('every week')
    elif freq == 'monthly':
        bits.append('every month')
    elif freq == 'yearly':
        bits.append('every year')
    elif freq == 'hourly':
        bits.append('every hour')
    elif freq == 'minutely':
        bits.append('every minute')
    elif freq == 'secondly':
        bits.append('every second')
    elif freq == '':
        # No FREQ key in the rule — surface this rather than fabricating "every unknown"
        return 'unknown schedule (no FREQ)'
    else:
        # Graceful fallback for any RFC 5545 freq we haven't enumerated above
        bits.append(f'every {freq}')

    # Time block — only emit if BYHOUR is set. BYMINUTE alone (without BYHOUR)
    # is exotic and surfacing it as "at 00:MM UTC" would be misleading (implies
    # midnight); we drop it silently in that case.
    if 'BYHOUR' in parts:
        hour = int(parts['BYHOUR'])
        minute = int(parts.get('BYMINUTE', '0'))
        bits.append(f'at {hour:02d}:{minute:02d} UTC')

    return ' '.join(bits)


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('Usage: rrule_helper.py <rrule>')
        sys.exit(1)
    rule_str = sys.argv[1]
    valid, err = validate_rrule(rule_str)
    if not valid:
        print(f'INVALID: {err}')
        sys.exit(1)
    print(f'Description: {describe_rrule(rule_str)}')
    print(f'Next fire:   {next_fire_time(rule_str).isoformat()}')
