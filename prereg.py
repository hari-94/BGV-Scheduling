"""
prereg.py — the front desk's Pre-Reg list, on their board (Hari, 25 Nov).

The desk keeps the day's pre-registered arrivals on the "Pre-Reg" tab of
"Daily Tasks Ops Departments.xlsx" (GC8Team site): one row per reservation,
cleared and filled again every day, added to as the day goes. The board shows
a Pre-reg tile -- how many of those rooms are not ready yet -- and a click
lists just them with their status, housekeeper, RQS and the tab's own columns.

Read by the office PC (`refresh`, every READ_SECONDS, through the signed-in
Chrome profile in sharepoint.py) and kept in app_settings under KEY; pages
read it off the shared floor (floor.py), like everything else.

The tab combines rooms: "3246EGHI" is a lock-off unit booked whole -- rooms
3246E, 3246G, 3246H and 3246I -- and "2336HI" two of one. `split` takes them
apart; a bare "1426" means every room of that number the day knows of.

Only what the board needs is copied. The guest's name, phone number and the
other numbers for keys stay on the tab: this app's database is read with a
publishable key, and the board already shows the arriving guest from the
Arrival Report.

The tab carries no date. A list that is the same as yesterday's last one is
yesterday's, not yet cleared; it is kept with `carried` set, and the board
says so instead of counting it.
"""
import io
import re

TEAM_SITE = "https://grandtimber.sharepoint.com/sites/GC8Team"
FILE_ID = "201EC969-8876-4F9F-A872-24711746ED2A"   # Daily Tasks Ops Departments.xlsx
TAB = "Pre-Reg"
KEY = "prereg"                # app_settings: {date, at, modified, first_seen, carried, entries}
READ_SECONDS = 300
BLANK_RUN = 40                # this many empty rows in a row: the list has ended

#: Header words -> our field. Matched as "the header contains this", lower case.
#: Name, phone and "other numbers" are left out on purpose (module docstring).
COLUMNS = [
    ("room", ("room",)),
    ("keys", ("keys made",)),
    ("checkin", ("check-in status", "check in status")),
    ("notes", ("notes",)),
    ("mobile", ("mobile key",)),
    ("rushed", ("rushed",)),
    ("zingle_added", ("added to the pre-reg",)),
    ("ready_zingled", ("room ready zingled",)),
]

_TOKEN = re.compile(r"\d{4}|[A-Z]+")
_LETTERS = re.compile(r"^[A-L]{1,8}$")


def split(text, known=()) -> list:
    """The rooms in one Pre-Reg cell, in order, each once.

    "3246EGHI" -> 3246E 3246G 3246H 3246I; "2336 H/I" the same way; several
    units in one cell ("1426B + 2336HI", "1426B, 1430A") each; a bare number
    -> every room of it in `known` (or the number alone if none is known).
    Letters that can't be a room (a word like "AND", a repeated letter) are
    skipped. `known` is today's room codes, upper case."""
    s = str(text or "").upper()
    known = {str(k).strip().upper() for k in known or ()}
    out, cur, got = [], None, False

    def add(room):
        if room not in out:
            out.append(room)

    def close():
        if cur and not got:
            mine = sorted(k for k in known if k[:4] == cur and len(k) == 5)
            for r in mine or [cur]:
                add(r)

    for tok in _TOKEN.findall(s):
        if tok.isdigit():
            close()
            cur, got = tok, False
        elif cur and _LETTERS.match(tok) and len(set(tok)) == len(tok):
            for ch in tok:
                add(cur + ch)
            got = True
    close()
    return out


