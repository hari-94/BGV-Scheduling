"""
Roster Import — build the day's roster from the weekly Schedule.xlsx.

Upload the workbook, pick a date, review what was parsed, then apply it to the
scheduler's roster (housekeepers + buildings, inspectors, RQS 1/2 and the
Daily Service team).
"""
import streamlit as st
import sys, os, io, datetime
import html as _html
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, db, roster_import as ri

st.set_page_config(page_title="Roster Import · Cleaning Schedule",
                   page_icon="GC8", layout="wide")

st.markdown("""<style>
[data-testid="stSidebarNav"]{display:none !important;}
</style>""", unsafe_allow_html=True)

for _k, _v in [("logged_in",False),("username",""),("role","")]:
    if _k not in st.session_state: st.session_state[_k] = _v

auth.init_auth()
if not st.session_state.get("logged_in"):
    st.markdown("""
<div style="text-align:center;padding:60px 20px;font-family:Inter,sans-serif">
  <div style="font-size:1.2rem;font-weight:700;color:#1e293b;margin-bottom:8px">Not signed in</div>
  <div style="color:#64748b;margin-bottom:20px">Please sign in from the main page.</div>
</div>""", unsafe_allow_html=True)
    st.stop()
if not auth.can("can_edit_roster"):
    st.error("Admin access required to import a roster.")
    st.stop()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500;600&display=swap');
:root{--bg:#f4f5f7;--bg2:#ffffff;--border:#e2e5ea;--border-hi:#c3c9d4;
  --indigo:#2563a8;--cyan:#3b7fb8;--txt:#1f2733;--txt2:#5b6675;--txt3:#8a93a1;
  --radius:14px;--radius-sm:8px;}
