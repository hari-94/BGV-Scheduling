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
        # The sheet and old logins shout some names ("ARACELI", "DIANIS"), and
        # a trailing dot comes and goes: "Luis U." one week, "Luis U" the next
        # (25 Nov) -- each missed the table and became a person of its own.
        low = {_key(k): v for k, v in table.items()}
        return low.get(_key(base), base) + sep + suffix
    return table[base] + sep + suffix


def _key(name) -> str:
    """How a typed name is looked up: case, spacing and a trailing dot don't count."""
    return " ".join(str(name or "").split()).rstrip(".").strip().lower()


def canon(name, table=None, attendant_list=None) -> str:
    """The one name a person goes by in a list: the approved full name, else a
    full name the directory can't get wrong ("Jose Z" -> Jose Zendejas), else
    HotSOS's own name when only one attendant fits ("Ana H." -> Ana Hernandez),
    else the name as typed -- never with a section after it."""
    table = aliases() if table is None else table
    base = " ".join(str(name or "").partition(SUFFIX)[0].split())
    hit = full(base, table)                      # the approved table first
    if hit != base:
        return hit.partition(SUFFIX)[0].strip()
    words = base.rstrip(".").split()
    # A first and a last name is a full name already: "Ana Centeno" is not
    # "Ana Caisa" because both begin "Ana C" (resolve matches only an initial).
    if len(words) >= 2 and len(words[-1].rstrip(".")) > 1:
        return base
    # A first name, or a first name and an initial: the one person it can be
    # among the approved full names and HotSOS's attendants together -- "Ana C."
    # stays as typed while HotSOS has an Ana Caisa and an Ana Centeno.
    people = ({v.partition(SUFFIX)[0].strip() for v in table.values()}
              | {a["label"] for a in (attendant_list or [])})
    first = words[0].rstrip(".").lower() if words else ""
    init = words[1].rstrip(".")[:1].lower() if len(words) > 1 else None
    hits = {p for p in people if p.split() and p.split()[0].lower() == first
            and (init is None or (len(p.split()) > 1 and p.split()[1][:1].lower() == init))}
    return hits.pop() if len(hits) == 1 else base


def one_name_each(rows, table=None):
    """roster_import.history_rows with every spelling and every section of a
    person under one name and one id (Hari, 25 Nov): "Luis U.", "Luis U" and
    "Luis Urbina" were three people in My Home's picker, and a second section
    ("Nancy Ramirez · Houseperson PM") one more."""
    import roster_import as ri
    table = aliases() if table is None else table
    try:
        att = attendants()
    except Exception:
        att = []
    memo, out = {}, []
    for r in rows:
        typed = r.get("person") or ""
        if typed not in memo:
            memo[typed] = canon(typed, table, att)
        name = memo[typed]
        out.append(dict(r, person=name,
                        pid=ri.norm_name(name) + (f"@{r['home']}" if r.get("home") else "")))
    return out


def resolve(typed: str, table=None) -> str:
    """The one person a name typed on a sheet means, or '' if it isn't
    clearly one: an alias ("Grace", "Claudia P."), a full name already, or a
    first name with a last initial that fits only one person ("Claudia P").
    Unlike `full`, never hands back an unknown name as if it were a person."""
    table = aliases() if table is None else table
    t = " ".join(str(typed or "").split()).rstrip(".").strip()
    if not t:
        return ""
    # "SAYRA. H", "MIGUE. C" (Oct): a dot after the first name, not the initial.
    if "." in t:
        t = " ".join(w.strip(".") for w in t.replace(".", ". ").split() if w.strip("."))
    low = {k.lower().rstrip("."): v for k, v in table.items()}
    if t.lower() in low:
        return low[t.lower()]
    people = set(table.values())
    for p in people:
        if p.lower() == t.lower():
            return p
    words = t.split()
    first, init = words[0].lower(), (words[1][0].lower() if len(words) > 1 else None)
    hits = {p for p in people if p.split()[0].lower() == first
            and (init is None or (len(p.split()) > 1 and p.split()[1][0].lower() == init))}
    return hits.pop() if len(hits) == 1 else ""


def _sound(word) -> str:
    """A spelling key: lower case, y as i, doubled letters single --
    "Jennifer", "Jenifer" and "Jennyfer" all read "jenifer"."""
    w = str(word or "").lower().replace("y", "i")
    return "".join(c for i, c in enumerate(w) if i == 0 or c != w[i - 1])


def resolve_among(typed, candidates) -> str:
    """The one person in `candidates` (today's housekeepers) a name typed on
    the sheet means when `resolve` can't tell: the first name spelled a
    little differently ("Jennifer" for Jenifer Santana, 25 Nov -- three
    rooms the team added stayed "not assigned" on the Front Desk all day),
    and a last initial if one was typed. '' unless exactly one fits."""
    t = " ".join(str(typed or "").replace(".", " ").split())
    if not t:
        return ""
    words = t.split()
    first, init = _sound(words[0]), (words[1][0].lower() if len(words) > 1 else None)
    hits = {c for c in candidates if c and _sound(c.split()[0]) == first
            and (init is None or (len(c.split()) > 1 and c.split()[1][0].lower() == init))}
    return hits.pop() if len(hits) == 1 else ""


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
            key = nn
            # Same person on two rows of one kind (a housekeeper moved from
            # Building 2 to 3 mid-week): one record. A row in a different kind
            # of section is a different job and stays apart, the way
            # parse_week keeps it. Merging them let Nancy's Houseperson PM
            # cell ("1") fill her empty housekeeper day on 12 Oct, and the
            # 5 AM build put her on rooms she was never scheduled for.
            if key in people and people[key].get("group") != p.get("group"):
                key = f"{nn} · {p.get('section') or p.get('group')}"
            people[key] = _merge_person(people[key], p) if key in people else p
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
