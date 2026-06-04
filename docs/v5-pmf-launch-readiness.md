# V5 PMF — Launch Readiness & Go/No-Go

**Status: correctness GREEN on real data; activation pending (set config → enable cron → clear 2 blockers).**

Validated end-to-end against the **20-Mar–20-May historical backfill (346 real users)**, run via Alaska on Railway (live read-only Amplitude + dev User-360). This is the record behind the launch decision; the operational specs live in `skills/pmf-cohort-os/SKILL.md`.

---

## §10 Go/No-Go scorecard (Rung C — 346 real users)

| Gate | Value | Verdict |
|---|---|---|
| Resolution rate (resolved / ingested) | 346/346 = **100%** | 🟢 |
| Enrich-failure rate (failed / resolved) | 0/346 = **0%** | 🟢 |
| Duplicate `bon_user_id` / `user_key` | 0 | 🟢 |
| Funnel monotonicity (signed_up ≥ … ≥ confirmed) | 346 ≥ 199 ≥ 114 ≥ 39 ≥ 7 ≥ 0 | 🟢 |
| Activation rate (activated+ / real_users) | 114/199 = **57.3%** | 🟢 (10–70) |
| Activated-saver rate (saver+ / real_users) | 39/199 = **19.6%** | 🟢 (just under 20 — **watch**) |
| Lover rate ((likely+confirmed) / real_users) | 7/199 = **3.5%** | 🟢 (<8) |
| `confirmed_lover` count (backfill) | **0** | 🟢 |
| Deferred metrics (`qualitative_positive_signal`, `retained_value`) set | 0 | 🟢 |
| Idempotency (new snapshots/transitions on identical re-run) | 0 (346/199 stable) | 🟢 |
| Orphans / impossible states | 0 | 🟢 |
| Live Customer.io send / unintended team-Slack post during testing | 0 | 🟢 |
| 10-user human sanity spot-check | **10/10 correct** | 🟢 |
| Projected daily runtime vs 600s cron budget | dev 2.58 s/user → over at *full* 1,000; **bounded by incremental enrichment** | 🟡 (mitigated — tune cap from prod latency) |

**Verdict: GO on correctness.** Funnel, metrics, idempotency, and delivery-safety are proven on real data. Two non-correctness items gate *full* activation (below).

---

## What was built + verified (testing-phase PRs)

| PR | Change |
|---|---|
| #103 | Guardrailed test-only wide signup window (enabled the 2-month backfill) |
| #105 | Idempotency fix — no no-op `recomputed` funnel transitions (re-run / daily stable) |
| #108 | Per-user enrich latency instrumentation (`run["latency"]`) |
| #109 | Incremental enrichment — daily cron enriches new + recently-moved + capped slow-refresh, not all 1,000 |
| #110 | Per-user wall-clock watchdog — a hung User-360 call can't stall the run |
| #111 | `intake_period` + `inactive_days` → **stuck_onboarding** + **at_risk** queues fire |
| #112 | `failed_link_attempts` via Amplitude (`add_card/bank_unsuccessful`) → **high_intent** queue fires |

All three friction queues now fire on real data; correctness held throughout (suite 151 → 177 green).

---

## Launch cohort config

The live launch cohort is a **normal ≤3-day window** (NOT `--allow-wide-window` — that's test-only). Create it with the incremental-enrichment config:

```bash
python3 lib/pmf_cohort_os.py --db /data/queue/alaska_pmf.db create-cohort \
  --cohort-id pmf-launch-<YYYYMMDD> --name "Launch cohort <window>" \
  --signup-window-start <T0> --signup-window-end <T0+3d> --activate \
  --config-json '{"enrichment": {"mode": "incremental", "active_window_days": 3, "slow_refresh_cap": 150}}'
```

- **`enrichment.mode = incremental`** — bounds the daily enrich to the moving subset. `slow_refresh_cap = 150` is sized **conservatively from the dev mean (2.58 s/user × 150 ≈ 387 s < 600 s)**; prod will be faster (less Amplitude fallback once 360 chat is full), so this is a floor — **tune it up from the first live day's measured latency.**
- **Thresholds: defaults** (no override). Rung C's distribution was green on the defaults — do not pre-tune. **Watch the saver rate** (19.6%, near the 20% seam) over the first days.

### ⚠️ Launch-burst sizing
`slow_refresh_cap` bounds the *dormant* refresh, but on the 3 signup days the **new-user first-reads (~330/day for a 1,000-in-3-days launch) are unavoidable**. At dev 2.58 s/user that's ~850 s (> budget); at a prod-projected ~1.5 s/user it's ~495 s (< budget). Mitigations, in order: (1) **measure prod per-user latency on day 1** (`run["latency"]`) before trusting the budget; (2) keep the **2nd intra-day pass** during the signup window (already in the skill's cron specs) to split the load; (3) if still over, chunk new-user enrichment across intra-day runs or raise that cron's timeout. Do not assume the dev number — confirm live.

---

## Activation sequence (launch day — gated on Abhinav's go)

1. **Create + activate** the launch cohort with the config above.
2. **Enable the daily cron(s)** in the **OpenClaw dashboard** (canonical — do NOT hand-edit `config/cron-jobs-backup.json`). Specs: `skills/pmf-cohort-os/SKILL.md` § *Cron activation* — daily `run-cohort-day --deliver --slack-channel <c> --briefing-live`, a 2nd pass during the signup window, and `judge-credgpt-reviews` after.
3. **Watch day 1:** resolution rate, funnel distribution, **per-user latency vs budget**, and which queues open. Compare to the Rung C baseline above.

---

## Remaining blockers / open items

- 🔴 **Customer.io suppression-check** — before ANY live `--execute-live` send, the live executor must implement + test + LOG a real suppression + frequency-cap check. Until then interventions stay drafted/human-approved and the only CIO path is the `no_executor` dry-run. (Gates live *sends*, not cohort activation.)
- 🟡 **`slow_refresh_cap` tuning** — needs the prod `profile`-only latency split (`run["latency"]`); 150 is a safe floor.
- 🟡 **Minors:** Phase-4 edge fixtures (empty cohort / garbled timestamp / tz boundary) and `summary --compact`.

## Known limitations (carry into launch)
- **CredGPT chat text** is dev-limited to ~10 curated users; activation uses the Amplitude message-count fallback for the rest (the Quality Observatory's text review is curated-10 until prod 360 chat is full).
- **`inactive_days`** is a chat-activity proxy (defensible for a CredGPT-centric cohort; `at_risk` also requires `is_real_user`).
- **`failed_link_attempts`** requires the Amplitude key present (gated; no-ops cleanly without it).
- **Deferred metrics** (`qualitative_positive_signal`, `retained_value`) are never set — they await the end-of-cohort survey.
