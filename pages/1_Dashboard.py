"""
Dashboard — Cleaning Schedule Performance Tracker
"""
from datetime import date
import pandas as pd
import streamlit as st
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(__file__)))
import db, auth
import ui
import clock
import property_map as pmap
import roomstatus as _rst

try:
    import plotly.graph_objects as go
    PLOTLY_OK = True
except ImportError:
    PLOTLY_OK = False

st.set_page_config(page_title="Dashboard", page_icon="GC8", layout="wide")
st.markdown("""<style>
[data-testid="stSidebarNav"]{display:none !important;}
</style>""", unsafe_allow_html=True)

for _k, _v in [("groups_data",None),("total_rooms",0),("inspectors_data",[])]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

# One guard for every page: it restores a signed-in browser from its cookie
# and, failing that, goes to the sign-in screen. The hand-rolled version that
# used to sit here seeded logged_in=False into the session before init_auth
# ran, which made the restore skip itself -- so a refresh on this page could
# never have brought anybody back, cookie or no cookie.
auth.require_login()
if not auth.can("can_view_dashboard"):
    st.error("Dashboard requires RQS or Admin role.")
    st.stop()
if not PLOTLY_OK:
    st.error("Install plotly: `pip install plotly`")
    st.stop()

# ── Theme (shared with main app via session_state) ─────────────────────────────
_THEME = "light"   # locked to formal office theme

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500;600&display=swap');
:root{
  --bg:#080810; --bg2:#13131f; --border:rgba(99,102,241,.18); --border-hi:rgba(99,102,241,.45);
  --indigo:#6366f1; --cyan:#22d3ee; --teal:#14b8a6; --amber:#f59e0b; --rose:#f43f5e;
  --txt:#e2e8f0; --txt2:#94a3b8; --txt3:#475569;
  --radius:14px; --radius-sm:8px;
}
*{box-sizing:border-box;}
html,body,[class*="css"]{font-family:'DM Sans',sans-serif!important;color:var(--txt)!important;}
.stApp{
  background:var(--bg)!important;
  background-image:
    radial-gradient(ellipse 80% 50% at 20% -10%,rgba(99,102,241,.12) 0%,transparent 60%),
    radial-gradient(ellipse 60% 40% at 80% 100%,rgba(34,211,238,.07) 0%,transparent 55%)!important;
}
.block-container{padding-top:1.4rem!important;max-width:1440px;background:transparent!important;}
::-webkit-scrollbar{width:4px;height:4px;}
::-webkit-scrollbar-thumb{background:var(--indigo);border-radius:99px;}

