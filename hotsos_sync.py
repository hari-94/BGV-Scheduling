"""
hotsos_sync.py — turn the day's sheet into HotSOS room assignments.

The flow, end to end:

  RQS presses "Preview" or "Push to HotSOS" on the HotSOS page
    -> the page writes a request to app_settings (REQUEST_KEY)
    -> hotsos_agent.py, running on the office PC, sees it within a minute
    -> reads today's tab of the inspections workbook (synced from SharePoint)
    -> reads HotSOS's rooms and attendants, builds a plan, and (for a push)
       sends one AssignRoom call per attendant
    -> writes the plan and the outcome to RESULT_KEY, which the page shows.

The agent has to be on the office PC because the two sources are inside the
company: SSRS signs in with the PC's Windows login, and the SharePoint file is
an organisation-only link, read from its OneDrive-synced copy.

This module is the part with no network and no Streamlit: picking the day's
tab, reading it, matching names, and building the plan. That is so it can be
tested against real workbooks on its own.
"""
import datetime as _dt
import re

# ── app_settings keys shared by the page and the agent ──────────────────────
REQUEST_KEY = "hotsos_push_request"     # {id, date, mode, by, at}
RESULT_KEY = "hotsos_push_result"       # {id, date, mode, status, plan, ...}
LAST_KEY = "hotsos_last_result"         # the last preview/push that finished
NAMES_KEY = "hotsos_names"              # {sheet name: HotSOS attendant label}
FORECAST_KEY = "ssrs_forecast"          # {pulled_at, days: [...], warnings}
FORECAST_REQUEST_KEY = "ssrs_forecast_request"   # {id, by, at}
HEARTBEAT_KEY = "hotsos_agent_heartbeat"         # {at, host}
ROSTER_STATUS_KEY = "roster_sync_status"         # last Schedule.xlsx import
HEALTH_KEY = "agent_health"                      # the agent's own report, every minute
EVENTS_KEY = "agent_events"                      # its last 80 log lines, newest last

# What a row of the plan can say. The page colours by these.
ASSIGN = "assign"            # will be (or was) assigned
MOVE = "move"                # assigned in HotSOS to someone else; the sheet wins
ALREADY = "already"          # HotSOS already has it with the right person
NO_ROOM = "room not in HotSOS"
NO_PERSON = "name not matched"
NO_HSKP = "no housekeeper on sheet"
SKIPPED = (NO_ROOM, NO_PERSON, NO_HSKP)

_ROOM_RE = re.compile(r"^[1-9]\d{3}[A-Z]$")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
     "nov", "dec"], 1)}
# The tabs are named by hand by a bilingual team: "Abril 23" sits beside
# "April14", and August has been typed "Agu".
_MONTHS.update({"ene": 1, "abr": 4, "ago": 8, "agu": 8, "dic": 12})

# Names on the sheet that mean "nobody" rather than a person.
_NOT_A_PERSON = {"", "none", "-", "—", "no hk", "no hk available", "manager",
                 "unassigned", "tbd", "verify"}


def _clean(v) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def _norm(v) -> str:
    return re.sub(r"[^a-z ]", "", _clean(v).lower()).strip()


# ── which tab is today's ─────────────────────────────────────────────────────
def tab_date(name: str, year: int):
    """The date a tab name stands for, or None.

    The tabs are named by hand, so this takes the forms people actually type:
    "10-08", "10.8", "10-08-26", "2026-10-08", "Oct 8", "8 October",
    "Thu 10-08". Month comes first for numbers, as it does in the US.
    """
    # "Oct_8" is a real tab name: an underscore is a word character, so the
    # \b before the day never matches unless it reads as a space.
    s = _clean(name.replace("_", " ")).lower()
    # "Jan27", "April2nd": no word boundary between the month and the day.
    s = re.sub(r"([a-z])(\d)", r"\1 \2", s)
    m = re.search(r"\b(20\d\d)[-._ ](\d{1,2})[-._ ](\d{1,2})\b", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.search(r"\b(\d{1,2})[-._ ](\d{1,2})(?:[-._ ](\d{2,4}))?\b", s)
        if m:
            mo, d = int(m.group(1)), int(m.group(2))
            y = int(m.group(3)) if m.group(3) else year
            y = y + 2000 if y < 100 else y
        else:
            mname = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
                              r"|ene|abr|ago|agu|dic)[a-z]*\.?", s)
            dnum = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", s)
            if not (mname and dnum):
                return None
            mo, d, y = _MONTHS[mname.group(1)], int(dnum.group(1)), year
            ynum = re.search(r"\b(20\d\d)\b", s)
            if ynum:
                y = int(ynum.group(1))
    try:
        return _dt.date(y, mo, d)
    except ValueError:
        return None


