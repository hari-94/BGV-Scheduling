"""
Dashboard — Cleaning Schedule Performance Tracker
"""
from datetime import date, timedelta
import pandas as pd
import streamlit as st
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(__file__)))
import db, auth
import ui
import clock

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

st.markdown('<p class="pg-title"> Performance Dashboard</p>', unsafe_allow_html=True)
st.markdown('<p class="pg-sub">Daily · weekly · monthly metrics</p>', unsafe_allow_html=True)

if not log:
    st.info("No data yet. Generate a schedule on the main page first.")
    st.stop()

today     = clock.today()
all_dates = sorted({s.get("date","") for s in log if s.get("date")}, reverse=True)

def filter_log(p):
    if p == "Today":      return [s for s in log if s.get("date") == str(today)]
    if p == "This Week":
        c = str(today - timedelta(days=today.weekday()))
        return [s for s in log if s.get("date","") >= c]
    if p == "This Month":
        c = str(today.replace(day=1))
        return [s for s in log if s.get("date","") >= c]
    return log

def agg_hk(snaps):
    out = {}
    for snap in snaps:
        for hk,s in snap.get("hk",{}).items():
            if hk not in out:
                out[hk]={"time":0,"rooms":0,"rooms_fc":0,"rooms_ds":0,"rooms_dv":0,"days":0}
            out[hk]["time"]     += s.get("time",0)
            out[hk]["rooms"]    += s.get("rooms",0)
            out[hk]["rooms_fc"] += s.get("rooms_fc",0)
            out[hk]["rooms_ds"] += s.get("rooms_ds",0)
            out[hk]["rooms_dv"] += s.get("rooms_dv",0)
            out[hk]["days"]     += 1
    return out

def agg_insp(snaps):
    out = {}
    for snap in snaps:
        sv = snap.get("schema_v",1)
        for nm,s in snap.get("inspectors",{}).items():
            rooms = s.get("rooms",0)
            if sv < 2 and rooms == s.get("groups",0)*10:
                rooms = 0
            if nm not in out:
                out[nm]={"rooms":0,"groups":0,"role":"","days":0}
            out[nm]["rooms"]  += rooms
            out[nm]["groups"] += s.get("groups",0)
            out[nm]["role"]    = s.get("role","FC")
            out[nm]["days"]   += 1
    return out

tab_hk, tab_insp, tab_log, tab_manage = st.tabs([
    "Housekeepers","Inspectors","Daily Log","Manage"])

