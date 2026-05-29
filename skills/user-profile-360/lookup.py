"""
lookup.py — single orchestration entry point for user-profile-360.

Ties the pieces together in CODE (not prompt) so the flow is reliable and
testable: resolve identity -> fetch sections (cache-aware) -> redact toxic PII
-> summarize (headline) or return redacted turns (deep-dive) -> audit.

Alaska calls this once and reads the JSON on stdout; she does not orchestrate
the modules herself.

CLI:
  python3 lookup.py --query 2762 --query-type user_id --intent user_summary \
    --requester-slack-id U07GKLVA9FE --requester-authority admin \
    --channel-type dm [--channel-id D123]

Output (stdout JSON):
  {
    "status": "ok" | "not_found" | "multiple" | "search_unavailable"
              | "invalid" | "auth_error" | "api_error" | "identity_mismatch"
              | "not_configured",
    "user_id": <int|null>,
    "intent": <str>,
    "mode": "headline" | "deep_dive",
    "matches": [ ... ],        # only when status == multiple
    "summary": { ... },        # headline mode
    "chat_turns": [ ... ],     # deep_dive mode: redacted real turns (recent)
    "served_stale": <bool>,
    "notes": [ ... ],          # caveats for Alaska to relay (e.g. null answers)
    "message": <str>
  }

Access policy is FLAT (confirmed 2026-05-29): the SKILL layer is responsible
for the in-roster vs unknown gate. This module does not re-gate; it records
requester_authority in the audit log. redaction_tier is always 'full'.
"""
from __future__ import annotations

import argparse
import json
import sys

import cache
import client
import redactor
import sections
import summarizer

# Intents whose value is the actual conversation content, not a metric summary.
DEEP_DIVE_INTENTS = {"chat_deep_dive"}

# How many recent real chat turns to surface in deep-dive mode.
DEEP_DIVE_TURN_LIMIT = 10


def _deep_dive_chat(redacted_chat: dict | None) -> tuple[list[dict], list[str]]:
    """From a redacted chat section, return (recent real turns, notes).

    Applies the proactive-filter (real = answered OR multi-turn thread) and
    flags when answers are missing (historical/null) so Alaska can say
    '[response not recorded]' rather than implying silence."""
    notes: list[str] = []
    if not redacted_chat:
        return [], ["No chat history for this user."]
    turns = redacted_chat.get("recent_turns") or []
    real, _proactive = summarizer._split_chat_turns(turns)
    # Most recent first.
    real_sorted = sorted(real, key=lambda t: t.get("created_at") or "", reverse=True)
    recent = real_sorted[:DEEP_DIVE_TURN_LIMIT]
    null_answers = sum(1 for t in recent if not t.get("answer"))
    if null_answers:
        notes.append(
            f"{null_answers} of the last {len(recent)} exchanges have no recorded "
            f"response (historical or proactive turns) — show '[response not recorded]'."
        )
    return recent, notes


def lookup(
    query: str,
    query_type: str,
    intent: str,
    requester_slack_id: str,
    requester_authority: str,
    channel_type: str | None = None,
    channel_id: str | None = None,
    db_path: str = cache.DEFAULT_DB_PATH,
) -> dict:
    out: dict = {"intent": intent, "user_id": None, "mode": None,
                 "served_stale": False, "notes": [], "message": ""}

    # Validate intent up front (don't silently fetch everything).
    try:
        section_names = sections.get_sections_for_intent(intent)
    except ValueError as e:
        out["status"] = "invalid"
        out["message"] = str(e)
        return out

    # 1. Resolve identity.
    r = client.resolve_user_id(query, query_type, db_path=db_path)
    if r.status != "resolved":
        out["status"] = r.status            # not_found | multiple | search_unavailable | invalid | not_configured
        out["matches"] = r.matches
        out["message"] = r.message
        return out
    user_id = r.user_id
    out["user_id"] = user_id

    # 2. Fetch (cache-aware) with audit logging.
    audit_ctx = {
        "requester_slack_id": requester_slack_id,
        "requester_authority": requester_authority,
        "invoking_skill": "user-profile-360",
        "channel_id": channel_id,
        "channel_type": channel_type,
        "intent_summary": intent,
        "redaction_tier": "full",  # flat policy
    }
    f = client.fetch_sections(user_id, section_names, db_path=db_path, audit_ctx=audit_ctx)
    if f.status != "ok":
        out["status"] = f.status            # auth_error | api_error | identity_mismatch | not_configured | not_found
        out["message"] = f.message
        return out
    out["served_stale"] = f.served_stale
    if f.served_stale:
        out["notes"].append("Served from stale cache — BON API was unreachable.")

    # 3. Redact toxic PII from raw sections (always).
    redacted = redactor.redact_sections(f.sections)

    # 4. Shape output by mode.
    if intent in DEEP_DIVE_INTENTS:
        out["mode"] = "deep_dive"
        recent, notes = _deep_dive_chat(redacted.get("chat"))
        out["chat_turns"] = recent
        out["notes"].extend(notes)
        # Also include a lightweight summary for context.
        out["summary"] = summarizer.summarize(redacted)
    else:
        out["mode"] = "headline"
        out["summary"] = summarizer.summarize(redacted)

    out["status"] = "ok"
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BON user-profile-360 lookup")
    ap.add_argument("--query", required=True)
    ap.add_argument("--query-type", required=True,
                    choices=sorted(client.VALID_QUERY_TYPES))
    ap.add_argument("--intent", required=True, choices=sections.all_intents())
    ap.add_argument("--requester-slack-id", required=True)
    ap.add_argument("--requester-authority", required=True,
                    choices=["admin", "founder", "engineer", "system", "unknown"])
    ap.add_argument("--channel-type", default=None,
                    choices=["dm", "channel", "cron", "agent_signal", None])
    ap.add_argument("--channel-id", default=None)
    ap.add_argument("--db-path", default=cache.DEFAULT_DB_PATH)
    args = ap.parse_args(argv)

    result = lookup(
        query=args.query,
        query_type=args.query_type,
        intent=args.intent,
        requester_slack_id=args.requester_slack_id,
        requester_authority=args.requester_authority,
        channel_type=args.channel_type,
        channel_id=args.channel_id,
        db_path=args.db_path,
    )
    print(json.dumps(result, indent=2, default=str))
    # Non-zero exit for hard failures so a cron/caller can detect them.
    return 0 if result.get("status") in ("ok", "not_found", "multiple") else 2


if __name__ == "__main__":
    sys.exit(main())
