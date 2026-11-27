# System review — BGV Scheduling (26 Nov 2026)

A review of the whole suite as it stands, the target it should move to, and
the order of work. Companion documents: `docs/DATA_MODEL.md` (the database),
`docs/CLOUDFLARE_MIGRATION.md` (the no-outage switch-over steps).

Measurements below were taken on `origin/main` at `614fb8b`.

## 1. What the system is

| Part | Where it runs | What it does |
|---|---|---|
| Web app | Streamlit Community Cloud | sign-in, Generate, Reassign, My Rooms, My Home, Front Desk, Property, Report, Stats, Forecast, Admin, HotSOS page |
| Database | Supabase (Postgres, free) | 6 tables; one of them (`app_settings`) holds 86 kinds of data as JSON |
| Office PC agent | `hotsos_agent.py` on GC8HSKP26-03 | 5 AM build, 5:30 HotSOS push, status mirror every 2 min, SSRS + forecast, SharePoint, Teams notes, watchdog |
| Backup agent | `hotsos_agent.py backup` on this PC | stands in when the office heartbeat is over 3 min old |
| Android app | WebView over the Streamlit site | retired with Streamlit; the new site installs from Chrome |
| Company side | M365, Power Automate, Office Script, HotSOS | outside the codebase |

The design has real strengths worth keeping: one module owns database
access (`db.py`), "one writer per kind of data" (CLAUDE.md, 21 Nov), a
single floor snapshot for every page (`floor.today()`), a free-plan meter
(`freetier.py`), service passwords sealed per PC (`credentials.py`), and a
93-test suite that passes with no database.

## 2. Findings

### 2.1 Architecture

| # | Finding | Consequence |
|---|---|---|
| A1 | **The office PC is a single point of failure** for the build, the push, the mirror and SSRS. The backup PC covers part of it; SSRS needs the office network. | 31 Oct: a Windows Update reboot took it down for 34 h. |
| A2 | **Phones poll.** Every page re-reads on a timer (10–30 s). | Load grows with every phone; updates arrive late. |
| A3 | **Jobs travel through settings keys** (`hotsos_push_request`, `day_rooms_request`, `cred_req_*`, …) that agents poll. | 12,000 polls a day for the push request alone; no history, no retry, no owner. |
| A4 | **Streamlit Cloud constraints leak into the design**: no cookies (session token in the URL), a deploy doesn't restart imported modules (the requirements.txt touch), the app sleeps (the Android app's wake-up button). | Workarounds that each cost code and attention. |
| A5 | **CI runs the tests but can't stop a deploy.** `tests.yml` runs the 93 tests on every push to `main`, but Streamlit deploys the same push regardless, and there is no lint step. | A failing push still reaches staff. |
| A6 | **Alerting rides on an unreliable scheduler.** `watchdog.yml` posts to Teams when the office PC goes quiet or the 5 AM build is missing — but GitHub drops scheduled runs (4–12 h gaps on 23–25 Nov), so each run stays up 5.5 h and starts the next. | Works, at the cost of a workaround; one break in the chain and alerts stop. |

### 2.2 Data

| # | Finding |
|---|---|
| D1 | `app_settings` is the real schema: **86 key families** in one key/value table — 302 sign-in sessions, 95 staff weeks (2.7 MB), per-person flags (`lang_*`, `staffchg_seen_*`), job requests and results, agent status, configuration, caches, and leftover test rows (`lang___pwtest_es__`). No constraints, no types, no history. |
| D2 | **The same thing is stored twice**: `schedule_full` and `schedule_log` both hold a day's plan; a person's name lives in `app_users`, `staff_directory`, `hotsos_attendants`, `hotsos_names`, `account_links`, `account_roles`. |
| D3 | **Room status keeps no history.** An upsert overwrites; timing reports reconstruct from timestamps. |
| D4 | A 2.1 MB copy of the staff workbook is stored in the database. |
| D5 | The role CHECK constraint can't be changed by the app's key, so a role lives in a side table (`account_roles`) until someone runs SQL. |
| D6 | Payloads are JSON strings inside a JSON column (double-encoded). |

### 2.3 Code (Python, 37,049 lines, 1,311 functions)

