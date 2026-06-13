"""user_casefile — `!case <id>`: a beautiful User Case File DOCX.

Deterministic generator (NOT LLM-hand-built): it shells the proven
user-profile-360 `lookup.py` for the structured summary, maps that summary into a
DocFlow spec, and renders + validates + stores + delivers a DOCX via the generic
Artifact Service (lib/alaska_artifacts). The `!case` command-gateway path invokes
this CLI and relays the result.

Privacy: the case file contains real financial PII. Delivery policy (2026-06-05):
it is posted to the channel the command was run in (`ctx['channel']`), NOT a DM by
default — so running `!case` in a shared channel posts PII there. The gateway passes
the invoking channel; the file is never broadcast beyond that channel.

Pipeline:  lookup.py(user_id) -> summary -> build_casefile_docflow() ->
           render_docx_from_docflow -> validate_docx -> store_artifact ->
           upload_artifact_to_slack

CLI:
  PYTHONPATH=/opt/lib python3 -m alaska_capabilities.user_casefile \
    --user-id 1414 --requester-slack-id U07GKLVA9FE --channel-id D0ANP0LQM44
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

# The Artifact Service (generic engine). /opt/lib is on PYTHONPATH in the image.
from alaska_artifacts import (
    render_docx_from_docflow,
    store_artifact,
    upload_artifact_to_slack,
    validate_docx,
)

DEFAULT_SKILLS_DIR = os.environ.get("ALASKA_SKILLS_DIR", "/data/skills")
OWNER_SKILL = "user-casefile"
ACCENT = "1F4E79"

# PMF cross-pointer (best-effort). Same env/default as pmf_os.store.DEFAULT_DB_PATH so
# `!case` and the PMF workstream read the one cohort DB. Used only by
# pmf_cohort_pointer(), which imports pmf_os lazily and swallows every fault — an
# absent/unreadable file here simply means "no pointer".
PMF_DB_PATH = os.environ.get("PMF_DB_PATH", "/data/queue/alaska_pmf.db")


# --------------------------------------------------------------------------
# value formatting (null-safe; dormant users have many None fields)
# --------------------------------------------------------------------------

DASH = "—"  # em dash used ONLY as the "no value" marker in tables


def _txt(v: Any) -> str:
    if v is None or v == "":
        return DASH
    return str(v)


def _money(v: Any) -> str:
    try:
        return "${:,.2f}".format(float(v))
    except (TypeError, ValueError):
        return DASH


def _int(v: Any) -> str:
    try:
        return "{:,}".format(int(v))
    except (TypeError, ValueError):
        return DASH


def _pct(v: Any) -> str:
    """Format a ratio as a percent. Utilization/APR arrive as either a fraction
    (0.62) or an already-percent number (62). The >1.5 normalization MIRRORS
    user-profile-360 summarizer._util_band exactly, so the percent we print can
    never contradict the utilization_band string it produces. Keep them in sync."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return DASH
    p = f * 100.0 if f <= 1.5 else f
    return "{:.1f}%".format(p)


def _yn(v: Any) -> str:
    if v is None:
        return DASH
    return "Yes" if v else "No"


def _join(parts: List[Any], sep: str = " · ") -> str:
    vals = [str(p) for p in parts if p not in (None, "")]
    return sep.join(vals) if vals else DASH


# --------------------------------------------------------------------------
# summary -> DocFlow spec  (pure function — unit-tested with a sample summary)
# --------------------------------------------------------------------------

def _kv_table(rows: List[List[str]], *, title: Optional[str] = None) -> Dict[str, Any]:
    block: Dict[str, Any] = {
        "type": "table",
        "columns": ["Field", "Value"],
        "rows": rows,
        "widths": [0.42, 0.58],
    }
    if title:
        block["title"] = title
    return block