*{box-sizing:border-box;}
html,body,[class*="css"]{font-family:'DM Sans',sans-serif!important;color:var(--txt)!important;}
.stApp{background:#f4f5f7!important;}
.block-container{padding-top:1.4rem!important;max-width:1180px;}
.pg-title{font-family:'Syne',sans-serif!important;font-size:1.6rem;font-weight:700;
  letter-spacing:-.03em;color:#16202e;margin:0 0 4px}
.pg-sub{font-size:.82rem;color:var(--txt2);margin:0 0 1rem}
.sec{font-family:'DM Mono',monospace!important;font-size:.6rem;font-weight:500;
  text-transform:uppercase;letter-spacing:.16em;color:var(--txt2);
  padding-bottom:6px;border-bottom:1px solid var(--border);margin:1.3rem 0 .7rem}
.card{background:#fff;border:1px solid var(--border);border-radius:var(--radius);
  padding:14px 16px;margin-bottom:10px}
.pill{display:inline-block;border-radius:6px;padding:1px 8px;font-size:.68rem;
  font-weight:700;margin-right:4px}
.mono{font-family:'DM Mono',monospace;font-size:.72rem;color:var(--txt3)}
section[data-testid="stSidebar"]{background:#fff!important;border-right:1px solid var(--border)!important;}
.stButton>button{border-radius:var(--radius-sm)!important;font-weight:600!important;
  background:#fff!important;color:var(--txt)!important;border:1px solid var(--border-hi)!important;}
.stButton>button:hover{background:#2563a8!important;color:#fff!important;border-color:#2563a8!important;}
.stButton>button[kind="primary"]{background:#2563a8!important;border:none!important;color:#fff!important;}
footer{visibility:hidden!important;}#MainMenu{visibility:hidden!important;}
header[data-testid="stHeader"]{background:transparent!important;height:0!important;}
@media (max-width:768px){
  .block-container{padding-left:.5rem!important;padding-right:.5rem!important;}
  .pg-title{font-size:1.3rem!important;}
  [data-testid="stHorizontalBlock"]{flex-direction:column!important;}
  [data-testid="stHorizontalBlock"] > [data-testid="column"]{width:100%!important;min-width:100%!important;}
}
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Navigate")
    st.page_link("cleaning_scheduler.py", label="Cleaning Schedule")
    st.page_link("pages/1_Dashboard.py", label="Dashboard")
    st.page_link("pages/3_Roster_Import.py", label="Roster Import")
    if auth.can("can_manage_users"):
        st.page_link("pages/2_Admin.py", label="Admin")

def e(s): return _html.escape(str(s) if s is not None else "")

KIND_STYLE = {
    ri.KIND_DAILY:   ("#ccfbf1", "#115e59", "Daily Service"),
    ri.KIND_WORKING: ("#dcfce7", "#15803d", "Working"),
    ri.KIND_OFF:     ("#f1f5f9", "#64748b", "Off"),
    ri.KIND_OTHER:   ("#fef3c7", "#92400e", "Other duty"),
    ri.KIND_UNKNOWN: ("#fee2e2", "#991b1b", "Unrecognised"),
}

st.markdown('<p class="pg-title">Roster Import</p>', unsafe_allow_html=True)
st.markdown('<p class="pg-sub">Upload the weekly <b>Schedule.xlsx</b> and pull a day\'s '
            'staff straight into the scheduler.</p>', unsafe_allow_html=True)

up = st.file_uploader("Weekly schedule workbook", type=["xlsx", "xlsm"],
                      key="roster_xlsx",
                      help="The workbook with one sheet per week (Sun–Sat in columns B–H).")
if up is None:
    st.info("Upload the schedule workbook to begin. Nothing changes until you press "
            "**Apply to roster**.")
    st.stop()

@st.cache_data(show_spinner="Reading workbook…")
def _load(raw: bytes):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
    idx = ri.index_workbook(wb)
    return wb, {d: list(v) for d, v in idx.items()}

try:
    wb, idx = _load(up.getvalue())
except Exception as ex:
    st.error(f"Could not read that workbook: {ex}")
    st.stop()

if not idx:
    st.error("No dated sheets found — is this the weekly schedule workbook?")
    st.stop()

dates = sorted(idx)
st.success(f"Loaded **{len(wb.worksheets)}** sheets · **{len(dates)}** dated days "
           f"({dates[0]:%b %d, %Y} → {dates[-1]:%b %d, %Y})")

# ── Day picker ────────────────────────────────────────────────────────────────
st.markdown('<p class="sec">1 · Choose the day</p>', unsafe_allow_html=True)
today = datetime.date.today()
default = today if today in idx else min(dates, key=lambda d: abs((d - today).days))
c1, c2 = st.columns([1, 2])
with c1:
    picked = st.date_input("Schedule date", value=default,
                           min_value=dates[0], max_value=dates[-1], key="ri_date")
if picked not in idx:
    st.warning(f"**{picked:%A, %B %d, %Y}** is not in this workbook. "
               f"Nearest available: **{min(dates, key=lambda d: abs((d-picked).days)):%b %d, %Y}**.")
    st.stop()

candidates = idx[picked]
with c2:
    if len(candidates) > 1:
        # Duplicated/copied sheets mean a date can live in more than one place.
        names = [f"{s}  (column {chr(64+c)})" for s, c in candidates]
        sel = st.selectbox(f"{len(candidates)} sheets contain this date — pick one",
                           names, key="ri_sheet")
        sheet_name, col = candidates[names.index(sel)]
        st.caption("Sheets copied without re-dating can share dates. Check you picked the right week.")
    else:
        sheet_name, col = candidates[0]
        st.markdown(f'<div class="card"><b>{e(sheet_name)}</b><br>'
                    f'<span class="mono">{picked:%A, %B %d, %Y} · column {chr(64+col)}</span></div>',
                    unsafe_allow_html=True)

people = ri.parse_day(wb[sheet_name], col)
if not people:
    st.error(f"No staff rows parsed from {sheet_name!r} — the layout may differ from the usual one.")
    st.stop()
update  = ri.build_roster_update(people, st.session_state.get("hk_roster", {}))
metrics = ri.day_metrics(wb[sheet_name], col)

# ── Summary ───────────────────────────────────────────────────────────────────
st.markdown('<p class="sec">2 · What was found</p>', unsafe_allow_html=True)
n_hk  = sum(1 for v in update["hk_roster"].values() if v["present"])
n_ins = sum(1 for v in update["insp_roster"].values() if v)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Housekeepers present", n_hk)
m2.metric("On Daily Service", len(update["ds_team"]))
m3.metric("Inspectors present", n_ins)
m4.metric("RQS 1 / RQS 2", f'{update["rqs1"] or "—"} / {update["rqs2"] or "—"}')

if metrics:
    sheet_n = metrics.get("HSKP on schedule")
    bits = " &nbsp;·&nbsp; ".join(f"{k}: <b>{v:g}</b>" for k, v in metrics.items())
    agree = sheet_n is not None and abs(sheet_n - n_hk) < 0.5
    tone = ("#ecfdf5", "#065f46") if agree else ("#fffbeb", "#92400e")
    note = ("matches our count" if agree else
            f"we parsed <b>{n_hk}</b> — worth a look" if sheet_n is not None else "")
    st.markdown(f'<div style="background:{tone[0]};border-radius:8px;padding:9px 13px;'
                f'font-size:.78rem;color:{tone[1]}">The sheet\'s own figures — {bits}'
                f'{" &nbsp;·&nbsp; " + note if note else ""}</div>', unsafe_allow_html=True)

if update["building_changes"]:
    rows = "<br>".join(
        f'&nbsp;&nbsp;<b>{e(n)}</b>: Building {o} <span style="opacity:.6">→</span> Building {w}'
        for n, o, w in update["building_changes"])
    st.markdown(f'<div style="background:#fffbeb;border:1px solid #fcd34d;border-radius:8px;'
                f'padding:10px 13px;font-size:.78rem;color:#92400e;margin-top:8px">'
                f'<b>{len(update["building_changes"])} building change(s)</b> — the sheet '
                f'disagrees with the current roster and will overwrite it:<br>{rows}</div>',
                unsafe_allow_html=True)

if update["new_people"]:
    st.markdown(f'<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;'
                f'padding:10px 13px;font-size:.78rem;color:#1e40af;margin-top:8px">'
                f'<b>{len(update["new_people"])} new name(s)</b> not in the current roster: '
                f'{e(", ".join(update["new_people"]))}.<br>'
                f'Check these are not a re-spelling of someone already on it — the import '
                f'matches names case-insensitively, so only genuinely different spellings '
                f'show up here.</div>', unsafe_allow_html=True)

if update["unknown"]:
    rows = ", ".join(f"<b>{e(n)}</b> ({e(v)})" for n, v in update["unknown"])
    st.markdown(f'<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;'
                f'padding:10px 13px;font-size:.78rem;color:#991b1b;margin-top:8px">'
                f'<b>{len(update["unknown"])} cell(s) not recognised</b> — treated as NOT '
                f'available: {rows}</div>', unsafe_allow_html=True)

# ── Detail ────────────────────────────────────────────────────────────────────
st.markdown('<p class="sec">3 · Detail</p>', unsafe_allow_html=True)

def render(rows, empty="Nobody in this section."):
    if not rows:
        st.caption(empty); return
    html = ['<table style="width:100%;border-collapse:collapse;font-size:.79rem">']
    for p in rows:
        bg, fg, lbl = KIND_STYLE[p["kind"]]
        name_col = "#1f2733" if p["present"] else "#94a3b8"
        deco = "none" if p["present"] else "line-through"
        html.append(
            f'<tr style="border-bottom:1px solid #eef1f5">'
            f'<td style="padding:6px 10px;color:{name_col};text-decoration:{deco};font-weight:500">{e(p["name"])}</td>'
            f'<td style="padding:6px 10px;color:#8a93a1;font-size:.72rem">{e(p["section"])}</td>'
            f'<td style="padding:6px 10px"><span class="pill" style="background:{bg};color:{fg}">{lbl}</span></td>'
            f'<td style="padding:6px 10px;font-family:\'DM Mono\',monospace;font-size:.71rem;color:#5b6675">{e(p["raw"]) or "—"}</td>'
            f'</tr>')
    html.append("</table>")
    st.markdown("".join(html), unsafe_allow_html=True)

t_hk, t_rqs, t_other = st.tabs(["Housekeepers", "Room Quality Supervisors", "Other teams"])
with t_hk:
    for b in (1, 2, 3):
        rows = [p for p in people if p["group"] == "hk" and p["building"] == b]
        n_on = sum(1 for p in rows if p["present"])
        st.markdown(f'<div class="sec" style="margin-top:.8rem">Building {b} — '
                    f'{n_on} of {len(rows)} available</div>', unsafe_allow_html=True)
        render(rows)
with t_rqs:
    render([p for p in people if p["group"] == "rqs"])
with t_other:
    st.caption("Parsed for reference. The scheduler has no slot for these roles, "
               "so they are not imported.")
    for label in ri.OTHER_SECTIONS.values():
        rows = [p for p in people if p["group"] == "other" and p["section"] == label]
        if not rows: continue
        st.markdown(f'<div class="sec" style="margin-top:.8rem">{e(label)}</div>',
                    unsafe_allow_html=True)
        render(rows)

# ── Apply ─────────────────────────────────────────────────────────────────────
st.markdown('<p class="sec">4 · Apply</p>', unsafe_allow_html=True)
opts = st.columns(3)
with opts[0]:
    do_hk = st.checkbox("Housekeepers + buildings", value=True, key="ri_do_hk")
with opts[1]:
    do_rqs = st.checkbox("Inspectors + RQS 1/2", value=True, key="ri_do_rqs")
with opts[2]:
    do_ds = st.checkbox("Daily Service team", value=True, key="ri_do_ds")

keep = st.checkbox(
    "Keep people who are not on this sheet (marked absent instead of removed)",
    value=False, key="ri_keep",
    help="Off: the roster becomes exactly who the sheet lists. "
         "On: anyone missing from the sheet stays on the roster but is marked absent.")

st.caption(f"Applies to this session's roster. Go back to the Schedule page and press "
           f"**Generate** to build {picked:%b %d}'s charts from it.")

if st.button("Apply to roster", type="primary", key="ri_apply"):
    applied = []
    if do_hk:
        new_roster = dict(update["hk_roster"])
        if keep:
            for name, v in st.session_state.get("hk_roster", {}).items():
                if name not in new_roster:
                    new_roster[name] = {"building": v.get("building", 1), "present": False}
        st.session_state["hk_roster"] = new_roster
        # Attendance checkboxes on the Schedule page are keyed per name; clear the
        # stale widget state so they redraw from the roster we just wrote.
        for k in [k for k in list(st.session_state) if k.startswith("att_")]:
            del st.session_state[k]
        applied.append(f"{sum(1 for v in new_roster.values() if v['present'])} housekeepers present "
                       f"of {len(new_roster)} on the roster")
    if do_rqs:
        new_insp = dict(update["insp_roster"])
        if keep:
            for name, v in st.session_state.get("insp_roster", {}).items():
                new_insp.setdefault(name, False)
        st.session_state["insp_roster"] = new_insp
        for k in [k for k in list(st.session_state) if k.startswith("insp_att_")]:
            del st.session_state[k]
        st.session_state["rqs1"] = update["rqs1"]
        st.session_state["rqs2"] = update["rqs2"]
        for k in ("rqs1_sel", "rqs2_sel"):
            st.session_state.pop(k, None)
        applied.append(f"{sum(1 for v in new_insp.values() if v)} inspectors present"
                       + (f", RQS 1 {update['rqs1']}" if update["rqs1"] else "")
                       + (f", RQS 2 {update['rqs2']}" if update["rqs2"] else ""))
    if do_ds:
        # Only people who are actually on the roster and present can be on the team.
        roster_now = st.session_state.get("hk_roster", {})
        team = [n for n in update["ds_team"]
                if roster_now.get(n, {}).get("present")] if do_hk else list(update["ds_team"])
        st.session_state["ds_team"] = team
        applied.append(f"{len(team)} on the Daily Service team")
    if not applied:
        st.warning("Nothing selected to apply.")
    else:
        # Same persistence the Schedule page uses, so the import survives a
        # reload or a new session instead of living only in this session.
        if do_hk or do_rqs:
            try:
                db.save_roster(st.session_state.get("hk_roster", {}),
                               st.session_state.get("insp_roster", {}))
            except Exception as ex:
                st.warning(f"Roster applied to this session, but saving to the "
                           f"database failed — it will not survive a reload. ({ex})")
        st.session_state["roster_import_note"] = (
            f"{picked:%b %d, %Y} from sheet '{sheet_name}'")
        st.success("Applied — " + "; ".join(applied) + ".")
        st.caption("Open the Schedule page to generate today's charts.")
