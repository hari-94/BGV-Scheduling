# Moving BGV Scheduling to Cloudflare (free plan)

Plan agreed with Hari, 26 Nov 2026. Written for whoever runs or takes over the
suite: what moves, in what order, why nothing goes down, and how each step is
undone.

## The rule: no outages

1. **The current app keeps running, untouched, until nobody needs it.** The new
   app is built beside it on the same data, and people move across at their
   own pace by installing the new one from Chrome.
2. **Every switch is one setting and can be switched back.** No step depends
   on a rebuild or a new address to undo.
3. **Live changes happen at night** (after 10 PM, before the 2 AM archive), the
   way code reaches Streamlit today, and never on a day the office PC is down.
4. **Nothing is deleted until its replacement has run cleanly for two weeks.**

Two things follow from rule 1:

- **The repo stays at `hari-94/BGV-Scheduling` until Streamlit is switched
  off.** Streamlit Community Cloud tracks an app by its repo's owner and name.
  Moving the repo means deleting and redeploying the app, and the redeployed app
  gets a new generated address
  (today: `bgv-scheduling-qvt9nhbqqbusvbcpm7kidq.streamlit.app`), which breaks
  the Android app and every bookmark. Moved last, it costs nothing.
- **The Cloudflare code lives in the same repo**, on the `cloudflare` branch
  (folder `web/`) until it is ready, so Streamlit (which deploys `main`) never
  sees it.

## Where things are

| | Today | After |
|---|---|---|
| Screens | Streamlit Community Cloud | Cloudflare Worker + static pages, installable from Chrome |
| Database | Supabase (free) | Cloudflare D1 `bgv` (free, western North America) |
| Sign-in | app usernames + passwords | the same accounts and passwords; Microsoft 365 sign-in later, once IT agrees |
| Generate (OR-Tools), roster Excel parsing | the Streamlit server | Python jobs: the office PC takes them, GitHub Actions when it is off |
| HotSOS, SSRS, SharePoint, Teams, 5 AM build | office PC agent + backup PC | unchanged |
| Phones | Android WebView app | the new site installed from Chrome; the Android app is retired with Streamlit |
| Code | `hari-94/BGV-Scheduling` (public) | GitHub organisation `BGVgrandtimber` |

Accounts (all on the suite's own e-mail; it and its recovery details are in
the password vault, not in this public repo):

- Cloudflare: account `5203a9b813c556e90a14110cb9613e53`; Worker `bgv` at
  https://bgv.bgvgrandtimber.workers.dev; D1 database `bgv`
  (`f105d97e-4c45-45c1-84f2-1d00ee819f14`).
- GitHub: organisation `BGVgrandtimber` (owners: `bgvgrandtimber-boop`,
  `hari-94`). Android source: `BGVgrandtimber/bgv-android` (private). The
  organisation was created as belonging to the business "BGV".

## Does it fit the free plan? (measured 26 Nov)

| | Free limit | The app |
|---|---|---|
| Database size | 500 MB | 19.8 MB, ~6,500 rows |
| Rows written | 100,000 / day | a few thousand (heartbeat each minute, only changed rooms) |
| Rows read | 5,000,000 / day | **to be measured on the copy** — Cloudflare counts every row a query looks through |
| Worker requests | 100,000 / day | phones and the board only; static pages are free and unlimited |
| CPU per request | 10 ms | reading and saving fit; the solver and Excel parsing don't, so they stay Python |

Since 1 Sep 2026 D1 refuses queries for the rest of the UTC day (until 6 PM
Breckenridge time in winter) once a daily limit is passed, so reads must be
measured with real margin before the database switches, and metered after.

Today's database calls a day: office PC agent ~19,000, the app ~4,000, the
backup PC ~2,000. The Python side reaches D1 through Cloudflare's D1 REST API,
so these do not spend the Worker's 100,000 requests.

## The steps

Each step lists what proves it is done and how it is undone. Steps marked
**live** touch something people use and happen at night.

