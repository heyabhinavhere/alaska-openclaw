"""Daily orchestrator for PMF Cohort OS.

`run_cohort_day` is the single idempotent, partial-failure-tolerant pass that
turns the collectors + store into an actual operating loop:

    intake (Amplitude)  ->  enrich + snapshot each user (User 360 -> funnel)
        ->  refresh CredGPT quality clusters  ->  render team cockpit + Slack summary

Every store write is an upsert, so re-running a day is safe (idempotent). One
user's API error is captured and skipped — it never sinks the whole run. The
collectors are injectable, so the loop is fixture-tested with no live API calls.

This module does NOT schedule itself. Wiring `run-cohort-day` to a cron is a
separate, explicit activation step — it is the first V5 component that would run
on a schedule in prod and hit live APIs.

Deferred to P3.1 (noted, not built here): the Amplitude *activity* fetch that
backfills `gp:user_id` for users keyed only by `amplitude_id`. Until then such
users are counted as "unresolved" for the run rather than failed.
"""

from __future__ import annotations

from typing import Any, Callable

from .collectors import amplitude, user360
from .store import DEFAULT_ARTIFACT_ROOT


def run_cohort_day(
    store: Any,
    cohort_id: str,
    snapshot_date: str,
    *,
    do_intake: bool = True,
    render: bool = True,
    artifact_root: str = DEFAULT_ARTIFACT_ROOT,
    export_fetcher: Callable | None = None,
    search_fetcher: Callable | None = None,
    profile_fetcher: Callable | None = None,
    summarize_fn: Callable | None = None,
    segmentation_fetcher: Callable | None = None,
) -> dict[str, Any]:
    """Run one full cohort day. Returns a structured run record (never raises for
    per-user/per-step failures — they're captured in `errors`)."""
    run: dict[str, Any] = {
        "cohort_id": cohort_id,
        "snapshot_date": snapshot_date,
        "intake": None,
        "users": {"total": 0, "enriched": 0, "unresolved": 0, "failed": 0},
        "clusters": 0,
        "turns_ingested": 0,
        "amplitude_fallback_used": 0,
        "report": None,
        "summary": {},
        "errors": [],
    }
    cohort = store.get_cohort(cohort_id)

    # 1. Intake — refresh the registry from Amplitude (idempotent; skippable when
    #    the operator already ran ingest-cohort).
    if do_intake:
        try:
            events = amplitude.fetch_signup_events(
                cohort["signup_window_start"],
                cohort["signup_window_end"],
                export_fetcher=export_fetcher,
            )
            run["intake"] = store.ingest_signup_events(cohort_id, events)
        except Exception as exc:  # noqa: BLE001 - capture, never sink the run
            run["errors"].append({"step": "intake", "error": str(exc)})

    # 2. Enrich + snapshot each registry user (one bad user never sinks the run).
    users = store.list_users(cohort_id)
    run["users"]["total"] = len(users)
    for row in users:
        key = row.get("user_key")
        try:
            resolved = user360.resolve_bon_user_id(row, search_fetcher=search_fetcher)
            if resolved["status"] != "resolved":
                run["users"]["unresolved"] += 1
                continue
            fetched = user360.fetch_profile(resolved["user_id"], profile_fetcher=profile_fetcher)
            if fetched["status"] != "ok":
                run["users"]["failed"] += 1
                run["errors"].append({"user_key": key, "step": "fetch_profile", "error": fetched["status"]})
                continue
            enriched = user360.enrich_facts(fetched["payload"], summarize_fn=summarize_fn)
            facts = enriched["daily_facts"]
            # Activation fallback: if User 360 chat is thin/empty, use Amplitude's
            # message count (the canonical engagement metric) so the funnel stages
            # correctly. Validated need — User 360 chat can be incomplete.
            if not facts.get("meaningful_credgpt_messages"):
                try:
                    count = amplitude.fetch_message_count(
                        resolved["user_id"], cohort["signup_window_start"], snapshot_date,
                        segmentation_fetcher=segmentation_fetcher,
                    )
                    if count:
                        facts["meaningful_credgpt_messages"] = count
                        run["amplitude_fallback_used"] += 1
                except Exception as exc:  # noqa: BLE001 - fallback is best-effort
                    run["errors"].append({"user_key": key, "step": "amplitude_fallback", "error": str(exc)})
            store.update_user_profile(cohort_id, key, enriched["profile_facts"])
            store.apply_daily_snapshot(cohort_id, key, snapshot_date, facts)
            run["users"]["enriched"] += 1
            # Ingest the user's real chat turns into the CredGPT quality observatory.
            for idx, turn in enumerate(enriched.get("chat_turns") or []):
                try:
                    store.record_credgpt_turn(cohort_id, key, {
                        "thread_id": turn.get("thread_id"),
                        "turn_id": turn.get("turn_id") or f"{turn.get('thread_id')}:{idx}",
                        "event_time": turn.get("created_at"),
                        "question": turn.get("question"),
                        "answer": turn.get("answer"),
                    })
                    run["turns_ingested"] += 1
                except Exception as exc:  # noqa: BLE001 - one turn never sinks the user
                    run["errors"].append({"user_key": key, "step": "ingest_turn", "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            run["users"]["failed"] += 1
            run["errors"].append({"user_key": key, "step": "enrich", "error": str(exc)})

    # 3. Refresh CredGPT quality clusters from the turns ingested above. (The LLM
    #    quality judge on flagged turns is the P4.1 follow-up.)
    try:
        run["clusters"] = len(store.refresh_credgpt_clusters(cohort_id))
    except Exception as exc:  # noqa: BLE001
        run["errors"].append({"step": "clusters", "error": str(exc)})

    # 4. Aggregate summary for the Slack line (always — decoupled from rendering).
    try:
        run["summary"] = store.generate_report_snapshot(
            cohort_id, report_type="daily_cockpit", privacy_tier="team", snapshot_date=snapshot_date
        ).get("summary", {})
    except Exception as exc:  # noqa: BLE001
        run["errors"].append({"step": "summary", "error": str(exc)})

    # 5. Render the team cockpit (HTML; DOCX/PDF deferred per plan).
    if render:
        try:
            report = store.render_report_artifacts(
                cohort_id,
                report_id=f"daily-{snapshot_date}-team",
                report_type="daily_cockpit",
                privacy_tier="team",
                artifact_root=artifact_root,
                snapshot_date=snapshot_date,
                require_visual_qa=False,
            )
            run["report"] = {
                "report_id": report.get("report_id"),
                "status": report.get("status"),
                "html_path": report.get("html_path"),
            }
        except Exception as exc:  # noqa: BLE001
            run["errors"].append({"step": "report", "error": str(exc)})

    run["slack_summary"] = _slack_summary(run)
    return run


def _slack_summary(run: dict[str, Any]) -> str:
    summary = run.get("summary") or {}
    stage = summary.get("stage_counts") or {}
    activated = sum(
        stage.get(s, 0)
        for s in ("activated_user", "activated_saver", "likely_lover", "confirmed_lover")
    )
    users = run["users"]
    queue_total = sum((summary.get("queue_counts") or {}).values())
    lines = [
        f"PMF Cohort daily run · {run['snapshot_date']}",
        (
            f"Signups: {summary.get('total_signup_users', 0)} · "
            f"Real users: {summary.get('real_users', 0)} · "
            f"Activated+: {activated} · "
            f"Likely lovers: {stage.get('likely_lover', 0)}"
        ),
        (
            f"Enriched: {users['enriched']}/{users['total']} "
            f"(unresolved {users['unresolved']}, failed {users['failed']}) · "
            f"Open queues: {queue_total} · "
            f"Weak CredGPT: {summary.get('weak_credgpt_reviews', 0)}"
        ),
    ]
    if run["errors"]:
        lines.append(f"⚠️ {len(run['errors'])} step/user errors captured (see run record).")
    return "\n".join(lines)