# ── HK tab ────────────────────────────────────────────────────────────────────
with tab_hk:
    p = st.radio("Period",["Today","This Week","This Month","All Time"],horizontal=True,key="hkp")
    snaps = filter_log(p)
    hkd   = agg_hk(snaps)
    nd    = len(snaps)

    if not hkd:
        st.info(f"No data for {p}.")
    else:
        tfc = sum(v["rooms_fc"] for v in hkd.values())
        tds = sum(v["rooms_ds"] for v in hkd.values())
        tdv = sum(v["rooms_dv"] for v in hkd.values())
        tot = tfc+tds+tdv
        nh  = len(hkd)
        avt = sum(v["time"] for v in hkd.values())//max(nh*nd,1)

        st.markdown(f"""<div class="kpi-row">
  <div class="kpi pu"><div class="val">{tot}</div><div class="lbl">Total Rooms</div>
    <div class="sub">{nd} day(s)</div></div>
  <div class="kpi bl"><div class="val">{tfc}</div><div class="lbl">Full Clean</div></div>
  <div class="kpi te"><div class="val">{tds}</div><div class="lbl">Daily Service</div></div>
  <div class="kpi am"><div class="val">{tdv}</div><div class="lbl">Dust &amp; Vac</div></div>
  <div class="kpi"><div class="val">{nh}</div><div class="lbl">Active HKs</div></div>
  <div class="kpi"><div class="val">{avt}m</div><div class="lbl">Avg Time/Day</div></div>
</div>""", unsafe_allow_html=True)

        rows = sorted([{"HK":hk,"FC":v["rooms_fc"],"DS":v["rooms_ds"],"DV":v["rooms_dv"],
                         "Total":v["rooms"],"Avg Time":v["time"]//max(v["days"],1),"Days":v["days"]}
                        for hk,v in hkd.items()], key=lambda r:-r["Total"])
        df = pd.DataFrame(rows)

        st.markdown('<p class="sec">Rooms Cleaned by Service Type</p>', unsafe_allow_html=True)
        if df["Total"].sum() == 0:
            st.info("ℹ No room data yet. Generate a schedule and revisit.")
        else:
            dfc = df.sort_values("Total",ascending=True)
            fig = go.Figure()
            fig.add_trace(go.Bar(name="Full Clean",y=dfc["HK"],x=dfc["FC"],orientation="h",
                marker_color=BLUE,text=[str(v) if v>0 else ""for v in dfc["FC"]],
                textposition="inside",hovertemplate="<b>%{y}</b> FC: %{x}<extra></extra>"))
            fig.add_trace(go.Bar(name="Daily Service",y=dfc["HK"],x=dfc["DS"],orientation="h",
                marker_color=TEAL,text=[str(v) if v>0 else ""for v in dfc["DS"]],
                textposition="inside",hovertemplate="<b>%{y}</b> DS: %{x}<extra></extra>"))
            fig.add_trace(go.Bar(name="Dust & Vac",y=dfc["HK"],x=dfc["DV"],orientation="h",
                marker_color=AMBER,text=[str(v) if v>0 else ""for v in dfc["DV"]],
                textposition="inside",hovertemplate="<b>%{y}</b> DV: %{x}<extra></extra>"))
            fig.update_layout(barmode="stack",height=max(300,len(dfc)*26+80),
                margin=dict(l=10,r=60,t=30,b=10),
                plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="DM Sans",size=12,color=_PLOT_FONT),
                legend=dict(orientation="h",y=1.04,x=0),
                xaxis=dict(title="Rooms",showgrid=True,gridcolor="rgba(128,128,128,.15)"),
                yaxis=dict(showgrid=False),hovermode="y unified")
            st.plotly_chart(fig, use_container_width=True)

        st.markdown('<p class="sec">Average Working Time per Day</p>', unsafe_allow_html=True)
        dft = df.sort_values("Avg Time",ascending=True)
        bc  = [TEAL if t>=330 else AMBER if t>=250 else RED for t in dft["Avg Time"]]
        ft  = go.Figure(go.Bar(y=dft["HK"],x=dft["Avg Time"],orientation="h",
            marker_color=bc,opacity=.9,text=[f"{t}m"for t in dft["Avg Time"]],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>%{x} min/day<extra></extra>"))
        ft.add_vline(x=380,line_dash="dot",line_color=RED,annotation_text="380m cap")
        ft.add_vline(x=330,line_dash="dash",line_color=AMBER,annotation_text="330m min")
        ft.update_layout(height=max(300,len(dft)*26+80),margin=dict(l=10,r=90,t=10,b=10),
            plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="DM Sans",size=12,color=_PLOT_FONT),showlegend=False,
            xaxis=dict(range=[0,430],showgrid=True,gridcolor="rgba(128,128,128,.15)",ticksuffix="m"),
            yaxis=dict(showgrid=False))
        st.plotly_chart(ft, use_container_width=True)

        st.markdown('<p class="sec">Detail Table</p>', unsafe_allow_html=True)
        mxt = max(int(df["Avg Time"].max()),1)
        st.dataframe(df.rename(columns={"HK":"Housekeeper","FC":"FC Rooms","DS":"DS Rooms",
            "DV":"DV Rooms","Total":"Total Rooms","Avg Time":"Avg Time/Day (min)","Days":"Days Active"}),
            use_container_width=True, hide_index=True,
            column_config={"Avg Time/Day (min)":st.column_config.ProgressColumn(
                "Avg Time/Day",min_value=0,max_value=mxt,format="%d min")})

# ── Inspector tab ─────────────────────────────────────────────────────────────
with tab_insp:
    pi  = st.radio("Period",["Today","This Week","This Month","All Time"],horizontal=True,key="ip")
    si  = filter_log(pi)
    id_ = agg_insp(si)
    ndi = len(si)

    if not id_:
        st.info(f"No data for {pi}.")
    else:
        tir = sum(v["rooms"]  for v in id_.values())
        tig = sum(v["groups"] for v in id_.values())
        ni  = len(id_)
        ari = tir//max(ni*ndi,1)

        st.markdown(f"""<div class="kpi-row">
  <div class="kpi pu"><div class="val">{tir}</div><div class="lbl">Rooms Inspected</div>
    <div class="sub">{ndi} day(s)</div></div>
  <div class="kpi te"><div class="val">{tig}</div><div class="lbl">Groups Inspected</div></div>
  <div class="kpi"><div class="val">{ni}</div><div class="lbl">Active Inspectors</div></div>
  <div class="kpi am"><div class="val">{ari}</div><div class="lbl">Avg Rooms/Insp/Day</div></div>
</div>""", unsafe_allow_html=True)

        RCOL = {"RQS1":AMBER,"RQS2":TEAL,"FC":PURPLE}
        RLBL = {"RQS1":"RQS1","RQS2":"RQS2","FC":"Full Clean"}
        ri   = sorted([{"Inspector":nm,"Rooms":v["rooms"],"Groups":v["groups"],
                         "Role":RLBL.get(v["role"],v["role"]),"Days":v["days"],
                         "Avg/Day":v["rooms"]//max(v["days"],1)}
                        for nm,v in id_.items()], key=lambda r:-r["Rooms"])
        dfi  = pd.DataFrame(ri)

        st.markdown('<p class="sec">Rooms Inspected</p>', unsafe_allow_html=True)
        if dfi["Rooms"].sum() == 0:
            st.info("ℹ Inspector room counts are 0. Re-generate the schedule and revisit.")
        else:
            dic = dfi.sort_values("Rooms",ascending=True)
            cr  = [RCOL.get(next((v["role"] for nm,v in id_.items() if nm==r),"FC"),PURPLE)
                   for r in dic["Inspector"]]
            fi2 = go.Figure(go.Bar(y=dic["Inspector"],x=dic["Rooms"],orientation="h",
                marker_color=cr,opacity=.9,text=dic["Rooms"],textposition="outside",
                customdata=dic[["Groups","Role"]].values,
                hovertemplate="<b>%{y}</b><br>Rooms: %{x}<br>Groups: %{customdata[0]}<br>Role: %{customdata[1]}<extra></extra>"))
            fi2.update_layout(height=max(280,len(dic)*30+80),margin=dict(l=10,r=60,t=10,b=10),
                plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="DM Sans",size=12,color=_PLOT_FONT),showlegend=False,
                xaxis=dict(title="Rooms Inspected",showgrid=True,gridcolor="rgba(128,128,128,.15)"),
                yaxis=dict(showgrid=False))
            st.plotly_chart(fi2, use_container_width=True)

        mxr = max(int(dfi["Rooms"].max()),1)
        st.dataframe(dfi,use_container_width=True,hide_index=True,
            column_config={"Rooms":st.column_config.ProgressColumn(
                "Rooms Inspected",min_value=0,max_value=mxr,format="%d")})

# ── Daily Log tab ─────────────────────────────────────────────────────────────
with tab_log:
    st.markdown('<p class="sec">Schedule History</p>', unsafe_allow_html=True)
    for snap in sorted(log, key=lambda s:s.get("date",""), reverse=True):
        d = snap.get("date","")
        is_today = (d == str(today))
        nr=snap.get("total_rooms",0); ng=snap.get("n_groups",0)
        nh2=len(snap.get("hk",{})); ni2=len(snap.get("inspectors",{}))
        lbl = f"{' TODAY' if is_today else ''} {d} · {nr} rooms · {ng} groups · {nh2} HKs · {ni2} inspectors"
        with st.expander(lbl, expanded=is_today):
            c1,c2 = st.columns(2)
            with c1:
                if snap.get("hk"):
                    st.markdown("**Housekeepers**")
                    st.dataframe(pd.DataFrame([
                        {"Name":k,"FC":v.get("rooms_fc",0),"DS":v.get("rooms_ds",0),
                         "DV":v.get("rooms_dv",0),"Total":v.get("rooms",0),"Time":v.get("time",0)}
                        for k,v in snap["hk"].items()
                    ]).sort_values("Total",ascending=False),use_container_width=True,hide_index=True)
            with c2:
                if snap.get("inspectors"):
                    st.markdown("**Inspectors**")
                    st.dataframe(pd.DataFrame([
                        {"Name":k,"Rooms":v.get("rooms",0),"Groups":v.get("groups",0),"Role":v.get("role","")}
                        for k,v in snap["inspectors"].items()
                    ]).sort_values("Rooms",ascending=False),use_container_width=True,hide_index=True)

# ── Manage tab ────────────────────────────────────────────────────────────────
with tab_manage:
    st.markdown('<p class="sec">Data Management</p>', unsafe_allow_html=True)
    m1,m2 = st.columns(2)
    with m1:
        st.markdown("** Export as CSV**")
        ar = []
        for snap in log:
            for hk,s in snap.get("hk",{}).items():
                ar.append({"Date":snap["date"],"Type":"HK","Name":hk,
                    "Time":s.get("time",0),"Total":s.get("rooms",0),
                    "FC":s.get("rooms_fc",0),"DS":s.get("rooms_ds",0),"DV":s.get("rooms_dv",0)})
            for nm,s in snap.get("inspectors",{}).items():
                ar.append({"Date":snap["date"],"Type":"Inspector","Name":nm,
                    "Rooms":s.get("rooms",0),"Groups":s.get("groups",0),"Role":s.get("role","")})
        if ar:
            csv = pd.DataFrame(ar).to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV",data=csv,
                file_name="schedule_history.csv",mime="text/csv",use_container_width=True)
    with m2:
        if auth.can("can_delete_data"):
            st.markdown("** Delete a Day**")
            dd = st.selectbox("Date",["— select —"]+all_dates)
            if st.button("Delete",type="secondary") and dd != "— select —":
                db.delete_snapshot(dd); get_log.clear()
                st.success(f"Deleted {dd}. Refresh to update.")
        else:
            st.info("Only admins can delete data.")
    st.caption(f"Records: {len(log)} day(s)")
