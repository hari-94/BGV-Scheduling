# BGV Scheduling — housekeeping at Grand Colorado on Peak Eight, Breckenridge

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
| `pages/1_Dashboard.py` | 340 | today's floor as a timeline, one bar per room |
| `pages/2_Admin.py` | 410 | accounts and sign-in history |
| `pages/7_Profile.py` | 90 | your own account: changing your password |
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
| `pages/6_Property.py` | 300 | the property in 3-D, coloured by status — admin and RQS only |
| `property_map.py` | 400 | where every room is and what it costs to walk between two |
| `daystart.py` | 210 | what to clean first, and when each room is reached |
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

## The building

`property_map.py` holds the property's shape, taken off the floor plans posted by
the service elevators and checked against all 245 rooms that have ever appeared on
a chart. Three things in the room code are not what they look like:

- **The level digit is not the level.** Digit 0 is *two* levels — Plaza and Terrace —
  split by room number, in buildings 1 and 3.
- **Building 1 has no rooms on level 1** (lobby, pool, spa) and **building 2 has none
  on Plaza or Terrace** (parking, and the housekeeping office).
- **Building 3 renumbers the same plate on its low levels.** 3240A, 3020A and 3010A
  are the same door on three levels. `_canon` undoes it so one floor plan serves the
  whole stack.

Buildings 2 and 3 **do not touch**. Building 1 is the link: bridges to 2 at Plaza,
Terrace, 1 and 2; to 3 at Plaza and 1 only. A chart holding rooms in both 2 and 3
costs two bridge crossings, and that is the single most expensive thing a chart can
do — about eight minutes a round trip.

`property_map.py` also carries what is *not* a guest room — service lifts, trash
chutes, laundry and ice rooms, refill closets, stairs, the housekeeping office
in building 2's Terrace, and the amenity volumes on the three levels that hold
no rooms at all. That is not decoration: a housekeeper's day is largely trips
between a room, the linen, the refill closet and the chute, and it is the
groundwork for costing those trips rather than only room-to-room ones.

`travel_seconds(a, b)`, `best_order(rooms)`, `chart_travel(rooms)`, `spread(rooms)`.
The seconds are estimates with names (`ELEVATOR_WAIT`, `BRIDGE_CROSS`…) so they can
be tuned once somebody times a real trip; what matters is their ratio. Rooms are
ordered by route on the chart card and on the phone page — the order a housekeeper
reads down her list is the order that walks least.

## Daily Service charts

`split_daily_service` packs **each building on its own first**, so every chart a
building can fill by itself is single-building by construction. Only each
building's trailing part-chart is left over, and each of those keeps a chart to
itself until the headcount forces a merge — cheapest merge first, scored in
bridge crossings from `pmap.BRIDGES`.

It used to sort every room by building and cut wherever the cap fell, then run a
tightening pass that pulled the first room of a later chart forward. Between them
**half the DS charts touched more than one building**, and housekeepers
complained about being sent across the property. Two rules keep it from coming
back: **never merge a remainder that the budget does not force**, and **never
merge on size alone** — packing by size pairs buildings 2 and 3, the only two
that do not touch, which is the single most expensive chart the property can
produce.

The arithmetic is why it is free: full charts plus packed remainders needs
exactly `ceil(total/cap)` people. Measured over every stored day — same 216
housekeepers, single-building charts 112 → 153, rooms stranded away from their
building 18% → 11%.

Not fixable in code: **`DS_CAP` is 460 minutes against a 330-minute day.** The
median DS chart is exactly 460 and 87% are over 330. Either those minutes are
nominal and badly beaten, or DS is structurally overloaded — a staffing
question, and not one the packer should paper over.

## Full Clean charts, and who inspects them

**Two ways to split the day, chosen on the Schedule page** (`fc_mode`), because
it is a real trade and only a person can price it: a housekeeper is a whole
shift, a building crossing is a few minutes of walking.

- **Fewest housekeepers** (what the schedulers do by hand):
  each building fills its own charts and only the rooms left over once it can
  no longer fill one are pooled across buildings. Crossings land in one or two
  tail charts instead of being spread about. Never uses more people than the
  solver already found.
- **Stay in one building** (the default): nobody crosses, and it may cost a
  housekeeper. Measured over eight real days — 124 people and 0 crossings,
  against 116 and 9.

`_tidy_full_clean` passes a target only in the pooled mode: a target is what
licenses a merge across buildings, which is the one thing the pure mode exists
to avoid. The choice is remembered for the property in `app_settings` under
`fc_mode` — it is one schedule, so it is not a per-person setting — and seeded
into session state before the widget is drawn, since that is what makes
Streamlit take it as the starting value.

`solve_full_clean` picks the fewest housekeepers and the tidiest arrangement it
can find at that number, but it packs the whole property as one pool, so a chart
boundary lands mid-building and the chart spills over. `_tidy_full_clean` then
redeals the result per building (`fcpack.pack_full_clean`), filling each chart
from one floor before it takes another, and merges back down to the count the
solver already reached. **It can only be free**: more charts than the solver used
and it hands the solver's answer back untouched. Measured over every stored day —
same 1,143 housekeepers, charts crossing a building 152 → 100, walking −2%.

Building 1's minutes, building 2's and building 3's each round up to a whole
person on their own, and on many days that still comes to the same total, which
is why this is usually free. Forcing it always would cost about one extra
housekeeper a day, which is why it is not forced.

Inspectors are batched the same way: a building at a time, its trailing
part-batch left alone until there are not enough inspectors, then merged
cheapest-bridge-first. RQS rounds crossing a building 245 → 192.