| # | Finding | Measure |
|---|---|---|
| C1 | **Very large functions.** 30 functions are radon grade F (complexity > 40), 17 grade E; 31 are over 100 lines. Worst: `assign_inspectors` (complexity 140, 328 lines), `forecast_panel` (111), Stats `health` (104), `app_sync.from_sheet` (103). | radon cc |
| C2 | **`cleaning_scheduler.py` is 7,502 lines** and mixes the sign-in, the Generate UI, the Reassign board and the scheduling algorithms. | |
| C3 | **Dead code.** `pack_fc_ordered` (297 lines) has no caller; vulture lists 20 more candidate unused functions (each to be confirmed — some are called from strings). | vulture |
| C4 | **Four Full Clean packers** (`pack_fc_ordered`, `pack_fc_sequential`, `fcpack.pack`, `fcsolve.pack`): one dead, the others an exact solver with heuristic fallbacks — legitimate, but not documented as one strategy. | |
| C5 | Little copy-paste: two duplicated blocks (config helpers in `hotsos_push.py` / `room_scores.py`; an Excel reader in two pages). | pylint R0801 |
| C6 | Lint is mostly clean: no undefined names; 36 closures defined in loops (B023 — the sample checked is called within the iteration, so harmless, but they should take arguments), 12 f-strings without placeholders, 8 `global` statements, 3 bare `except:`. | ruff |
| C7 | Dependencies: Streamlit pinned, the rest open-ended (`pandas>=2.0.0`). | |
| C8 | Tests: 93 pass in 107 s; good coverage of floor, rules, fairness, names; no tests for `db.py`, the agent loop or the HotSOS client. | unittest |

**What to clean, and what not to.** The Streamlit pages, `ui.py`, `session.py`,
`appmode.py` and the i18n wrappers are replaced page by page; polishing them
is wasted work. Clean-code effort goes to what survives: the scheduling core
(`fcpack`, `fcsolve`, `property_map`, `daystart`, `staffing`, the algorithms
inside `cleaning_scheduler.py`), the importers, the agents and `db.py`, and
the new Cloudflare code, which is written to standard from the first line.

### 2.4 Security

| # | Finding | Fix |
|---|---|---|
| S1 | Session token rides in the URL (`?k=`), so it lands in history, screenshots and shared links. | HttpOnly, Secure, SameSite cookie set by the Worker. |
| S2 | Permissions are enforced in page code. | Enforced in the API for every request. |
| S3 | Sign-in has a lockout but no bot check. | Turnstile after repeated failures (free). |
| S4 | The repo is public. | Private once it moves (no secrets were found in code or history). |
| S5 | The database key is all-powerful and shared by every process. | Per-client tokens: the Worker holds the database; agents get scoped API tokens. |

## 3. Cloudflare's free plan — what to use and what not to

| Feature (free allowance) | Use it for | Decision |
|---|---|---|
| Workers + static assets (100k requests/day; static files free) | the API and the installable site | **Use** |
| D1 (5 GB, 5M rows read, 100k written/day; Time Travel 7 days) | the database; Time Travel gives point-in-time restore for a week | **Use** |
| Durable Objects, SQLite (100k requests/day) | one live "floor" per property: phones hold a WebSocket and get changes pushed, instead of polling (A2) | **Use** |
| Cron Triggers (5 per account) | the watchdog every 5 minutes, reliably (replaces the self-restarting GitHub chain, A6); nightly retention; usage metering | **Use** |
| Web Push (a web standard; signed in the Worker) | alerts to managers (dead agent, failed push) and "your rooms changed" to housekeepers | **Use** |
| Turnstile | bot check on sign-in (S3) | **Use** |
| Workers Logs + Traces | structured logs and request traces | **Use** |
| Workers AI (10k neurons/day) | translate RQS notes EN↔ES; later the "Ask" assistant (guest names never sent) | **Later** |
| Queues (10k ops/day, 24 h retention) | agent jobs | **No** — a `jobs` table is inspectable, keeps history and the agents are outside Cloudflare |
| Workflows (3,000 steps/day) | orchestrating Generate | **No** for now — the jobs table covers it |
| KV (1,000 writes/day) | caching | **No** — D1 plus the Cache API is enough |
| R2 (10 GB; needs a card on file) | room photos, archive exports | **Optional** — needs Hari to add a card |
| Email Routing (needs a domain) | receive the 5 AM SSRS e-mail directly, removing a PC dependency (A1) | **Optional** — needs a domain (~$10/yr) and IT's forwarding rule |
| Access (Zero Trust, 50 users) | Microsoft sign-in for managers without writing OIDC | **Optional** — when IT agrees; app passwords stay for the rest |

