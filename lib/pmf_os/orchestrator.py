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

import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Callable

from .collectors import amplitude, user360
from .enrichment import resolve_enrichment_config, select_users_to_enrich
from .store import DEFAULT_ARTIFACT_ROOT
from .thresholds import resolve_thresholds


def _latency_stats(samples: list[float]) -> dict[str, Any]:
    """count + total/mean/p50/p95 (seconds) over a list of per-call durations.
    Nearest-rank percentiles, stdlib-only. Empty -> all zeros."""
    n = len(samples)
    if not n:
        return {"count": 0, "total_s": 0.0, "mean_s": 0.0, "p50_s": 0.0, "p95_s": 0.0}
    s = sorted(samples)

    def _pct(q: float) -> float:
        return s[min(n - 1, max(0, int(round(q * (n - 1)))))]

    return {
        "count": n,
        "total_s": round(sum(samples), 3),
        "mean_s": round(sum(samples) / n, 4),
        "p50_s": round(_pct(0.50), 4),
        "p95_s": round(_pct(0.95), 4),
    }


# A hard per-user wall-clock deadline. The HTTP fetchers have their own socket
# timeouts, but a hung/trickling server can outlast a socket read timeout — so each
# user's enrich runs under this deadline in a worker thread; exceeding it marks the
# user failed and moves on (incremental selection + idempotent snapshots re-try it
# next run). Env-overridable for ops.
ENRICH_USER_TIMEOUT_SECONDS = float(os.environ.get("PMF_ENRICH_USER_TIMEOUT_SECONDS", "120"))


