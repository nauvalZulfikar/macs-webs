# Postmortem: MACS web backend unreachable (~5 min)

**Date:** 2026-06-19
**Incident window:** 07:42:22Z – 07:47:43Z (reported 5m8s; see caveat in Detection)
**Severity:** Sev-3 (single-node API unreachable, no data loss observed)
**Service:** MACS web backend (`http://127.0.0.1:8101`, also `100.81.47.91:8101` via Tailscale)
**Author:** incident-retro agent + shaka
**Status:** Resolved

## Summary

The MACS web backend stopped accepting connections for roughly five minutes on
2026-06-19. The health-check probe could not establish a TCP connection
(curl exit, HTTP status `000000`) at the 07:42Z probe and saw a healthy `200`
again at the 07:47Z probe. No code change landed in the `macs` repo during the
outage window, and the failure mode (connection refused, not a 5xx from a live
server) indicates the backend process was not listening rather than serving
errors. This is **one instance of a recurring pattern** — at least 11
DOWN→RECOVERED cycles appear in the health-check log between 2026-06-11 and
2026-06-19, the majority reporting ~5 minutes. Root cause is **undetermined
from available telemetry**; candidate causes are listed below.

## Impact

- MACS web API (`/api/*`) and any Tailnet client (HP at `100.81.47.91:8101`)
  could not reach the backend for the duration. New chat spawns, polling, and
  mission control calls issued in that window would have failed with connection
  refused.
- No data-loss signal: the failure was at the listener/connection layer
  (`HTTP 000000`), and the next probe returned `200`. Database state impact was
  **not captured in available telemetry** — no DB integrity check is run on
  recovery.
- User-facing impact scope (whether anyone actually hit the API in that window)
  is **not captured in available telemetry** — there is no request-level access
  log referenced here.

## Timeline (UTC)

| Time (UTC) | Event | Source |
|------------|-------|--------|
| 2026-06-19 07:23:48Z | Last `macs` repo commit before outage: `0283738` "feat(chat): verify_url+verify_what inputs + inline verdict display (#164/#165)" — ~19 min prior, not in outage window | git log (AuthorDate 09:23:48+02:00) |
| 2026-06-19 07:42:22Z | Health-check probe fails: `DOWN — HTTP 000000 · body:` (empty body, TCP connect failure) | macs-healthcheck.log (`[2026-06-19 09:42]`, local +0200) |
| 2026-06-19 07:42–07:47Z | Backend unreachable; no intermediate "still DOWN" line logged (probe interval is 300s, so only one failing probe was recorded) | macs-healthcheck.log |
| 2026-06-19 07:47:43Z | Health-check probe succeeds: `RECOVERED — back to 200 after 5m8s` | macs-healthcheck.log (`[2026-06-19 09:47]`) |
| 2026-06-19 07:47:xxZ | Autosnapshot launchd run executes against *other* projects (TradingAgents, astrocode, career-ops, …); unrelated to backend restart | macs-autosnapshot.log (`[2026-06-19 09:47]`) |
| 2026-06-19 07:47:xxZ | `auto-incident-retro spawned in MACS pid=2, stream=da27de8c` | macs-healthcheck.log |

> Note on clock: the health-check and autosnapshot logs record **local wall-clock
> time (CEST, +0200)**; git AuthorDates are also +0200. All times in this table
> are converted to UTC to match the incident facts (`07:42:22Z`–`07:47:43Z`).

## Root Cause — UNDETERMINED

Available telemetry is insufficient to name a single root cause. What the logs
*do* establish:

- The failure was **connection-level**: `HTTP 000000` with an empty body is a
  curl connect failure, i.e. nothing was listening on `127.0.0.1:8101`. It was
  **not** a live server returning 5xx.
- **No `macs` code deploy coincides with the window.** The nearest preceding
  commit (`0283738`) is ~19 minutes earlier; the next commits land later and
  outside the window. A bad-deploy crash-loop is therefore not directly
  supported by the commit timeline (though `0283738` is the newest code the
  process would have been running).
- This is **recurring**: 11+ DOWN/RECOVERED cycles since 2026-06-11, most
  reporting ~5 minutes, all with `HTTP 000000`. A repeating ~5-minute
  unreachability strongly suggests a **periodic process restart/respawn** or an
  external dependency blip rather than a one-off crash tied to this date.

Candidate causes (ranked, none confirmed):

1. **Scheduled / supervised process restart.** Something restarts or reloads the
   backend on a cadence, and the listener is unavailable during restart. The
   regularity of ~5-minute outages across days fits this best. Not confirmed —
   no restart/supervisor log was located in available telemetry.
2. **Backend crash + auto-respawn (launchd KeepAlive or similar).** A crash that
   is automatically restarted would also produce a short connection-refused gap.
   The crash trigger is **not captured** — no backend stderr/crash log was
   referenced here.
