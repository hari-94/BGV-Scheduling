"""
staff_names.py — one name per person: the full name HotSOS knows them by.

Every sheet the team touches spells people its own way -- "Amalia",
"Jenifer S.", "Camila O", "Liliana L" -- and HotSOS knows "Camila Ochoa". The
pushes to HotSOS match those spellings every morning; the roster, the charts
and the phone page match them again in their own ways. This module keeps one
directory instead:

    DIRECTORY_KEY  {"aliases": {"Camila O": "Camila Ochoa", ...},
                    "approved_by", "approved_at"}
    ATTENDANTS_KEY {"pulled_at", "attendants": [{"id", "label"}, ...]}
                   -- HotSOS's own list, refreshed by the office PC agent
                   every time it signs in.

`suggest` proposes a full name for every name in use, using only matches
that cannot be wrong (hotsos_sync.match_name); the RQS approves the table on
the HotSOS page. `plan_rename` / `apply_rename` then rename what is stored:
the staff weeks, the in-app overrides, the standing roster and today's
schedule. After that, `rename_weeks` renames each Schedule.xlsx import on its
way in, so the stored roster stays in full names while the sheet keeps
whatever the team types.

Past schedules and room-status history are left alone: they record what was
written at the time.

No Streamlit here.
"""
import copy

import clock
import db
import hotsos_sync as hs

DIRECTORY_KEY = "staff_directory"
ATTENDANTS_KEY = "hotsos_attendants"


# ── reading ──────────────────────────────────────────────────────────────────
def aliases() -> dict:
    """{name as typed: HotSOS full name} -- only approved entries."""
    return (db._load_key(DIRECTORY_KEY) or {}).get("aliases") or {}


def attendants() -> list:
    return (db._load_key(ATTENDANTS_KEY) or {}).get("attendants") or []


SUFFIX = " · "     # roster_import's "Rosibel · Houseperson AM"


def full(name: str, table=None) -> str:
    """The full name for `name`, or `name` itself if it has none.

    roster_import keeps someone who works two sections as two rows,
    "Rosibel" and "Rosibel · Houseperson AM". The suffix is kept -- merging
    the rows would mix two sections' days -- and only the name is renamed."""
    table = aliases() if table is None else table
    base, sep, suffix = name.partition(SUFFIX)
    if base not in table:
        # The sheet and old logins shout some names ("ARACELI", "DIANIS").
        low = {k.lower(): v for k, v in table.items()}
        return low.get(base.lower(), base) + sep + suffix
    return table[base] + sep + suffix


def names_in_use(weeks=None, roster=None, since_days=28) -> dict:
    """{name: where it appears} for the people who matter now: housekeepers
    and RQS on the last four weeks and everything ahead, plus the standing
    roster. Two years of past staff and one-off spellings are not worth a
    planner's morning."""
    weeks = db.load_staff_weeks() if weeks is None else weeks
    roster = (db.load_roster() or {}) if roster is None else roster
    cutoff = (clock.today() - __import__("datetime").timedelta(days=since_days)).isoformat()
    seen = {}
    for w in weeks.values():
        if max(w.get("dates") or [""]) < cutoff:
            continue
        for n, p in (w.get("people") or {}).items():
            if p.get("group") in ("hk", "rqs"):
                seen.setdefault(n.partition(SUFFIX)[0], set()).add("schedule")
    for part in ("hk_roster", "insp_roster"):
        for n in (roster.get(part) or {}):
            seen.setdefault(n, set()).add("roster")
    return {n: sorted(v) for n, v in seen.items()}


def suggest(names, attendant_list, approved=None):
    """One row per name: the approved full name if there is one, else a match
    that cannot be wrong, else nothing (the RQS picks)."""
    approved = approved or {}
    labels = {a["label"] for a in attendant_list}
    rows = []
    for n in sorted(names, key=str.lower):
        if n in approved:
            rows.append({"name": n, "full": approved[n], "how": "approved"})
        elif n in labels:
            rows.append({"name": n, "full": n, "how": "already full"})
        else:
            hit = hs.match_name(n, attendant_list)
            rows.append({"name": n, "full": hit["label"] if hit else "",
                         "how": "suggested" if hit else "no match"})
    return rows


# ── renaming ─────────────────────────────────────────────────────────────────
def _merge_person(into: dict, other: dict) -> dict:
    """Two rows for one person (the sheet had "Jenifer S." on one week and the
    full name on another): keep every filled cell, the existing one first."""
    cells = dict(other.get("cells") or {})
    cells.update({k: v for k, v in (into.get("cells") or {}).items() if v})
    into = dict(into, cells=cells)
    into["nocall"] = sorted(set(into.get("nocall") or []) | set(other.get("nocall") or []))
    return into


