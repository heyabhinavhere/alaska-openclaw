"""Identity reconciliation for PMF cohort users.

P1 keys signup rows by `amplitude_id`, because BON's `gp:user_id` isn't assigned
until after Spinwheel. P2 enrichment resolves the real BON user_id and updates
that same row in place (via `update_user_profile` on its existing user_key) — so
the common path needs no merge and creates no duplicate.

The edge case this guards: the same resolved BON user_id ends up under more than
one `user_key` in the registry (e.g. one ingested event carried `user_id` while
another carried only `amplitude_id`). That should be reconciled by a human rather
than silently auto-merged — merging financial user records is exactly the kind of
irreversible action we keep human-in-the-loop. So this module DETECTS collisions
and leaves the merge decision to an operator (surfaced via needs_human_review).

Canonical key precedence (matches store.user_key_from_event):
    bon_user_id  >  amplitude_user_id  >  hashed phone  >  hashed email
"""

from __future__ import annotations

from typing import Any

KEY_PRECEDENCE = ("bon_user_id", "amplitude_user_id", "phone", "email")


def canonical_user_key(bon_user_id: Any) -> str | None:
    """The canonical key once a BON user_id is known."""
    if bon_user_id in (None, ""):
        return None
    return f"user:{bon_user_id}"


def detect_collisions(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find registry rows that resolve to the same BON user_id under different keys.

    `users` is the output of `PmfStore.list_users(cohort_id)`. Returns one group
    per colliding bon_user_id: {bon_user_id, user_keys:[...]}. Empty list = clean.
    """
    by_bon: dict[str, list[str]] = {}
    for user in users:
        bon_user_id = user.get("bon_user_id")
        if bon_user_id in (None, ""):
            continue
        by_bon.setdefault(str(bon_user_id), []).append(user.get("user_key"))
    return [
        {"bon_user_id": bon_user_id, "user_keys": sorted(k for k in keys if k)}
        for bon_user_id, keys in sorted(by_bon.items())
        if len(keys) > 1
    ]