## The day## The day

`daystart.py` decides what to clean first. The order is not a sort — it is a
simulation of the day from ten in the morning, choosing at each step the room
that costs least to reach *and* is worth doing next, where **waiting for a guest
to leave counts as cost**. That one idea is what pushes late checkouts to the
back without a rule saying so, and it is why the module is a loop rather than a
`sorted(key=...)`.

HP's clock: **carts roll at 10:00, the floor should be done by 15:30, guests
check in at 16:00.**

**The 70/120/140 on a chart are standards, not durations.** HP says the floor
beats them, and the numbers agree: Full Clean charts run a median of 350 minutes
against a 330-minute window. So `plan_day` paces — it takes whatever is left of
the window once walking and waiting are removed and spreads it across the rooms
in proportion to their sheet minutes, giving each room a **done-by** time. That
is what the card shows, because "be finished here by 11:45" survives the day
slipping and "start at 10:07" does not.

Pacing runs *after* ordering and iterates, because the two depend on each other:
compress the morning and a late-checkout room gets reached before the guest has
gone, which changes the waiting, which changes the pace. It never exceeds 1.0 —
a light chart finishes early, and stretching rooms to fill the day would be a
fiction — and never drops below `MIN_PACE`, below which the chart genuinely does
not fit and is left visibly overrunning instead. Measured over every stored day:
**95% of charts land on 15:30, median pace 0.92**; the 5% that cannot fit at
`MIN_PACE` overrun on screen where somebody can see them.

**Big rooms first**, HP's rule, is `SIZE_SECONDS` — and it is 1.0 because the
effect saturates there. Measured over all 1,387 charts it lands the 140s a third
of the way through the day, the 120s at the half and the 70s at three quarters;
2.0, 3.0 and 5.0 give that same order while walking 2%, 4% and 8% further. It
sits well under an early check-in's 600, so a promise made at the front desk
still outranks a big room, and a late checkout still overrides both because
waiting is priced.

Signals actually in the data (checked, not assumed): `late_checkout` carries real
times ("Late Out: 10:30 am"), `notes` carry **"early in"** and "vip", `arriving`
holds the incoming guest's name — not a time, so there is no per-room deadline,
only "somebody is checking in here today". Dust n Vac rooms carry **no minutes at
all**; `UNTIMED_MINUTES` is a stated guess and `summary()["untimed"]` counts the
rooms it was applied to so the page can say the finish time is an estimate.

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

**Every page needs a width cap, and they should be the same one.** Admin was
capped at 1100 and My Home at 1180; the scheduler, roster and dashboard were far
wider and My Rooms and Property had no cap at all, so they took Streamlit's wide
default and stretched across a big monitor. HP reported exactly that split —
those two pages fine, every other one "zoomed in". They are all
`max-width:min(1200px,97%)` now (My Rooms 1100, since it is a phone page). The
`min()` matters: a bare pixel cap cannot promise to stay inside a small window.

Two ways to set this and miss. `cleaning_scheduler.py` states `.block-container`
twice — once at ~194 and again in the light theme at ~554 — and the second
silently wins. And `pages/6_Property.py` has no page-level stylesheet of its own;
its `PLAN_CSS` renders only in the 2-D view, so a rule put there leaves the 3-D
view uncapped.

**Measure the layout, do not reason about it.** Playwright against a local
instance settles in a minute what a screenshot cannot: `document.scrollWidth`
against `clientWidth` says whether anything really overflows, and walking every
element's `getBoundingClientRect` names the one that does. It cost a wrong guess
here — the top nav looked like the culprit and measurably was not.

**A cookie written from the page has a life the browser decides.** Safari on
iOS caps a script-set cookie at seven days and drops it whether or not the app
is being used, so a sign-in that is never renewed dies in a week, phones first.
`ensure_cookie` used to stop as soon as the browser was carrying the cookie,
which is precisely when it needed to start again. It now rewrites the cookie and
pushes the record's expiry out once per browser session, so anyone opening the
app in a normal week stays signed in. Do not "optimise" that write away.

**One key at a time is what makes a page slow.** Every `_load_key` is its own
round trip to Supabase, about eighty milliseconds. The roster page asked for
weeks one at a time and asked 175 times on a cold load — eight of its nine
seconds — and `staff_file_info`, whose docstring said it avoided pulling the
1.8 MB workbook blob, read the whole record anyway, five times a load. Both are
batched now: `_weeks_all` reads every week in one query and the writers empty it,
and the workbook's name and date live under their own small key. Measured: 190
settings reads to 15, and the page from 19.7s to 6.6s cold. Reach for
`_like_keys` before a loop of `_load_key`.

**Test the page, not the function.** `group_card_html` had been dead for a
while, and a "minutes of walking" badge was added to it, verified by calling the
function directly, and shipped — where nobody could ever see it. A test that
imports a function and asserts on its output proves the function works, not that
anything runs it.

**A deploy does not reload an imported module.** Streamlit re-reads a *page* file
on every rerun, but `import db` comes back from `sys.modules`. A process that was
already running when a deploy lands therefore runs the **new page against the old
db**, and a page calling a `db` function added in that same deploy dies with
`AttributeError: module 'db' has no attribute ...` until somebody reboots the
app. It happened to the dashboard. Rebooting fixes it; so does reaching the new
function through `getattr(db, "name", None)` with a fallback, which is what
`_stored_days` in `pages/1_Dashboard.py` does. Adding a `db` function and calling
it from a page in the same commit is the shape to watch for.

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
