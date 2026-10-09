"""
daily_build.py — build the day's schedule at 5 AM and write it as a tab of
GC8 Daily Schedule.xlsx in SharePoint.

What the RQS used to do by hand each morning, in the same order:
  1. the Housekeeping Dashboard for the day         <- SSRS, pulled by the agent
  2. the front desk's Arrival Report (late checkouts,
     pets, pack n plays...)                         <- the e-mail, saved into the
                                                       synced folder by a Power
                                                       Automate flow the night before
  3. press Generate on the Schedule page            <- run here, headless
  4. download the Excel and paste it into the day's tab
                                                    <- written here, names in the
                                                       HotSOS full form

Step 3 is not a copy of the scheduler: the Schedule page itself is run through
Streamlit's AppTest, with the room list and the e-mail typed into its boxes
and Generate pressed -- so the 5 AM schedule is exactly what a person pressing
the button would get, including today's roster (auto-applied as the page does
on its first open) and the save to the app that the phones read. The page's
own helpers (`excel_to_room_text`, `build_export_frame`) are borrowed from its
source by `borrow`, for the same reason: one implementation, two callers.

The tab is written once. If anybody has edited it since (a call-off moved,
a room swapped), a rebuild leaves it alone and says so -- the sheet is the
team's from the moment they touch it.

`publish=False` runs everything with every database write stubbed out, for
trying a build without touching the live day.
"""
import ast
import datetime as _dt
import hashlib
import io
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = HERE / "cleaning_scheduler.py"
BUILD_KEY = "daily_build_status"           # app_settings: the last 5 AM build
KEEP_TABS = 31                             # older day tabs are dropped
COLUMNS = ["Room", "Service", "Time (min)", "Pet", "Current Guest or Status", "HSKP",
           "RQS", "Notes", "Status", "Carpet", "Stripping", "Arriving Guest"]
WIDTHS = {"Room": 10, "Service": 16, "Time (min)": 11, "Pet": 6,
          "Current Guest or Status": 30, "HSKP": 22, "RQS": 18, "Notes": 30,
          "Status": 12, "Carpet": 9, "Stripping": 10, "Arriving Guest": 22}


# ── the Schedule page's own helpers ──────────────────────────────────────────
def borrow(*names, path=PAGE):
    """Functions from the Schedule page's source, with every module-level name
    they reach for, executed on their own -- the page itself is not run.

    Raises a clear error if the page has renamed one, rather than quietly
    falling back to a copy that would drift."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    defs, imports = {}, []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            defs[n.name] = n
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    defs[t.id] = n
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            imports.append(n)
    missing = [n for n in names if n not in defs]
    if missing:
        raise LookupError(f"cleaning_scheduler.py no longer defines {missing}")
    def free(node):
        """Names a definition reads but does not bind itself. A function's
        parameters and locals are not dependencies -- following them pulled in
        the page's top-level `fg = st.session_state[...]` for `build_export_frame(fg)`."""
        loads = {x.id for x in ast.walk(node)
                 if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}
        if not isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            return loads
        bound = {x.id for x in ast.walk(node)
                 if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store)}
        for f in ast.walk(node):
            if isinstance(f, (ast.FunctionDef, ast.Lambda)):
                a = f.args
                bound |= {x.arg for x in a.args + a.kwonlyargs + a.posonlyargs}
                bound |= {x.arg for x in (a.vararg, a.kwarg) if x}
        return loads - bound

    need, todo = set(), list(names)
    while todo:
        k = todo.pop()
        if k in need or k not in defs:
            continue
        need.add(k)
        todo += list(free(defs[k]))
    nodes = sorted({id(defs[k]): defs[k] for k in need}.values(), key=lambda n: n.lineno)
    code = "\n".join(ast.get_source_segment(src, n) for n in imports + nodes)
    ns = {"__name__": "borrowed_from_schedule_page"}
    exec(compile(code, str(path), "exec"), ns)
    return [ns[n] for n in names]


# ── the Arrival Report ───────────────────────────────────────────────────────
def find_arrival_report(folder, day: _dt.date):
    """The Arrival Report for `day` in `folder`, or None.

    The flow names each file after the e-mail's subject, "Arrival Report
    10/8/26" -> "Arrival Report 10-8-26.txt". The date in the subject is the
    day it's for, which is what matters: it's sent the night before. A resend
    wins over an earlier one."""
    folder = Path(folder)
    if not folder.exists():
        return None
    hits = []
    for p in [*folder.glob("*.txt"), *folder.glob("*.htm*")]:
        m = re.search(r"(\d{1,2})[-._ ](\d{1,2})[-._ ](\d{2,4})", p.stem)
        if not m:
            continue
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            if _dt.date(y, mo, d) == day:
                hits.append(p)
        except ValueError:
            pass
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None