.pg-title{font-family:'Syne',sans-serif!important;font-size:1.7rem;font-weight:800;letter-spacing:-.04em;
  background:linear-gradient(135deg,#fff 0%,var(--indigo) 45%,var(--cyan) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin:0 0 4px}
.pg-sub{font-size:.82rem;color:var(--txt2);margin:0 0 1rem}
.sec{font-family:'DM Mono',monospace!important;font-size:.6rem;font-weight:500;text-transform:uppercase;
     letter-spacing:.16em;color:var(--indigo);padding-bottom:6px;border-bottom:1px solid var(--border);margin:1.2rem 0 .6rem}

.kpi-row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:1rem}
.kpi{flex:1 1 130px;background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:var(--radius);
     padding:16px 14px;backdrop-filter:blur(12px);transition:transform .2s,box-shadow .2s}
.kpi:hover{transform:translateY(-3px);border-color:var(--border-hi);box-shadow:0 0 12px rgba(99,102,241,.25)}
.kpi.pu{background:linear-gradient(135deg,rgba(99,102,241,.25),rgba(99,102,241,.1));border-color:rgba(99,102,241,.4)}
.kpi.te{background:linear-gradient(135deg,rgba(20,184,166,.2),rgba(20,184,166,.06));border-color:rgba(20,184,166,.35)}
.kpi.am{background:linear-gradient(135deg,rgba(245,158,11,.2),rgba(245,158,11,.06));border-color:rgba(245,158,11,.35)}
.kpi.bl{background:linear-gradient(135deg,rgba(37,99,235,.2),rgba(37,99,235,.06));border-color:rgba(37,99,235,.35)}
.kpi .val{font-family:'Syne',sans-serif!important;font-size:1.8rem;font-weight:800;color:#fff;line-height:1;margin-bottom:3px;
     text-shadow:0 0 20px rgba(99,102,241,.5)}
.kpi .lbl{font-family:'DM Mono',monospace!important;font-size:.58rem;color:var(--txt2);text-transform:uppercase;letter-spacing:.1em;font-weight:500}
.kpi .sub{font-size:.7rem;color:var(--txt2);margin-top:3px}

.stTabs [data-baseweb="tab-list"]{gap:4px;background:rgba(255,255,255,.03)!important;border:1px solid var(--border)!important;border-radius:var(--radius-sm);padding:4px!important}
.stTabs [data-baseweb="tab"]{border-radius:6px!important;padding:7px 18px!important;font-size:.78rem!important;
  font-weight:600!important;color:var(--txt2)!important;border:none!important;background:transparent!important}
.stTabs [aria-selected="true"]{background:rgba(99,102,241,.2)!important;color:var(--cyan)!important;
  box-shadow:0 0 0 1px rgba(99,102,241,.4)!important}

section[data-testid="stSidebar"]{
  background:rgba(13,13,26,.88)!important;backdrop-filter:blur(20px)!important;
  border-right:1px solid var(--border)!important;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] *{color:var(--txt2)!important;}
.stButton>button{border-radius:var(--radius-sm)!important;font-weight:600!important;border:1px solid var(--border)!important;
  background:rgba(255,255,255,.04)!important;color:var(--txt)!important;}
.stButton>button:hover{border-color:var(--border-hi)!important;background:rgba(99,102,241,.1)!important;}
.stSelectbox [data-baseweb="select"]>div,.stMultiSelect [data-baseweb="select"]>div,
.stDateInput input,.stTextInput input{background:rgba(255,255,255,.03)!important;border:1px solid var(--border)!important;color:var(--txt)!important;}
[data-baseweb="popover"] [role="listbox"],[data-baseweb="menu"]{background:var(--bg2)!important;border:1px solid var(--border)!important;}
hr{border:none!important;height:1px!important;background:var(--border)!important;}
footer{visibility:hidden!important;}#MainMenu{visibility:hidden!important;}
header[data-testid="stHeader"]{background:transparent!important;height:0!important;}
[data-testid="stSidebarNav"]{display:none !important;}

/* MOBILE */
@media (max-width: 768px) {
  .block-container{padding-left:.5rem!important;padding-right:.5rem!important;max-width:100%!important;}
  .pg-title{font-size:1.35rem!important;}
  .kpi{flex:1 1 calc(50% - 5px)!important;min-width:calc(50% - 5px)!important;padding:11px 9px!important;}
  .kpi .val{font-size:1.35rem!important;}
  .stTabs [data-baseweb="tab-list"]{flex-wrap:wrap!important;}
  .stTabs [data-baseweb="tab"]{padding:5px 10px!important;font-size:.7rem!important;}
  section[data-testid="stSidebar"][aria-expanded="true"]{min-width:88vw!important;max-width:92vw!important;}
  section[data-testid="stSidebar"][aria-expanded="false"]{min-width:0!important;max-width:0!important;margin-left:-92vw!important;}
  [data-testid="stHorizontalBlock"]{flex-direction:column!important;}
  [data-testid="stHorizontalBlock"] > [data-testid="column"]{width:100%!important;flex:1 1 100%!important;min-width:100%!important;}
}
</style>""", unsafe_allow_html=True)

# Light theme override
if _THEME == "light":
    st.markdown("""<style>
:root{--bg:#f4f5f7;--bg2:#ffffff;--border:#e2e5ea;--border-hi:#c3c9d4;
  --indigo:#2563a8;--cyan:#3b7fb8;
  --txt:#1f2733;--txt2:#5b6675;--txt3:#8a93a1;}
.stApp{background:#f4f5f7!important;background-image:none!important;}
/* Flat, solid page title — no gradient text. */
.pg-title{color:#16202e!important;-webkit-text-fill-color:#16202e!important;background:none!important;font-weight:700!important;}
.sec{color:#5b6675!important;border-bottom:1px solid var(--border)!important;}
.kpi{background:#ffffff!important;border:1px solid var(--border)!important;box-shadow:0 1px 2px rgba(20,32,54,.06)!important;}
.kpi .val{color:#16202e!important;text-shadow:none!important;}
.stTabs [data-baseweb="tab-list"]{background:#ffffff!important;border:1px solid var(--border)!important;}
.stTabs [aria-selected="true"]{background:#2563a8!important;color:#ffffff!important;}
.stButton>button{background:#ffffff!important;color:var(--txt)!important;border:1px solid var(--border-hi)!important;}
.stButton>button:hover{background:#2563a8!important;color:#ffffff!important;border-color:#2563a8!important;}
section[data-testid="stSidebar"]{background:#ffffff!important;border-right:1px solid var(--border)!important;}
.stSelectbox [data-baseweb="select"]>div,.stDateInput input,.stTextInput input{background:#ffffff!important;color:var(--txt)!important;border:1px solid var(--border-hi)!important;}
[data-baseweb="popover"] [role="listbox"],[data-baseweb="menu"]{background:#ffffff!important;}
::-webkit-scrollbar-thumb{background:#c3c9d4!important;}
</style>""", unsafe_allow_html=True)
elif _THEME == "glass-light":
    st.markdown("""<style>
:root{--bg:#eef1f7;--bg2:rgba(255,255,255,.62);--border:rgba(255,255,255,.75);--border-hi:rgba(94,92,230,.45);
  --indigo:#5e5ce6;--cyan:#0a84c1;--txt:#1c1c1e;--txt2:#5b5b60;--txt3:#9a9aa2;}
.stApp{background:#eef1f7!important;background-image:
  radial-gradient(ellipse 90% 60% at 15% -10%,rgba(94,92,230,.14) 0%,transparent 60%),
  radial-gradient(ellipse 70% 50% at 90% 0%,rgba(10,132,193,.10) 0%,transparent 55%)!important;
  background-attachment:fixed!important;}
.kpi{background:rgba(255,255,255,.55)!important;backdrop-filter:blur(26px) saturate(180%)!important;
  -webkit-backdrop-filter:blur(26px) saturate(180%)!important;border:1px solid rgba(255,255,255,.78)!important;
  border-radius:18px!important;box-shadow:0 8px 28px rgba(31,38,135,.10), inset 0 1px 0 rgba(255,255,255,.95)!important;}
.kpi .val{color:#1c1c1e!important;text-shadow:none!important;}
.stTabs [data-baseweb="tab-list"]{background:rgba(255,255,255,.5)!important;border:1px solid rgba(255,255,255,.75)!important;
  backdrop-filter:blur(20px) saturate(170%)!important;-webkit-backdrop-filter:blur(20px) saturate(170%)!important;border-radius:14px!important;}
.stTabs [aria-selected="true"]{background:rgba(255,255,255,.92)!important;color:#5e5ce6!important;
  box-shadow:0 2px 10px rgba(31,38,135,.12)!important;border-radius:10px!important;}
.stButton>button{background:rgba(255,255,255,.6)!important;color:var(--txt)!important;border:1px solid rgba(255,255,255,.8)!important;
  border-radius:13px!important;backdrop-filter:blur(16px)!important;-webkit-backdrop-filter:blur(16px)!important;}
section[data-testid="stSidebar"]{background:rgba(255,255,255,.55)!important;backdrop-filter:blur(34px) saturate(180%)!important;
  -webkit-backdrop-filter:blur(34px) saturate(180%)!important;border-right:1px solid rgba(255,255,255,.7)!important;}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] *{color:var(--txt)!important;}
.stSelectbox [data-baseweb="select"]>div,.stDateInput input,.stTextInput input,.stTextArea textarea{
  background:rgba(255,255,255,.62)!important;color:var(--txt)!important;border:1px solid rgba(255,255,255,.85)!important;border-radius:13px!important;}
[data-baseweb="popover"] [role="listbox"],[data-baseweb="menu"]{background:rgba(255,255,255,.92)!important;backdrop-filter:blur(28px)!important;border-radius:14px!important;}
</style>""", unsafe_allow_html=True)

elif _THEME == "glass-dark":
    st.markdown("""<style>
:root{--bg:#0b0b0f;--bg2:rgba(38,38,48,.5);--border:rgba(255,255,255,.14);--border-hi:rgba(125,122,255,.5);
  --indigo:#7d7aff;--cyan:#64d2ff;--txt:#f2f2f7;--txt2:#aeaeb6;--txt3:#6c6c75;}
.stApp{background:#0b0b0f!important;background-image:
  radial-gradient(ellipse 90% 60% at 15% -10%,rgba(125,122,255,.16) 0%,transparent 60%),
  radial-gradient(ellipse 70% 50% at 90% 0%,rgba(100,210,255,.09) 0%,transparent 55%)!important;
  background-attachment:fixed!important;}
.kpi{background:rgba(36,36,46,.45)!important;backdrop-filter:blur(26px) saturate(160%)!important;
  -webkit-backdrop-filter:blur(26px) saturate(160%)!important;border:1px solid rgba(255,255,255,.14)!important;
  border-radius:18px!important;box-shadow:0 8px 28px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.10)!important;}
.kpi .val{color:#f2f2f7!important;text-shadow:0 0 20px rgba(125,122,255,.4)!important;}
.stTabs [data-baseweb="tab-list"]{background:rgba(36,36,46,.45)!important;border:1px solid rgba(255,255,255,.13)!important;
  backdrop-filter:blur(22px) saturate(150%)!important;-webkit-backdrop-filter:blur(22px) saturate(150%)!important;border-radius:14px!important;}
.stTabs [aria-selected="true"]{background:rgba(125,122,255,.25)!important;color:#cfcdff!important;
  box-shadow:0 0 0 1px rgba(125,122,255,.45)!important;border-radius:10px!important;}
.stButton>button{background:rgba(46,46,58,.5)!important;color:var(--txt)!important;border:1px solid rgba(255,255,255,.15)!important;
  border-radius:13px!important;backdrop-filter:blur(18px)!important;-webkit-backdrop-filter:blur(18px)!important;}
section[data-testid="stSidebar"]{background:rgba(22,22,30,.55)!important;backdrop-filter:blur(36px) saturate(160%)!important;
  -webkit-backdrop-filter:blur(36px) saturate(160%)!important;border-right:1px solid rgba(255,255,255,.12)!important;}
.stSelectbox [data-baseweb="select"]>div,.stDateInput input,.stTextInput input,.stTextArea textarea{
  background:rgba(36,36,46,.5)!important;color:var(--txt)!important;border:1px solid rgba(255,255,255,.15)!important;border-radius:13px!important;}
[data-baseweb="popover"] [role="listbox"],[data-baseweb="menu"]{background:rgba(30,30,40,.92)!important;backdrop-filter:blur(30px)!important;border-radius:14px!important;}
</style>""", unsafe_allow_html=True)

# Plotly font color follows theme
_PLOT_FONT = "#1e293b"if _THEME.endswith("light") else "#e2e8f0"

# Chart palette — brighter on dark, deeper on light
if _THEME.endswith("light"):
    PURPLE="#5B4FE9"; TEAL="#0D9488"; AMBER="#D97706"; BLUE="#2563EB"; RED="#DC2626"
else:
    PURPLE="#818cf8"; TEAL="#2dd4bf"; AMBER="#fbbf24"; BLUE="#60a5fa"; RED="#fb7185"

# ── Snapshot builder ───────────────────────────────────────────────────────────
def build_snapshot(fg, total_rms, inspectors):
    hk_snap = {}
    insp_snap = {}
    for g in fg:
        hk  = g.get("housekeeper","")
        svc = g.get("service_type","")
        if not hk or hk == "Manager":
            continue
        if hk not in hk_snap:
            hk_snap[hk] = {"time":0,"rooms":0,"rooms_fc":0,"rooms_ds":0,"rooms_dv":0}
        room_list = g.get("rooms",[])
        n = len(room_list)
        hk_snap[hk]["time"]  += g.get("time",0)
        hk_snap[hk]["rooms"] += n
        if svc == "Full Clean":
            hk_snap[hk]["rooms_fc"] += n
        elif svc == "Daily Service":
            hk_snap[hk]["rooms_ds"] += n
        elif svc == "Dust n Vac":
            hk_snap[hk]["rooms_dv"] += n
    for insp in inspectors:
        nm = insp.get("name","")
        if not nm:
            continue
        labels = set(insp.get("groups",[]))
        n_rooms = sum(len(g.get("rooms",[])) for g in fg if g.get("label") in labels)
        insp_snap[nm] = {
            "rooms":   n_rooms,
            "groups":  len(labels),
            "role":    insp.get("role","FC"),
            "buildings": insp.get("buildings",[]),
        }
    return {
        "date":        clock.today_iso(),
        "total_rooms": total_rms,
        "n_groups":    len(fg),
        "hk":          hk_snap,
        "inspectors":  insp_snap,
        "saved_by":    st.session_state.get("username","unknown"),
        "schema_v":    2,
    }

@st.cache_data(ttl=30)
def get_log():
    try:    return db.load_log()
    except Exception as ex: st.error(f"DB: {ex}"); return []

fg         = st.session_state.get("groups_data")
total_rms  = st.session_state.get("total_rooms",0)
inspectors = st.session_state.get("inspectors_data",[])
if fg:
    try:
        db.save_snapshot(build_snapshot(fg,total_rms,inspectors))
        get_log.clear()
    except Exception:
        pass

log = get_log()

ui.topnav("Dashboard")


# ══════════════════════════════════════════════════════════════════════════════
#  THE DATA
#
#  Everything below is built from the schedules themselves rather than from the
#  snapshot log. The log records what was handed out — rooms and minutes per
#  person — and nothing about the rooms, so it cannot answer the questions
#  worth asking: whether a day fits in the day, where the work actually is, or
#  who is being sent across the property.
# ══════════════════════════════════════════════════════════════════════════════
SVC_FC, SVC_IH = "Full Clean", "Full Clean (IH)"
SVC_DS, SVC_DV = "Daily Service", "Dust n Vac"
SVC_COL = {SVC_FC: BLUE, SVC_IH: PURPLE, SVC_DS: TEAL, SVC_DV: AMBER}

#: The working day, from the scheduler's own constants: carts roll at ten and
#: the floor should be clear by half three.
DAY_MINUTES = 330
CAP_MINUTES = 380


@st.cache_data(ttl=300, show_spinner="Reading the schedule history…")
def load_history():
    """Every stored day, flattened to one row per chart and one per room."""
    charts, rooms = [], []
    for day in db.load_schedule_history():
        d = day["date"]
        for g in day["groups_data"]:
            rs = g.get("rooms") or []
            if not rs:
                continue
            codes = [str(x.get("room", "")).strip().upper() for x in rs]
            sp = pmap.spread(codes)
            svc = g.get("service_type", "") or "—"
            hk = (g.get("housekeeper", "") or "").strip()
            insp = (g.get("inspector", "") or "").strip()
            label = g.get("label", "") or "—"
            mins = sum(float(x.get("time") or 0) for x in rs)
            late = sum(1 for x in rs if str(x.get("late_checkout") or "").strip())
            early = sum(1 for x in rs if "early in" in str(x.get("notes") or "").lower())
            arr = sum(1 for x in rs if str(x.get("arriving") or "").strip())
            charts.append({
                "date": d, "chart": label, "service": svc,
                "housekeeper": hk or "— unassigned —",
                "inspector": insp or "— none —",
                "rooms": len(rs), "minutes": mins,
                "buildings": ", ".join("B%d" % b for b in sp["buildings"]) or "—",
                "n_bld": sp["n_buildings"], "n_floor": sp["n_floors"],
                "travel": round(pmap.chart_travel(codes) / 60.0, 1),
                "late_outs": late, "early_ins": early, "arriving": arr,
                "over_day": mins > DAY_MINUTES,
            })
            for x, code in zip(rs, codes):
                loc = pmap.parse(code)
                rooms.append({
                    "date": d, "room": code, "service": svc, "chart": label,
                    "housekeeper": hk or "— unassigned —",
                    "inspector": insp or "— none —",
                    "bld": loc.bld if loc else 0,
                    "level": loc.level if loc else "—",
                    "minutes": float(x.get("time") or 0),
                    "guest": str(x.get("guest") or "").strip(),
                    "arriving": str(x.get("arriving") or "").strip(),
                    "late_out": str(x.get("late_checkout") or "").strip(),
                    "res_type": str(x.get("res_type") or "").strip(),
                })
    return pd.DataFrame(charts), pd.DataFrame(rooms)


CH, RM = load_history()

st.markdown('<p class="pg-title">Performance Dashboard</p>', unsafe_allow_html=True)

if CH.empty:
    st.info("No schedules stored yet. Generate one on the main page first.")
    st.stop()

# ── Filters ───────────────────────────────────────────────────────────────────
ALL_DATES = sorted(CH["date"].unique(), reverse=True)
_today = clock.today_iso()

f1, f2, f3, f4 = st.columns([1.5, 1.4, 1.1, 1.6])
with f1:
    period = st.selectbox("Period", ["Last 7 days", "Last 30 days", "Last 90 days",
                                     "Today", "All time"], index=1, key="dsh_p")
with f2:
    svcs = st.multiselect("Service", sorted(CH["service"].unique()),
                          default=[], key="dsh_svc",
                          placeholder="All services")
with f3:
    blds = st.multiselect("Building", [1, 2, 3], default=[], key="dsh_bld",
                          placeholder="All")
with f4:
    people = st.multiselect("Housekeeper", sorted(CH["housekeeper"].unique()),
                            default=[], key="dsh_hk",
                            placeholder="Everyone")


def _window(dates):
    if period == "Today":
        return [d for d in dates if d == _today]
    if period == "All time":
        return list(dates)
    n = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}[period]
    return sorted(dates, reverse=True)[:n]


keep = set(_window(ALL_DATES))
ch = CH[CH["date"].isin(keep)].copy()
rm = RM[RM["date"].isin(keep)].copy()
if svcs:
    ch = ch[ch["service"].isin(svcs)]
    rm = rm[rm["service"].isin(svcs)]
if people:
    ch = ch[ch["housekeeper"].isin(people)]
    rm = rm[rm["housekeeper"].isin(people)]
if blds:
    rm = rm[rm["bld"].isin(blds)]
    ok = set(zip(rm["date"], rm["chart"]))
    ch = ch[[t in ok for t in zip(ch["date"], ch["chart"])]]

if ch.empty:
    st.warning("Nothing matches those filters.")
    st.stop()

n_days = ch["date"].nunique()

# ── The numbers that matter ───────────────────────────────────────────────────
_rooms = int(ch["rooms"].sum())
_charts = len(ch)
_over = int(ch["over_day"].sum())
_avg_load = ch["minutes"].mean()
_walk = ch["travel"].mean()
_xb = int((ch["n_bld"] > 1).sum())
_late = int(ch["late_outs"].sum())

st.markdown(f"""<div class="kpi-row">
  <div class="kpi pu"><div class="val">{_rooms:,}</div><div class="lbl">Rooms</div>
    <div class="sub">{n_days} day(s) · {_rooms/max(n_days,1):.0f}/day</div></div>
  <div class="kpi bl"><div class="val">{_charts}</div><div class="lbl">Housekeeper-days</div>
    <div class="sub">{_charts/max(n_days,1):.1f} per day</div></div>
  <div class="kpi {'am' if _avg_load > DAY_MINUTES else 'te'}"><div class="val">{_avg_load:.0f}m</div>
    <div class="lbl">Average chart</div><div class="sub">the day holds {DAY_MINUTES}m</div></div>
  <div class="kpi {'am' if _over/max(_charts,1) > .3 else ''}"><div class="val">{100*_over/max(_charts,1):.0f}%</div>
    <div class="lbl">Over a day's work</div><div class="sub">{_over} of {_charts} charts</div></div>
  <div class="kpi te"><div class="val">{_walk:.1f}m</div><div class="lbl">Walking per chart</div>
    <div class="sub">{100*_xb/max(_charts,1):.0f}% cross a building</div></div>
  <div class="kpi"><div class="val">{_late}</div><div class="lbl">Late checkouts</div>
    <div class="sub">{ch['early_ins'].sum()} early check-ins</div></div>
</div>""", unsafe_allow_html=True)


def _lay(fig, h=340, legend=True):
    fig.update_layout(
        height=h, margin=dict(l=10, r=20, t=28, b=10),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", size=12, color=_PLOT_FONT),
        showlegend=legend,
        legend=dict(orientation="h", y=1.12, x=0, bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,.14)", zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,.14)", zeroline=False))
    return fig


t_over, t_people, t_rooms, t_today, t_manage = st.tabs(
    ["Overview", "People", "Rooms & travel", "Today", "Manage"])

# ══════════════════════════════════════════════════════════════════════ OVERVIEW
with t_over:
    st.markdown('<p class="sec">Can the day be done in a day?</p>', unsafe_allow_html=True)
    st.caption("Each bar is one housekeeper's chart. The line at 330 minutes is "
               "the working day, 10:00 to 3:30; the one at 380 is the packing cap.")
    bins = ch["minutes"]
    hist = go.Figure()
    hist.add_trace(go.Histogram(
        x=bins, nbinsx=28, marker_color=BLUE, opacity=.85,
        hovertemplate="%{y} charts at %{x} min<extra></extra>", name="charts"))
    hist.add_vline(x=DAY_MINUTES, line_dash="dash", line_color=AMBER,
                   annotation_text="330m · the day", annotation_position="top")
    hist.add_vline(x=CAP_MINUTES, line_dash="dot", line_color=RED,
                   annotation_text="380m · cap", annotation_position="top left")
    _lay(hist, 320, legend=False)
    hist.update_layout(xaxis_title="minutes of cleaning on one chart",
                       yaxis_title="charts")
    st.plotly_chart(hist, use_container_width=True)

    c1, c2 = st.columns([1.7, 1])
    with c1:
        st.markdown('<p class="sec">Rooms a day, by service</p>', unsafe_allow_html=True)
        piv = rm.pivot_table(index="date", columns="service", values="room",
                             aggfunc="count").fillna(0).sort_index()
        f = go.Figure()
        for s in piv.columns:
            f.add_trace(go.Bar(x=piv.index, y=piv[s], name=s,
                               marker_color=SVC_COL.get(s, PURPLE),
                               hovertemplate="%{x}<br>%{y} " + s + "<extra></extra>"))
        f.update_layout(barmode="stack")
        _lay(f, 330)
        st.plotly_chart(f, use_container_width=True)
    with c2:
        st.markdown('<p class="sec">Service mix</p>', unsafe_allow_html=True)
        mix = rm.groupby("service")["room"].count().sort_values(ascending=False)
        d = go.Figure(go.Pie(labels=mix.index, values=mix.values, hole=.58,
                             marker=dict(colors=[SVC_COL.get(s, PURPLE) for s in mix.index]),
                             textinfo="percent", sort=False,
                             hovertemplate="%{label}<br>%{value} rooms<extra></extra>"))
        _lay(d, 330)
        d.update_layout(legend=dict(orientation="v", y=.5, x=1.0))
        st.plotly_chart(d, use_container_width=True)

    st.markdown('<p class="sec">Pressure on the day</p>', unsafe_allow_html=True)
    st.caption("Rooms that cannot simply be cleaned in order: a late checkout "
               "holds the room until the guest goes, an early check-in has to be "
               "finished before the rest.")
    dd = ch.groupby("date").agg(late=("late_outs", "sum"),
                                early=("early_ins", "sum"),
                                arriving=("arriving", "sum")).sort_index()
    f2 = go.Figure()
    f2.add_trace(go.Scatter(x=dd.index, y=dd["arriving"], name="arriving guest",
                            mode="lines", line=dict(color=BLUE, width=2), fill="tozeroy",
                            fillcolor="rgba(37,99,235,.10)"))
    f2.add_trace(go.Scatter(x=dd.index, y=dd["late"], name="late checkout",
                            mode="lines+markers", line=dict(color=RED, width=2)))
    f2.add_trace(go.Scatter(x=dd.index, y=dd["early"], name="early check-in",
                            mode="lines+markers", line=dict(color=AMBER, width=2)))
    _lay(f2, 300)
    st.plotly_chart(f2, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════ PEOPLE
with t_people:
    st.markdown('<p class="sec">Housekeepers</p>', unsafe_allow_html=True)
    hk = ch[ch["housekeeper"] != "— unassigned —"]
    if hk.empty:
        st.info("No named housekeepers in this range.")
    else:
        g = hk.groupby("housekeeper").agg(
            days=("date", "nunique"), rooms=("rooms", "sum"),
            minutes=("minutes", "sum"), walk=("travel", "sum"),
            over=("over_day", "sum"), cross=("n_bld", lambda s: int((s > 1).sum())),
            floors=("n_floor", "mean")).reset_index()
        g["per_day"] = (g["minutes"] / g["days"]).round(0)
        g["rooms_day"] = (g["rooms"] / g["days"]).round(1)
        g["walk_day"] = (g["walk"] / g["days"]).round(1)

        s1, s2 = st.columns([1.6, 1])
        with s1:
            sort_by = st.selectbox(
                "Sort by", ["Minutes per day", "Rooms per day", "Total rooms",
                            "Days worked", "Walking per day",
                            "Charts over a day", "Cross-building charts"],
                key="dsh_sort")
        with s2:
            asc = st.toggle("Low to high", value=False, key="dsh_asc")
        col = {"Minutes per day": "per_day", "Rooms per day": "rooms_day",
               "Total rooms": "rooms", "Days worked": "days",
               "Walking per day": "walk_day", "Charts over a day": "over",
               "Cross-building charts": "cross"}[sort_by]
        g = g.sort_values(col, ascending=asc)

        st.caption("Bars are minutes of work a day. Green sits inside the "
                   "330-minute day; amber is over it; red is past the 380 cap.")
        gg = g.sort_values("per_day")
        bc = [RED if v > CAP_MINUTES else AMBER if v > DAY_MINUTES else TEAL
              for v in gg["per_day"]]
        fb = go.Figure(go.Bar(
            y=gg["housekeeper"], x=gg["per_day"], orientation="h",
            marker_color=bc, text=[f"{v:.0f}m" for v in gg["per_day"]],
            textposition="outside",
            customdata=gg[["rooms_day", "days", "walk_day"]].values,
            hovertemplate="<b>%{y}</b><br>%{x:.0f} min/day<br>"
                          "%{customdata[0]} rooms/day<br>"
                          "%{customdata[1]} days<br>"
                          "%{customdata[2]} min walking/day<extra></extra>"))
        fb.add_vline(x=DAY_MINUTES, line_dash="dash", line_color=AMBER)
        fb.add_vline(x=CAP_MINUTES, line_dash="dot", line_color=RED)
        _lay(fb, max(300, len(gg) * 26 + 90), legend=False)
        fb.update_layout(xaxis=dict(ticksuffix="m", showgrid=True,
                                    gridcolor="rgba(128,128,128,.14)"),
                         yaxis=dict(showgrid=False))
        st.plotly_chart(fb, use_container_width=True)

        show = g.rename(columns={
            "housekeeper": "Housekeeper", "days": "Days", "rooms": "Rooms",
            "rooms_day": "Rooms/day", "per_day": "Minutes/day",
            "walk_day": "Walking/day", "over": "Charts over a day",
            "cross": "Cross-building", "floors": "Floors/chart"})[
            ["Housekeeper", "Days", "Rooms", "Rooms/day", "Minutes/day",
             "Walking/day", "Charts over a day", "Cross-building", "Floors/chart"]]
        show["Floors/chart"] = show["Floors/chart"].round(1)
        st.dataframe(show, use_container_width=True, hide_index=True,
                     column_config={"Minutes/day": st.column_config.ProgressColumn(
                         "Minutes/day", min_value=0,
                         max_value=int(max(show["Minutes/day"].max(), CAP_MINUTES)),
                         format="%d m")})

    st.markdown('<p class="sec">Inspectors</p>', unsafe_allow_html=True)
    ins = ch[ch["inspector"] != "— none —"]
    if ins.empty:
        st.info("No inspectors recorded in this range.")
    else:
        gi = ins.groupby("inspector").agg(
            days=("date", "nunique"), charts=("chart", "count"),
            rooms=("rooms", "sum"),
            people=("housekeeper", "nunique")).reset_index()
        gi["charts_day"] = (gi["charts"] / gi["days"]).round(1)
        gi["rooms_day"] = (gi["rooms"] / gi["days"]).round(1)
        gi = gi.sort_values("rooms", ascending=False)
        st.dataframe(gi.rename(columns={
            "inspector": "Inspector", "days": "Days", "charts": "Charts",
            "charts_day": "Charts/day", "rooms": "Rooms",
            "rooms_day": "Rooms/day", "people": "Housekeepers covered"}),
            use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════════ ROOMS & TRAVEL
with t_rooms:
    st.markdown('<p class="sec">Where the work is</p>', unsafe_allow_html=True)
    st.caption("Rooms cleaned, by building and level. Building 1 has no rooms on "
               "level 1 and building 2 none on Plaza or Terrace — those gaps are "
               "the lobby, the pool and the car parks.")
    lv_order = [l for l in pmap.LEVELS]
    hm = rm[rm["bld"] > 0].pivot_table(index="level", columns="bld", values="room",
                                       aggfunc="count")
    hm = hm.reindex([l for l in lv_order if l in hm.index])
    if not hm.empty:
        fh = go.Figure(go.Heatmap(
            z=hm.values, x=["Building %d" % c for c in hm.columns], y=hm.index,
            colorscale=[[0, "rgba(37,99,235,.06)"], [1, BLUE]],
            hovertemplate="%{x} · %{y}<br>%{z} rooms<extra></extra>",
            text=hm.values, texttemplate="%{text:.0f}",
            colorbar=dict(title="rooms")))
        _lay(fh, 360, legend=False)
        fh.update_layout(yaxis=dict(autorange="reversed", showgrid=False),
                         xaxis=dict(showgrid=False))
        st.plotly_chart(fh, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<p class="sec">Walking, by service</p>', unsafe_allow_html=True)
        st.caption("Minutes a chart costs in corridor, lift and bridge.")
        tv = ch.groupby("service").agg(walk=("travel", "mean"),
                                       n=("chart", "count")).reset_index()
        tv = tv.sort_values("walk")
        ftv = go.Figure(go.Bar(
            y=tv["service"], x=tv["walk"].round(1), orientation="h",
            marker_color=[SVC_COL.get(s, PURPLE) for s in tv["service"]],
            text=[f"{v:.1f}m" for v in tv["walk"]], textposition="outside",
            customdata=tv[["n"]].values,
            hovertemplate="<b>%{y}</b><br>%{x:.1f} min/chart<br>"
                          "%{customdata[0]} charts<extra></extra>"))
        _lay(ftv, 300, legend=False)
        ftv.update_layout(xaxis=dict(ticksuffix="m"), yaxis=dict(showgrid=False))
        st.plotly_chart(ftv, use_container_width=True)
    with c2:
        st.markdown('<p class="sec">How scattered a chart is</p>', unsafe_allow_html=True)
        st.caption("Buildings on one chart. Two and three do not touch — those "
                   "charts cross building 1 twice.")
        sc = ch["n_bld"].value_counts().sort_index()
        fsc = go.Figure(go.Bar(
            x=[f"{i} building" + ("s" if i > 1 else "") for i in sc.index],
            y=sc.values,
            marker_color=[TEAL, AMBER, RED][:len(sc)],
            text=sc.values, textposition="outside",
            hovertemplate="%{x}<br>%{y} charts<extra></extra>"))
        _lay(fsc, 300, legend=False)
        st.plotly_chart(fsc, use_container_width=True)

    st.markdown('<p class="sec">The rooms that come up most</p>', unsafe_allow_html=True)
    top = (rm.groupby(["room", "service"]).agg(times=("date", "count"),
                                               minutes=("minutes", "mean"))
           .reset_index().sort_values("times", ascending=False).head(40))
    top["minutes"] = top["minutes"].round(0)
    st.dataframe(top.rename(columns={"room": "Room", "service": "Service",
                                     "times": "Times scheduled",
                                     "minutes": "Minutes"}),
                 use_container_width=True, hide_index=True)

# ═════════════════════════════════════════════════════════════════════════ TODAY
with t_today:
    st.markdown('<p class="sec">Today on the floor</p>', unsafe_allow_html=True)
    try:
        statuses = db.get_room_statuses()
    except Exception:
        statuses = {}
    today_rooms = RM[RM["date"] == _today]
    if today_rooms.empty:
        st.info("No schedule stored for today yet.")
    else:
        marked = {k: _rst.normalise(v.get("status")) for k, v in statuses.items()}
        done_set = {_rst.DONE, _rst.INSPECTED, _rst.ALREADY_CLEAN}
        n_tot = len(today_rooms)
        n_marked = sum(1 for r in today_rooms["room"] if r in marked)
        n_done = sum(1 for r in today_rooms["room"] if marked.get(r) in done_set)
        n_insp = sum(1 for r in today_rooms["room"]
                     if marked.get(r) == _rst.INSPECTED)
        st.markdown(f"""<div class="kpi-row">
  <div class="kpi pu"><div class="val">{n_tot}</div><div class="lbl">Rooms today</div></div>
  <div class="kpi bl"><div class="val">{n_done}</div><div class="lbl">Cleaned</div>
    <div class="sub">{100*n_done/max(n_tot,1):.0f}% of the day</div></div>
  <div class="kpi te"><div class="val">{n_insp}</div><div class="lbl">Inspected</div></div>
  <div class="kpi"><div class="val">{n_tot-n_marked}</div><div class="lbl">Not yet marked</div></div>
</div>""", unsafe_allow_html=True)

        prog = (today_rooms.assign(
            state=[_rst.META.get(marked.get(r), ("Waiting to clean",))[0]
                   if r in marked else "Not marked"
                   for r in today_rooms["room"]])
            .groupby(["housekeeper", "state"])["room"].count().unstack(fill_value=0))
        fpr = go.Figure()
        for s in prog.columns:
            meta = next((v for v in _rst.META.values() if v[0] == s), None)
            fpr.add_trace(go.Bar(y=prog.index, x=prog[s], name=s, orientation="h",
                                 marker_color=meta[2] if meta else "#cbd5e1"))
        fpr.update_layout(barmode="stack")
        _lay(fpr, max(280, len(prog) * 30 + 90))
        fpr.update_layout(yaxis=dict(showgrid=False))
        st.plotly_chart(fpr, use_container_width=True)

        if n_marked < n_tot * 0.5:
            st.caption("Live marking is still being taken up — most of today's "
                       "rooms have not been marked on a phone yet, so this is a "
                       "picture of what has been recorded, not of the floor.")

# ════════════════════════════════════════════════════════════════════════ MANAGE
with t_manage:
    st.markdown('<p class="sec">Data</p>', unsafe_allow_html=True)
    m1, m2 = st.columns(2)
    with m1:
        st.markdown("**Export**")
        st.download_button("Charts (CSV)", data=ch.to_csv(index=False).encode("utf-8"),
                           file_name="charts.csv", mime="text/csv",
                           use_container_width=True)
        st.download_button("Rooms (CSV)", data=rm.to_csv(index=False).encode("utf-8"),
                           file_name="rooms.csv", mime="text/csv",
                           use_container_width=True)
        st.caption("Both follow the filters above.")
    with m2:
        if auth.can("can_delete_data"):
            st.markdown("**Delete a day**")
            dd = st.selectbox("Date", ["— select —"] + list(ALL_DATES))
            if st.button("Delete", type="secondary") and dd != "— select —":
                db.delete_snapshot(dd)
                get_log.clear()
                load_history.clear()
                st.success(f"Deleted {dd}. Refresh to update.")
        else:
            st.info("Only admins can delete data.")
    st.caption(f"{len(CH)} charts across {CH['date'].nunique()} stored days · "
               f"{len(log)} snapshot record(s)")