def rename_weeks(weeks: dict, table: dict) -> dict:
    """The same weeks with people renamed by `table`. Pure."""
    if not table:
        return weeks
    out = {}
    for wk, w in weeks.items():
        w = copy.deepcopy(w)
        people = {}
        for n, p in (w.get("people") or {}).items():
            nn = full(n, table)
            p = dict(p, name=nn)
            people[nn] = _merge_person(people[nn], p) if nn in people else p
        w["people"] = people
        out[wk] = w
    return out


def plan_rename(table: dict):
    """What `apply_rename` would change, without changing it."""
    weeks = db.load_staff_weeks()
    renamed = rename_weeks(weeks, table)
    changed_weeks = [wk for wk in weeks if weeks[wk] != renamed[wk]]
    ov = db.load_staff_overrides()
    ov_changed = [k for k in ov if full(k.split("|", 2)[1], table) != k.split("|", 2)[1]]
    roster = db.load_roster() or {}
    ro_changed = sorted({n for part in ("hk_roster", "insp_roster")
                         for n in (roster.get(part) or {}) if full(n, table) != n})
    sched = db.load_full_schedule() or {}
    ch_changed = sum(1 for g in sched.get("groups_data") or []
                     if g.get("housekeeper") in table or g.get("inspector") in table)
    return {"weeks": changed_weeks, "overrides": ov_changed, "roster": ro_changed,
            "charts": ch_changed, "names": sorted(table)}


def apply_rename(table: dict):
    """Rename everything stored that a person is looked up by. Idempotent:
    running it twice changes nothing the second time."""
    done, failed = [], []
    weeks = db.load_staff_weeks()
    for wk, w in rename_weeks(weeks, table).items():
        if w != weeks[wk]:
            try:
                db.save_staff_week(wk, w)
                done.append(f"week {wk}")
            except Exception as ex:
                failed.append(f"week {wk}: {ex}")

    ov = db.load_staff_overrides()
    new_ov = {}
    for k, v in ov.items():
        wk, n, d = k.split("|", 2)
        new_ov[f"{wk}|{full(n, table)}|{d}"] = v
    if new_ov != ov:
        try:
            db.save_staff_overrides(new_ov)
            done.append("overrides")
        except Exception as ex:
            failed.append(f"overrides: {ex}")

    roster = db.load_roster() or {}
    hk = {full(n, table): v for n, v in (roster.get("hk_roster") or {}).items()}
    insp = {full(n, table): v for n, v in (roster.get("insp_roster") or {}).items()}
    if hk != roster.get("hk_roster") or insp != roster.get("insp_roster"):
        try:
            db.save_roster(hk, insp)
            done.append("roster")
        except Exception as ex:
            failed.append(f"roster: {ex}")

    sched = db.load_full_schedule()
    if sched:
        new = copy.deepcopy(sched)
        for g in new.get("groups_data") or []:
            for f in ("housekeeper", "inspector"):
                if g.get(f) in table:
                    g[f] = table[g[f]]
        if new != sched:
            try:
                db.save_full_schedule(new)
                # Today's room rows carry the names too; the phone page reads them.
                rows = []
                for room, r in (db.get_room_statuses() or {}).items():
                    fields = {f: table[r[f]] for f in ("housekeeper", "inspector")
                              if r.get(f) in table}
                    if fields:
                        rows.append(dict(fields, room=room))
                if rows:
                    db.bulk_upsert_room_statuses(rows)
                done.append("today's schedule")
            except Exception as ex:
                failed.append(f"today's schedule: {ex}")
    return {"done": done, "failed": failed, "at": clock.stamp()}


def canon_roster(roster: dict, table=None) -> dict:
    """The standing roster with every name in its full form and no person
    listed twice.

    The roster keeps anyone it has ever seen (marked absent), so after the
    rename to full names the old spellings stayed beside them: "David S." and
    "David Serrano", "Amalia" and "Amalia Hernandez" -- 42 such pairs. Where a
    person appears under both, the entry already in the full form wins
    (its building and today's attendance); an old spelling with no full-form
    twin is simply renamed."""
    table = aliases() if table is None else table
    out = {}
    for name, v in (roster or {}).items():
        key = full(name, table)
        if key in out and name != key:
            continue                      # the full-form entry already won
        out[key] = v
    return out
