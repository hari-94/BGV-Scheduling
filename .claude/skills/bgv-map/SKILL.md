---
name: bgv-map
description: Where to make a change in the BGV housekeeping app. Use when asked to change anything in this repo — a room card, the boards, statuses, the staff sheet, staffing numbers, roles, Spanish, sign-in — so the right file and lines are opened first instead of searching. Also carries the traps that have already caused bugs here.
---

# Where the change goes

Open the named lines first. Line numbers drift; the anchors in `grep` are stable.

## The phone page — a housekeeper's rooms, an RQS's team
`pages/5_My_Rooms.py`

| want to change | go to |
|---|---|
| what a room card shows | `_room_row` — the `<div class="tk">` block |
| the chips (OWNER, ARRIVING, PET, VIP…) | `_flags_for` — reads `res_type`, `arriving`, `notes`, `pet`, `late_checkout` |
| the expanded detail | `_detail_html` — arrival first, then room, then progress |
| the circle's menu | `_menu` and `_OPTIONS` |
| what a status does or is called | **`roomstatus.py`**, not here |
| card colours | `roomstatus.META` — `(label, short, dot, background, ink)` |
| the header count and bar | `shown_rooms`, computed before the hero; it is own rooms **plus** team |
| who is on the team | `_my_team`, from `g["inspector"] == my_insp` |
| notes reaching the RQS | the "notes from the floor" block; read-state is `db.load_note_seen` |
| the live refresh | `_fresh` (5s cache) and `_watch` (20s poll); `_fingerprint` decides what counts as a change |

After any write here: bump `st.session_state["mr_gen"]` and call `_fresh.clear()`, or
the menu stays open and the page shows stale data for up to five seconds.

## The boards — Reassign and Live
`cleaning_scheduler.py`

| want to change | go to |
|---|---|
| the housekeeper→RQS board | `with tab_reassign:` ~4865 |
| the room-level board | same tab, `_move_room`, `room_home`, `SET_ASIDE` |
| column order | `_col_order` — others by name, then RQS 2, then RQS 1, then the pen |
| card order inside a column | `_card_order`, driven by `kb_sort` |
| wide columns (Daily Service, Set aside) | the `ds_cols` CSS block — targets `div:nth-of-type(n)` |
| undo | `_snapshot_for_undo` / `_undo_last` (~917); snapshot **before** mutating |
| the Live board | `with tab_live:` ~5637 |
| the day's numbers strip | search `k2row` (~4180) |
| the sidebar (attendance, RQS roles, DS team) | SIDEBAR ~3486; tick boxes are keyed `att_{gen}_{name}` |

## The staff sheet
`pages/3_Roster_Import.py` for the screens, `roster_import.py` for the parsing.

Week view · Month view · Plan a week · Attendance · Apply to roster · What changed ·
Upload & sync. The parser has `__version__` — bump it when adding helpers, since the
pages reload the module if it looks stale.

Staffing numbers are in `staffing.py`; the daily-service rotation is
`roster_import.suggest_daily_service`.

## Where rooms are in the building
`property_map.py` — no Streamlit, so it is testable alone.

| want to change | go to |
|---|---|
| the floor plans | `B1_TOWER`, `B1_STRIP`, `B2_TOWER`, `B3_PLATE` — `(row, x)` in door-widths |
| what a walk costs | the constants block: `SLOT_SECONDS`, `ELEVATOR_WAIT`, `BRIDGE_CROSS`… |
| which levels bridge to which | `BRIDGES` |
| the order rooms are cleaned in | `best_order` — nearest neighbour then 2-opt |
| where the day starts | `OFFICE_BLD` / `OFFICE_LEVEL` — building 2, Terrace |

The room code lies twice: digit 0 is Plaza **and** Terrace split by room number, and
building 3 renumbers the same doors on its low levels (`_canon`). Buildings 2 and 3
have no bridge — everything between them goes through building 1.

Ordering is applied in two places: `group_card_html` (`_seat`) and the phone page's
`_flat`. Both fall back to code order if a room is not on the plans, so a new room
code degrades the order without blanking the page.

