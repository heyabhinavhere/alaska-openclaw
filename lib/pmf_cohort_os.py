#!/usr/bin/env python3
"""CLI entry point for Alaska V5 PMF Cohort OS."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pmf_os.customerio_guard import build_approval_pack, validate_customerio_action
from pmf_os.store import DEFAULT_ARTIFACT_ROOT, DEFAULT_DB_PATH, PmfStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alaska V5 PMF Cohort Operating System")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create-cohort", help="Create or update a PMF cohort config")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--signup-window-start", required=True)
    p.add_argument("--signup-window-end", required=True)
    p.add_argument("--timezone", default="America/Los_Angeles")
    p.add_argument("--expected-signups", type=int)
    p.add_argument("--expected-real-users", type=int)
    p.add_argument("--created-by")
    p.add_argument("--activate", action="store_true")
    p.add_argument("--config-json")
    p.add_argument(
        "--allow-wide-window",
        action="store_true",
        help="TEST-ONLY: allow a signup window > 3 days. Refused unless the DB is a "
        "test DB (filename contains '_test', or under /tmp/) AND the cohort is NOT "
        "activated. Never affects production.",
    )

    p = sub.add_parser("activate-cohort", help="Mark an existing cohort active")
    p.add_argument("--cohort-id", required=True)

    p = sub.add_parser("ingest-signup", help="Ingest one Amplitude signup event JSON")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--event-json", required=True)

    p = sub.add_parser("ingest-signups-file", help="Batch ingest signup events from JSON array or JSONL")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--events-file", required=True)

    p = sub.add_parser("ingest-cohort", help="Pull signup events from the Amplitude Export API for the cohort window and ingest them")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--pad-days", type=int, default=1, help="Days to over-fetch on each side (timezone/boundary safety)")

    p = sub.add_parser("enrich-user", help="Resolve a cohort user's BON id, fetch their User 360 profile, and update the registry")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--user-key", required=True)

    p = sub.add_parser("update-profile", help="Update user registry fields from User 360/profile facts")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--user-key", required=True)
    p.add_argument("--profile-json", required=True)

    p = sub.add_parser("snapshot-user", help="Compute one user's daily snapshot and funnel stage")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--user-key", required=True)
    p.add_argument("--snapshot-date", required=True)
    p.add_argument("--facts-json", required=True)

    p = sub.add_parser("review-credgpt-turn", help="Record deterministic CredGPT quality review")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--user-key", required=True)
    p.add_argument("--turn-json", required=True)

    p = sub.add_parser("refresh-credgpt-clusters", help="Cluster recurring CredGPT quality issues")
    p.add_argument("--cohort-id", required=True)

    p = sub.add_parser("judge-credgpt-reviews", help="Run the LLM quality/safety judge on flagged CredGPT turns (gated; needs ANTHROPIC_API_KEY)")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--limit", type=int, help="Max number of pending reviews to judge in this run")

    p = sub.add_parser("render-report", help="Render PMF report artifacts")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--report-id", required=True)
    p.add_argument("--report-type", default="daily_cockpit")
    p.add_argument("--privacy-tier", default="team", choices=["team", "founder", "internal"])
    p.add_argument("--snapshot-date")
    p.add_argument("--artifact-root", default=DEFAULT_ARTIFACT_ROOT)
    p.add_argument("--include-docx", action="store_true")
    p.add_argument("--include-pdf", action="store_true")
    p.add_argument("--no-require-visual-qa", action="store_true")

    p = sub.add_parser("summary", help="Print cohort summary snapshot JSON")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--report-type", default="daily_cockpit")
    p.add_argument("--privacy-tier", default="team", choices=["team", "founder", "internal"])
    p.add_argument("--snapshot-date")

    p = sub.add_parser("cohort-membership", help="Cross-aware pointer: is a BON user in the ACTIVE PMF cohort? (returns stage, or null)")
    p.add_argument("--bon-user-id", required=True)

    p = sub.add_parser("case-file", help="Read one cohort user's case file (the /pmf user query); --cohort-id defaults to the active cohort")
    p.add_argument("--cohort-id")
    p.add_argument("--user-key")
    p.add_argument("--bon-user-id")

    p = sub.add_parser("validate-customerio-action", help="Validate a PMF Customer.io action JSON")
    p.add_argument("--action-json", required=True)

    p = sub.add_parser("draft-intervention", help="Draft a Customer.io intervention (never sends; mutation channels start needs_approval)")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--intervention-json", required=True)

    p = sub.add_parser("approve-intervention", help="Human approval gate for a drafted intervention")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--intervention-id", required=True)
    p.add_argument("--approved-by", required=True)

    p = sub.add_parser("reject-intervention", help="Reject a drafted intervention")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--intervention-id", required=True)
    p.add_argument("--approved-by", required=True)
    p.add_argument("--reason")

    p = sub.add_parser("execute-intervention", help="Execute an APPROVED intervention (gated; --execute-live actually sends via Customer.io)")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--intervention-id", required=True)
    p.add_argument("--customerio-ref", help="Record a ref for a send a human/skill already performed")
    p.add_argument("--execute-live", action="store_true", help="Send via the live Customer.io API (needs CUSTOMERIO_APP_API_KEY)")

    p = sub.add_parser("record-intervention-outcome", help="Record delivery/open/click/conversion outcome JSON")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--intervention-id", required=True)
    p.add_argument("--outcome-json", required=True)

    p = sub.add_parser("list-interventions", help="List interventions for a cohort")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--status", help="Filter by approval_status")

    p = sub.add_parser("draft-queue-interventions", help="Propose (never send) interventions for actionable open queues; lands in needs_approval, idempotent")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--draft-copy-live", action="store_true", help="Use the LLM to draft the message body (gated; needs ANTHROPIC_API_KEY)")

    p = sub.add_parser("end-cohort-memo", help="Build the end-of-cohort intelligence memo (aggregate facts + optional LLM narrative)")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--artifact-root", default=DEFAULT_ARTIFACT_ROOT)
    p.add_argument("--narrate-live", action="store_true", help="Write the LLM narrative (gated; needs ANTHROPIC_API_KEY)")

    p = sub.add_parser("weekly-digest", help="Build the weekly PMF digest (trajectory + this-week movements + friction + outcomes; optional LLM narrative)")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--week-start", help="ISO date; movements counted since this date (default: all)")
    p.add_argument("--artifact-root", default=DEFAULT_ARTIFACT_ROOT)
    p.add_argument("--narrate-live", action="store_true", help="Write the LLM narrative (gated; needs ANTHROPIC_API_KEY)")

    p = sub.add_parser("run-cohort-day", help="Run the full daily cohort pass: intake -> enrich+snapshot -> clusters -> report")
    p.add_argument("--cohort-id", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--no-intake", action="store_true", help="Skip Amplitude intake (use when already ingested)")
    p.add_argument("--no-render", action="store_true", help="Skip artifact rendering")
    p.add_argument("--deliver", action="store_true", help="Post the daily summary + cockpit to Slack (needs SLACK_BOT_TOKEN)")
    p.add_argument("--slack-channel", help="Slack channel id for --deliver (e.g. C0APP7V6H8C)")
    p.add_argument("--briefing-live", action="store_true", help="Write the LLM founder briefing (gated; needs ANTHROPIC_API_KEY)")

    args = parser.parse_args(argv)
    store = PmfStore(args.db)

    try:
        if args.cmd == "create-cohort":
            out = store.create_cohort(
                cohort_id=args.cohort_id,
                name=args.name,
                signup_window_start=args.signup_window_start,
                signup_window_end=args.signup_window_end,
                timezone_name=args.timezone,
                expected_signups=args.expected_signups,
                expected_real_users=args.expected_real_users,
                created_by=args.created_by,
                activate=args.activate,
                config=_load_json_arg(args.config_json) if args.config_json else {},
                allow_wide_window=args.allow_wide_window,
            )
        elif args.cmd == "activate-cohort":
            out = store.activate_cohort(args.cohort_id)
        elif args.cmd == "ingest-signup":
            out = store.upsert_signup_user(args.cohort_id, _load_json_arg(args.event_json))
        elif args.cmd == "ingest-signups-file":
            out = store.ingest_signup_events(args.cohort_id, _load_events_file(args.events_file))
        elif args.cmd == "ingest-cohort":
            from pmf_os.collectors.amplitude import fetch_signup_events

            cohort = store.get_cohort(args.cohort_id)
            events = fetch_signup_events(
                cohort["signup_window_start"],
                cohort["signup_window_end"],
                pad_days=args.pad_days,
            )
            out = store.ingest_signup_events(args.cohort_id, events)
            out["fetched_events"] = len(events)
        elif args.cmd == "enrich-user":
            from pmf_os.collectors import user360

            row = store.get_user(args.cohort_id, args.user_key)
            resolved = user360.resolve_bon_user_id(row)
            if resolved["status"] != "resolved":
                out = {"status": resolved["status"], "user_key": args.user_key, "detail": resolved.get("detail")}
            else:
                fetched = user360.fetch_profile(resolved["user_id"])
                if fetched["status"] != "ok":
                    out = {"status": fetched["status"], "user_key": args.user_key, "bon_user_id": resolved["user_id"], "detail": fetched.get("detail")}
                else:
                    enriched = user360.enrich_facts(fetched["payload"])
                    store.update_user_profile(args.cohort_id, args.user_key, enriched["profile_facts"])
                    out = {
                        "status": "ok",
                        "user_key": args.user_key,
                        "bon_user_id": resolved["user_id"],
                        "profile_facts": enriched["profile_facts"],
                        "daily_facts": enriched["daily_facts"],
                    }
        elif args.cmd == "update-profile":
            out = store.update_user_profile(args.cohort_id, args.user_key, _load_json_arg(args.profile_json))
        elif args.cmd == "snapshot-user":
            out = store.apply_daily_snapshot(
                args.cohort_id,
                args.user_key,
                args.snapshot_date,
                _load_json_arg(args.facts_json),
            )
        elif args.cmd == "review-credgpt-turn":
            out = store.record_credgpt_turn(args.cohort_id, args.user_key, _load_json_arg(args.turn_json))
        elif args.cmd == "refresh-credgpt-clusters":
            out = {"clusters": store.refresh_credgpt_clusters(args.cohort_id)}
        elif args.cmd == "judge-credgpt-reviews":
            out = store.judge_pending_credgpt_reviews(args.cohort_id, limit=args.limit)
        elif args.cmd == "render-report":
            out = store.render_report_artifacts(
                args.cohort_id,
                report_id=args.report_id,
                report_type=args.report_type,
                privacy_tier=args.privacy_tier,
                artifact_root=args.artifact_root,
                snapshot_date=args.snapshot_date,
                include_docx=args.include_docx,
                include_pdf=args.include_pdf,
                require_visual_qa=not args.no_require_visual_qa,
            )
        elif args.cmd == "summary":
            out = store.generate_report_snapshot(
                args.cohort_id,
                report_type=args.report_type,
                privacy_tier=args.privacy_tier,
                snapshot_date=args.snapshot_date,
            )
        elif args.cmd == "cohort-membership":
            out = {"membership": store.get_active_cohort_membership(args.bon_user_id)}
        elif args.cmd == "case-file":
            cohort_id = args.cohort_id
            if not cohort_id:
                active = store.active_cohort()
                cohort_id = active["cohort_id"] if active else None
            user_key = args.user_key
            if not user_key and args.bon_user_id and cohort_id:
                user_key = store.user_key_for_bon_id(cohort_id, args.bon_user_id) or f"user:{args.bon_user_id}"
            if not cohort_id:
                out = {"case_file": None, "note": "no active cohort"}
            elif not user_key:
                out = {"case_file": None, "note": "provide --user-key or --bon-user-id"}
            else:
                cf = store.get_case_file(cohort_id, user_key)
                out = {"cohort_id": cohort_id, "user_key": user_key, "case_file": cf,
                       "note": None if cf else "no case file — user not in this cohort, or no daily run has populated it yet"}
        elif args.cmd == "validate-customerio-action":
            action = _load_json_arg(args.action_json)
            out = {
                "decision": validate_customerio_action(action).as_dict(),
                "approval_pack": build_approval_pack(action),
            }
        elif args.cmd == "draft-intervention":
            out = store.draft_intervention(args.cohort_id, _load_json_arg(args.intervention_json))
        elif args.cmd == "approve-intervention":
            out = store.approve_intervention(args.cohort_id, args.intervention_id, args.approved_by)
        elif args.cmd == "reject-intervention":
            out = store.reject_intervention(args.cohort_id, args.intervention_id, args.approved_by, args.reason)
        elif args.cmd == "execute-intervention":
            cio_executor = None
            if args.execute_live:
                from pmf_os.customerio_exec import make_live_executor

                cio_executor = make_live_executor()
            out = store.execute_intervention(
                args.cohort_id, args.intervention_id,
                cio_executor=cio_executor, customerio_ref=args.customerio_ref,
            )
            if isinstance(out, dict) and out.get("status") == "executed":
                out["queue_resolution"] = store.resolve_queue_for_intervention(args.cohort_id, args.intervention_id)
        elif args.cmd == "record-intervention-outcome":
            out = store.record_intervention_outcome(args.cohort_id, args.intervention_id, _load_json_arg(args.outcome_json))
        elif args.cmd == "list-interventions":
            out = {"interventions": store.list_interventions(args.cohort_id, approval_status=args.status)}
        elif args.cmd == "draft-queue-interventions":
            copy_drafter = None
            if args.draft_copy_live:
                from pmf_os.queue_actions import default_copy_drafter

                copy_drafter = default_copy_drafter()
            out = {"drafted": store.draft_interventions_for_open_queues(args.cohort_id, copy_drafter=copy_drafter)}
        elif args.cmd == "end-cohort-memo":
            narrator = None
            if args.narrate_live:
                from pmf_os.end_cohort import default_narrator

                narrator = default_narrator()
            out = store.build_end_cohort_report(args.cohort_id, narrator=narrator, artifact_root=args.artifact_root)
        elif args.cmd == "weekly-digest":
            narrator = None
            if args.narrate_live:
                from pmf_os.weekly_digest import default_narrator

                narrator = default_narrator()
            out = store.build_weekly_digest_report(
                args.cohort_id, narrator=narrator, week_start=args.week_start, artifact_root=args.artifact_root,
            )
        elif args.cmd == "run-cohort-day":
            from pmf_os.orchestrator import run_cohort_day

            slack_sender = None
            if args.deliver:
                from pmf_os.slack_delivery import make_live_sender

                slack_sender = make_live_sender()
            daily_narrator = None
            if args.briefing_live:
                from pmf_os.daily_briefing import default_narrator

                daily_narrator = default_narrator()
            out = run_cohort_day(
                store,
                args.cohort_id,
                args.date,
                do_intake=not args.no_intake,
                render=not args.no_render,
                slack_sender=slack_sender,
                slack_channel=args.slack_channel,
                daily_narrator=daily_narrator,
            )
        else:
            parser.error(f"unknown command {args.cmd}")
            return 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "type": exc.__class__.__name__}, indent=2), file=sys.stderr)
        return 1

    print(json.dumps({"ok": True, "result": out}, indent=2, sort_keys=True, default=str))
    return 0


def _load_json_arg(value: str) -> Any:
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)


def _load_events_file(path: str) -> list[dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("["):
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("events JSON must be an array")
        return data
    events = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError(f"JSONL line {line_no} is not an object")
        events.append(item)
    return events


if __name__ == "__main__":
    raise SystemExit(main())
