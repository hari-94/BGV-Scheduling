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


def generate(room_text: str, arrival_text: str, publish=True, timeout=900):
    """Run the Schedule page's Generate with these inputs. Returns the groups
    (charts) it produced. With publish=True the page saves them as today's
    schedule, exactly as a person pressing Generate would."""
    from contextlib import nullcontext
    from streamlit.testing.v1 import AppTest
    with (nullcontext() if publish else _NoWrites()):
        at = AppTest.from_file(str(PAGE), default_timeout=timeout)
        for k, v in {"logged_in": True, "username": "auto-5am",
                     "display_name": "5 AM auto-build", "role": "admin"}.items():
            at.session_state[k] = v
        at.run()                                   # first open: today's roster is applied
        _raise(at, "opening the Schedule page")
        _day_roles(at)
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


def _fingerprint(ws) -> str:
    rows = [[("" if c is None else str(c)) for c in r]
            for r in ws.iter_rows(values_only=True)]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def write_tab(path, day: _dt.date, frame, state: dict):
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
    if name in wb.sheetnames:
        if state.get(name) != _fingerprint(wb[name]):
            return "kept (edited)"
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
            ws.cell(row=ri, column=ci, value=v if v not in (None, "nan") else "").font = reg
    ws.freeze_panes = "A2"
    # Day tabs in date order, the newest last, and only the last month kept.
    from hotsos_sync import tab_date
    dated = sorted((tab_date(s, day.year) or _dt.date.min, s) for s in wb.sheetnames)
    for _, s in dated[:-KEEP_TABS]:
        wb.remove(wb[s])
    wb._sheets.sort(key=lambda ws_: tab_date(ws_.title, day.year) or _dt.date.min)
    wb.active = len(wb.sheetnames) - 1
    tmp = path.with_suffix(".tmp.xlsx")
    wb.save(tmp)
    tmp.replace(path)                 # one rename: OneDrive never sees a half-written file
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
    fg = generate(room_text, arrival_text, publish=publish)
    frame = assign_dust_n_vac(build_export_frame(fg))
    outcome = write_tab(workbook_path, day, frame, state)
    staffed = sorted({g.get("housekeeper") for g in fg if g.get("housekeeper")})
    dv = frame[frame["Service"].fillna("").str.strip().str.lower().eq("dust n vac")]         if not frame.empty else frame
    dv_blank = int((dv["HSKP"].fillna("").astype(str).str.strip() == "").sum()) if len(dv) else 0
    return {"rooms": int(n_rooms), "charts": len(fg), "housekeepers": len(staffed),
            "tab": tab_name(day), "outcome": outcome, "dv_unassigned": dv_blank}