def read_arrival_report(path) -> str:
    """The report as plain text. The flow may save the e-mail body as HTML
    (Outlook's own, with <p>/<br>/<div> for every line); the Schedule page's
    parse_email_notes wants one line per line, so the tags are turned back
    into line breaks here rather than needing a conversion step in the flow."""
    import html as _html
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    if "<" not in raw or not re.search(r"<(html|body|div|p|br|span|table)\b", raw, re.I):
        return raw
    raw = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|div|li|tr|h\d)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    text = _html.unescape(raw).replace("\xa0", " ")
    text = "\n".join(l.rstrip() for l in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ── Generate, as the page does it ────────────────────────────────────────────
class _NoWrites:
    """Stub every db write for a trial run; reads still see the live data."""
    PREFIXES = ("save_", "upsert", "bulk_", "delete_", "_upsert_key", "_delete_key",
                "log_", "update_", "create_")

    def __init__(self):
        import db
        self.db, self.saved, self.calls = db, {}, []

    def __enter__(self):
        for name in dir(self.db):
            if name.startswith(self.PREFIXES) and callable(getattr(self.db, name)):
                self.saved[name] = getattr(self.db, name)
                setattr(self.db, name, (lambda n: lambda *a, **k: self.calls.append(n))(name))
        return self

    def __exit__(self, *exc):
        for name, f in self.saved.items():
            setattr(self.db, name, f)


def generate(room_text: str, arrival_text: str, publish=True, timeout=900, day=None):
    """Run the Schedule page's Generate with these inputs. Returns the groups
    (charts) it produced. With publish=True the page saves them as today's
    schedule, exactly as a person pressing Generate would.

    `day` other than today builds a look-ahead: that day's roster is put on
    the page before Generate, and nothing is saved (the app holds one day's
    schedule, today's)."""
    import clock
    ahead = day is not None and day != clock.today()
    if ahead and publish:
        raise ValueError("A day other than today can only be built as a preview (publish=False).")
    from contextlib import nullcontext
    from streamlit.testing.v1 import AppTest
    with (nullcontext() if publish else _NoWrites()):
        at = AppTest.from_file(str(PAGE), default_timeout=timeout)
        for k, v in {"logged_in": True, "username": "auto-5am",
                     "display_name": "5 AM auto-build", "role": "admin"}.items():
            at.session_state[k] = v
        at.run()                                   # first open: today's roster is applied
        _raise(at, "opening the Schedule page")
        if ahead:
            _apply_roster(at, day.isoformat())
        else:
            _day_roles(at)
        iso = (day or clock.today()).isoformat()
        at.session_state["sched_day"] = iso          # weekend rules follow the day built
        generate.borrowed = []

        def run_generate():
            at.text_area(key="room_input").set_value(room_text)
            at.text_area(key="email_input").set_value(arrival_text or "")
            next(b for b in at.button if b.label == "Generate").click()
            at.run()
            _raise(at, "Generate")
            fg = at.session_state["groups_data"] if "groups_data" in at.session_state else None
            if not fg:
                warn = "; ".join(w.value for w in at.warning) or "no charts came back"
                raise RuntimeError(f"Generate produced nothing: {warn}")
            return fg

        fg = run_generate()
        need_hk, need_rqs = _shortfall(
            fg, at.session_state["inspectors_data"] if "inspectors_data" in at.session_state
            else [])
        if need_hk or need_rqs:
            rqs = {k: (at.session_state[k] if k in at.session_state else "")
                   for k in ("rqs1", "rqs2")}
            taken = _borrow(at, iso, need_hk, need_rqs)
            if taken:
                at.run()                         # redraw attendance with them in it
                none = "— none —"
                for sel, k in (("rqs1_sel", "rqs1"), ("rqs2_sel", "rqs2")):
                    opts = list(at.selectbox(key=sel).options)
                    at.selectbox(key=sel).set_value(rqs[k] if rqs[k] in opts else none)
                at.run()
                fg = run_generate()
                generate.borrowed = taken
        return fg


def _day_roles(at):
    """Today's Daily Service team and RQS 1 / RQS 2, from the staff schedule.

    The page sets these only when it applies the day's roster, which is once
    a day for the whole property. At 5 AM that is this run; but a rebuild later
    in the day opens a fresh session after the roster was already applied, and
    the page would then build with nobody on Daily Service. Read-only: the
    roster itself (and anyone's fixes to it) is left as the page loaded it."""
    import clock
    import db
    import roster_import as ri
    today = clock.today_iso()
    wk = ri.find_week_key(db.staff_week_keys(), today)
    week = db.load_staff_week(wk) if wk else None
    hk = at.session_state["hk_roster"] if "hk_roster" in at.session_state else {}
    update = ri.day_roster(week, db.load_staff_overrides(), wk, today, hk) if week else None
    if not update:
        return
    present = {n for n, v in hk.items() if v.get("present")}
    if not [n for n in (at.session_state["ds_team"] if "ds_team" in at.session_state else [])]:
        at.session_state["ds_team"] = [n for n in update["ds_team"] if n in present]
    for k in ("rqs1", "rqs2"):
        if not (at.session_state[k] if k in at.session_state else None) and update.get(k):
            at.session_state[k] = update[k]


def _apply_roster(at, iso):
    """Put `iso`'s roster on the page, the way its own _auto_apply_today does
    for today: attendance merged with the standing roster, inspectors, RQS 1
    and 2, the Daily Service team -- and the attendance boxes re-keyed and the
    RQS dropdowns pointed at the right people, or the page's widgets would
    write today's values straight back over them."""
    import db
    import roster_import as ri
    wk = ri.find_week_key(db.staff_week_keys(), iso)
    week = db.load_staff_week(wk) if wk else None
    if not week:
        raise LookupError(f"No week in the staff schedule covers {iso}.")
    hk = at.session_state["hk_roster"] if "hk_roster" in at.session_state else {}
    update = ri.day_roster(week, db.load_staff_overrides(), wk, iso, hk)
    if not update:
        raise LookupError(f"The staff schedule has no entries for {iso}.")
    roster = ri.merge_roster(update, hk, keep_missing=True)
    insp = dict(update["insp_roster"])
    for name in (at.session_state["insp_roster"] if "insp_roster" in at.session_state else {}):
        insp.setdefault(name, False)
    at.session_state["hk_roster"] = roster
    at.session_state["insp_roster"] = insp
    at.session_state["rqs1"] = update["rqs1"]
    at.session_state["rqs2"] = update["rqs2"]
    at.session_state["ds_team"] = [n for n in update["ds_team"]
                                   if roster.get(n, {}).get("present")]
    gen = at.session_state["_att_gen"] if "_att_gen" in at.session_state else 0
    at.session_state["_att_gen"] = gen + 1
    at.run()                 # the page draws the day's attendance boxes first ...
    # ... and only then are the day's inspectors among the RQS dropdowns'
    # options; picking one before that fails with "not in list".
    none = "— none —"                       # the page's RQS_NONE
    for sel, val in (("rqs1_sel", update["rqs1"]), ("rqs2_sel", update["rqs2"])):
        opts = list(at.selectbox(key=sel).options)
        at.selectbox(key=sel).set_value(val if val in opts else none)
    at.run()


# ── short of people: borrow from other duties ─────────────────────────────────
# The manager's rule. Only when charts would otherwise go out with nobody on
# them, people on some other duties that day are counted as working -- Dust
# and Vac first, then projects and anything else. Deep cleans of named units
# and HSP (houseperson) are never borrowed: that work has to happen anyway.
_DV_DUTY = re.compile(r"dust\s*(and|&|n|y)?\s*vac", re.I)
_NEVER_BORROW = re.compile(r"\b\d{4}[a-i]\b|deep\s*clean|\bhsp\b|house\s*person|"
                           r"\bsick\b|\bvto\b", re.I)


def borrowable(iso):
    """[(name, group, duty)] -- who could be pulled onto rooms on `iso`, in the
    order they should be: Dust and Vac first, then other duties."""
    import db
    import roster_import as ri
    wk = ri.find_week_key(db.staff_week_keys(), iso)
    week = db.load_staff_week(wk) if wk else None
    if not week:
        return []
    eff, _ = ri.apply_overrides(week, db.load_staff_overrides() or {}, wk)
    out = []
    for p in ri.week_to_people(eff, iso):
        if p["kind"] != ri.KIND_OTHER or p["group"] not in ("hk", "rqs"):
            continue
        if _NEVER_BORROW.search(p["raw"]) or ri.is_room_cover(p["raw"]):
            continue
        out.append((0 if _DV_DUTY.search(p["raw"]) else 1, p["name"], p["group"], p["raw"]))
    return [(n, g, raw) for _, n, g, raw in sorted(out, key=lambda x: x[0])]


def _shortfall(fg, inspectors):
    """(charts with no housekeeper, inspector slots with nobody named)."""
    hk = sum(1 for g in fg if not g.get("verify_group") and not g.get("dv_rqs2")
             and str(g.get("housekeeper") or "").startswith(("No HK available",
                                                              "Need Housekeeper")))
    rqs = sum(1 for e in inspectors or [] if str(e.get("name", "")).startswith("Inspector "))
    return hk, rqs


def _borrow(at, iso, need_hk, need_rqs):
    """Mark the first `need_hk` housekeepers and `need_rqs` RQS from
    borrowable() present on the page. Returns who was taken."""
    import roster_import as ri
    hk = dict(at.session_state["hk_roster"]) if "hk_roster" in at.session_state else {}
    insp = dict(at.session_state["insp_roster"]) if "insp_roster" in at.session_state else {}
    by_norm_hk = {ri.norm_name(n): n for n in hk}
    by_norm_rq = {ri.norm_name(n): n for n in insp}
    taken = []
    for name, group, duty in borrowable(iso):
        if group == "hk" and need_hk > 0:
            key = by_norm_hk.get(ri.norm_name(name))
            if key and not hk[key].get("present"):
                hk[key] = dict(hk[key], present=True)
                need_hk -= 1
                taken.append((key, "Housekeeper", duty))
        elif group == "rqs" and need_rqs > 0:
            key = by_norm_rq.get(ri.norm_name(name), name)
            if not insp.get(key):
                insp[key] = True
                need_rqs -= 1
                taken.append((key, "RQS", duty))
    if taken:
        at.session_state["hk_roster"] = hk
        at.session_state["insp_roster"] = insp
        gen = at.session_state["_att_gen"] if "_att_gen" in at.session_state else 0
        at.session_state["_att_gen"] = gen + 1
    return taken


def _raise(at, step):
    if at.exception:
        raise RuntimeError(f"Schedule page failed while {step}: "
                           f"{at.exception[0].message}")
    errs = [e.value for e in at.error if "Error" in e.value]
    if errs:
        raise RuntimeError(f"Schedule page error while {step}: {errs[0][:300]}")


# ── the day's tab ────────────────────────────────────────────────────────────
def tab_name(day: _dt.date) -> str:
    """"Oct 9" -- the team's own style, which hotsos_sync.tab_date reads."""
    return f"{day:%b} {day.day}"


# The "Built ..." stamp sits in the header row, clear of the columns. It
# changes on every build, so the fingerprint leaves it out -- otherwise a
# rebuild would never be "unchanged" and every tab would look edited.
STAMP_COL = len(COLUMNS) + 2


def _fingerprint(ws) -> str:
    rows = []
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        r = ["" if c is None else str(c) for c in r]
        if i == 0 and len(r) >= STAMP_COL:
            r[STAMP_COL - 1] = ""
        while len(r) > len(COLUMNS) and r[-1] == "":
            r.pop()                        # the stamp widens the sheet; tabs written
        r += [""] * (len(COLUMNS) - len(r))  # before it must hash the same
        rows.append(r)
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def _write_summary(ws, top, frame, day=None, borrowed=()):
    """Under the rooms: minutes per housekeeper, then suggestions for the
    light ones. Nothing in either table starts with a room code, so a push
    -- which reads only rows whose first cell is a room -- never sees them."""
    from openpyxl.styles import Font, PatternFill
    if frame is None or frame.empty:
        return
    bold = Font(name="Arial", size=11, bold=True, color="16202E")
    hdr = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    reg = Font(name="Arial", size=10)
    blue = PatternFill("solid", fgColor="2563A8")
    fills = {"Light": PatternFill("solid", fgColor="FFF4E5"),
             "Over": PatternFill("solid", fgColor="FDECEC"),
             "Full": PatternFill("solid", fgColor="EAF7EE"),
             "RQS 2 · Dust n Vac": PatternFill("solid", fgColor="EEF0F3")}
    summary = staff_summary(frame)
    moves, after = suggest_moves(frame)

    def header(row, cols):
        for ci, h in enumerate(cols, 1):
            c = ws.cell(row=row, column=ci, value=h)
            c.font, c.fill = hdr, blue

    r = top
    ws.cell(row=r, column=1, value="Staff summary — minutes per housekeeper").font = bold
    ws.cell(row=r + 1, column=1, value=f"Light = under {LOW_MIN} min · Full Clean chart up to "
                                       f"{CAP_FC} · Daily Service up to {CAP_DS}").font = reg
    r += 2
    header(r, ["Housekeeper", "Rooms", "Minutes", "Full Clean min", "Daily min",
               "Dust n Vac rooms", "Status", "After suggestions"])
    for p in summary:
        r += 1
        vals = [p["name"], p["rooms"], p["minutes"], p["Full Clean"], p["Daily Service"],
                p["Dust n Vac"], p["status"],
                after[p["name"]] if after.get(p["name"]) != p["minutes"] else ""]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row=r, column=ci, value=v)
            c.font, c.fill = reg, fills[p["status"]]
    recs = frame.to_dict("records")
    unst = [x for x in recs if _needs_person(x.get("HSKP"))]
    blank = [x for x in recs if not str(x.get("HSKP") or "").strip()
             and str(x.get("Room") or "").strip()
             and not str(x.get("Service") or "").startswith("Dust")]
    if blank:
        r += 1
        vals = ["Left blank to check", len(blank), sum(_minutes(x.get("Time (min)")) for x in blank),
                "", "", "", "Unallocated / stayovers — RQS decides"]
        for ci, v in enumerate(vals, 1):
            ws.cell(row=r, column=ci, value=v).font = Font(name="Arial", size=10, italic=True)
    if unst:
        r += 1
        mins = sum(_minutes(x.get("Time (min)")) for x in unst)
        # Counted per job, like the forecast: a Full Clean chart holds 380, a
        # Daily Service round 460, and nobody works a fraction of either.
        ds = sum(_minutes(x.get("Time (min)")) for x in unst
                 if str(x.get("Service") or "").startswith("Daily"))
        charts = -(-(mins - ds) // CAP_FC) + -(-ds // CAP_DS)
        vals = ["No housekeeper available", len(unst), mins, "", "", "",
                f"≈ {charts} more housekeeper{'s' if charts != 1 else ''} needed"]
        for ci, v in enumerate(vals, 1):
            ws.cell(row=r, column=ci, value=v).font = Font(name="Arial", size=10, italic=True)

    fs = free_staff(frame, day) if day else None
    if fs is not None:
        r += 3
        ws.cell(row=r, column=1, value="Free today — on the staff schedule, no rooms in this "
                                       "sheet").font = bold
        ws.cell(row=r + 1, column=1, value=(
            f"RQS 1 ({fs['rqs1'] or 'not named'}) is never counted as free: projects. "
            "People on other duties are listed apart.")).font = reg
        r += 2
        if fs["free"]:
            header(r, ["Name", "Role", "Scheduled as"])
            for name, role, as_ in fs["free"]:
                r += 1
                for ci, v in enumerate([name, role, as_], 1):
                    c = ws.cell(row=r, column=ci, value=v)
                    c.font, c.fill = reg, fills["Light"]
        else:
            ws.cell(row=r, column=1, value="Nobody is free — everyone scheduled has rooms.").font = reg
        names = {n for n, _, _ in borrowed}
        other = [o for o in fs["other"] if not any(o.startswith(n) for n in names)]
        if other:
            r += 1
            ws.cell(row=r, column=1, value="On other duties (not free): "
                                           + "; ".join(other)).font = reg
    if borrowed:
        r += 2
        ws.cell(row=r, column=1, value="Short of people — moved onto rooms from other "
                                       "duties").font = bold
        for n, role, duty in borrowed:
            r += 1
            c = ws.cell(row=r, column=1, value=f"{n} ({role}) — was: {duty}")
            c.font, c.fill = reg, fills["Light"]

    r += 3
    ws.cell(row=r, column=1, value="Suggestions to fill light charts — check, then edit the "
                                   "HSKP column above if you agree").font = bold
    r += 1
    if not moves:
        light = [p["name"] for p in summary if p["status"] == "Light"]
        ws.cell(row=r, column=1, value=("Nobody is light." if not light else
                                        "No rooms fit: " + ", ".join(light) +
                                        " stay light (no unstaffed or spare rooms of the same "
                                        "service).")).font = reg
        return
    header(r, ["Suggestion", "Give rooms", "Service", "Minutes", "From", "To",
               "To's minutes", "Why"])
    for i, m in enumerate(moves, 1):
        r += 1
        vals = [f"Suggestion {i}", ", ".join(map(str, m["rooms"])), m["service"], m["minutes"],
                m["from"], m["to"], f"{m['before']} → {m['after']}", m["why"]]
        for ci, v in enumerate(vals, 1):
            ws.cell(row=r, column=ci, value=v).font = reg


def _save_in_place(path, data: bytes, tries=30, wait=20):
    """Overwrite the workbook's bytes in the same file.

    Saving to a temporary file and renaming it over the old one looked safe,
    but OneDrive reads a rename as a delete plus a brand-new file: a full
    re-upload, version history broken, and -- with the file open in Excel
    Online at the time -- an upload that sat spinning. Writing into the same
    file is an ordinary edit, which OneDrive uploads in seconds.

    The bytes are built in memory first, so the file is only open for the
    write itself. If Excel or OneDrive has it locked, wait and retry rather
    than fail (or fight the sync)."""
    import time
    path = Path(path)
    for attempt in range(tries):
        try:
            if path.exists():
                with open(path, "r+b") as f:
                    f.seek(0)
                    f.write(data)
                    f.truncate()
            else:
                path.write_bytes(data)
            return
        except PermissionError:
            if attempt == tries - 1:
                raise PermissionError(f"{path.name} stayed locked for {tries * wait // 60} "
                                      "minutes (open in Excel, or OneDrive busy).")
            time.sleep(wait)


def write_tab(path, day: _dt.date, frame, state: dict, note: str = "", borrowed=()):
    """Write `frame` as the day's tab. Returns "written", "replaced" or
    "kept (edited)". `state` remembers the fingerprint of what was written,
    so an edited tab is never overwritten."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    path = Path(path)
    wb = openpyxl.load_workbook(path) if path.exists() else openpyxl.Workbook()
    if not path.exists():
        wb.remove(wb.active)
    name = tab_name(day)
    outcome = "written"
    old_fp = None
    if name in wb.sheetnames:
        old_fp = _fingerprint(wb[name])
        if state.get(name) != old_fp:
            return "kept (edited)"
        had_stamp = bool(wb[name].cell(row=1, column=STAMP_COL).value)
        wb.remove(wb[name])
        outcome = "replaced"
    ws = wb.create_sheet(name)
    reg = Font(name="Arial", size=10)
    hdr = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    fill = PatternFill("solid", fgColor="2563A8")
    for ci, h in enumerate(COLUMNS, 1):
        c = ws.cell(row=1, column=ci, value=h)
        c.font, c.fill = hdr, fill
        c.alignment = Alignment(horizontal="left", vertical="center")
        ws.column_dimensions[get_column_letter(ci)].width = WIDTHS.get(h, 14)
    for ri, row in enumerate(frame.to_dict("records"), 2):
        for ci, h in enumerate(COLUMNS, 1):
            v = row.get(h, "")
            if h == "Time (min)":
                try:
                    v = int(float(v))
                except (TypeError, ValueError):
                    v = v or ""
            if v is None or (isinstance(v, float) and v != v) or v == "nan":
                v = ""                         # NaN is pandas' blank; write it as one
            ws.cell(row=ri, column=ci, value=v).font = reg
    _write_summary(ws, len(frame) + 3, frame, day, borrowed)
    import clock
    built = clock.now()
    c = ws.cell(row=1, column=STAMP_COL,
                value=f"Built {built:%a %b} {built.day}, {built:%I:%M %p}".replace(" 0", " ")
                      + (f" · {note}" if note else ""))
    c.font = Font(name="Arial", size=10, bold=True, color="16202E")
    c.fill = PatternFill("solid", fgColor="FFF4CC")
    ws.column_dimensions[get_column_letter(STAMP_COL)].width = 58
    ws.freeze_panes = "A2"
    # Day tabs in date order, the newest last, and only the last month kept.
    from hotsos_sync import tab_date
    dated = sorted((tab_date(s, day.year) or _dt.date.min, s) for s in wb.sheetnames)
    for _, s in dated[:-KEEP_TABS]:
        wb.remove(wb[s])
    wb._sheets.sort(key=lambda ws_: tab_date(ws_.title, day.year) or _dt.date.min)
    wb.active = len(wb.sheetnames) - 1
    # Nothing new: don't touch the file. Every save is an upload, and a
    # rebuild that changes nothing shouldn't put the file back in the queue.
    if old_fp is not None and had_stamp and _fingerprint(ws) == old_fp:
        return "unchanged"                 # the stamp keeps the build that made it
    buf = io.BytesIO()
    wb.save(buf)
    _save_in_place(path, buf.getvalue())
    state[name] = _fingerprint(openpyxl.load_workbook(path)[name])
    return outcome


def assign_dust_n_vac(frame):
    """Dust n Vac is RQS 2's round: in the sheet, RQS 2 is its housekeeper too.

    The app leaves HSKP empty on those rows (no housekeeper wants the round),
    which left HotSOS with nobody to give the rooms to; the team filled in RQS 2
    by hand every morning. The RQS column of a Dust n Vac row already names
    that day's RQS 2, so it's copied across where HSKP is empty."""
    if frame is None or frame.empty or "Service" not in frame.columns:
        return frame
    frame = frame.copy()
    hskp = frame["HSKP"].fillna("").astype(str).str.strip()
    rqs = frame["RQS"].fillna("").astype(str).str.strip()
    dv = frame["Service"].fillna("").astype(str).str.strip().str.lower().eq("dust n vac")
    # The app writes the placeholder "RQS 2" when the staff schedule names
    # nobody for the role that day; that isn't a person HotSOS knows.
    placeholder = rqs.str.lower().str.replace(r"[^a-z0-9]", "", regex=True).isin(["rqs2", "rq2"])
    fill = dv & hskp.eq("") & rqs.ne("") & ~placeholder
    frame.loc[fill, "HSKP"] = frame.loc[fill, "RQS"]
    return frame


# ── who is light, and what would fill their chart ───────────────────────────
LOW_MIN, CAP_FC, CAP_DS = 330, 380, 460      # the Schedule page's LOW_MIN, MAX_FC, DS_CAP


def _unstaffed(name) -> bool:
    n = str(name or "").strip().lower()
    return not n or n.startswith(("no hk", "need housekeeper"))


def _needs_person(name) -> bool:
    """A chart the app couldn't staff ("No HK available 1"). A blank HSKP is
    different: the app leaves Unallocated rooms (maybe already clean) and
    stayovers to verify blank on purpose, for the RQS to decide."""
    return str(name or "").strip().lower().startswith(("no hk", "need housekeeper"))


def _minutes(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def staff_summary(frame):
    """One line per housekeeper: rooms, minutes by service, and whether the
    day is Light (under LOW_MIN), Full, or Over the chart's cap."""
    people = {}
    for r in frame.to_dict("records"):
        who = str(r.get("HSKP") or "").strip()
        if _unstaffed(who):
            continue
        p = people.setdefault(who, {"name": who, "rooms": 0, "minutes": 0,
                                    "Full Clean": 0, "Daily Service": 0, "Dust n Vac": 0})
        svc = str(r.get("Service") or "").strip()
        m = _minutes(r.get("Time (min)"))
        p["rooms"] += 1
        p["minutes"] += m
        key = next((k for k in ("Full Clean", "Daily Service", "Dust n Vac") if svc.startswith(k)), None)
        if key:
            p[key] += m if key != "Dust n Vac" else 1
    out = []
    for p in people.values():
        p["main"] = "Daily Service" if p["Daily Service"] > p["Full Clean"] else "Full Clean"
        p["cap"] = CAP_DS if p["main"] == "Daily Service" else CAP_FC
        # Dust n Vac carries no minutes on the sheet, and it is RQS 2's round:
        # someone whose day is only that is not a light housekeeper.
        if p["Dust n Vac"] and not (p["Full Clean"] or p["Daily Service"]):
            p["status"] = "RQS 2 · Dust n Vac"
        else:
            p["status"] = ("Light" if p["minutes"] < LOW_MIN else
                           "Over" if p["minutes"] > p["cap"] else "Full")
        out.append(p)
    return sorted(out, key=lambda p: p["minutes"])


def _bundles(rows):
    """Rooms that move together: one guest's rooms on one floor are an
    apartment (the app's own rule), and two people in one apartment is two
    people doing one turnover."""
    groups = {}
    for r in rows:
        room = str(r["Room"])
        key = (str(r.get("Current Guest or Status") or room), room[:2], str(r.get("Service")))
        groups.setdefault(key, []).append(r)
    return [{"rooms": [x["Room"] for x in g], "minutes": sum(_minutes(x.get("Time (min)")) for x in g),
             "service": str(g[0].get("Service") or ""), "bld": str(g[0]["Room"])[0],
             "floor": int(str(g[0]["Room"])[1]) if str(g[0]["Room"])[1].isdigit() else 0,
             "from": str(g[0].get("HSKP") or "") or "nobody"} for g in groups.values()]


def suggest_moves(frame):
    """For each Light housekeeper, lightest first: rooms that would fill the
    chart toward a full day without passing its cap -- unstaffed rooms first,
    then rooms from anyone Over. Same service only, the same building first,
    then the nearest floor. Advice for the RQS, not a change."""
    rows = [r for r in frame.to_dict("records") if str(r.get("Room") or "").strip()]
    summary = {p["name"]: p for p in staff_summary(frame)}
    loads = {n: p["minutes"] for n, p in summary.items()}
    taken, moves = set(), []

    def place(person, pool, source):
        p = summary[person]
        mine = [r for r in rows if r.get("HSKP") == person]
        blds = {str(r["Room"])[0] for r in mine}
        floors = [int(str(r["Room"])[1]) for r in mine if str(r["Room"])[1].isdigit()] or [0]
        for b in sorted(pool, key=lambda b: (b["bld"] not in blds,
                                             min(abs(b["floor"] - f) for f in floors),
                                             -b["minutes"])):
            if loads[person] >= LOW_MIN:
                return
            if tuple(b["rooms"]) in taken or not b["minutes"]:
                continue
            if not b["service"].startswith(p["main"]):
                continue
            import rule23
            if rule23._is_fc(b["service"]) and rule23.mixes(
                    {str(r["Room"])[0] for r in mine if rule23._is_fc(r.get("Service"))} | {b["bld"]}):
                continue                       # hard rule: never buildings 2 and 3
            if loads[person] + b["minutes"] > p["cap"]:
                continue
            if source == "over" and loads[b["from"]] - b["minutes"] < LOW_MIN:
                continue                       # don't make the giver light
            taken.add(tuple(b["rooms"]))
            before = loads[person]
            loads[person] += b["minutes"]
            if source == "over":
                loads[b["from"]] -= b["minutes"]
            moves.append({"rooms": b["rooms"], "service": b["service"], "minutes": b["minutes"],
                          "from": b["from"], "to": person, "before": before, "after": loads[person],
                          "why": ("unstaffed" if source == "unstaffed" else f"{b['from']} is over")
                                 + ("" if b["bld"] in blds else ", other building")})

    unstaffed = _bundles([r for r in rows if _needs_person(r.get("HSKP"))
                          and not str(r.get("Service") or "").startswith("Dust")])
    over = _bundles([r for r in rows if summary.get(r.get("HSKP"), {}).get("status") == "Over"])
    for person in [n for n, p in summary.items() if p["status"] == "Light"]:
        place(person, unstaffed, "unstaffed")
        place(person, over, "over")
    return moves, loads


def free_staff(frame, day):
    """Who the staff schedule has on for `day` with nothing in the sheet.

    Housekeepers and RQS scheduled to work (Schedule.xlsx, read the way the
    rest of the app reads it) whose name is in neither the HSKP nor the RQS
    column. RQS 1 is never free -- the role carries projects even with no
    rooms -- and people on other duties (deep clean, HSP, projects) aren't
    free either; they're returned apart, as help a short day could ask for.
    None when the staff schedule doesn't cover the day."""
    try:
        import db
        import forecast
        import roster_import as ri
        iso = day.isoformat()
        sched = forecast.scheduled(db.load_staff_weeks(), db.load_staff_overrides(), iso)
        if sched is None:
            return None
        wk = ri.find_week_key(db.staff_week_keys(), iso)
        upd = ri.day_roster(db.load_staff_week(wk), db.load_staff_overrides(), wk, iso,
                            (db.load_roster() or {}).get("hk_roster", {})) or {}
    except Exception as ex:
        print(f"[daily_build] free staff not worked out: {ex}")
        return None
    used = {str(v).strip() for col in ("HSKP", "RQS") for v in frame[col].dropna()}
    rqs1 = (upd.get("rqs1") or "").strip()
    free = []
    for name in sched["hk_fc"]:
        if name not in used:
            free.append((name, "Housekeeper", "Full Clean"))
    for name in sched["hk_ds"]:
        if name not in used:
            free.append((name, "Housekeeper", "Daily Service"))
    for name in sched["rqs"]:
        if name not in used and name != rqs1:
            free.append((name, "RQS", "RQS 2" if name == upd.get("rqs2") else "RQS"))
    return {"free": free, "rqs1": rqs1, "other": sched["other"]}


def tab_edited(path, day: _dt.date, state: dict) -> bool:
    """Has anyone changed the day's tab since it was written?"""
    import openpyxl
    path = Path(path)
    if not path.exists():
        return False
    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        name = tab_name(day)
        return name in wb.sheetnames and state.get(name) != _fingerprint(wb[name])
    finally:
        wb.close()


def build(day: _dt.date, ssrs_xlsx: bytes, arrival_text: str, workbook_path,
          state: dict, publish=True):
    """The whole morning: rooms + e-mail -> Generate -> the day's tab.

    Once the team has edited the day's tab, the day is theirs: nothing is
    generated, written or saved."""
    if tab_edited(workbook_path, day, state):
        return {"rooms": None, "charts": None, "housekeepers": None,
                "tab": tab_name(day), "outcome": "kept (edited)"}
    excel_to_room_text, build_export_frame = borrow("excel_to_room_text",
                                                    "build_export_frame")
    room_text, n_rooms, _sheet = excel_to_room_text(io.BytesIO(ssrs_xlsx))
    fg = generate(room_text, arrival_text, publish=publish, day=day)
    frame = assign_dust_n_vac(build_export_frame(fg))
    # Whoever was pulled off another duty says so on their own rows, where the
    # RQS reading the sheet will see it.
    for name, role, duty in getattr(generate, "borrowed", []):
        col = "HSKP" if role == "Housekeeper" else "RQS"
        mask = frame[col].fillna("").astype(str).str.strip() == name
        tag = f"{name.split()[0]} pulled from {duty} (short staffed)"
        frame.loc[mask, "Notes"] = [
            f"{n}; {tag}" if str(n or "").strip() not in ("", "nan") else tag
            for n in frame.loc[mask, "Notes"]]
    outcome = write_tab(workbook_path, day, frame, state,
                        note="Arrival Report included" if (arrival_text or "").strip()
                        else "no Arrival Report yet",
                        borrowed=getattr(generate, "borrowed", []))
    staffed = sorted({g.get("housekeeper") for g in fg if g.get("housekeeper")})
    dv = frame[frame["Service"].fillna("").str.strip().str.lower().eq("dust n vac")]         if not frame.empty else frame
    dv_blank = int((dv["HSKP"].fillna("").astype(str).str.strip() == "").sum()) if len(dv) else 0
    return {"rooms": int(n_rooms), "charts": len(fg), "housekeepers": len(staffed),
            "tab": tab_name(day), "outcome": outcome, "dv_unassigned": dv_blank,
            "borrowed": [f"{n} ({duty})" for n, _, duty in getattr(generate, "borrowed", [])]}