## What to clean first, and the timeline
`daystart.py` — no Streamlit, testable alone.

| want to change | go to |
|---|---|
| the working day's clock | `DAY_START` 10:00, `TARGET_END` 15:30, `CHECKIN` 16:00 |
| how the day is paced to fit | the fitting loop in `plan_day`; `MIN_PACE` is the floor |
| one pass at a fixed pace | `_simulate` — `plan_day` calls it until the pace settles |
| what counts as urgent | `urgency` — early in 100, VIP 70, arriving 50, owner 30, stayover 5 |
| how hard urgency pulls | `URGENCY_SECONDS` — seconds of detour one rank is worth |
| reading a late checkout | `release_minute` / `BARE_LATE_OUT` |
| rooms with no minutes | `UNTIMED_MINUTES`; `summary()["untimed"]` counts them |
| the reason shown on a card | `why` |

The order is a forward simulation, not a sort: waiting for a guest counts as
cost, which is what sends late checkouts to the back on its own. Do not replace
it with a tiered sort — that throws the travel saving away.

The timeline strip is `_day_strip` in `pages/5_My_Rooms.py`, drawn once per
housekeeper above their rooms; the per-card start time is the `when` argument to
`_room_row`.

## The property page
`pages/6_Property.py` — gated on `can_view_insp_tab` (admin + RQS).

Three.js from cdnjs, fed by `pmap.layout(codes)` and `pmap.bridge_spans()`.
Geometry constants (`DOOR_W`, `LEVEL_H`, `HALL_D`, `BLD_GAP`, `BLD_ORDER`) live
in `property_map.py`, not the page. `layout` needs explicit room codes — a plate
is shared between levels, so it cannot know which rooms a level has;
`db.all_known_rooms()` supplies them. Colours come from `roomstatus.META`, never
invented locally, or the legend stops matching the phone in somebody's hand.

## Everything else

- **Roles and access**: `auth.py`. `can_manage_users` is admin only; `can_view_insp_tab` is admin + rqs.
- **Spanish**: add the exact English string as a key in `i18n_es.ES`. Do not wrap the
  call site. Never translate dropdown options.
- **Sign-in across a refresh**: `session.py`, cookie written from the page by JS.
- **Anything touching a date**: `clock.py`.
- **Any database call**: `db.py`. Nothing else talks to Supabase.

## Before you write to `room_status`

These columns exist and no others:

```
date room status group_label housekeeper inspector
started_at cleaned_at inspected_at marked_clean_at
notes swapped_from updated_by updated_at
```

An unknown field makes PostgREST reject the whole write (`PGRST204`) and the failure
looks like "could not save". Anything else belongs in `app_settings` via
`db._upsert_key`.

## Asked for, not built

**Inspection scoring** — read `docs/inspection-scoring.md` first. Waiting on HP's
checklist. Hangs off the existing `inspected` step in `pages/5_My_Rooms.py` (gated by
`roomstatus.RQS_ONLY` / `can_inspect`), rolls up in `pages/1_Dashboard.py`, and needs a
new `room_inspection` table — `room_status` cannot take it.

## Traps

- `on_click` arguments are bound when the widget is drawn. Pass a widget **key** and
  read `st.session_state[key]` in the callback, never the value.
- `streamlit-sortables` reads props once on mount. Use `_remount_slot`, not a new key.
- Popovers need a changing `key` to close. Dialogs close reliably but are too slow to open.
- Never `date.today()`. The host is UTC; the property is not.
- Do not hide `[data-testid="stToolbar"]` — the sidebar's reopen button lives in it.

## Testing

Write a throwaway `v*.py` beside the code, drive it with `AppTest`, run it, delete it.
Stub `db.*` functions, not the client. Reading the real schedule
(`db.load_full_schedule()`) makes a test argue about a real day.

Test the sequence a person performs. Committing a text value with a rerun before
clicking Save hides the bug that loses every note.
