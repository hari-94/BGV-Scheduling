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
| `forecast.py` | 230 | reads a multi-day Housekeeping Dashboard export into per-day workload |
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

**One packer, `fcpack.pack`.** There used to be two, chosen on the Schedule
page (`fc_mode`): "stay in one building" and "fewest housekeepers". That choice
is gone, and so is the `fc_mode` widget — `db.save_fc_mode`/`load_fc_mode`
survive unused.

It was never a real choice. Both answers broke the same two rules, and neither
broke them in a way the other fixed. On the 12 September sheet:

| | one building | fewest HK | `fcpack.pack` |
|---|---|---|---|
| charts (floor 27) | 30 | 29 | **29** |
| guest apartments split | **11** | **8** | 0 |
| 140/120 rule broken | 0 | **1** | 0 |
| cross-building | 0 | 3 | 0 |
| mean floor span | 0.20 | 0.76 | 0.28 |

**The rules live in `fcpack` now, at the top of the module, and every pass goes
through `_legal`.** A chart may not split an apartment, run over the cap, hold
more than one 140 or a 140 beside more than one 120, or hold rooms in both
building 2 and building 3.

**The 140/120 rule is `_fc_feasible`'s, and it always was.** The scheduler has
stated it since the solver was written. The bug was that `_tidy_full_clean`
flattened the solver's legal charts back to a list of rooms and handed them to
a packer that knew neither that rule nor what an apartment was. `140+120+120`
comes to exactly 380 and passes a minutes check, which is why a minutes check
was never enough.

**An apartment is guest + room number + floor**, the same test
`_cluster_adjacent_same_guest` uses. A guest holding 2336E, 2336G and 2336H
holds one lock-off apartment with doors between the rooms; two housekeepers in
it is two people doing one turnover. A guest holding rooms in two *buildings*
is two bundles — that split is real, and the floor is fine with it.

**A bundle that cannot legally be a chart is split, not forced.** Two 140s
behind one door, or more than 380 minutes, has to go to two people whatever
anybody prefers. Without `_split_illegal` the bundle would be forced whole onto
a fresh chart and quietly break the cap — the fault this module exists to stop.

**Still only measured on one day.** The old two-mode numbers came from 67
stored days; these come from the 12 September sheet alone, because the machine
this was written on has no database credentials. Re-run the comparison over the
stored days before trusting the headcount figure.

**Floors per chart is the wrong measure; the span between them is the right
one.** Counting floors treats Plaza-and-4 the same as 2-and-3, and to somebody
pushing a cart one is a lift ride past three landings and the other is a
staircase. Over 61 stored days, packing by floor moved the mean span from 1.01
to 0.64 for about a third of a housekeeper a day.

**Slack-gathering is part of the same search.** `balance_low` is gone; its job
is the third term of `fcpack._score`, which ranks an arrangement by *(fewest
housekeepers, least walking, fewest short days)* and descends on it with three
moves — shift one bundle, swap two, empty the lightest chart outright. The
third is what removes a housekeeper; the first two make room for it. Every move
goes through `_legal`, so none of them can smuggle a broken rule back in.

Count comes first because a housekeeper is a whole shift and a crossing is a
few minutes. Travel outranks fullness because a short chart is somebody's easy
day and a long walk is nobody's.

`_tidy_full_clean` **audits the redeal and can refuse it**: a lost room, a
broken rule or an extra housekeeper and the solver's own charts are handed back
untouched. That guard is what makes the redeal safe rather than merely better —
`solve_full_clean` already produces legal charts, so falling back always lands
somewhere legal.

`solve_full_clean` picks the fewest housekeepers and the tidiest arrangement it
can find at that number, but it packs the whole property as one pool, so a chart
boundary lands mid-building and the chart spills over. `_tidy_full_clean` redeals
the result through `fcpack.pack`, which seeds one building at a time down the
floors in order and then descends on *(count, travel, short days)*. **It can only
be free**: more charts than the solver used, or any rule broken, and it hands the
solver's answer back untouched.

Building 1's minutes, building 2's and building 3's each round up to a whole
person on their own, and on many days that still comes to the same total, which
is why building purity is usually free. On 12 September it was entirely free —
29 charts, the same as the pooled answer, with nobody crossing at all.

Inspectors are batched the same way: a building at a time, its trailing
part-batch left alone until there are not enough inspectors, then merged
cheapest-bridge-first. RQS rounds crossing a building 245 → 192.

