"""
Report — who inspected and who cleaned how many rooms, beside the days the
staff schedule had them on.

The rooms come from the team's own record, GC8 Inspections (one tab a day),
which the office PC reads at 4 PM and whenever somebody presses Sync
(report_data, hotsos_agent.sync_report). The days come from the staff
schedule the app already holds. Managers only, as Stats is.

Nothing here touches a workbook. The page writes two things: a sync request
for the office PC, and its own name fixes (report_data.NAMES_KEY).
"""
import datetime as _dt
import hashlib
import html
import json
import os
import sys
import uuid

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, clock, db, ui            # noqa: E402
import hotsos_sync as hs              # noqa: E402
import report_data as rd              # noqa: E402
import report_table                   # noqa: E402

st.set_page_config(page_title="Report", page_icon="📋", layout="wide")
st.markdown("""<style>
.block-container{max-width:min(1200px,97%);}
[data-testid='stSidebarNav']{display:none!important;}
.rp-h1{font-size:1.55rem;font-weight:800;color:#16202e;margin:0;line-height:1.2}
.rp-src{font-size:.8rem;color:#5b6675;margin:3px 0 0}
.rp-badges{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 4px}
.rp-b{font-size:.72rem;font-weight:600;padding:3px 10px;border-radius:999px;background:#e8f6ec;
      color:#11692f;border:1px solid #c6ebd1}
.rp-b.warn{background:#fff6e5;color:#7a4b00;border-color:#f6d9a0}
.rp-badges [data-tip]{position:relative;cursor:help;outline:none}
.rp-badges [data-tip]:hover::after,.rp-badges [data-tip]:focus::after{content:attr(data-tip);
  position:absolute;top:calc(100% + 7px);left:0;z-index:40;width:300px;white-space:pre-line;
  font-weight:500;font-size:.76rem;line-height:1.45;color:#1f2733;background:#fff;
  border:1px solid #d5dce6;border-radius:10px;padding:9px 11px;
  box-shadow:0 10px 26px rgba(16,26,42,.16)}
.rp-hint{font-size:.74rem;color:#7b8798;margin:2px 2px 0}
.rp-lo{font-size:.82rem;color:#1f2733;line-height:1.75}
.rp-lo b{color:#16202e}
</style>""", unsafe_allow_html=True)

# The tables are drawn inside the report_table component (components/
# report_table), which sorts them when a column name is clicked; their look
# goes with them, since a component's frame doesn't see the page's styles.
TABLE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700;9..40,800&display=swap');
html,body{margin:0;padding:0;background:transparent}
body{font-family:'DM Sans',system-ui,-apple-system,'Segoe UI',sans-serif;color:#1f2733;
     -webkit-font-smoothing:antialiased}
#root{padding:2px 2px 4px}
.rp-card{background:#fff;border:1px solid #e6e9ee;border-radius:16px;padding:14px 16px 8px;
         box-shadow:0 1px 2px rgba(16,26,42,.04)}
