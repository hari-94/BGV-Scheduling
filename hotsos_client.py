"""
hotsos_client.py — HotSOS's own web API, as its Room Assignment page uses it.

HotSOS publishes no API for this outside Amadeus's partner programme. These
are the calls the web app at na3.m-tech.com makes, read out of its JavaScript:

  POST  /V2/housekeepingService/RoomAssignment            the room board
  POST  /V2/housekeepingService/RoomAttendant/Timeline    attendants + their rooms
  PATCH /V2/housekeepingService/RoomAssignment/AssignRoom
        {"roomGlobalIds": [...], "shift": "AM", "assignRoomPersonId": "<id>"}

Signing in: HotSOS takes a plain username and password, then hands the page a
bearer token. Rather than re-implement that handshake, a headless Chrome fills
in the real login form and the token is lifted from the app's first API call.
It is kept in memory and never written down. Needs Chrome installed and
`pip install playwright` (no `playwright install` -- it drives the real Chrome).

Field names on the room board were never seen during development (the
discovery run needed a login nobody was there to type). So each field is
looked for under the names it plausibly has, and if none fits, the error says
which names *were* there -- one look at that and the list below is fixed.
"""
HOST = "https://na3.m-tech.com"
HK = HOST + "/V2/housekeepingService"
START = HOST + "/service-optimization/operations/housekeeping/attendant-productivity"

_ROOM_CODE = ("roomNumber", "room", "roomName", "roomCode", "locationName", "name")
_ROOM_GID = ("roomGlobalId", "globalId", "roomId", "id")
_ROOM_SVC = ("taskNameStr", "serviceName", "service", "cleanType", "serviceType")
_PERSON_ID = ("id", "personId", "attendantId", "roomAttendantId")
_PERSON_NAME = ("label", "name", "personName", "fullName", "attendantName")


class HotSOSError(RuntimeError):
    pass


def _pick(d, names, what):
    for n in names:
        if d.get(n) not in (None, ""):
            return d[n]
    raise HotSOSError(f"HotSOS {what}: none of {names} in fields {sorted(d)}")


class HotSOS:
    def __init__(self, username, password, shift="AM", headless=True):
        from playwright.sync_api import sync_playwright
        self.shift = shift
        self.token = None
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(channel="chrome", headless=headless)
        self.ctx = self._browser.new_context()
        self.ctx.on("request", self._sniff)
        try:
            self._login(username, password)
        except Exception:
            self.close()
            raise

    def _sniff(self, req):
        auth = req.headers.get("authorization")
        if auth and "/V2/" in req.url:
            self.token = auth

    def _login(self, username, password):
        page = self.ctx.new_page()
        page.goto(START, timeout=60000)
        pw = page.locator("input[type=password]")
        user = page.locator("input:not([type=password]):not([type=hidden])"
                            ":not([type=checkbox]):not([type=radio])").first
        # The form may ask for the username first and the password on a second
        # step; handle both.
        try:
            pw.first.wait_for(state="visible", timeout=20000)
        except Exception:
            user.wait_for(state="visible", timeout=20000)
            user.fill(username)
            user.press("Enter")
            pw.first.wait_for(state="visible", timeout=20000)
        else:
            user.fill(username)
        pw.first.fill(password)
        pw.first.press("Enter")
        for _ in range(120):                 # 60 s for the app to call home
            if self.token:
                return
            page.wait_for_timeout(500)
        raise HotSOSError("Signed in to HotSOS but never saw an API call -- "
                          "wrong username/password, or the login page changed.")

    def call(self, method, path, body=None):
        r = self.ctx.request.fetch(
            HK + path, method=method, data=body, timeout=60000,
            headers={"Authorization": self.token, "Content-Type": "application/json",
                     "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"})
        try:
            data = r.json()
        except Exception:
            data = r.text()
        return r.status, data

    def _paged(self, path, body, take):
        out, skip = [], 0
        while True:
            st, d = self.call("POST", path, dict(body, skip=skip, **take))
            if st != 200:
                raise HotSOSError(f"{path} -> HTTP {st}: {str(d)[:300]}")
            page = (d or {}).get("data") or []
            out += page
            skip += len(page)
            if not page or skip >= ((d or {}).get("count") or 0):
                return out

    # ── reads ──────────────────────────────────────────────────────────────
    def timeline(self):
        """Attendants on the board, each with the rooms they hold now."""
        return self._paged("/RoomAttendant/Timeline", {
            "filter": {"serviceStatusList": [], "reservationStatus": [],
                       "isUnderEstimatedTime": False, "isOverEstimatedTime": False},
            "includeCount": True}, {"take": 50})

    def attendants(self):
        """[{"id", "label"}] for everyone HotSOS will take rooms for."""
        seen = {}
        for a in self.timeline():
            pid = _pick(a, _PERSON_ID, "attendant id")
            seen[pid] = {"id": pid, "label": str(_pick(a, _PERSON_NAME, "attendant name"))}
        # The attendant console also lists people with no rooms yet; the
        # timeline may not. Best effort -- the timeline alone is enough to run.
        try:
            for a in self._paged("/RoomAttendant/AssignmentsList", {
                    "shift": self.shift, "includeCount": True, "filters": {},
                    "search": []}, {"takePerPage": 200}):
                pid = _pick(a, _PERSON_ID, "attendant id")
                seen.setdefault(pid, {"id": pid,
                                      "label": str(_pick(a, _PERSON_NAME, "attendant name"))})
        except HotSOSError as ex:
            print(f"[hotsos] attendant console list skipped: {ex}")
        return sorted(seen.values(), key=lambda a: a["label"])

    def rooms(self):
        """{room code: {"gid", "service", "assigned_to"}} for the board."""
        holder = {}
        for a in self.timeline():
            label = str(_pick(a, _PERSON_NAME, "attendant name"))
            for x in a.get("assignments") or []:
                if x.get("room") and not x.get("isBreak"):
                    holder[str(x["room"]).upper()] = label
        out = {}
        for r in self._paged("/RoomAssignment", {
                "shift": self.shift, "includeCount": True, "filters": {},
                "search": []}, {"takePerPage": 200}):
            code = str(_pick(r, _ROOM_CODE, "room number")).upper().strip()
            # The board's own assignedTo is the truth; the timeline leaves
            # rooms out (1422E, assigned and awaiting service, wasn't on it),
            # and a room it missed looked unassigned on every preview.
            out[code] = {"gid": _pick(r, _ROOM_GID, "room id"),
                         "service": str(next((r[k] for k in _ROOM_SVC if r.get(k)), "")),
                         "assigned_to": str(r.get("assignedTo") or holder.get(code, ""))}
        return out

    # ── write ──────────────────────────────────────────────────────────────
    def assign(self, room_gids, person_id):
        st, d = self.call("PATCH", "/RoomAssignment/AssignRoom", {
            "roomGlobalIds": list(room_gids), "shift": self.shift,
            "assignRoomPersonId": person_id})
        return st, d

    def close(self):
        for f in (getattr(self, "_browser", None) and self._browser.close,
                  getattr(self, "_pw", None) and self._pw.stop):
            try:
                f and f()
            except Exception:
                pass
