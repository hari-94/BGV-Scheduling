"""
assignments.py — who is on which rooms today.

Both the My Rooms page and the navigation need to answer "does this person
have rooms today, and which?", and they must answer it the same way -- a link
that appears for someone with nothing on it, or hides from someone who has
work, is worse than either behaviour on its own. The matching lives here so
there is only one answer.
"""
import re
import streamlit as st

import clock
import db


def norm(s) -> str:
    """A name reduced to comparable letters. Sign-ins carry dots, digits and
    capitals that the schedule does not."""
    return re.sub(r"[^a-z]", "", str(s or "").lower())


def match_name(names, *candidates):
    """The name in `names` that best answers to any of `candidates`.

    Exact first, then either side being a prefix of the other, so "Maricruz"
    finds "Maricruz G." and "mgarcia" does not accidentally find "Marta".
    """
    for cand in candidates:
        n = norm(cand)
        if not n:
            continue
        hit = next((h for h in names if norm(h) == n), None)
        if hit:
            return hit
        hit = next((h for h in names
                    if norm(h).startswith(n) or n.startswith(norm(h))), None)
        if hit:
            return hit
    # A work sign-in against a full name: "rmejia@..." is Rosibel Mejia,
    # "jenifers@..." is Jenifer Santana. Only once the schedule carries full
    # names (staff_names) is there a last name to match, and only a single
    # hit counts.
    for cand in candidates:
        local = norm(str(cand or "").split("@")[0])
        if len(local) < 4:
            continue
        hits = []
        for h in names:
            t = [norm(x) for x in str(h).split() if norm(x)]
            if len(t) < 2:
                continue
            # Any surname: "lperez" is Lorena Perez Caballero.
            if any(local in (t[0][0] + x, t[0] + x[0], t[0] + x) for x in t[1:]):
                hits.append(h)
        if len(hits) == 1:
            return hits[0]
    return None


def todays_charts():
    """Today's published charts and room statuses, at the property's date.

    Uncached on purpose: the pages that call this exist to show what a
    supervisor changed a moment ago.
    """
    sched = db.load_full_schedule() or {}
    charts, statuses = sched.get("groups_data") or [], db.get_room_statuses()
    try:
        import roomstatus
        if roomstatus.mirrored():
            charts = _rehome(charts, statuses)
    except Exception as ex:
        print(f"[assignments] HotSOS owners not applied: {ex}")
    return charts, statuses


def _rehome(charts, statuses):
    """Charts with each room under whoever holds it now.

    While HotSOS is where rooms are marked, it is also where they get handed
    round: 9 October's Daily Service went from Darling to Melissa there, and
    Melissa's phone still listed Darling's chart. The status mirror records
    HotSOS's holder on each room; a room held by someone else moves to a
    chart of theirs (the same service if they have one), and a chart left
    empty goes. The stored schedule is not touched."""
    import copy
    out = copy.deepcopy(charts)
    moves = []
    for g in out:
        keep = []
        for r in g.get("rooms") or []:
            who = str((statuses.get(str(r.get("room", ""))) or {}).get("housekeeper") or "")
            if who and who != g.get("housekeeper"):
                moves.append((g, r, who))
            else:
                keep.append(r)
        g["rooms"] = keep
    for src, r, who in moves:
        dest = next((x for x in out if x.get("housekeeper") == who
                     and x.get("service_type") == src.get("service_type")), None) \
            or next((x for x in out if x.get("housekeeper") == who), None)
        if dest is None:
            dest = {k: v for k, v in src.items() if k != "rooms"}
            dest.update(label=f"{src.get('label', '')}·{who.split()[0]}",
                        housekeeper=who, rooms=[])
            out.append(dest)
        dest.setdefault("rooms", []).append(r)
    out = [g for g in out if g.get("rooms")]
    for g in out:
        g["time"] = sum(int(float(x.get("time") or 0)) for x in g["rooms"])
    return out


def housekeepers(charts) -> list:
    return sorted({g.get("housekeeper", "") for g in charts
                   if g.get("housekeeper")})


def charts_for(charts, person) -> list:
    return [g for g in charts if g.get("housekeeper") == person]


@st.cache_data(ttl=60, show_spinner=False)
def _room_count(display: str, user: str, day: str) -> int:
    """How much of today's work is this person's -- their own rooms, or the
    rooms of the housekeepers they are inspecting.

    An RQS on duty belongs on the page even with no rooms of their own, since
    that is where they mark for a housekeeper whose hands are full. Cached
    briefly: the navigation asks on every page load, and it only decides
    whether a link is shown.
    """
    try:
        charts, _ = todays_charts()
    except Exception:
        return 0
    who = match_name(housekeepers(charts), display, user)
    n = sum(len(g.get("rooms") or []) for g in charts_for(charts, who)) if who else 0
    if n:
        return n
    insp = match_name(sorted({g.get("inspector", "") for g in charts
                              if g.get("inspector")}), display, user)
    if not insp:
        return 0
    return sum(len(g.get("rooms") or []) for g in charts
               if g.get("inspector") == insp)


def has_rooms_today() -> bool:
    """Does the signed-in person personally have rooms today?"""
    return _room_count(st.session_state.get("display_name", "") or "",
                       st.session_state.get("username", "") or "",
                       clock.today_iso()) > 0