def build_casefile_docflow(
    summary: Dict[str, Any],
    user_id: Any,
    *,
    served_stale: bool = False,
    notes: Optional[List[str]] = None,
    now: Optional[str] = None,
) -> Dict[str, Any]:
    """Map a user-profile-360 `summary` dict into a DocFlow spec. Pure + null-safe."""
    summary = summary or {}
    identity = summary.get("identity") or {}
    linking = summary.get("linking") or {}
    credit = summary.get("credit") or {}
    debt = summary.get("debt") or {}
    liquidity = summary.get("liquidity") or {}
    income = summary.get("income") or {}
    spending = summary.get("spending") or {}
    subs = summary.get("subscriptions") or {}
    chat = summary.get("chat") or {}
    meta = summary.get("_meta") or {}

    first_name = identity.get("first_name")
    title_who = first_name or ("User #%s" % user_id)
    date_str = (now or datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    blocks: List[Dict[str, Any]] = [
        {"type": "callout", "style": "warning",
         "text": "INTERNAL · contains financial PII. Do not share externally."},

        {"type": "heading", "level": 2, "text": "Identity"},
        _kv_table([
            ["First name", _txt(first_name)],
            ["Age", _txt(identity.get("age"))],
            ["Location", _txt(identity.get("location"))],
            ["Days since signup", _int(identity.get("days_since_signup"))],
            ["Platform", _txt(identity.get("platform"))],
        ]),

        {"type": "heading", "level": 2, "text": "Account linking"},
        _kv_table([
            ["Card linked", _yn(linking.get("card_linked"))],
            ["Bank linked", _yn(linking.get("bank_linked"))],
            ["Credit activated", _yn(linking.get("credit_activated"))],
        ]),

        {"type": "heading", "level": 2, "text": "Credit"},
        _kv_table([
            ["Score", _join([credit.get("score"), credit.get("score_band")])],
            ["Source", _txt(credit.get("source"))],
            ["Model", _txt(credit.get("model"))],
            ["Bureau", _txt(credit.get("bureau"))],
            ["As of", _txt(credit.get("as_of"))],
        ]),

        {"type": "heading", "level": 2, "text": "Debt"},
        _kv_table([
            ["Total card balance", _money(debt.get("total_cc_balance"))],
            ["Total card limit", _money(debt.get("total_cc_limit"))],
            ["Utilization", _join([_pct(debt.get("utilization")), debt.get("utilization_band")])],
            ["Weighted avg APR", _pct(debt.get("weighted_avg_apr"))],
            ["Est. monthly interest", _money(debt.get("monthly_interest"))],
            ["Total min payment", _money(debt.get("total_min_payment"))],
            ["Active cards", _int(debt.get("num_cards"))],
            ["Any card overdue", _yn(debt.get("any_overdue"))],
            ["Source", _txt(debt.get("source"))],
        ]),

        {"type": "heading", "level": 2, "text": "Liquidity"},
        _kv_table([
            ["Cash on hand", _money(liquidity.get("cash_on_hand"))],
            ["Low-balance risk", _yn(liquidity.get("low_balance_risk"))],
        ]),

        {"type": "heading", "level": 2, "text": "Income"},
        _kv_table([
            ["Monthly income", _money(income.get("monthly_income"))],
            ["Stability", _txt(income.get("stability"))],
            ["Source", _txt(income.get("source"))],
        ]),

        {"type": "heading", "level": 2, "text": "Spending"},
        _kv_table([
            ["Current month total", _money(spending.get("current_month_total"))],
            ["Source", _txt(spending.get("source"))],
        ]),
    ]

    top_cats = spending.get("top_categories") or []
    if top_cats:
        blocks.append({
            "type": "table", "title": "Top spending categories",
            "columns": ["Category", "Amount"], "widths": [0.6, 0.4], "align": ["left", "right"],
            "rows": [[_txt(c.get("category")), _money(c.get("amount"))] for c in top_cats],
        })

    blocks += [
        {"type": "heading", "level": 2, "text": "Subscriptions"},
        _kv_table([
            ["Active subscriptions", _int(subs.get("active_count"))],
            ["Monthly total", _money(subs.get("monthly_total"))],
        ]),

        {"type": "heading", "level": 2, "text": "Chat activity"},
        _kv_table([
            ["Total threads", _int(chat.get("total_threads"))],
            ["Real user turns", _int(chat.get("real_turns"))],
            ["Proactive turns", _int(chat.get("proactive_turns"))],
            ["Thumbs up", _int(chat.get("thumbs_up"))],
            ["Thumbs down", _int(chat.get("thumbs_down"))],
        ]),
    ]

    topics = chat.get("dominant_topics") or []
    if topics:
        blocks.append({
            "type": "table", "title": "Dominant chat topics",
            "columns": ["Topic", "Count"], "widths": [0.7, 0.3], "align": ["left", "right"],
            "rows": [[_txt(t.get("topic")), _int(t.get("count"))] for t in topics],
        })

    # Transparency footer.
    blocks.append({"type": "heading", "level": 2, "text": "Data sources"})
    present = ", ".join(meta.get("sections_present") or []) or DASH
    empty = ", ".join(meta.get("sections_empty") or []) or "none"
    blocks.append({"type": "paragraph", "text": "Sections with data: %s." % present})
    blocks.append({"type": "paragraph", "text": "Sections empty: %s." % empty})
    if served_stale:
        blocks.append({"type": "callout", "style": "muted",
                       "text": "Served from stale cache — the BON API was unreachable at generation time."})
    for note in (notes or []):
        blocks.append({"type": "callout", "style": "info", "text": str(note)})

    return {
        "meta": {
            "title": "User Case File — %s" % title_who,
            "subtitle": "BON Credit · internal user profile · #%s" % user_id,
            "author": "Alaska",
            "date": date_str,
            "format": "letter",
        },
        "options": {"accent_color": ACCENT, "font": "Calibri"},
        "blocks": blocks,
    }


# --------------------------------------------------------------------------
# lookup (subprocess to the proven user-profile-360 entry point)
# --------------------------------------------------------------------------

def run_lookup(
    user_id: Any,
    requester_slack_id: str,
    *,
    requester_authority: str = "engineer",
    channel_type: str = "dm",
    channel_id: Optional[str] = None,
    skills_dir: Optional[str] = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """Shell user-profile-360/lookup.py for the headline summary. Returns its
    parsed JSON, or {status:'generator_error', message} if the call itself fails.

    channel_type/channel_id are recorded in lookup's audit log (it does not gate
    on them) — pass the real channel the command came from for an honest trail."""
    skills_dir = skills_dir or DEFAULT_SKILLS_DIR
    script = os.path.join(skills_dir, "user-profile-360", "lookup.py")
    cmd = [
        sys.executable, script,
        "--query", str(user_id), "--query-type", "user_id",
        "--intent", "case_file",
        "--requester-slack-id", requester_slack_id,
        "--requester-authority", requester_authority,
        "--channel-type", channel_type or "dm",
    ]
    if channel_id:
        cmd += ["--channel-id", channel_id]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "generator_error", "message": "lookup failed to run: %s" % exc}
    try:
        return json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        msg = (proc.stderr or proc.stdout or "no output").strip()[:400]
        return {"status": "generator_error", "message": "lookup produced no JSON: %s" % msg}


# --------------------------------------------------------------------------
# PMF cohort cross-pointer (best-effort, fully isolated)
# --------------------------------------------------------------------------

def pmf_cohort_pointer(user_id: Any, *, pmf_db_path: Optional[str] = None) -> str:
    """One-line pointer from the general 360 case file (`!case <id>`) to the PMF
    cohort case file (`!pmf user <id>`) — returned IFF this BON user is a member of
    the ACTIVE PMF cohort, else "".

    Best-effort and fully isolated: it never raises and never blends PMF data into
    the 360. If pmf_os isn't importable, the alaska_pmf.db is absent/unreadable, or
    anything else goes wrong, it returns "" so the 360 case file is never broken or
    delayed. pmf_os.store is imported LAZILY (inside the try) so this capabilities
    module keeps NO import-time dependency on the PMF workstream — see the
    module-level isolation test in tests/test_user_casefile.py.
    """
    try:
        db_path = pmf_db_path or PMF_DB_PATH
        if not os.path.exists(db_path):
            return ""  # PMF not set up here — add nothing.
        from pmf_os.store import PmfStore  # lazy: no import-time workstream dependency
        membership = PmfStore(db_path).get_active_cohort_membership(user_id)
        if not membership:
            return ""  # not a cohort member, or no active cohort.
        stage = membership.get("current_stage") or "unknown"
        return ("→ This user is also in the active PMF cohort (stage: %s). "
                "For their PMF cohort case file, run `!pmf user %s`." % (stage, user_id))
    except Exception:
        # A PMF lookup fault must NEVER break or delay the 360 case file.
        return ""


# --------------------------------------------------------------------------
# orchestrate: lookup -> docflow -> docx -> store -> upload
# --------------------------------------------------------------------------

def generate(
    user_id: Any,
    requester_slack_id: str,
    *,
    requester_authority: str = "engineer",
    channel_id: Optional[str] = None,
    channel_type: str = "dm",
    thread_ts: Optional[str] = None,
    lookup_result: Optional[Dict[str, Any]] = None,
    skills_dir: Optional[str] = None,
    base_dir: Optional[str] = None,
    out_dir: Optional[str] = None,
    token: Optional[str] = None,
    http_request: Optional[Callable] = None,
    deliver: bool = True,
    run_id: Optional[str] = None,
    now: Optional[str] = None,
    pmf_db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Produce (and optionally deliver) the user case file. Never raises; returns
    a structured result. `lookup_result` can be injected to bypass the subprocess
    (tests). If `deliver` and `channel_id`, uploads the file to that channel."""
    res = lookup_result if lookup_result is not None else run_lookup(
        user_id, requester_slack_id, requester_authority=requester_authority,
        channel_type=channel_type, channel_id=channel_id, skills_dir=skills_dir)
    status = res.get("status")
    if status != "ok":
        # not_found / multiple / no_data / invalid / auth_error / api_error / ...
        return {"ok": False, "status": status, "user_id": res.get("user_id", user_id),
                "message": res.get("message") or "lookup returned status=%s" % status,
                "matches": res.get("matches")}

    summary = res.get("summary") or {}
    spec = build_casefile_docflow(
        summary, res.get("user_id", user_id),
        served_stale=bool(res.get("served_stale")), notes=res.get("notes"), now=now)

    rid = run_id or (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6])
    work = out_dir or tempfile.mkdtemp(prefix="casefile_")
    out_path = os.path.join(work, "user-casefile-%s.docx" % res.get("user_id", user_id))

    try:
        render = render_docx_from_docflow(spec, out_path)
    except Exception as exc:  # DocflowValidationError or any render fault
        return {"ok": False, "status": "render_error", "user_id": res.get("user_id", user_id),
                "message": "failed to render case file: %s" % exc}

    # Delivery gate. check_placeholders=False: this is rendered from a model, not a
    # template, so any "[...]" in real data (e.g. a chat topic) is content, not a
    # leftover placeholder.
    gate = validate_docx(render["path"], check_placeholders=False)
    if not gate["ok"]:
        return {"ok": False, "status": "validation_failed", "user_id": res.get("user_id", user_id),
                "message": "rendered case file failed validation: %s" % gate["errors"],
                "path": render["path"]}

    meta = store_artifact(render["path"], "docx", OWNER_SKILL, str(res.get("user_id", user_id)),
                          base_dir=base_dir, overwrite=True, now=now,
                          extra={"requester_slack_id": requester_slack_id, "run_id": rid})

    result: Dict[str, Any] = {
        "ok": True, "status": "ok", "user_id": res.get("user_id", user_id),
        "artifact_id": meta["artifact_id"], "path": meta["path"], "bytes": meta["bytes"],
        "served_stale": bool(res.get("served_stale")),
        "message": "User case file generated for #%s." % res.get("user_id", user_id),
    }
    if deliver and channel_id:
        uid = res.get("user_id", user_id)
        initial_comment = "Internal user case file (financial PII — do not forward)."
        # Best-effort cross-pointer to the PMF cohort case file (`!pmf user <id>`) when
        # this user is in the active PMF cohort. Disambiguates the two case-file surfaces
        # (`!case` = general 360, `!pmf user` = PMF funnel) without merging funnel data in.
        # pmf_cohort_pointer() swallows all faults, so it can never break/delay delivery.
        pointer = pmf_cohort_pointer(uid, pmf_db_path=pmf_db_path)
        if pointer:
            initial_comment += "\n" + pointer
            result["pmf_pointer"] = pointer
        up = upload_artifact_to_slack(
            meta["path"], channel_id, thread_ts=thread_ts,
            title="User Case File — #%s" % uid,
            initial_comment=initial_comment,
            token=token, http_request=http_request)
        result["slack"] = up
        result["delivered"] = bool(up.get("ok"))
    return result


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="alaska_capabilities.user_casefile",
                                 description="/alaska user <id> — build + deliver a User Case File DOCX")
    ap.add_argument("--user-id", required=True)
    ap.add_argument("--requester-slack-id", required=True)
    ap.add_argument("--requester-authority", default="engineer",
                    choices=["admin", "founder", "engineer", "system", "unknown"])
    ap.add_argument("--channel-id", default=None, help="Slack channel/DM to deliver to (omit to skip delivery)")
    ap.add_argument("--channel-type", default="dm", help="channel|dm|group — recorded in lookup's audit log")
    ap.add_argument("--thread-ts", default=None, help="post the file into this Slack thread, if set")
    ap.add_argument("--no-deliver", action="store_true")
    args = ap.parse_args(argv)

    result = generate(
        args.user_id, args.requester_slack_id,
        requester_authority=args.requester_authority,
        channel_id=args.channel_id,
        channel_type=args.channel_type,
        thread_ts=args.thread_ts,
        deliver=not args.no_deliver,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