.rp-ct{font-size:1.12rem;font-weight:800;color:#16202e}
.rp-cs{font-size:.8rem;color:#5b6675;margin:2px 0 10px}
.rp-cs b{color:#16202e}
.rp-scroll{overflow-x:auto}
.rp-tab{min-width:900px}
.rp-grid{display:grid;align-items:center;column-gap:10px}
.rp-hdr{background:#f3f6fa;border-radius:10px;padding:7px 8px;row-gap:3px}
.rp-hdr .h{font-size:.64rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
           color:#4b5667;text-align:right;line-height:1.25}
.rp-hdr .h.l{text-align:left}
.rp-hdr .h.s{cursor:pointer;user-select:none;border-radius:6px;padding:3px 4px;margin:-3px -4px;
             outline:none;transition:background .12s,color .12s}
.rp-hdr .h.s:hover,.rp-hdr .h.s:focus-visible{background:#e2e9f2;color:#16202e}
.rp-hdr .h.on{color:#1c4a78;background:#e8eff8}
.rp-hdr .h .ar{display:inline-block;margin-left:4px;font-size:.66rem;color:#aab3bf;letter-spacing:0}
.rp-hdr .h.on .ar{color:#2563a8}
.rp-hdr .g{font-size:.6rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
           color:#7b8798;text-align:center;border-bottom:1px solid #d5dce6;padding-bottom:3px}
details.rp-p{border-bottom:1px solid #eef1f5}
details.rp-p:last-child{border-bottom:none}
details.rp-p>summary{list-style:none;cursor:pointer;padding:7px 8px;border-radius:8px}
details.rp-p>summary::-webkit-details-marker{display:none}
details.rp-p>summary:hover{background:#f6f8fb}
details.rp-p[open]>summary{background:#eef4fb}
.rp-c{font-size:.84rem;color:#16202e;text-align:right;font-variant-numeric:tabular-nums;
      font-family:'DM Mono',ui-monospace,SFMono-Regular,Menlo,monospace}
.rp-c.z{color:#a9b1bd}
.rp-c.rk{color:#7b8798}
.rp-c.nm{text-align:left;font-family:inherit;font-weight:600;white-space:nowrap;overflow:hidden;
         text-overflow:ellipsis}
.rp-c.nm .chev{display:inline-block;color:#9aa5b4;margin-left:6px;transition:transform .15s}
details[open] .chev{transform:rotate(90deg)}
.rp-bar{display:flex;align-items:center;gap:8px}
.rp-trk{flex:1;height:9px;background:#eef1f5;border-radius:5px;overflow:hidden}
.rp-fil{display:block;height:9px;background:#3b82d6;border-radius:5px}
.rp-bar b{min-width:48px;text-align:right;font-weight:700}
.rp-nc{display:inline-block;min-width:22px;padding:0 7px;border-radius:999px;background:#fdecec;
       color:#b42318;font-weight:700;text-align:center}
.rp-more{padding:10px 8px 16px 46px}
.rp-facts{display:flex;flex-wrap:wrap;gap:5px 20px;font-size:.8rem;color:#3b4554;margin-bottom:10px}
.rp-facts b{color:#16202e}
.rp-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.rp-k{background:#f7f9fc;border:1px solid #e6e9ee;border-radius:12px;padding:8px 10px}
.rp-k .kt{font-size:.68rem;font-weight:700;color:#5b6675;text-transform:uppercase;letter-spacing:.05em}
.rp-k .kv{font-size:1.15rem;font-weight:800;color:#16202e;margin:1px 0 2px}
.rp-k .kv small{font-size:.7rem;font-weight:600;color:#5b6675;margin-left:4px}
.rp-k .kl{font-size:.74rem;color:#3b4554;line-height:1.5}
.rp-k.empty{opacity:.5}
.rp-k .nc{color:#b42318;font-weight:700}
"""
auth.require_login()
ui.topnav("Report")
# Managers only, the same permission Stats uses: auth is an imported module and
# a running app keeps its old copy after a deploy, so no new permission name.
if not auth.can("can_manage_users"):
    st.error("The report is for managers.")
    st.stop()

e = html.escape
me = st.session_state.get("display_name") or auth.current_user().get("username", "")


def tip(text) -> str:
    """A note for a data-tip attribute. Its line breaks go in as &#10;: a
    blank line inside st.markdown's HTML ends the HTML block, and the rest of
    the table came out as text."""
    return e(text).replace("\n", "&#10;")


def _md5(obj) -> str:
    return hashlib.md5(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _t(stamp):
    try:
        t = _dt.datetime.fromisoformat(str(stamp))
        return t if t.tzinfo else t.replace(tzinfo=clock.MTN)
    except Exception:
        return None


def _when(stamp) -> str:
    t = _t(stamp)
    if not t:
        return "—"
    t = t.astimezone(clock.MTN)
    day = "today" if t.date() == clock.today() else f"{t:%a %b} {t.day}"
    return f"{day} at {t:%I:%M %p}".replace(" 0", " ").lower().replace("am", "AM").replace("pm", "PM")


def _d(iso) -> str:
    d = _dt.date.fromisoformat(iso)
    return f"{d:%b} {d.day}"


# ── the numbers ──────────────────────────────────────────────────────────────
@st.cache_resource(max_entries=2, show_spinner="Counting every day on the sheet…")
def _built(sync_token, roster_token, names_token, _weeks, _ov, _fixes, _aliases):
    import roster_import as ri
    import staff_names
    days = rd.load_days(db)
    if not days:
        return None
    first, last = min(days), max(days)
    roster, visiting = rd.roster_days(_weeks, _ov, first, last)
    directory = rd.Directory(list(roster), [a["label"] for a in staff_names.attendants()],
                             _aliases, _fixes, ri.NAME_ALIASES)
    res = rd.build(days, roster, visiting, directory)
    res.update(first=first, last=last, names=directory.names,
               tabs={iso: d["tab"] for iso, d in days.items()})
    return res


sync = db._load_key(rd.SYNC_KEY) or {}
req = db._load_key(rd.REQUEST_KEY) or {}
fixes = db._load_key(rd.NAMES_KEY) or {}
try:
    import staff_names
    aliases = staff_names.aliases()
except Exception:
    aliases = {}
weeks = db.load_staff_weeks()
overrides = db.load_staff_overrides()
res = _built(f"{sync.get('at')}|{_md5(sync.get('months') or {})}",
             f"{getattr(db, '_WEEKS', {}).get('v')}|{len(weeks)}|{_md5(overrides)}",
             _md5([fixes, aliases]), weeks, overrides, fixes, aliases)


# ── header: where the numbers come from, and Sync ────────────────────────────
def _pending(s, r) -> bool:
    if s.get("status") == "running":
        t = _t(s.get("started_at"))
        return bool(t) and (clock.now() - t).total_seconds() < 900
    ra = _t(r.get("at"))
    if not ra or (clock.now() - ra).total_seconds() > 900:
        return False
    done = [x for x in (_t(s.get("at")), _t(s.get("failed_at"))) if x]
    return not done or ra > max(done)


h1, h2 = st.columns([5, 1.2], vertical_alignment="bottom")
with h1:
    src = []
    if sync.get("at"):
        src.append(f"Synced {_when(sync['at'])} — {e(sync.get('source') or '')}")
        if sync.get("file_saved_at"):
            src.append(f"sheet last saved {_when(sync['file_saved_at'])}"
                       + (f" by {e(sync['file_by'])}" if sync.get("file_by") else ""))
    st.markdown(f'<div class="rp-h1">📋 Report</div><div class="rp-src">Rooms from '
                f'<b>GC8 Inspections</b>, read every day at 4 PM · days from the staff schedule'
                f'{"<br>" + " · ".join(src) if src else ""}</div>', unsafe_allow_html=True)
with h2:
    if st.button("🔄 Sync now", use_container_width=True,
                 help="Ask the office PC to read GC8 Inspections again now — for a "
                      "correction somebody just made. It takes about a minute."):
        db._upsert_key(rd.REQUEST_KEY, {"id": uuid.uuid4().hex, "by": me, "at": clock.stamp()})
        req = db._load_key(rd.REQUEST_KEY) or {}

if _pending(sync, req):
    @st.fragment(run_every=5)
    def _watch():
        s = db._load_key(rd.SYNC_KEY) or {}
        if not _pending(s, db._load_key(rd.REQUEST_KEY) or {}):
            st.rerun()
        beat = _t((db._load_key(hs.HEARTBEAT_KEY) or {}).get("at"))
        if beat and (clock.now() - beat).total_seconds() < 180:
            st.info("⏳ The office PC is reading GC8 Inspections — the numbers update by "
                    "themselves in about a minute.")
        else:
            st.warning("Sync asked for, but the office PC isn't connected. It will read the "
                       "sheet as soon as it's back on.")
    _watch()
elif sync.get("status") == "error":
    st.error(f"The last sync failed ({_when(sync.get('failed_at'))}): {sync.get('error')}. "
             "The numbers below are from the sync before it.")

if not res:
    st.info("Nothing synced yet. Press **Sync now** and the office PC will read the sheet.")
    st.stop()

# Workbook-wide checks, as badges.
chk = sync.get("checks") or {}
badges = []
two = chk.get("two_tabs") or {}
badges.append(("", "✓ One tab per date",
               "Where two tabs claim a date, the one filled in more is used:\n" +
               "\n".join(f"{_d(d)}: '{v['used']}' (not {', '.join(repr(x) for x in v['not used'])})"
                         for d, v in sorted(two.items())) if two else "Every date has a single tab."))
if chk.get("app_copies"):
    badges.append(("", "✓ The app's own copies left out",
                   "Tabs the app made to compare with the team's: " + ", ".join(chk["app_copies"])))
badges.append(("", f"✓ Repeated rows removed ({chk.get('repeats_removed', 0)})",
               "A room listed twice for the same job on one tab is counted once."))
badges.append(("" if not chk.get("copied_tabs") else "warn",
               "✓ No copied tabs" if not chk.get("copied_tabs") else
               f"! {len(chk['copied_tabs'])} tab(s) look copied",
               "A tab identical to another day's would carry that day's names." +
               ("\n" + "\n".join(chk["copied_tabs"]) if chk.get("copied_tabs") else "")))
if chk.get("unreadable"):
    badges.append(("warn", f"! {len(chk['unreadable'])} tab(s) couldn't be read",
                   "No Service/RQS header row found:\n" + "\n".join(chk["unreadable"])))
if chk.get("missing_dates"):
    badges.append(("warn", f"! {len(chk['missing_dates'])} date(s) have no tab",
                   "No tab for: " + ", ".join(_d(d) for d in chk["missing_dates"])))
st.markdown('<div class="rp rp-badges">' + "".join(
    f'<span class="rp-b {c} tl" data-tip="{tip(t_)}" tabindex="0">{e(lab)}</span>'
    for c, lab, t_ in badges) + "</div>", unsafe_allow_html=True)


# ── filters ──────────────────────────────────────────────────────────────────
first = _dt.date.fromisoformat(res["first"])
last = _dt.date.fromisoformat(res["last"])
f1, f2, f3 = st.columns([2.3, 2.2, 2.2], vertical_alignment="bottom")
with f1:
    mode = st.segmented_control("Period", ["Week", "Month", "Year", "Date range"],
                                default="Year", key="rp_mode") or "Year"
with f2:
    if mode == "Date range":
        rng = st.date_input("From – to", value=(last.replace(day=1), last), min_value=first,
                            max_value=last, key="rp_range", format="MM/DD/YYYY")
        a = rng[0] if rng else last
        b = rng[1] if isinstance(rng, (tuple, list)) and len(rng) > 1 else a
    else:
        pick = st.date_input("Any day in it", value=last, min_value=first, max_value=last,
                             key="rp_pick", format="MM/DD/YYYY")
        if mode == "Week":
            a = pick - _dt.timedelta(days=(pick.weekday() + 1) % 7)
            b = a + _dt.timedelta(days=6)
        elif mode == "Month":
            a = pick.replace(day=1)
            b = (a.replace(day=28) + _dt.timedelta(days=4)).replace(day=1) - _dt.timedelta(days=1)
        else:
            a, b = pick.replace(month=1, day=1), pick.replace(month=12, day=31)
with f3:
    team = st.segmented_control("Show", ["Both", "RQS", "Housekeepers"], default="Both",
                                key="rp_team") or "Both"
start, end = max(a, first).isoformat(), min(b, last).isoformat()
if start > end:
    st.info("No synced days in that period.")
    st.stop()
so_far = " (so far)" if b > last else ""
s0, e0 = _dt.date.fromisoformat(start), _dt.date.fromisoformat(end)
period = (f"{s0:%b} {s0.day} – {e0:%b} {e0.day}, {e0.year}" if s0.year == e0.year
          else f"{s0:%b} {s0.day}, {s0.year} – {e0:%b} {e0.day}, {e0.year}")
if s0 == e0:
    period = f"{s0:%a %b} {s0.day}, {s0.year}"


# ── the tables ───────────────────────────────────────────────────────────────
MORE, LESS, NEITHER = "\n\n▲ More is better.", "\n\n▼ Less is better — 0 is the goal.", "\n\n◆ Neither better nor worse: it explains the other numbers."
RQS_COLS = [
    # key, group, label, tip
    ("rank", None, "#", "Rank by rooms inspected in this period. The same number shared means the same count."),
    ("person", None, "Name", "Click a name for their day-of-week habits and month-by-month cards."),
    ("in", None, "Rooms inspected",
     "Full Clean rooms with this person's name in the RQS column — check-outs, in-house full "
     "cleans, early outs and deep cleans. The first name in the cell counts (\"Oralia/Josseling\" "
     "is Oralia with a trainee). Daily Service rooms are not counted: RQS 2 looks at those on a "
     "round, not one by one. Read it with Days on the schedule." + MORE),
    ("fc", "Rooms they cleaned", "Full Clean",
     "Full Clean rooms with this person's name in the HSKP column: rooms an RQS cleaned "
     "themselves. A room two people cleaned counts for both." + NEITHER +
     " A high number means they were pulled off inspecting to clean."),
    ("ds", "Rooms they cleaned", "Daily Service",
     "Daily Service rooms (stayovers, exchanges) with this person's name in the HSKP column." +
     NEITHER),
    ("days_in", None, "Days inspecting",
     "Days with at least one inspected room on the sheet. The gap to Days on the schedule is "
     "RQS 2 days (Daily Service and Dust n Vac rounds), projects, and days nobody wrote a name."
     + MORE),
    ("per_day", None, "Per day",
     "Rooms inspected ÷ days inspecting: the size of an ordinary day. 12–13 is a full round."
     "\n\n▲ Higher means a heavier day — but very high can mean rushed inspections."),
    ("sched", "On the schedule", "Days",
     "Days the staff schedule had them working on the RQS team, projects included, up to the "
     "last synced day." + MORE),
    ("project", "On the schedule", "Projects",
     "Days on their RQS row that weren't inspecting: projects, ENG, ULLR, rollaways…" + NEITHER),
    ("nocall", None, "No call / no show",
     "Days marked no-call/no-show on the staff schedule — a red cell, or NCNS typed in." + LESS),
]
HK_COLS = [
    ("rank", None, "#", "Rank by rooms cleaned in this period. The same number shared means the same count."),
    ("person", None, "Name", "Click a name for their day-of-week habits and month-by-month cards."),
    ("cleaned", None, "Rooms cleaned",
     "Every room with this person's name in the HSKP column: Full Clean and Daily Service "
     "together. A room two people cleaned counts for both. Read it with the days on the "
     "schedule — a Full Clean takes 70–140 minutes, a Daily Service about 30." + MORE),
    ("fc", "Rooms cleaned by service", "Full Clean",
     "Check-outs, in-house full cleans, early outs and deep cleans. Four or five is a full day."
     + MORE),
    ("ds", "Rooms cleaned by service", "Daily Service",
     "Stayovers, sheet and towel exchanges. Ten to thirteen is a full day." + MORE),
    ("main", "Days on the schedule", "Full Clean",
     "Days the staff schedule had them on Full Clean charts (a building number or ON)." + MORE),
    ("ds_days", "Days on the schedule", "Daily Service",
     "Days the staff schedule had them on Daily Service." + NEITHER),
    ("project", "Days on the schedule", "Projects",
     "Days on their row that were other duties: projects, garages, food, HSP cover, stripping "
     "linen…" + NEITHER),
    ("nocall", None, "No call / no show",
     "Days marked no-call/no-show on the staff schedule — a red cell, or NCNS typed in." + LESS),
]
GRID = {"rqs": "36px minmax(150px,1.25fr) minmax(190px,2fr) 72px 72px 78px 62px 60px 66px 78px",
        "hk": "36px minmax(150px,1.25fr) minmax(190px,2fr) 72px 72px 74px 74px 66px 78px"}


def _num(v, key):
    if v is None:
        return '<div class="rp-c z">—</div>'
    if key == "nocall":
        return (f'<div class="rp-c"><span class="rp-nc">{v}</span></div>' if v
                else '<div class="rp-c z">0</div>')
    txt = f"{v:,}" if isinstance(v, int) else f"{v}"
    return f'<div class="rp-c{" z" if not v else ""}">{txt}</div>'


def _header(cols, role):
    """Column names that sort the table when clicked (report_table does the
    sorting): numbers most first, names A to Z, a second click reverses."""
    cells, groups = [], {}
    for i, (k, g, lab, _note) in enumerate(cols, 1):
        left = " l" if k in ("person", "in", "cleaned") else ""
        first = "asc" if k in ("rank", "person") else "desc"
        if g:
            groups.setdefault(g, []).append(i)
            pos = f"grid-row:2;grid-column:{i}"
        else:
            pos = f"grid-row:1/span 2;grid-column:{i}"
        cells.append(f'<div class="h s{left}" style="{pos}" data-col="{k}" data-first="{first}" '
                     f'role="button" tabindex="0" aria-label="Sort by {e(lab)}">'
                     # The arrow travels with the last word rather than
                     # wrapping onto a line of its own in a narrow column.
                     f'{e(lab).rsplit(" ", 1)[0] + " " if " " in lab else ""}'
                     f'<span style="white-space:nowrap">{e(lab.rsplit(" ", 1)[-1])}'
                     f'<span class="ar">⇅</span></span></div>')
    for g, idx in groups.items():
        cells.append(f'<div class="g" style="grid-row:1;grid-column:{idx[0]}/span {len(idx)}">'
                     f'{e(g)}</div>')
    return (f'<div class="rp-grid rp-hdr" style="grid-template-columns:{GRID[role]}">'
            + "".join(cells) + "</div>")


def _facts(r, role, start, end):
    out = []
    ud = rd.usual_days(r.get("dows") or {})
    if ud:
        per_wk = r.get("sched", 0) / max(rd.weeks_in(start, end), 1)
        out.append(f"Usually works <b>{' · '.join(ud)}</b>")
        out.append(f"<b>{per_wk:.1f}</b> days a week on average "
                   f"({r.get('sched', 0)} days in {rd.weeks_in(start, end):.1f} weeks)")
    if role == "rqs":
        if r.get("rqs2"):
            out.append(f"RQS 2 on <b>{r['rqs2']}</b> day{'s' if r['rqs2'] != 1 else ''}")
        if r.get("dv"):
            out.append(f"Dust n Vac inspected <b>{r['dv']:,}</b>")
    else:
        out.append(f"Rooms on the sheet on <b>{r.get('days_clean', 0)}</b> days")
        if r.get("in"):
            out.append(f"Inspected <b>{r['in']}</b> rooms")
    if r.get("projects"):
        top = sorted(r["projects"].items(), key=lambda x: -x[1])[:5]
        out.append("Projects: " + " · ".join(f"{e(k)} <b>{v}</b>" for k, v in top))
    if r.get("other_team"):
        teams = ", ".join(e(t) for t in r.get("teams") or {})
        out.append(f"Worked with another team on <b>{r['other_team']}</b> days ({teams})")
    if r.get("vto"):
        out.append(f"VTO <b>{r['vto']}</b> days")
    return "".join(f"<span>{x}</span>" for x in out)


def _card(label, t, role):
    if role == "rqs":
        main = f'{t.get("in", 0):,}<small>inspected</small>'
        lines = [f'{t["per_day"]} a day · {t.get("days_in", 0)} days' if t.get("per_day") else "",
                 f'Cleaned FC {t.get("fc", 0)} · DS {t.get("ds", 0)}' if t.get("fc") or t.get("ds") else "",
                 f'Scheduled {t.get("sched", 0)} days' + (f' · projects {t["project"]}' if t.get("project") else ""),
                 f'RQS 2 on {t["rqs2"]} days' if t.get("rqs2") else ""]
    else:
        main = f'{t.get("cleaned", 0):,}<small>cleaned</small>'
        lines = [f'FC {t.get("fc", 0)} · DS {t.get("ds", 0)}',
                 f'Days FC {t.get("main", 0)} · DS {t.get("ds_days", 0)}'
                 + (f' · proj {t["project"]}' if t.get("project") else "")]
    if t.get("nocall"):
        lines.append(f'<span class="nc">No call / no show {t["nocall"]}</span>')
    empty = not (t.get("sched") or t.get("in") or t.get("cleaned") or t.get("nocall"))
    return (f'<div class="rp-k{" empty" if empty else ""}"><div class="kt">{e(label)}</div>'
            f'<div class="kv">{main}</div>'
            + "".join(f'<div class="kl">{x}</div>' for x in lines if x) + "</div>")


def table_html(rows, role, start, end, title, sub):
    cols = RQS_COLS if role == "rqs" else HK_COLS
    bar_key = "in" if role == "rqs" else "cleaned"
    top = max([r.get(bar_key, 0) for r in rows] + [1])
    parts = [f'<div class="rp-card" data-table="{role}"><div class="rp-ct">{e(title)}</div>'
             f'<div class="rp-cs">{sub}</div><div class="rp-scroll"><div class="rp-tab">',
             _header(cols, role), '<div class="rp-body">']
    cuts = rd.slices(start, end)
    for r in rows:
        # What each column sorts on, as numbers ("per day" stays blank, not 0,
        # for someone with no inspections, and sorts last).
        sort_on = {k: (r.get(k) if k in ("per_day", "person") else r.get(k, 0))
                   for k, *_ in cols}
        cells = []
        for k, _g, _lab, _tip in cols:
            if k == "rank":
                cells.append(f'<div class="rp-c rk">{r["rank"]}</div>')
            elif k == "person":
                cells.append(f'<div class="rp-c nm">{e(r["person"])}<span class="chev">›</span></div>')
            elif k == bar_key:
                v = r.get(k, 0)
                cells.append(f'<div class="rp-c rp-bar"><span class="rp-trk"><span class="rp-fil" '
                             f'style="width:{100 * v / top:.1f}%"></span></span><b>{v:,}</b></div>')
            else:
                cells.append(_num(r.get(k, 0) if k != "per_day" else r.get(k), k))
        by_day = res["days"].get(r["person"], {})
        cards = "".join(_card(lab, rd.tally(by_day, a_, b_, role), role) for lab, a_, b_ in cuts)
        parts.append(f'<details class="rp-p" data-s="{e(json.dumps(sort_on))}">'
                     f'<summary class="rp-grid" '
                     f'style="grid-template-columns:{GRID[role]}">{"".join(cells)}</summary>'
                     f'<div class="rp-more"><div class="rp-facts">{_facts(r, role, start, end)}</div>'
                     f'<div class="rp-cards">{cards}</div></div></details>')
    parts.append("</div></div></div></div>")
    return "".join(parts)


def show(role):
    rows = rd.rows_for(res, start, end, role)
    label = "RQS" if role == "rqs" else "Housekeepers"
    if not rows:
        st.info(f"No {label.lower()} on the sheet or the schedule for {period}.")
        return
    if role == "rqs":
        tot = sum(r.get("in", 0) for r in rows)
        sub = (f"{len(rows)} people · <b>{tot:,}</b> rooms inspected · "
               f"{sum(r.get('nocall', 0) for r in rows)} no-call/no-show days")
    else:
        tot = sum(r.get("cleaned", 0) for r in rows)
        sub = (f"{len(rows)} people · <b>{tot:,}</b> rooms cleaned "
               f"({sum(r.get('fc', 0) for r in rows):,} Full Clean · "
               f"{sum(r.get('ds', 0) for r in rows):,} Daily Service) · "
               f"{sum(r.get('nocall', 0) for r in rows)} no-call/no-show days")
    report_table.table(html=table_html(rows, role, start, end, f"{label} · {period}{so_far}", sub),
                       css=TABLE_CSS, key=f"rp_table_{role}")
    st.markdown('<div class="rp-hint">Click a column name to sort by it — again to reverse · '
                'click a name for their months.</div>', unsafe_allow_html=True)
    with st.expander(f"What each {'RQS' if role == 'rqs' else 'housekeeper'} column means"):
        st.markdown("\n".join(
            f"- **{e(g) + ' · ' if g else ''}{e(lab)}** — "
            f"{e(note).replace(chr(10) + chr(10), ' ').replace(chr(10), ' ')}"
            for k, g, lab, note in (RQS_COLS if role == "rqs" else HK_COLS)
            if k not in ("person",)))


if team in ("Both", "RQS"):
    show("rqs")
if team in ("Both", "Housekeepers"):
    show("hk")


# ── download ─────────────────────────────────────────────────────────────────
EXCEL = {
    "rqs": [("Rank", "rank"), ("Name", "person"), ("Rooms inspected", "in"),
            ("Cleaned: Full Clean", "fc"), ("Cleaned: Daily Service", "ds"),
            ("Days inspecting", "days_in"), ("Inspections per day", "per_day"),
            ("Days on the schedule (RQS)", "sched"), ("Project days", "project"),
            ("No call / no show", "nocall"), ("RQS 2 days", "rqs2"),
            ("Dust n Vac inspected", "dv"), ("Days with another team", "other_team"),
            ("VTO days", "vto")],
    "hk": [("Rank", "rank"), ("Name", "person"), ("Rooms cleaned", "cleaned"),
           ("Full Clean", "fc"), ("Daily Service", "ds"), ("Days on Full Clean", "main"),
           ("Days on Daily Service", "ds_days"), ("Project days", "project"),
           ("No call / no show", "nocall"), ("Days with rooms on the sheet", "days_clean"),
           ("Days with another team", "other_team"), ("VTO days", "vto")],
}


@st.cache_data(max_entries=8, show_spinner="Making the file…")
def _excel(who, start, end, token):
    roles = ["rqs", "hk"] if who in ("Both", "RQS", "Housekeepers") else None
    person = None
    if who == "RQS":
        roles = ["rqs"]
    elif who == "Housekeepers":
        roles = ["hk"]
    elif roles is None:
        person = who
        roles = [res["people"][who]["role"]]
    sheets, by_month, by_day = {}, [], []
    for role in roles:
        rows = [r for r in rd.rows_for(res, start, end, role) if not person or r["person"] == person]
        cols = EXCEL[role]
        weeks_n = rd.weeks_in(start, end)
        sheets["RQS" if role == "rqs" else "Housekeepers"] = (
            [c for c, _ in cols] + ["Usual days", "Days a week (avg)"],
            [[r.get(k) if k in ("person", "per_day") else r.get(k, 0) for _, k in cols]
             + [" ".join(rd.usual_days(r.get("dows") or {})),
                round(r.get("sched", 0) / max(weeks_n, 1), 1)] for r in rows])
        for r in rows:
            by_d = res["days"].get(r["person"], {})
            for lab, a_, b_ in rd.slices(start, end):
                t = rd.tally(by_d, a_, b_, role)
                by_month.append([r["person"], "RQS" if role == "rqs" else "Housekeeper", lab, a_, b_,
                                 t.get("in", 0), t.get("per_day"), t.get("cleaned", 0), t.get("fc", 0),
                                 t.get("ds", 0), t.get("sched", 0), t.get("main", 0),
                                 t.get("ds_days", 0), t.get("project", 0), t.get("nocall", 0)])
            for iso in sorted(d for d in by_d if start <= d <= end):
                slot = by_d[iso]
                sched = [c for g, _s, k, c in slot.get("sched", ()) if g == role and c]
                nc = any(k == "no_call" for _g, _s, k, _c in slot.get("sched", ()))
                if not (sched or slot.get("in") or slot.get("fc") or slot.get("ds") or nc):
                    continue
                d = _dt.date.fromisoformat(iso)
                by_day.append([r["person"], "RQS" if role == "rqs" else "Housekeeper", iso,
                               f"{d:%a}", " / ".join(sched), res["tabs"].get(iso, ""),
                               len(slot.get("in", ())), " ".join(slot.get("in", ())),
                               len(slot.get("fc", ())), " ".join(slot.get("fc", ())),
                               len(slot.get("ds", ())), " ".join(slot.get("ds", ())),
                               len(slot.get("dv", ())), "yes" if nc else ""])
    span = rd.weeks_in(start, end) * 7
    if span > 7:                          # a week's slices are its days: "By day" has them
        sheets["By month" if span > 35 else "By week"] = (
            ["Name", "Role", "Period", "From", "To", "Rooms inspected", "Inspections per day",
             "Rooms cleaned", "Full Clean cleaned", "Daily Service cleaned",
             "Days on the schedule", "Full Clean / RQS days", "Daily Service days",
             "Project days", "No call / no show"], by_month)
    sheets["By day"] = (["Name", "Role", "Date", "Day", "On the schedule", "Sheet tab",
                         "Rooms inspected", "Inspected rooms", "Full Clean cleaned",
                         "Full Clean rooms", "Daily Service cleaned", "Daily Service rooms",
                         "Dust n Vac inspected", "No call / no show"], by_day)
    lo = rd.loose_for(res, start, end)
    notes = [f"BGV Peak 8 report — {who} — {start} to {end}",
             f"Rooms: GC8 Inspections, synced {sync.get('at', '')} ({sync.get('source', '')}). "
             f"Days: the staff schedule (Schedule.xlsx as the app holds it, in-app edits included).",
             "", "What the numbers mean:"]
    for role in roles:
        for k, g, lab, note in (RQS_COLS if role == "rqs" else HK_COLS):
            if k not in ("rank", "person"):
                notes.append(f"{'RQS' if role == 'rqs' else 'Housekeepers'} — {(g + ': ') if g else ''}"
                             f"{lab}: {note.replace(chr(10), ' ')}")
    notes += ["", "Not counted for anyone in this period:",
              f"Full Clean rooms with no RQS named: {lo.get('in_none', 0)}",
              f"Rooms with no housekeeper named: {lo.get('cl_none', 0)}",
              "Inspected by staff who aren't RQS: " + ", ".join(
                  f"{k} {v}" for k, v in sorted((lo.get('in_other') or {}).items(), key=lambda x: -x[1])),
              "Names on the sheet not matched to anyone: " + ", ".join(
                  f"{k} {v}" for k, v in sorted({**(lo.get('in_unknown') or {}),
                                                 **(lo.get('cl_unknown') or {})}.items(),
                                                key=lambda x: -x[1]))]
    return rd.to_excel(sheets, notes)


st.markdown("#### ⬇️ Download")
people_opts = sorted((p for p, i in res["people"].items() if i.get("role") in ("rqs", "hk")),
                     key=str.lower)
GROUPS = {"Both": "RQS and housekeepers", "RQS": "RQS only", "Housekeepers": "Housekeepers only"}


def _who_label(x):
    if x in GROUPS:
        return GROUPS[x]
    return f"{x} ({'RQS' if res['people'][x]['role'] == 'rqs' else 'housekeeper'})"


d1, d2 = st.columns([2.5, 1.5], vertical_alignment="bottom")
with d1:
    who = st.selectbox("What to download", list(GROUPS) + people_opts, format_func=_who_label,
                       key="rp_dl_who",
                       help="The period above, as an Excel file: the table, each month (or week, "
                            "or day) per person, every day with the room numbers, and what each "
                            "column means.")
with d2:
    data = _excel(who, start, end, f"{sync.get('at')}|{_md5([fixes, aliases])}|"
                                    f"{getattr(db, '_WEEKS', {}).get('v')}|{_md5(overrides)}")
    st.download_button("Download Excel", data, use_container_width=True, type="primary",
                       file_name=f"BGV report - {who} - {start} to {end}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ── what the numbers leave out ───────────────────────────────────────────────
lo = rd.loose_for(res, start, end)
unknown = {**(lo.get("in_unknown") or {})}
for k, v in (lo.get("cl_unknown") or {}).items():
    unknown[k] = unknown.get(k, 0) + v
n_out = (lo.get("in_none", 0) + sum((lo.get("in_other") or {}).values())
         + sum(unknown.values()))
with st.expander(f"What these numbers leave out — {period}", expanded=False):
    def _top(d, n=12):
        items = sorted(d.items(), key=lambda x: -x[1])
        txt = ", ".join(f"{e(k)} <b>{v}</b>" for k, v in items[:n])
        return txt + (f" and {len(items) - n} more" if len(items) > n else "") if items else "none"
    st.markdown(
        f'<div class="rp-lo">'
        f'<b>Full Clean rooms with no RQS named:</b> {lo.get("in_none", 0):,}<br>'
        f'<b>Inspected by staff who aren\'t RQS</b> (managers, leads, housekeepers): '
        f'{_top(lo.get("in_other") or {})}<br>'
        f'<b>Rooms with no housekeeper named:</b> {lo.get("cl_none", 0):,}<br>'
        f'<b>Cleaned by other staff</b> (housepersons, leads): {_top(lo.get("cl_other") or {})}<br>'
        f'<b>Cleaned by help from another property:</b> {_top(lo.get("cl_visiting") or {})}<br>'
        f'<b>Names on the sheet not matched to anyone:</b> {_top(unknown)}</div>',
        unsafe_allow_html=True)
    st.caption("A name that can mean two people (\"David\", \"Ana\") goes to the one the column is "
               "about, then to the one the schedule had at work that day; if that still leaves "
               "two, it isn't counted. Tell the report who a name is below and it counts from "
               "the next refresh of this page.")
    every = {}
    for iso_lo in res["loose"].values():
        for k in ("in_unknown", "cl_unknown"):
            for n, v in (iso_lo.get(k) or {}).items():
                every[n] = every.get(n, 0) + v
    names = sorted(every, key=lambda n: -every[n])
    if names:
        n1, n2, n3 = st.columns([2, 2, 1], vertical_alignment="bottom")
        typed = n1.selectbox("Name on the sheet", names, key="rp_fix_typed",
                             format_func=lambda n: f"{n} ({every[n]} rooms this year)")
        target = n2.selectbox("Is", res["names"], key="rp_fix_person", index=None,
                              placeholder="Pick the person")
        if n3.button("Save", use_container_width=True, disabled=not target, key="rp_fix_save"):
            fixes = dict(fixes, **{typed: target})
            db._upsert_key(rd.NAMES_KEY, fixes)
            st.rerun()
    if fixes:
        st.markdown("**Names you've told the report:**")
        for k, v in sorted(fixes.items()):
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            c1.markdown(f"{e(k)} → **{e(v)}**")
            if c2.button("Remove", key=f"rp_fix_rm_{k}"):
                fixes = {x: y for x, y in fixes.items() if x != k}
                db._upsert_key(rd.NAMES_KEY, fixes)
                st.rerun()