## 4. Target design

```
 phones / desk / managers (installed site, EN/ES)
        │  HTTPS + one WebSocket
        ▼
 Worker "bgv" ── static pages (free) ── /api/* (typed, validated, role-checked)
        │                    │
        │ D1 binding         │ RPC
        ▼                    ▼
   D1 "bgv"  ◄──────── Durable Object "Floor" (one per property)
        ▲                    pushes changes to every open screen
        │ /api/agent/* (scoped token)
 office PC agent · backup agent · GitHub Actions job runner
   HotSOS · SSRS · SharePoint · Teams           (Generate when no PC is up)

 Cron: watchdog (alerts) · nightly retention · usage meter
```

Principles:

1. **The Worker owns the database.** Pages and agents talk to its API; only
   migrations change the schema. (During the switch-over, `db.py` reaches D1
   directly so the live app moves first with nothing else changing; each
   domain then moves behind the API as its pages move.)
2. **Live, not polled.** Writers notify the Floor object; it pushes to
   screens. A one-minute alarm catches anything missed.
3. **Jobs, not flags.** One `jobs` table: queued → claimed → done/failed, with
   who asked, who ran it and the result.
4. **History by default.** Room changes are appended to `room_events`;
   current state is kept beside it for fast reads.
5. **Ready for a second property.** Everything property-scoped carries
   `property_id`.
6. **Free plan by design, with a meter.** Usage is recorded daily and alerts
   fire at 70% of any limit.

## 5. Engineering standards (new code, and old code as it is touched)

- TypeScript `strict`; no `any`; binding types generated by `wrangler types`.
- Biome for lint and format; Vitest on the real Workers runtime
  (`@cloudflare/vitest-pool-workers`) with a local D1.
- Every API input validated (zod); one error shape; structured JSON logs.
- Python: ruff in CI; the 93 tests plus new ones run on every push; a
  golden-master test (Generate on stored days must produce the same charts)
  before any refactor of the scheduling core.
- Dependencies pinned to exact versions, updated on purpose.
- CI on GitHub Actions: lint, type-check, tests for both halves; deploy the
  Worker from `main` once the repo is in the organisation.
- Each decision recorded in §7 with its reason.

## 6. Order of work

| # | Work | Live effect |
|---|---|---|
| 1 | D1 copy + read measurement | done 26 Nov |
| 2 | Worker foundation to standard: tooling, CI, schema v2 migrations, API skeleton, sign-in, tests | done 26 Nov (deployed, 24 tests) |
| 3 | `db.py` D1 client + mode switch; Python dead code removed; ruff + tests in CI | one night deploy, switched off |
| 4 | Database switch: both → D1 (CLOUDFLARE_MIGRATION.md steps 3–4) | none (reversible) |
| 5 | Domain by domain onto schema v2 (accounts and sessions first), each with its pages | per domain, at night |
| 6 | Watchdog moves into the Worker's cron (once the database is D1); Floor object; Web Push | none |
| 7 | Scheduling core extracted from `cleaning_scheduler.py` under golden-master tests; F-grade functions split | none |
| 8 | Streamlit off, repo into the organisation, private | none |

## 7. Decisions

| Decision | Why |
|---|---|
| Cloudflare free plan, not Supabase + Streamlit | one platform, no sleep, real cookies, push updates, owner-neutral account for hand-over |
| D1 for the database | owner's choice; fits with 95% headroom on reads (measured) |
| Browser does the 200,000-round password step | Workers cap PBKDF2 at 100,000 rounds and allow 10 ms CPU; keeps every existing password |
| Repo moves last | Streamlit's address would change on a redeploy |
| Schema v2 arrives domain by domain | each move is small, at night and reversible; a big-bang schema change during the database switch would double the risk |
| Jobs table over Queues | history, inspection, no 24 h expiry, agents live outside Cloudflare |
| Durable Object for live updates | removes polling; the free plan covers it |
| Generate stays Python | OR-Tools can't run in a Worker; the office PC runs it, GitHub Actions when no PC is up |