3. **Host-level resource pressure** (e.g. memory pressure, swap, or a competing
   batch job) briefly killing or freezing the listener. Not captured — no host
   metrics (CPU/RAM/load) are in the consulted logs.
4. **Transient port/bind contention** on `:8101` during a redeploy or manual
   restart that happened outside git (e.g. `npm run build` + restart). Not
   captured — no deploy/restart audit log.

## Detection

- Detected automatically by `com.shaka.macs-healthcheck` (launchd, `StartInterval
  = 300`s). The probe at 07:42Z recorded the failure; the probe at 07:47Z
  recorded recovery.
- An `auto-incident-retro` workflow was spawned on recovery (stream
  `da27de8c`), so the alerting/automation chain fired as designed.

**Critical caveat on the "5m8s" figure:** the probe runs every 300 seconds, so
the *minimum observable* outage is one probe interval. Across the historical log,
the overwhelming majority of recoveries read 5m0s–5m16s — this clustering is an
**artifact of probe granularity**, not measured truth. True downtime for this
incident is bounded as: **greater than 0s and at most ~5 minutes**, with `5m8s`
being the probe-to-probe delta rather than the real process-down duration.

## Resolution

- The backend recovered on its own — by the 07:47:43Z probe it was serving `200`
  again. No manual intervention is recorded in the consulted telemetry.
- No rollback occurred and none was warranted (no offending deploy identified).

## What Went Well

- Automated detection worked: the outage was caught and logged without a human
  watching, and an incident-retro automation was triggered on recovery.
- The failure signature is **consistent and machine-readable** (`HTTP 000000`),
  which made it easy to distinguish "process down" from "process erroring."
- No data-loss signal surfaced; recovery was fast (≤5 min) and self-healing.

## What Went Wrong

- **Root cause is not diagnosable from current telemetry.** There is no backend
  process log, no restart/supervisor log, and no host-metrics snapshot tied to
  the outage timestamp, so the postmortem cannot name a cause.
- **This is a recurring, unactioned pattern.** 11+ near-identical outages over 8
  days have been logged but not driven to a fix — the system normalizes a
  repeating ~5-minute unreachability.
- **Probe granularity (300s) hides true severity.** Every short outage looks like
  "~5 minutes," so it is impossible to tell a 3-second blip from a genuine
  5-minute outage. This both over- and under-states impact.
- **No request-level visibility.** There is no access log to confirm whether any
  client actually failed a call during the window, so blast radius is unknown.

## Action Items

| # | Action | Owner | Concrete step | Due | Done |
|---|--------|-------|---------------|-----|------|
| 1 | Capture backend process logs to a fixed path | @shaka | Redirect backend stdout/stderr to `~/Library/Logs/macs-backend.log` (or via the launchd plist `StandardErrorPath`); confirm a crash/restart leaves a line there | 2026-06-26 | [ ] |
| 2 | Identify the restart/respawn source | @shaka | Check whether `:8101` is run under a launchd plist with `KeepAlive`/`ThrottleInterval`, a cron, or a watcher; if a periodic restart exists, document its cadence and reconcile it against the outage timestamps | 2026-06-26 | [ ] |
| 3 | Tighten probe granularity during/after a failure | @shaka | On a `DOWN` result, have the health-check retry every 15–30s until recovery and log each attempt, so true downtime is measured instead of rounded to the 300s interval | 2026-06-26 | [ ] |
| 4 | Add a recovery integrity check | @shaka | On `RECOVERED`, hit one read endpoint (e.g. `GET /api/projects` with the service cookie) and log row/count sanity, to convert "no data-loss signal" into "verified no data loss" | 2026-06-30 | [ ] |
| 5 | Investigate the recurring pattern as its own item | @shaka | Open a tracking issue listing the 11 historical DOWN/RECOVERED cycles; treat the *pattern* (not this single instance) as the thing to eliminate | 2026-06-23 | [ ] |
| 6 | Add minimal request/host telemetry | @shaka | Enable a backend access log and a lightweight host-metrics sample (load/RAM) so the next occurrence is diagnosable rather than undetermined | 2026-07-03 | [ ] |

## Lessons Learned

1. **A monitor's resolution is a hard floor on what you can know.** A 5-minute
   probe can only ever report 5-minute-granular outages; the "5m8s" here is the
   sampling interval, not the incident length. Match probe cadence to the
   severity you need to distinguish.
2. **Recurring small outages are an incident, not noise.** Eleven self-healing
   ~5-minute blips logged without follow-up is a louder signal than any single
   one — the pattern deserves a root-cause hunt more than the instance does.
3. **You can only do a real postmortem on data you collected before the
   incident.** The single biggest gap here is the absence of backend process and
   restart logs; everything downstream ("undetermined root cause") follows from
   that missing instrumentation.
