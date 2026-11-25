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


def todays_charts(marks=True):
    """Today's charts and room statuses, off the shared floor (floor.py) --
    the same snapshot every page reads, at most a few seconds old and fresh
    after any write. Copies: the page may change them.

    The charts already follow who holds each room in HotSOS: the office PC
    moves rooms on the saved schedule after every mirror pass
    (app_sync.from_hotsos). This used to be done again here, at read time, by
    a looser rule of its own (_rehome: a moved room joined *any* chart of its
    new holder, the Dust n Vac round included) -- two processes doing one job
    and able to disagree. With `marks`, the front desk's late checkouts,
    departures and notes are on the rooms (frontdesk.apply)."""
    import floor
    return floor.copies(marks=marks)


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
        charts, _ = todays_charts(marks=False)      # who, not what: no marks needed
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