Charts are handed to inspectors in **walking order** — `_chart_place`, which
reads building, level and corridor position off `property_map`. Two things it
fixes: `_primary_bld` sorted buildings 1, 2, 3, which puts 3 next to 2, the
only pair that does not touch; and the old key sorted on `g["floors"]`, the
second digit of the room code, which is not a floor (0 is Plaza *and* Terrace,
and building 3 renumbers its lower levels). `_insp_travel_score` had the same
two faults and now scores real levels and real bridge counts — crossings 130 →
112 over 67 days.

The one round a day that covers all three buildings is the Daily Service and
Dust n Vac inspector, which is property-wide by design. It is not a Full Clean
problem and no amount of sorting will change it.

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

## Forecasting a week from the bookings

**Plan a week** used to seed its three numbers — labour minutes, checkouts,
daily services — from the same weekday last week, and a planner typed over
them. The property already publishes the real answer: the Housekeeping
Dashboard runs over a **date range**, and `forecast.read_dashboard` reads it
into per-day workload. The tab now takes that file, shows what each day needs,
and seeds the editor from it where the dates overlap the week being planned.
`staffing.estimate` does the arithmetic, unchanged, so a forecast and a built
schedule cannot drift apart.

Three things about that export, each of which produced wrong numbers first:

- **Column positions move between exports.** Time was column 4 in the
  12 September file and column 3 in the 13–30 one. Every column is found by its
  header label, and the header row is re-read at each date block.
- **The sheet holds more than one table**, and *the same dates appear in each*.
  After the cleaning services come "Housekeeping Hold, UT, Unallocated" and the
  non-clean services. Reading to the end of the file counts the hold list as
  cleaning work; the first pass at this reported 144 rooms for a day the sheet
  says has 131. The cleaning table ends at its `Total Labor (Minutes):` footer,
  and that is where the parser stops.
- **The workbook states its own totals** — `Rooms: N` per day in the header,
  `Daily Labor (Minutes): N` in the footer. They are compared against what was
  counted and any disagreement is surfaced, not smoothed over. On the September
  file the parse matches every day to the digit.

The same uploader reads a single-day export; it simply comes back as one day.

**Inspectors are counted from Full Clean rooms only.** The daily services all
go to RQS 2 — one person, property-wide, whatever the count — so they add a
head, not a ratio. What scales is the checkouts, at the 12–13 an inspector
carries (`INSP_ROOM_MAX` in the scheduler is 13; 12 is the comfortable number
to plan on, and `rqs_tight` uses 13). So the estimate is
`ceil(checkouts / 12) + 1 if there is any daily-service or Dust n Vac work`.

Counting dailies into the divisor, as it used to, asked for **eleven**
inspectors on 15 September — eighteen checkouts and a hundred and seven
dailies — when the floor runs that day on RQS 2 and two others. Over the 13–30
September range it came to 144 inspector-days against 100. It moves the other
way too: a checkout-heavy day with few dailies now costs slightly more, because
RQS 2's round is a whole person rather than something absorbed into a ratio —
27 September goes 11 → 12.

**The sheet's own divisor is not ours, and that is the point.** This dashboard
divides labour minutes by 390 for its "Daily Housekeeper Shifts"; `staffing.py`
splits the minutes between Full Clean and Daily Service and divides each by its
own target. So the two disagree on purpose — more people than the sheet on a
checkout-heavy day (32 against 28.9 on 13 September), fewer on a daily-service
one (11 against 11.6 on the 15th). If they ever agree exactly, something has
been flattened.

**A `data_editor` keeps whatever it was first drawn with.** Loading a forecast
after the table is on screen changes nothing until the widget key changes, so
the key carries a token derived from the parsed file.

## Traps — each of these has already bitten

**The front desk's report changes shape, and an empty parse looks like a quiet
day.** `parse_email_notes` required a heading to begin with a letter and end
with a colon. The desk started writing `-Room Moves:` instead of `Room Moves:`,
and the parser captured **nothing at all** — no late checkouts, no pets, no
room moves — without an error, because zero notes is indistinguishable from a
day with no notes. It now matches on a normalised heading (bullets stripped,
punctuation dropped, case flattened) against a table of names each section has
actually gone by, and an *unrecognised* heading still closes the previous
section so its contents cannot be filed under the wrong label. Arrows arrive as
`>`, `->`, `→` and `®` — the last is a Wingdings arrow pasted out of Outlook.
If the format shifts again, add the spelling to `_NOTE_SECTIONS` rather than
touching the loop.

**A room code carries exactly one letter.** All 174 codes on the September
sheet do, A through I. So `2232EG` is the desk's shorthand for two doors. The
old expander only split *consecutive* letters, which handled `1010AB` and
`1222EF` and quietly left `2232EG` as a room that does not exist — this
property's lock-offs skip F as often as not. The split is now verified against
`property_map` rather than assumed: it happens only when the whole code is not
a real room and every single-letter part is.

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
