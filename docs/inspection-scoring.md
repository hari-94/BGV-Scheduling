# Inspection scoring — agreed, not yet built

**Status: waiting on the checklist itself.** HP is writing the questions. Nothing here
is built. Do not start until the list arrives; the shape below is settled, the content
is not.

## What it is

The RQS already signs a room off as `inspected`. That step becomes a short checklist,
and the answers turn into a score for the housekeeper for that day. Scores accumulate
into a week, a month and a year per person.

## What HP specified

**Two checklists, chosen by room size.**

| checklist | applies to |
|---|---|
| studio | 70-minute rooms |
| full | 120- and 140-minute rooms, which share one list |

The minutes are already on every room (`r["time"]`), so the right list can be chosen
without anyone picking it.

**Two question types.**

- yes / no
- a 1–5 rating, where **1 is bad and 5 is good**

**Scoring.** Each answered question contributes; the day's answers produce one rating
for that housekeeper. Weekly, monthly and yearly figures roll up from the daily ones.

## Open questions — ask before building

1. **How does a yes/no score against a 1–5?** Is "yes" worth full marks and "no" zero,
   or are some questions pass/fail gates that fail the whole inspection?
2. **Are questions weighted?** A bathroom miss and a crooked lampshade probably should
   not count the same.
3. **What is the day's rating when a housekeeper has several rooms inspected?** The mean
   across rooms, the worst room, or the mean weighted by room minutes?
4. **Is an uninspected room neutral or missing?** A person whose rooms were never
   inspected should not read as zero.
5. **Who sees the score?** The RQS and admin certainly. Does the housekeeper see her own?
   Worth deciding early — it changes the tone of the whole feature.
6. **Does a bad score raise anything?** A re-clean, a note to the manager, nothing.

## Shape it should take when built

**Storage.** `room_status` cannot hold this — it has no columns for it and PostgREST
rejects unknown fields (see CLAUDE.md). Two options:

- a new Supabase table `room_inspection` — `date, room, housekeeper, inspector,
  checklist, answers (jsonb), score, max_score, created_at`; needs SQL run by HP, or
- `app_settings` under `inspection_<date>` — no migration, but querying a year of it
  means loading every day.

A real table is the right answer if scores are going to be reported on for a year.
That is the only part of this that needs HP to run SQL, so raise it early.

**The checklist definition** belongs in code, versioned — a `checklists.py` beside
`roomstatus.py` — not in the database. It changes rarely, it needs review when it
changes, and a question's wording is part of what a score means. Keep a version number
on each list and store it with the answers, or last year's scores stop being comparable
when the list is edited.

**Where it hangs in the UI.** `pages/5_My_Rooms.py`, the RQS path only:
`roomstatus.RQS_ONLY` already gates the sign-off, and `can_inspect` already exists.
The checklist opens when an RQS moves a room to `inspected`, and the room does not
reach that state until the list is answered.

**Where the rollups belong.** `pages/1_Dashboard.py`, which is already the history
page and already has period filters. The per-person view fits `pages/4_My_Home.py` if
housekeepers are to see their own.

## Why it is worth doing

It is the second item on the roadmap, and the reason is that `inspected` currently
records only that someone looked. Every competing product — HotSOS's inspection steps,
Quore's digital inspections, Flexkeeping's custom checklists — treats the checklist as
the point of the inspection, because it is what makes quality reportable rather than
remembered.
