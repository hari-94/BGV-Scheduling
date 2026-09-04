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
