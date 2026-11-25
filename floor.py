"""
floor.py — today's floor, read once for the whole app (Hari, 21 Nov: "use
one process where it puts the data and from there deliver to all the tabs").

Every kind of data has ONE writer:

  schedule_full      the day's plan. Made by the 5 AM build (or a Generate on
                     the Schedule page); after that only the office PC changes
                     it -- to follow who holds each room in HotSOS
                     (app_sync.from_hotsos, right after each mirror pass) and
                     what the team types on the day's tab (app_sync.from_sheet,
                     every 10 minutes).
  room_status        where each room is, and who holds it: the office PC's
                     HotSOS mirror, every two minutes. On a day HotSOS is down
                     (roomstatus.mirrored() off) the floor's own taps instead.
  fdmark_<date>_*    the front desk's late checkouts, departures and notes
                     (frontdesk.py, the Front Desk page).
  sheet_unplaced     rooms on today's tab that nobody holds yet (office PC).
  hotsos_status_sync when the mirror last read HotSOS, and how it went.

And every page reads them HERE, through `today()`: one snapshot for the whole
server, with the front desk's marks laid over the charts, fetched at most every
REFRESH_SECONDS. Fifty phones, the desk and the Dashboard cost one read, not
one each -- and they all see the same rooms under the same people. Before
this, each page joined the tables itself on its own timer (My Rooms 5 s,
Dashboard and Property 20 s, the desk 8 s), and My Rooms also moved rooms to
their HotSOS holder at read time by a rule of its own (assignments._rehome,
gone) while the Dashboard didn't, so two tabs could name two housekeepers for
one room.

Nothing here writes. db.py calls `invalidate()` after any write to these
tables, so a page's own change shows on its next draw; the office PC's are
seen within REFRESH_SECONDS. No Streamlit here.
"""
import copy
import threading
import time

import clock

REFRESH_SECONDS = 10
LOCK_WAIT = 15


class Floor:
    """One day's floor, as every page sees it. Shared by every session: read
    it, never change it (assignments.todays_charts hands out copies)."""

    def __init__(self, day, schedule, statuses, marks, unplaced, sync, prereg=None):
        import frontdesk
        self.day = day
        self.fetched = time.time()
        self.schedule = schedule or {}
        self.raw_charts = self.schedule.get("groups_data") or []
        self.statuses = statuses or {}
        self.marks = marks or {}
        self.unplaced = unplaced or []
        self.sync = sync or {}
        self.prereg = prereg or {}          # the desk's Pre-Reg tab, as kept (prereg.py)
        # The charts the floor works to: the saved plan with the desk's late
        # checkouts, departures and notes on its rooms (frontdesk.apply).
        self.charts = frontdesk.apply(self.raw_charts, self.marks)

    @property
    def inspectors(self):
        return self.schedule.get("inspectors_data") or []

    @property
    def generated_at(self):
        return self.schedule.get("generated_at")

    def status(self, room) -> dict:
        return self.statuses.get(str(room).strip()) or self.statuses.get(str(room).strip().upper()) or {}

    def rooms(self):
        """(chart, room) for every room on today's charts."""
        return [(g, r) for g in self.charts for r in g.get("rooms") or []]

    def board(self, now=None):
        """The front desk's rows (frontdesk.board)."""
        import frontdesk
        import prereg
        return frontdesk.board(self.raw_charts, self.statuses, self.marks, now=now,
                               unplaced=self.unplaced,
                               prereg=prereg.for_day(self.prereg, self.day))


_LOCK = threading.Lock()
_SNAP = {}            # day -> Floor
_STALE = {}           # day -> True once a write asked for a fresh read


def _fetch(day):
    import db
    import frontdesk
    import hotsos_sync as hs
    import prereg
    sched = db.load_full_schedule(day) or {}          # stamp-checked: downloads only on change
    statuses = db.get_room_statuses(day) or {}        # the same
    marks = frontdesk.load(day)
    keys = db._load_keys([frontdesk.UNPLACED_KEY, hs.STATUS_SYNC_KEY, prereg.KEY])
    up = keys.get(frontdesk.UNPLACED_KEY) or {}
    unplaced = (up.get("rooms") or []) if up.get("date") == day else []
    return Floor(day, sched, statuses, marks, unplaced, keys.get(hs.STATUS_SYNC_KEY) or {},
                 keys.get(prereg.KEY) or {})


def today(fresh: bool = False, day: str = None) -> Floor:
    """Today's floor (or `day`'s). At most REFRESH_SECONDS old, unless a write
    in this process has made it stale or `fresh` is asked for."""
    day = day or clock.today_iso()
    snap = _SNAP.get(day)
    if snap and not fresh and not _STALE.get(day) and time.time() - snap.fetched < REFRESH_SECONDS:
        return snap
    # One read at a time, so a crowd arriving together costs one read. But a
    # read stuck on a hung connection must never hold every page up behind
    # it: past LOCK_WAIT the last floor is shown, or, with none yet, this
    # page reads for itself.
    if not _LOCK.acquire(timeout=LOCK_WAIT):
        snap = _SNAP.get(day)
        if snap:
            return snap
        return _fetch(day)
    try:
        # Somebody else may have fetched while this one waited for the lock.
        snap = _SNAP.get(day)
        if snap and not fresh and not _STALE.get(day) and time.time() - snap.fetched < REFRESH_SECONDS:
            return snap
        _STALE.pop(day, None)
        try:
            snap = _fetch(day)
        except Exception as ex:
            old = _SNAP.get(day)
            if old is None:
                raise
            # Keep showing the last good floor rather than nothing; say so.
            print(f"[floor] refresh failed, keeping the floor from "
                  f"{int(time.time() - old.fetched)} s ago: {type(ex).__name__}: {ex}")
            return old
        for d in [d for d in _SNAP if d != day]:      # yesterday's: gone
            _SNAP.pop(d, None)
        _SNAP[day] = snap
        return snap
    finally:
        _LOCK.release()


def invalidate(day: str = None):
    """The next `today()` reads again. db.py calls this after every write to
    the floor's tables; cheap, and safe from any thread."""
    if day:
        _STALE[day] = True
    else:
        for d in list(_SNAP):
            _STALE[d] = True
        _STALE[clock.today_iso()] = True


def copies(f: Floor = None, marks: bool = True):
    """(charts, statuses) as copies a page may change: the shared floor must
    never be edited in place."""
    f = f or today()
    return copy.deepcopy(f.charts if marks else f.raw_charts), copy.deepcopy(f.statuses)