### Step 0 — accounts and skeleton (done 26 Nov)

Suite e-mail, Cloudflare account, workers.dev address, D1 database, GitHub
organisation, Android source in git, `web/` skeleton deployed (placeholder page
and `/api/health`). Nothing live touched.

### Step 1 — the database copy (no effect on the live app)

- D1 tables matching Supabase column for column (`web/migrations/0001_init.sql`).
- `web/tools/copy_from_supabase.py`: copies every table, checks row counts and
  a checksum per table, can be re-run any time (it replaces the copy).
- Payloads over 1 MB are stored compressed (`gz:` + base64): D1 refuses rows
  over 2 MB, and the stored staff-schedule workbook is 2.1 MB.
- Measure: replay a day of the agent's and the app's queries against the copy
  and read D1's own rows-read figures. Add indexes or reshape queries until a
  day's reads sit under **half** the free limit.

Done when: the copy matches Supabase and a day's measured reads are under 2.5 M.
Undo: delete the copy.

**Result, 26 Nov:** copied 6,471 rows, every table's checksum identical (12
rows too long for SQL text went in as bound values; the 2.1 MB workbook copy
went in compressed). Each of this month's query patterns, run on the copy,
times its call rate from the freetier meter: **~270,000 rows read a day, about
5% of the free limit** (a 245-room day: ~500,000, 10%). The largest share is
the room-status stamp (count + latest change for the day, ~1,500 calls a day
reading that day's rooms). One rule for Step 2: a prefix lookup must be a
range (`key >= 'p' AND key < 'p'` with the last character bumped) — the same
lookup as `LIKE 'p%'` reads all 643 settings rows instead of the matching ones.

### Step 2 — `db.py` learns D1 (deployed, but switched off)

- `db.py` stays the one place that talks to the database (plus the four
  modules that call the client directly: account_links, freetier, Admin,
  report_timing). It gains a D1 client with the same calls.
- A **database mode** setting, re-read every minute by the app and both PCs,
  so a switch needs no restart: `supabase` (default) → `both` → `d1`.
- D1's rows read and written are metered from Cloudflare's own analytics by
  the Worker's cron (with the watchdog, review §6 item 6); until then the
  Cloudflare dashboard shows them per day. `freetier.py` keeps metering
  Supabase while Supabase is in use.
- **Live (night):** push to `main`, restart Streamlit the usual way
  (requirements.txt touch), office PC and backup PC pull and restart. Mode is
  still `supabase`, so nothing behaves differently.
- Needs from Hari: a Cloudflare **account API token** limited to D1, put in
  Streamlit's secrets and on both PCs.

Done when: a full day passes in `supabase` mode with no change.
Undo: revert the commit.

**Built, 26 Nov (branch `cloudflare`, not yet on `main`):**

- `d1store.py` — the D1 client (the supabase-py calls this code uses, with
  Postgres' behaviour: jsonb decoding, timestamptz format, `updated_at`
  stamping, safe-update guard), the both-databases `TeeClient`, and the mode
  switch. In "both" and "d1", a D1 that can't be reached or set up falls back
  to Supabase alone and logs it, so D1 can't take the app down.
- `appsecrets.py` — secrets by name (environment → secrets.toml →
  st.secrets), extracted from `db._get_credentials`.
- `db.py` — `_client()` asks `d1store.client()`; `load_users` returns users
  by username (it had no order, so the Admin list reshuffled at every sign-in).
- `tests/test_d1store.py` — 28 tests running the client's real SQL on SQLite
  built from `0001_init.sql`. The suite: 121 tests, all passing.
- Parity on the live data: db.py's 16 read-only functions return
  byte-identical results from Supabase and from the D1 copy.

**The night it goes live**

1. Hari creates the token: Cloudflare dashboard → *Manage account* →
   *Account API tokens* → *Create token* → *Custom token*; permission
   **Account · D1 · Edit**; this account only. (Account tokens belong to the
   account, not a person, so they survive the hand-over.)
2. The token goes in as `D1_API_TOKEN`: Streamlit Cloud → app → *Settings* →
   *Secrets*; and `.streamlit/secrets.toml` on the office PC and this PC.
3. Merge `cloudflare` into `main` (after rebasing on the day's `main`), touch
   `requirements.txt` so Streamlit restarts; both PCs `git pull` and restart
   their agents (`schtasks /End`, `/Run`).
4. Check: the app works; `[d1store]` lines appear in no log; the mode is
   `supabase` (no `db_mode` row yet).

### Step 3 — write to both (Supabase still the one that's read)

- **Live (night):** a fresh full copy (`web/tools/copy_from_supabase.py`),
  then mode `both`: the `db_mode` row in Supabase's app_settings set to
  `{"mode": "both"}`. Every write goes to Supabase and D1; every read still
  comes from Supabase. A nightly check compares the two.

Done when: three days with the two identical every night.
Undo: mode `supabase`.

### Step 4 — read from D1

- **Live (night):** a fresh full copy, then mode `d1`. Writes keep going to
  Supabase too, so going back loses nothing.

Done when: two weeks clean (5 AM build, 5:30 push, Teams notes, the mirror,
sign-ins, reports).
Undo: mode `both` (Supabase never fell behind).

### Step 5 — the new app, page by page (runs beside Streamlit)

Built on D1, installable from Chrome, English and Spanish. In order of daily use:

1. Sign-in (same accounts; 30-day stay-signed-in in a proper secure cookie),
   My Rooms, My Home, Profile, the Front Desk board.
2. RQS and schedule boards: Reassign, Property, Who's Working, Fair share.
3. Manager pages: Generate (as a job), Roster Import (parsing as a job),
   Report, Stats, Forecast, Admin, HotSOS.

Each page: two or three testers use it next to the Streamlit page, then
everyone is told it's ready. **Once a page has moved, its Streamlit version is
frozen**; new features go to the new page only.

Passwords: they are stored as PBKDF2 with 200,000 rounds, and a Cloudflare
Worker can't run that (it caps PBKDF2 at 100,000 rounds and allows 10 ms of
CPU). The browser does the 200,000 rounds and the Worker checks the result, so
no password changes and no reset. The stored form is tightened once Streamlit,
which still checks passwords itself, is switched off.

Undo: people keep using the Streamlit page.

### Step 6 — Supabase stops

- **Live (night):** mode `d1` without the Supabase writes. Supabase is left
  intact, unused, for 30 days, then deleted (after a final export kept in the
  App Archive folder).

### Step 7 — Streamlit is switched off, the repo moves

- When the sign-in log shows nobody on Streamlit for a week: delete the
  Streamlit app, move the repo into `BGVgrandtimber`, deploy Cloudflare from
  GitHub Actions with a Cloudflare token stored in the organisation.
- Tell anyone still holding the Android app to install the new site from
  Chrome instead.

## What happens to the PCs

Nothing changes in what they do. They change *where they save*: from Step 2
`db.py` can write to D1, from Step 4 they read from it. The office PC's own
Claude session is told before each step that touches code it also edits, so
two sessions never push `db.py` changes over each other.

## Hand-over checklist (for later)

- GitHub: add IT's account as owner of `BGVgrandtimber`.
- Cloudflare: invite IT's account as administrator, or hand over the suite
  e-mail.
- The suite e-mail and its recovery details, in a password vault that can be
  handed over, with the Cloudflare API token and the HotSOS service account.
- Company-side pieces the app cannot move: Power Automate flows and the Office
  Script, the office PC's Windows sign-in, the HotSOS service account, Teams
  workflow addresses (Admin → Service Passwords → Teams chats).
- Microsoft 365 sign-in (needs IT): an app registration in Microsoft Entra ID;
  each account gets an optional work e-mail so Microsoft sign-in lands on the
  existing account and role.

## Open decisions

- Microsoft 365 sign-in: waiting on IT.
- The repo is **public** today. It should probably be private once in the
  organisation; decide before Step 7.
