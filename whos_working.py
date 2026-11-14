"""
whos_working.py — the "Who's Working" page's rule and data (Hari, 14 Nov).

The page lists today's working people, team by team, with their shift. It is
for whoever is RQS 1 or RQS 2 today -- they already have the staff workbook for
the whole month, so the app shows that day only. Managers (admin) can always
open it. Nobody else sees it, and the menu link appears only when it applies.

An RQS 1 / RQS 2 day is a worked day in the RQS section whose cell names RQS
1, RQS 2 or both -- roster_import.rqs_roles, the reading the scheduler uses.
An account is matched to its sheet row the way My Home matches it: the
admin's link (account_links) first, else display name, the name directory's
full name for it, and the username.

Roster Import itself is managers-only now.

No Streamlit here.
"""
import datetime
import re
import threading
import time

import clock
import db
import roster_import as ri

_TTL = 300                   # the menu asks on every page; the sheet changes weekly
_CACHE = {}
_ROWS = {"at": 0.0, "rows": None}
_LOCK = threading.Lock()


def rows():
    """Every stored day of the staff sheet, in-app edits applied (5 min)."""
    with _LOCK:
        if _ROWS["rows"] is not None and time.time() - _ROWS["at"] < _TTL:
            return _ROWS["rows"]
    out = ri.history_rows(db.load_staff_weeks(), db.load_staff_overrides())
    with _LOCK:
        _ROWS.update(at=time.time(), rows=out)
    return out


def pid_for(all_rows, username, display=""):
    """This account's person on the sheet, or None."""
    index = ri.people_index(all_rows)
    try:
        import staff_names
        aliases = staff_names.aliases() or {}
    except Exception:
        aliases = {}
    full = {k.lower(): v for k, v in aliases.items()}.get((display or "").strip().lower(), "")
    cands = [n for n in (full, display) if n] + [username]
    try:
        pid = ri.match_person(index, *cands, aliases=aliases)
    except TypeError:                         # an older roster_import
        pid = ri.match_person(index, *cands)
    try:
        import account_links
        pid = account_links.find_pid(index, account_links.link_for(username), aliases) or pid
    except Exception as ex:
        print(f"[whos_working] account link: {ex}")
    return pid


def is_rqs12(all_rows, pid, iso: str) -> bool:
    """Whether `pid` is RQS 1 and/or RQS 2 on `iso`."""
    return any(r["pid"] == pid and r["date"] == iso and r.get("group") == "rqs"
               and r.get("worked") and ri.rqs_roles(r.get("raw")) for r in all_rows)


def can_see(username: str, role: str, display: str = "", today: datetime.date = None) -> bool:
    """Managers always; an RQS only on a day they are RQS 1 / RQS 2."""
    if role == "admin":
        return True
    if role != "rqs":
        return False
    iso = (today or clock.today()).isoformat()
    key = (str(username).lower(), iso)
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < _TTL:
            return hit[1]
    all_rows = rows()
    pid = pid_for(all_rows, username, display)
    out = bool(pid) and is_rqs12(all_rows, pid, iso)
    with _LOCK:
        _CACHE[key] = (now, out)
    return out


def shift_label(section: str, raw: str) -> str:
    """What to show beside a name: nothing for a plain "ON", "HSP 6" for a
    houseperson's route number, else the sheet's own words."""
    raw = " ".join(str(raw or "").split())
    if raw.upper() in ("ON", "X", "WORK", "WORKING"):
        return ""
    if "houseperson" in str(section).lower() and re.fullmatch(r"\d+(\s*[+&,/-]\s*\d+)*", raw):
        return "HSP " + raw
    return raw


def day(all_rows, iso: str) -> dict:
    """{"sections": [(section, [(name, shift)])], "rqs1": name, "rqs2": name,
    "total": n} -- only the people working on `iso`, in the sheet's order."""
    sections, rqs = {}, {1: [], 2: []}
    for r in all_rows:
        if r["date"] != iso or not r.get("worked"):
            continue
        sections.setdefault(r["section"], []).append(
            (r["person"], shift_label(r["section"], r.get("raw"))))
        if r.get("group") == "rqs":
            for role in ri.rqs_roles(r.get("raw")):
                rqs[role].append(r["person"])
    return {"sections": list(sections.items()),
            "rqs1": " / ".join(rqs[1]), "rqs2": " / ".join(rqs[2]),
            "total": sum(len(v) for v in sections.values())}