def pick_tab(sheet_names, day: _dt.date, hidden=()):
    """The tab for `day`, or None.

    Hidden tabs are still read -- the team hides past days while they work,
    and a hidden tab is no less the day's. But if two tabs claim the day, a
    visible one beats a hidden one (the hidden copy is the stale one), and
    otherwise the last wins: a copied tab is added after its original."""
    hits = [n for n in sheet_names if tab_date(n, day.year) == day]
    visible = [n for n in hits if n not in hidden]
    return (visible or hits or [None])[-1]


# ── reading a tab ────────────────────────────────────────────────────────────
_HDR = {
    "room": ("room", "room #", "room number", "unit"),
    "service": ("service", "service type", "clean type"),
    "hskp": ("hskp", "housekeeper", "attendant", "room attendant", "hk"),
    "rqs": ("rqs", "inspector"),
    "time": ("time (min)", "time", "minutes", "credits"),
}


def read_rows(rows):
    """Room lines from a tab, given its rows as tuples of cell values.

    The header row is found by its labels rather than its position, because
    the tab is edited by hand. Reading stops at nothing in particular: every
    row whose Room cell is a real room code is a room, and anything else --
    blank lines, the staff summary under the schedule, notes -- is ignored.
    """
    rows = [tuple(r) for r in rows]
    cols = None
    start = 0
    for i, r in enumerate(rows[:30]):
        labels = [_clean(c).lower() for c in r]
        found = {}
        for key, names in _HDR.items():
            for j, lab in enumerate(labels):
                if lab in names and key not in found:
                    found[key] = j
        if "room" in found and "hskp" in found:
            cols, start = found, i + 1
            break
    if cols is None:
        raise ValueError("Couldn't find a header row with both a 'Room' and an "
                         "'HSKP' (or 'Housekeeper') column in the first 30 rows.")

    def cell(r, key):
        j = cols.get(key)
        return r[j] if j is not None and j < len(r) else None

    out, seen = [], set()
    for r in rows[start:]:
        room = _clean(cell(r, "room")).upper()
        if not _ROOM_RE.match(room):
            continue
        if room in seen:          # the export repeats a room on a second line
            continue
        seen.add(room)
        out.append({"room": room,
                    "service": _clean(cell(r, "service")),
                    "hskp": _clean(cell(r, "hskp")),
                    "rqs": _clean(cell(r, "rqs"))})
    return out