def _enrich_one_user(
    store: Any,
    cohort_id: str,
    cohort: dict[str, Any],
    snapshot_date: str,
    row: dict[str, Any],
    *,
    thresholds: dict[str, int],
    search_fetcher: Callable | None,
    profile_fetcher: Callable | None,
    summarize_fn: Callable | None,
    segmentation_fetcher: Callable | None,
) -> dict[str, Any]:
    """Enrich + snapshot ONE user. Returns its own counters/latency/errors and never
    mutates shared run state, so it can run under a per-user deadline in a worker
    thread. Every store write opens its own connection (thread-safe under WAL)."""
    key = row.get("user_key")
    out: dict[str, Any] = {
        "status": "failed",
        "samples": {"resolve": [], "profile": [], "amplitude_fallback": [], "per_user_enrich": []},
        "fallback_used": 0,
        "turns_ingested": 0,
        "errors": [],
    }
    t_user = time.perf_counter()
    try:
        t0 = time.perf_counter()
        resolved = user360.resolve_bon_user_id(row, search_fetcher=search_fetcher)
        out["samples"]["resolve"].append(time.perf_counter() - t0)
        if resolved["status"] != "resolved":
            out["status"] = "unresolved"
            return out
        t0 = time.perf_counter()
        fetched = user360.fetch_profile(resolved["user_id"], profile_fetcher=profile_fetcher)
        out["samples"]["profile"].append(time.perf_counter() - t0)
        if fetched["status"] != "ok":
            out["errors"].append({"user_key": key, "step": "fetch_profile", "error": fetched["status"]})
            return out
        enriched = user360.enrich_facts(fetched["payload"], summarize_fn=summarize_fn, thresholds=thresholds, as_of_date=snapshot_date)
        facts = enriched["daily_facts"]
        # Activation fallback: if User 360 chat is thin/empty, use Amplitude's message
        # count (the canonical engagement metric) so the funnel stages correctly.
        if not facts.get("meaningful_credgpt_messages"):
            try:
                t0 = time.perf_counter()
                count = amplitude.fetch_message_count(
                    resolved["user_id"], cohort["signup_window_start"], snapshot_date,
                    segmentation_fetcher=segmentation_fetcher,
                )
                out["samples"]["amplitude_fallback"].append(time.perf_counter() - t0)
                if count:
                    facts["meaningful_credgpt_messages"] = count
                    out["fallback_used"] = 1
            except Exception as exc:  # noqa: BLE001 - fallback is best-effort
                out["errors"].append({"user_key": key, "step": "amplitude_fallback", "error": str(exc)})
        # Failed-link attempts aren't in the 360 profile — query Amplitude
        # (add_card_unsuccessful / add_bank_unsuccessful) for channels the user has
        # NOT linked, so the high_intent ("tried to link, failed, still unlinked")
        # queue fires. Gated to onboarded users (link attempts are post-onboarding)
        # to bound the extra segmentation calls.
        unlinked = [ch for ch in ("card", "bank") if not facts.get(f"{ch}_linked")]
        if unlinked and facts.get("onboarding_complete") and (segmentation_fetcher or amplitude.is_configured()):
            try:
                failed = amplitude.fetch_failed_link_attempts(
                    resolved["user_id"], cohort["signup_window_start"], snapshot_date,
                    channels=tuple(unlinked), segmentation_fetcher=segmentation_fetcher,
                )
                if failed:
                    facts["failed_link_attempts"] = [f"{ch}:link_failed" for ch in failed]
            except Exception as exc:  # noqa: BLE001 - best-effort
                out["errors"].append({"user_key": key, "step": "failed_link_fallback", "error": str(exc)})
        store.update_user_profile(cohort_id, key, enriched["profile_facts"])
        store.apply_daily_snapshot(cohort_id, key, snapshot_date, facts, thresholds=thresholds)
        out["status"] = "enriched"
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
                out["turns_ingested"] += 1
            except Exception as exc:  # noqa: BLE001 - one turn never sinks the user
                out["errors"].append({"user_key": key, "step": "ingest_turn", "error": str(exc)})
        out["samples"]["per_user_enrich"].append(time.perf_counter() - t_user)
        return out
    except Exception as exc:  # noqa: BLE001
        out["errors"].append({"user_key": key, "step": "enrich", "error": str(exc)})
        return out


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
    slack_sender: Callable | None = None,
    slack_channel: str | None = None,
    daily_narrator: Callable | None = None,
    enrich_user_timeout: float | None = None,
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
        "delivery": None,
        "briefing": None,
        "summary": {},
        "latency": {},
        "enrichment": {},
        "errors": [],
    }
    cohort = store.get_cohort(cohort_id)
    # Resolve the cohort's tunable funnel/metric thresholds once (config overrides ->
    # defaults), then thread them through enrich (metrics) + snapshot (funnel).
    thresholds = resolve_thresholds(cohort.get("config_json"))

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
    #    Per-call latency is sampled so the run record can decompose enrich cost
    #    (resolve / profile-fetch / Amplitude-fallback) — used to size the daily
    #    enrichment budget. Purely observational; no behavior change.
    # Incremental enrichment: in 'incremental' mode enrich only NEW + recently-moved
    # + a capped slow-refresh slice instead of the whole cohort (bounds daily load).
    # 'full' (default) enriches everyone — unchanged behavior.
    enrichment = resolve_enrichment_config(cohort.get("config_json"))
    all_users = store.list_users(cohort_id)
    users = select_users_to_enrich(all_users, snapshot_date, config=enrichment)
    run["users"]["total"] = len(users)
    run["enrichment"] = {
        "mode": enrichment["mode"],
        "registry_total": len(all_users),
        "selected": len(users),
        "skipped_not_due": len(all_users) - len(users),
    }
    lat: dict[str, list[float]] = {"resolve": [], "profile": [], "amplitude_fallback": [], "per_user_enrich": []}
    deadline = enrich_user_timeout if enrich_user_timeout is not None else ENRICH_USER_TIMEOUT_SECONDS
    for row in users:
        key = row.get("user_key")
        # Run each user under a hard wall-clock deadline so a hung User-360/Amplitude
        # call can't stall the whole run. A timed-out user is recorded failed and
        # re-tried next run (incremental selection + idempotent snapshots make it safe).
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            res = pool.submit(
                _enrich_one_user, store, cohort_id, cohort, snapshot_date, row,
                thresholds=thresholds, search_fetcher=search_fetcher,
                profile_fetcher=profile_fetcher, summarize_fn=summarize_fn,
                segmentation_fetcher=segmentation_fetcher,
            ).result(timeout=deadline)
        except FuturesTimeoutError:
            run["users"]["failed"] += 1
            run["errors"].append({"user_key": key, "step": "enrich_timeout",
                                  "error": f"exceeded {deadline}s per-user deadline"})
            continue
        finally:
            pool.shutdown(wait=False)  # never block on an abandoned hung worker
        run["users"][res["status"]] += 1  # 'enriched' | 'unresolved' | 'failed'
        run["amplitude_fallback_used"] += res["fallback_used"]
        run["turns_ingested"] += res["turns_ingested"]
        run["errors"].extend(res["errors"])
        for phase, samples in res["samples"].items():
            lat[phase].extend(samples)

    run["latency"] = {phase: _latency_stats(samples) for phase, samples in lat.items()}

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

    # 4.5 Founder briefing (the interpretation layer) — Alaska's read over the day's
    #     facts: what changed, who needs you, what I'd do. Best-effort + explicit:
    #     daily_narrator=None -> 'skipped' (no tokens spent), unchanged from before.
    try:
        from .daily_briefing import build_briefing_facts, generate_daily_briefing

        facts = build_briefing_facts(
            snapshot_date=snapshot_date,
            summary=run["summary"],
            movements=store.recent_funnel_transitions(cohort_id),
            open_queues=store.open_queue_items(cohort_id),
            quality={"weak_credgpt_reviews": (run["summary"] or {}).get("weak_credgpt_reviews", 0)},
            users=users,
        )
        run["briefing"] = generate_daily_briefing(facts, narrator=daily_narrator)
    except Exception as exc:  # noqa: BLE001 - best-effort, never sinks the run
        run["errors"].append({"step": "briefing", "error": str(exc)})

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

    # 6. Deliver to Slack (best-effort): post the summary line + upload the HTML
    #    cockpit. Injectable sender so the run is fixture-tested with no live Slack
    #    call; a delivery failure is captured, it never sinks the run.
    if slack_sender and slack_channel:
        try:
            html_path = (run.get("report") or {}).get("html_path")
            run["delivery"] = slack_sender(slack_channel, run["slack_summary"], html_path)
            briefing_text = _briefing_text(run)
            if briefing_text:
                run["briefing_delivery"] = slack_sender(slack_channel, briefing_text, None)
        except Exception as exc:  # noqa: BLE001 - delivery is best-effort
            run["delivery"] = {"ok": False, "error": str(exc)}
            run["errors"].append({"step": "deliver", "error": str(exc)})

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


def _briefing_text(run: dict[str, Any]) -> str | None:
    """Render the founder briefing narrative to a Slack message, or None when there's
    no completed narrative (skipped/failed -> nothing extra is posted)."""
    briefing = run.get("briefing") or {}
    if briefing.get("narrative_status") != "completed":
        return None
    n = briefing.get("narrative") or {}
    lines = [f"*PMF briefing · {run['snapshot_date']}*"]
    if n.get("headline"):
        lines.append(n["headline"])
    if n.get("what_changed"):
        lines.append("\n*What changed:*\n" + "\n".join(f"• {x}" for x in n["what_changed"]))
    if n.get("who_needs_you"):
        lines.append("\n*Who needs you:*\n" + "\n".join(
            f"• {w.get('user')}: {w.get('why')} → {w.get('suggested_action')}" for w in n["who_needs_you"]))
    if n.get("recommendations"):
        lines.append("\n*Recommend today:*\n" + "\n".join(f"• {x}" for x in n["recommendations"]))
    if n.get("watch"):
        lines.append("\n*Watch:*\n" + "\n".join(f"• {x}" for x in n["watch"]))
    return "\n".join(lines)