def _flag(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("y", "yes", "true", "1", "x", "done")


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else ""
    s = str(v).strip()
    return "" if s.lower() in ("none", "nan", "false") else s


def parse(data: bytes, known=()) -> list:
    """The Pre-Reg tab's rows with a room, as entries:
    {"unit": as typed, "rooms": [...], "keys", "mobile", "checkin", "notes",
     "rushed", "zingle_added", "ready_zingled"}."""
    import openpyxl
    try:
        import xlsx_compat  # noqa: F401  (Excel Online's fonts)
    except Exception:
        pass
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        ws = next((w for w in wb.worksheets if w.title.strip().lower() == TAB.lower()), None)
        if ws is None:
            raise ValueError(f"no {TAB!r} tab in the workbook")
        cols, entries, blank = None, [], 0
        for row in ws.iter_rows(values_only=True):
            cells = list(row)
            if cols is None:
                heads = [str(c or "").strip().lower() for c in cells]
                if "room" in heads:
                    cols = {}
                    for field, words in COLUMNS:
                        for i, h in enumerate(heads):
                            if i in cols.values():
                                continue
                            if field == "room" and h != "room":
                                continue
                            if any(w in h for w in words):
                                cols[field] = i
                                break
                continue
            get = (lambda f: cells[cols[f]] if f in cols and cols[f] < len(cells) else None)
            unit = _text(get("room"))
            if not unit:
                blank += 1
                if blank >= BLANK_RUN:
                    break
                continue
            blank = 0
            rooms = split(unit, known)
            if not rooms:
                continue
            entries.append({
                "unit": unit, "rooms": rooms,
                "keys": _flag(get("keys")), "mobile": _flag(get("mobile")),
                "checkin": _text(get("checkin")), "notes": _text(get("notes")),
                "rushed": _flag(get("rushed")), "zingle_added": _flag(get("zingle_added")),
                "ready_zingled": _flag(get("ready_zingled")),
            })
        if cols is None:
            raise ValueError(f"no Room column on the {TAB!r} tab")
        return entries
    finally:
        wb.close()


def _same(a, b) -> bool:
    key = (lambda es: [(e.get("unit"), e.get("checkin"), e.get("notes")) for e in es or []])
    return key(a) == key(b)


def keep(entries, modified=None, day=None, prev=None) -> dict:
    """The record to store for today's read. A list identical to the one kept
    on an earlier day is that day's list, not cleared yet: `carried`."""
    import clock
    day = day or clock.today_iso()
    prev = prev or {}
    first = day
    if prev.get("entries") is not None and _same(prev.get("entries"), entries) and entries:
        first = prev.get("first_seen") or prev.get("date") or day
    return {"date": day, "at": clock.stamp(), "modified": modified, "first_seen": first,
            "carried": first < day, "entries": entries}


def refresh(known=(), fetch=None) -> dict:
    """Read the tab now and keep it (office PC). Returns the record, or
    {"error": why} -- the last good record is left as it was."""
    import db
    import sharepoint as sp
    fetch = fetch or (lambda: sp.fetch_by_id(TEAM_SITE, FILE_ID))
    import clock
    prev = db._load_key(KEY) or {}
    try:
        data, info = fetch()
        if data is None:
            raise RuntimeError(info.get("error", "no answer"))
        entries = parse(data, known)
    except Exception as ex:
        why = str(ex).splitlines()[0][:160] if str(ex) else type(ex).__name__
        # Keep the last good list; the board says it couldn't read a newer one.
        db._upsert_key(KEY, dict(prev, error=why, error_at=clock.stamp()))
        return {"error": why}
    rec = keep(entries, info.get("modified"), prev=prev)
    db._upsert_key(KEY, rec)
    return rec


def for_day(rec, day) -> dict:
    """{ROOM: entry} from a kept record, for `day` -- {} for another day's read
    or a list carried over from an earlier day."""
    if not rec or rec.get("date") != day or rec.get("carried"):
        return {}
    out = {}
    for e in rec.get("entries") or []:
        for r in e.get("rooms") or []:
            out.setdefault(str(r).upper(), e)
    return out


def card(e) -> dict:
    """What the board shows for a room's entry."""
    return {"unit": e.get("unit", ""), "keys": bool(e.get("keys")), "mobile": bool(e.get("mobile")),
            "checkin": e.get("checkin", ""), "notes": e.get("notes", ""),
            "rushed": bool(e.get("rushed")), "zingle_added": bool(e.get("zingle_added")),
            "ready_zingled": bool(e.get("ready_zingled"))}