def read_workbook(path, day: _dt.date):
    """(tab name, room rows) for `day` from the workbook at `path`."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        hidden = {ws.title for ws in wb.worksheets if ws.sheet_state != "visible"}
        tab = pick_tab(wb.sheetnames, day, hidden)
        if tab is None:
            raise LookupError(
                f"No tab for {day:%a %b %d} in {len(wb.sheetnames)} tabs. "
                f"Last few: {', '.join(wb.sheetnames[-5:])}")
        return tab, read_rows(wb[tab].iter_rows(values_only=True))
    finally:
        wb.close()


# ── names on the sheet -> HotSOS attendants ─────────────────────────────────
def match_name(sheet_name: str, attendants, saved=None):
    """The HotSOS attendant (dict with 'id' and 'label') for a sheet name.

    `saved` is the RQS's own table (NAMES_KEY) and always wins. After that,
    only matches that cannot be wrong: the full name, a unique first name, or
    a unique first name plus last initial ("Danny R."). Anything ambiguous is
    left unmatched, so the page asks rather than guessing.
    """
    by_label = {_norm(a["label"]): a for a in attendants}
    if saved and sheet_name in saved:
        return by_label.get(_norm(saved[sheet_name]))
    # The staff sheet appends the section to a name: "Adrian – Houseperson PM".
    n = _norm(re.split(r"\s+[–—-]\s+", _clean(sheet_name))[0])
    if not n:
        return None
    if n in by_label:
        return by_label[n]
    parts = n.split()
    first, rest = parts[0], parts[1:]
    hits = []
    for a in attendants:
        ap = _norm(a["label"]).split()
        if not ap or ap[0] != first:
            continue
        # Whatever follows the first name has to agree with HotSOS's: an
        # initial ("Danny R."), or the start of a last name ("Cecilia Ang").
        # "Jennifer Cortez" is not "Jennifer Humphrey-Sledge" just because
        # HotSOS has only one Jennifer.
        if rest and not any(t.startswith(rest[0]) for t in ap[1:]):
            continue
        hits.append(a)
    return hits[0] if len(hits) == 1 else None


_VISITING = re.compile(r"\b(peak\s*7|gl\s*7)\b", re.I)   # as roster_import


def team_members(hskp: str):
    """The people in an HSKP cell: "Jenifer S/ Ana C" -> ["Jenifer S", "Ana C"].
    Placeholders like "No HK" or "Manager" are not people."""
    parts = re.split(r"\s*(?:/|,|&|\+|\band\b|\by\b)\s*", _clean(hskp))
    # Help from a sister property ("PEAK 7", "PEAK 7 - Adriana", "Jaritza
    # GL7") isn't in this property's HotSOS; their rooms are left as they are.
    return [p for p in parts if p and _norm(p) not in _NOT_A_PERSON
            and not _VISITING.search(p)]


# ── the plan ─────────────────────────────────────────────────────────────────
def build_plan(sheet_rows, hotsos_rooms, attendants, saved_names=None):
    """What the push will do, one line per sheet room.

    `hotsos_rooms` maps room code -> {"gid": roomGlobalId, "service": str,
    "assigned_to": attendant label or ""}. Rooms already with the right
    person are left alone; rooms with somebody else are moved, because the
    sheet is the RQS's final word.
    """
    plan = []
    for r in sheet_rows:
        line = dict(r)
        # Only the housekeeper goes into HotSOS -- never the RQS, so a room with
        # nobody in HSKP (Dust n Vac, an unstaffed chart) is left alone.
        who = r["hskp"]
        line["who"] = who
        members = team_members(who)
        line["unmatched"] = []
        hs = hotsos_rooms.get(r["room"])
        line["hotsos_service"] = (hs or {}).get("service", "")
        line["current"] = (hs or {}).get("assigned_to", "")
        person = None
        if not members:
            line["action"] = NO_HSKP
        elif hs is None:
            line["action"] = NO_ROOM
        else:
            # A team ("Santos/Claudia/Oralia") is one HotSOS housekeeper and
            # helpers who aren't attendants there: the room goes to the member
            # HotSOS knows. The first such member if, unusually, it knows two.
            for m in members:
                person = match_name(m, attendants, saved_names)
                if person:
                    break
            if person is None:
                line["unmatched"] = members
                line["action"] = NO_PERSON
            elif _norm(line["current"]) == _norm(person["label"]):
                line["action"] = ALREADY
            elif line["current"]:
                line["action"] = MOVE
            else:
                line["action"] = ASSIGN
        line["hotsos_name"] = person["label"] if person else ""
        line["person_id"] = person["id"] if person else ""
        line["gid"] = (hs or {}).get("gid", "")
        plan.append(line)
    return plan


def batches(plan):
    """{person_id: [roomGlobalId, ...]} for the lines that need a call."""
    out = {}
    for line in plan:
        if line["action"] in (ASSIGN, MOVE):
            out.setdefault(line["person_id"], []).append(line["gid"])
    return out


def summary(plan):
    """Counts by action, and the sheet names that still need matching."""
    counts = {}
    for line in plan:
        counts[line["action"]] = counts.get(line["action"], 0) + 1
    unmatched = sorted({m for l in plan for m in l.get("unmatched", [])})
    return {"counts": counts, "unmatched_names": unmatched}
