"""
purge.py — daily cache housekeeping for user-profile-360.

Run via cron ~03:30 UTC (after BON's nightly Array 02:00 + Plaid 03:00 jobs, so
the next reads repopulate with fresh data). This is housekeeping only —
correctness comes from the read-time TTL check in cache.py, so a missed run is
harmless; it just lets stale rows linger on disk a bit longer.

  python3 /data/skills/user-profile-360/purge.py
"""
from __future__ import annotations

import cache


def main() -> int:
    expired = cache.purge_expired()
    orphans = cache.reap_orphan_inflight()
    search = cache.purge_expired_search()
    print(
        f"[user-profile-360 purge] removed {expired} expired cache rows, "
        f"{orphans} orphan inflight claims, {search} expired search rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
