# BGV Scheduling — housekeeping at Grand Timber Lodge, Breckenridge

A Streamlit app that turns a morning's room list into cleaning charts, hands each
housekeeper her rooms on a phone, and lets an RQS (inspector) watch and correct the
floor as the day runs. Data lives in Supabase. The team is largely Spanish-speaking,
so the pages they use are bilingual.

Read this before changing anything — it names where things live and, more usefully,
the traps that have already cost a day each.

## Running it

```bash
python -m streamlit run cleaning_scheduler.py --server.port 8502 --server.address 0.0.0.0
```

`.streamlit/secrets.toml` holds `SUPABASE_URL` and `SUPABASE_KEY`. It is gitignored,
so a fresh clone has no database until it is put back. Without it the app runs but
every page shows the connection error.

Tests are throwaway scripts driven by `streamlit.testing.v1.AppTest`, written next to
the code, run, then deleted. They stub `db.*` functions rather than the client, and
several of them read the *real* schedule to test against a real day.

## The modules

| file | lines | what it owns |
|---|---|---|
| `cleaning_scheduler.py` | 6200 | the entry point and most of the app — see the section map below |
| `pages/3_Roster_Import.py` | 1750 | the weekly staff sheet: upload, diff, week/month views, planning |
| `pages/5_My_Rooms.py` | 800 | the phone page: a housekeeper's rooms, and an RQS's whole team |
| `pages/1_Dashboard.py` | 510 | performance history |
| `pages/2_Admin.py` | 410 | accounts and sign-in history |
| `pages/4_My_Home.py` | 370 | one person's own week, from the staff sheet |
| `roster_import.py` | 1600 | the staff sheet parser — no Streamlit, so it is testable alone |
| `db.py` | 710 | every Supabase read and write, 55 functions |
| `i18n.py` + `i18n_es.py` | 830 | the language switch and ~340 Spanish phrases |
| `ui.py` | 320 | the top navigation and shared chrome |
| `staffing.py` | 200 | how many housekeepers and RQS a day needs |
| `session.py` | 150 | staying signed in across a refresh |
| `auth.py` | 155 | roles and permissions |
| `roomstatus.py` | 105 | the one vocabulary for a room's state |
| `assignments.py` | 92 | who is on which rooms today (shared by the page and the nav) |
| `clock.py` | 35 | property-local time |

### Inside `cleaning_scheduler.py`

| line | section |
|---|---|
| 43 | CONSTANTS — `SVC_*`, `MAX_FC` 380, `LOW_MIN` 330, `NEED_HK_PREFIX` |
| 160 | CSS |
| 915 | SESSION STATE — `_init_state`, `_auto_apply_today`, `_save_reassignment`, undo |
| 1212 | LOGIN GATE |
| 1684 | GROUPING LOGIC — rooms into charts |
| 2845 | STAFF ASSIGNMENT — charts to housekeepers and inspectors |
| 3222 | HTML BUILDERS — the chart cards |
| 3486 | SIDEBAR — attendance, RQS roles, daily-service team |
| 3854 | MAIN INPUT · 3999 SNAPSHOT · 4028 GENERATE |
| 4223 | RESULTS, then the three tabs: `tab_sched` 4559, `tab_reassign` 4865, `tab_live` 5637 |

## The data

**A chart** (`groups_data`): `label`, `service_type`, `housekeeper`, `inspector`,
`rooms`, `time`, `blds`, `floors`, `c140`, `c120`, plus flags `dv_rqs2` (the Dust n
Vac round, RQS 2's, never wants a housekeeper) and `verify_group` (stayovers, P/U
models, no-guest rooms — deliberately unassigned).

**A room**: `room`, `guest`, `arriving`, `res_type`, `status` (In House / Pending),
`service`, `time`, `bld`, `floor`, `pet`, `late_checkout`, `notes`, `verify`.

**Supabase tables**: `schedule_full` (today's charts, keyed by DATE), `room_status`
(one row per room per day), `app_users`, `login_events`, `schedule_log`, and
`app_settings` — a TEXT key plus JSONB payload used for everything that has no table
of its own: `roster`, `staffsched_*`, `lang_<user>`, `session_<hash>`,
`noteseen_<user>`.

`room_status` columns, and there are no others: `date, room, status, group_label,
housekeeper, inspector, started_at, cleaned_at, inspected_at, marked_clean_at, notes,
swapped_from, updated_by, updated_at`.

**Room states** live in `roomstatus.py`: `pending → cleaning_started → cleaning_done
→ inspected`, with `already_clean`, `dnd` and `help` off to the side. `NEXT` is the
road, `RQS_ONLY` is the sign-off, `META` is the label and colours. Change a colour or
a label there and both the phone page and the Live board follow.

## Traps — each of these has already bitten

**PostgREST rejects unknown columns.** Adding `note_at` to a `room_status` write made
the whole upsert fail with `PGRST204`, so every note typed on the floor was thrown
away. Check the column list above before writing a new field, or put it in
`app_settings`.

**Streamlit binds `on_click` arguments when the widget is drawn.** Passing a text
box's value as an argument sends whatever it held on the *previous* run — empty, for
somebody who types and immediately presses the button. Pass the widget's key and read
`st.session_state[key]` inside the callback.

**`streamlit-sortables` reads its props once, on mount.** New data does not reach a
board that is already on screen, and a changed widget key is not enough because
Streamlit hands the same iframe new arguments. Move the component to a different
position instead — `_remount_slot` cycles three containers.

**Popovers do not close on their own.** Their `key` carries a generation counter
(`mr_gen`); bump it after a change and the next render is a different widget, closed.
A dialog closes reliably but cannot open without a server round-trip, which is too
slow on a phone.

**Use `clock.py`, never `date.today()`.** The host runs UTC and the property does not;
the day rolls over at six in the evening Mountain, and an evening's work files itself
against tomorrow.

**Streamlit's cookie jar is not always a cookie jar.** Under AppTest it is a mock whose
`.get()` returns another mock, which is truthy. `session._cookie_token` insists on a
real string.

**The app hides its own chrome, and nearly lost the sidebar with it.** The button that
reopens a collapsed sidebar lives inside `[data-testid="stToolbar"]`; hiding that
toolbar hid the button. Empty the toolbar by name instead of switching it off.

**Test what a person does.** Two bugs survived a passing test because the test
committed a value with a rerun before clicking, which nobody does.

## Agreed but not built

`docs/inspection-scoring.md` — the RQS inspection checklist and the per-housekeeper
score that rolls up weekly, monthly and yearly. Two lists (studio for 70-minute rooms,
one shared list for 120 and 140), yes/no and 1-to-5 questions. HP is writing the
questions; the shape is settled, the content is not, and the doc lists the six
questions to ask before starting. It needs a real Supabase table, which is the one
part somebody has to run SQL for.

## Conventions

Language: `i18n.install()` in `ui.py` wraps Streamlit's text calls, so a label in
`i18n_es.ES` is translated on its way to the screen without touching the call site.
Dropdown **options** are deliberately not translated — the code compares against them.

Comments say *why*, not what. Several in here are load-bearing: they record a fault
that looked like a design choice.

Times shown to people are property-local; timestamps stored are ISO with an offset.
