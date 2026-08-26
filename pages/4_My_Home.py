"""
My Home — one person's own schedule.

Upcoming days from the staff schedule, plus what they have actually worked.
Everyone signed in gets this page, housekeepers included.
"""
import streamlit as st
import sys, os, datetime
import html as _html
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, db, roster_import as ri

st.set_page_config(page_title="My Home · Cleaning Schedule",
                   page_icon="GC8", layout="wide")
st.markdown("""<style>[data-testid="stSidebarNav"]{display:none !important;}</style>""",
            unsafe_allow_html=True)

for _k, _v in [("logged_in", False), ("username", ""), ("role", "")]:
    if _k not in st.session_state: st.session_state[_k] = _v
auth.init_auth()
if not st.session_state.get("logged_in"):
    st.markdown('<div style="text-align:center;padding:60px 20px">'
                '<div style="font-size:1.2rem;font-weight:700;color:#1e293b">Not signed in</div>'
                '<div style="color:#64748b">Please sign in from the main page.</div></div>',
                unsafe_allow_html=True)
    st.stop()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500;600&display=swap');
:root{--bg:#f4f5f7;--border:#e2e5ea;--border-hi:#c3c9d4;--indigo:#2563a8;
  --txt:#1f2733;--txt2:#5b6675;--txt3:#8a93a1;}
*{box-sizing:border-box;}
html,body,[class*="css"]{font-family:'DM Sans',sans-serif!important;color:var(--txt)!important;}
.stApp{background:#f4f5f7!important;}
.block-container{padding-top:1.2rem!important;max-width:1180px;}
.hero{background:linear-gradient(135deg,#1e3a5f 0%,#2563a8 55%,#3b7fb8 100%);
  border-radius:16px;padding:22px 26px;color:#fff;margin-bottom:16px;
  box-shadow:0 6px 24px rgba(37,99,168,.18);animation:fadeUp .4s cubic-bezier(.16,1,.3,1) both}
.hero h1{font-family:'Syne',sans-serif;font-size:1.7rem;font-weight:800;margin:0 0 2px;
  letter-spacing:-.03em}
.hero p{margin:0;font-size:.85rem;opacity:.85}
.hero .role{display:inline-block;background:rgba(255,255,255,.18);border-radius:20px;
  padding:2px 12px;font-size:.68rem;font-weight:700;letter-spacing:.06em;
  text-transform:uppercase;margin-top:8px}
@keyframes fadeUp{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.sec{font-family:'DM Mono',monospace!important;font-size:.6rem;font-weight:500;
  text-transform:uppercase;letter-spacing:.16em;color:var(--txt2);
  padding-bottom:6px;border-bottom:1px solid var(--border);margin:1.3rem 0 .7rem}
.dayrow{display:flex;gap:12px;overflow-x:auto;padding:4px 2px 10px}
.day{flex:0 0 132px;background:#fff;border:1px solid var(--border);border-radius:13px;
  padding:12px 13px;transition:transform .12s ease,box-shadow .12s ease}
.day:hover{transform:translateY(-3px);box-shadow:0 8px 20px rgba(31,39,51,.09)}
.day.today{border-color:#2563a8;box-shadow:0 0 0 2px rgba(37,99,168,.16)}
.day .dow{font-family:'DM Mono',monospace;font-size:.62rem;letter-spacing:.12em;
  text-transform:uppercase;color:var(--txt3)}
.day .num{font-family:'Syne',sans-serif;font-size:1.45rem;font-weight:800;color:#16202e;
  line-height:1.1;margin:1px 0 7px}
.day .what{font-size:.75rem;font-weight:600;border-radius:7px;padding:4px 8px;display:block}
.day .means{font-size:.66rem;color:var(--txt3);margin-top:6px;line-height:1.35}
.kpi{background:#fff;border:1px solid var(--border);border-radius:13px;padding:14px 16px;height:100%}
.kpi .n{font-family:'Syne',sans-serif;font-size:1.7rem;font-weight:800;color:#16202e;line-height:1}
.kpi .l{font-family:'DM Mono',monospace;font-size:.6rem;text-transform:uppercase;
  letter-spacing:.12em;color:var(--txt3);margin-top:3px}
.pill{display:inline-block;border-radius:6px;padding:2px 9px;font-size:.69rem;font-weight:700;
  margin:0 4px 4px 0}
footer{visibility:hidden!important;}#MainMenu{visibility:hidden!important;}
header[data-testid="stHeader"]{background:transparent!important;height:0!important;}
section[data-testid="stSidebar"]{background:#fff!important;border-right:1px solid var(--border)!important;}
@media (max-width:768px){
  .block-container{padding-left:.5rem!important;padding-right:.5rem!important;}
  .hero h1{font-size:1.32rem}
  [data-testid="stHorizontalBlock"]{flex-direction:row!important;flex-wrap:wrap!important;}
}
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Navigate")
    st.page_link("pages/4_My_Home.py", label="My Home")
    st.page_link("cleaning_scheduler.py", label="Cleaning Schedule")
    if auth.can("can_view_dashboard"):
        st.page_link("pages/1_Dashboard.py", label="Dashboard")
    if auth.can("can_generate"):
        st.page_link("pages/3_Roster_Import.py", label="Roster Import")
    if auth.can("can_manage_users"):
        st.page_link("pages/2_Admin.py", label="Admin")

def e(s): return _html.escape(str(s) if s is not None else "")

KIND_STYLE = {
    ri.KIND_DAILY:   ("#ccfbf1", "#115e59", "Daily Service"),
    ri.KIND_WORKING: ("#dcfce7", "#15803d", "Working"),
    ri.KIND_OFF:     ("#f1f5f9", "#94a3b8", "Off"),
    ri.KIND_OTHER:   ("#fef3c7", "#92400e", "Other duty"),
    ri.KIND_UNKNOWN: ("#fee2e2", "#991b1b", "Check with your lead"),
}

cu = auth.current_user()
me = cu.get("display_name") or cu.get("username", "")
first = me.split()[0].title() if me else "there"

week_keys = db.staff_week_keys()
if not week_keys:
    st.markdown(f'<div class="hero"><h1>Hello, {e(first)}</h1>'
                f'<p>No staff schedule has been loaded yet.</p></div>', unsafe_allow_html=True)
    st.info("Once a manager imports the weekly schedule, your days will show up here.")
    st.stop()

@st.cache_data(ttl=300, show_spinner="Loading your schedule…")
def _all_rows(_token: str):
    return ri.history_rows(db.load_staff_weeks(), db.load_staff_overrides())

meta = db.load_staff_meta() or {}
rows = _all_rows(f'{meta.get("uploaded_at","")}|{len(week_keys)}')

# ── Which row in the sheet is me? ─────────────────────────────────────────────
people = sorted({r["key"] for r in rows})
label_of = {}
for r in rows:
    label_of.setdefault(r["key"], r["person"])
mine_key = None
for k in people:
    if ri.norm_name(label_of[k]) == ri.norm_name(me):
        mine_key = k; break
if mine_key is None:                       # try first name
    for k in people:
        if ri.norm_name(label_of[k]).split(" ")[0] == ri.norm_name(me).split(" ")[0]:
            mine_key = k; break

can_browse = auth.can("can_generate")      # admins/RQS may look at anyone
if mine_key is None or can_browse:
    opts = [label_of[k] for k in people]
    default = opts.index(label_of[mine_key]) if mine_key else 0
    picked = st.selectbox(
        "Whose schedule?" if can_browse else
        "We could not match your sign-in to a name on the schedule — pick yours",
        opts, index=default, key="mh_person")
    mine_key = next(k for k in people if label_of[k] == picked)

s_all = ri.summarise_person(rows, person_key=mine_key)
my_name = label_of[mine_key]
my_section = s_all["rows"][0]["section"] if s_all["rows"] else ""

st.markdown(
    f'<div class="hero"><h1>Hello, {e(first if ri.norm_name(my_name)==ri.norm_name(me) else my_name)}</h1>'
    f'<p>Your schedule, straight from this week\'s staff sheet.</p>'
    f'<span class="role">{e(my_section) or e(cu["role"])}</span></div>',
    unsafe_allow_html=True)

today = datetime.date.today()
t_iso = today.isoformat()
by_date = {r["date"]: r for r in s_all["rows"]}

# ── Upcoming ──────────────────────────────────────────────────────────────────
st.markdown('<p class="sec">Next 14 days</p>', unsafe_allow_html=True)
cards, shown = "", 0
for i in range(0, 21):
    d = today + datetime.timedelta(days=i)
    r = by_date.get(d.isoformat())
    if r is None:
        continue
    shown += 1
    if shown > 14:
        break
    bg, fg, lbl = KIND_STYLE[r["kind"]]
    means = ri.legend_for(r, r["raw"])
    cards += (f'<div class="day{" today" if i == 0 else ""}">'
              f'<div class="dow">{d:%a}{" · today" if i == 0 else ""}</div>'
              f'<div class="num">{d.day}</div>'
              f'<span class="what" style="background:{bg};color:{fg}">'
              f'{e(r["raw"]) or lbl}</span>'
              f'{f"<div class=means>{e(means)}</div>" if means else ""}'
              f'</div>')
if cards:
    st.markdown(f'<div class="dayrow">{cards}</div>', unsafe_allow_html=True)
else:
    st.info("Nothing scheduled for you in the stored weeks ahead.")

nxt = [d for d in sorted(by_date) if d > t_iso and by_date[d]["worked"]]
if nxt:
    nd = datetime.date.fromisoformat(nxt[0])
    st.caption(f"Next working day: **{nd:%A, %B %d}** — "
               f"{by_date[nxt[0]]['raw'] or 'scheduled'}")

# ── How much you have worked ──────────────────────────────────────────────────
st.markdown('<p class="sec">What you have worked</p>', unsafe_allow_html=True)
wk_s, mo_s, yr_s = ri.period_bounds(today)
def count(start):
    return sum(1 for r in s_all["rows"] if start <= r["date"] <= t_iso and r["worked"])
k = st.columns(4)
for col, (n, lbl) in zip(k, [(count(wk_s), "days this week"),
                             (count(mo_s), "days this month"),
                             (count(yr_s), "days this year"),
                             (s_all["n_worked"], "days on record")]):
    col.markdown(f'<div class="kpi"><div class="n">{n}</div><div class="l">{lbl}</div></div>',
                 unsafe_allow_html=True)

c1, c2 = st.columns([3, 2])
with c1:
    st.markdown('<div style="font-family:\'DM Mono\',monospace;font-size:.62rem;'
                'letter-spacing:.12em;text-transform:uppercase;color:#8a93a1;'
                'margin:14px 0 6px">Days you usually work</div>', unsafe_allow_html=True)
    mx = max(s_all["by_dow"].values()) or 1
    bars = ""
    for d, n in s_all["by_dow"].items():
        pct = int(100 * n / mx)
        hot = n >= mx * 0.6
        bars += (f'<div style="display:flex;align-items:center;gap:9px;margin:3px 0">'
                 f'<span style="width:34px;font-size:.75rem;color:#5b6675">{d}</span>'
                 f'<div style="flex:1;background:#eef1f5;border-radius:4px;height:15px">'
                 f'<div style="width:{pct}%;height:15px;border-radius:4px;'
                 f'background:{"#2563a8" if hot else "#c3cedb"}"></div></div>'
                 f'<span style="width:28px;text-align:right;font-size:.75rem;font-weight:600">'
                 f'{n}</span></div>')
    st.markdown(bars, unsafe_allow_html=True)
    if s_all["usual_days"]:
        st.caption("Usually: " + ", ".join(s_all["usual_days"]))
with c2:
    st.markdown('<div style="font-family:\'DM Mono\',monospace;font-size:.62rem;'
                'letter-spacing:.12em;text-transform:uppercase;color:#8a93a1;'
                'margin:14px 0 6px">Roles and shifts</div>', unsafe_allow_html=True)
    chips = ""
    for k2, v2 in list(s_all["roles"].items())[:4]:
        chips += (f'<span class="pill" style="background:#eef2ff;color:#3730a3">'
                  f'{e(k2)} · {v2}</span>')
    for k2, v2 in s_all["shifts"].items():
        bg, fg = {"Daily Service": ("#ccfbf1", "#115e59"),
                  "Room cover": ("#ede9fe", "#5b21b6"),
                  "Other duty": ("#fef3c7", "#92400e")}.get(k2, ("#dcfce7", "#15803d"))
        chips += f'<span class="pill" style="background:{bg};color:{fg}">{e(k2)} · {v2}</span>'
    st.markdown(chips or '<span style="color:#8a93a1">—</span>', unsafe_allow_html=True)

with st.expander("Every day on record"):
    past = sorted([r for r in s_all["rows"] if r["date"] <= t_iso],
                  key=lambda x: x["date"], reverse=True)
    st.dataframe(
        pd.DataFrame([{"Date": r["date"], "Day": r["dow"],
                       "Scheduled": r["raw"] or "—",
                       "Status": KIND_STYLE[r["kind"]][2],
                       "Means": ri.legend_for(r, r["raw"]) or "—"} for r in past]),
        use_container_width=True, hide_index=True,
        height=min(60 + 33 * len(past), 460))
