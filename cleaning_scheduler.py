"""
Cleaning Schedule Grouper  v10
"""
import re, html as _html
import pandas as pd
import sys as _sys2, os as _os2
_sys2.path.insert(0, _os2.path.dirname(__file__))

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Cleaning Schedule",
    page_icon="🧹",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Import local modules after set_page_config
import auth, db

# ── Hide Streamlit's auto-generated page navigation IMMEDIATELY ───────────────
# This must be the first markdown call so the nav never flashes. We use every
# known selector variant across Streamlit versions to be bulletproof.
st.markdown("""<style>
/* Hide ONLY Streamlit's auto-generated page nav. The config.toml setting
   showSidebarNavigation=false is the primary fix; this is a safe backup that
   targets only the nav testid, never the sidebar content itself. */
[data-testid="stSidebarNav"]{
  display: none !important;
}
</style>""", unsafe_allow_html=True)

# ── Theme: locked to a single formal "light" theme for office use ─────────────
st.session_state["theme"] = "light"
_THEME    = "light"
_IS_GLASS = False
_IS_LIGHT = True

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
def e(s): return _html.escape(str(s) if s else "")

# ── Shared time helpers (Mountain time) ──────────────────────────────────────
# Consolidated here so the timezone and "now" / formatting logic live in one
# place instead of being rebuilt inside the HK view and Live tab.
import zoneinfo as _zoneinfo
from datetime import datetime as _datetime
_MTN_TZ = _zoneinfo.ZoneInfo("America/Denver")
def _now_iso():
    """Current Mountain-time timestamp as ISO string (for saved statuses)."""
    return _datetime.now(_MTN_TZ).isoformat()
def _fmt_mtn(ts):
    """Format a stored ISO timestamp as 'HH:MM AM/PM' in Mountain time."""
    if not ts: return ""
    try:
        dt = _datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.astimezone(_MTN_TZ).strftime("%I:%M %p")
    except Exception:
        return ""

def make_labels(prefix: str, n: int) -> list:
    alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    out = []
    for c in alpha:
        out.append(f"{prefix}-{c}")
        if len(out) >= n: return out
    for c1 in alpha:
        for c2 in alpha:
            out.append(f"{prefix}-{c1}{c2}")
            if len(out) >= n: return out
    return out

LOW_MIN  = 330
MAX_FC   = 380
MAX_DS   = 560
DS_OVER  = 700
LOW_FILL = 350

# Daily Service: HARD cap per housekeeper. Fill up to DS_CAP, never exceed;
# leftover rooms form new charts (blank housekeeper if none available, filled in
# manually later based on how the day goes).
DS_CAP   = 460
# IH charts below this total are treated as scraps and spill to Daily Service
# (kept charts at/above this are inspected by RQS 2).
IH_KEEP_MIN = 310

SVC_FC   = "Full Clean"
SVC_IH   = "Full Clean (IH)"
SVC_DS   = "Daily Service"
SVC_DV   = "Dust n Vac"

# RQS assigned to inspect all IH charts.
IH_RQS   = "RQS 2"

DEFAULT_TIMES = {
    SVC_FC: {"A":120,"B":70,"C":70,"D":120,"E":140,"F":70,"G":70,"H":70,"I":70},
    SVC_IH: {"A":120,"B":70,"C":70,"D":120,"E":140,"F":70,"G":70,"H":70,"I":70},
    SVC_DS: {"A":35, "B":20,"C":20,"D":35, "E":40, "F":20,"G":20,"H":20,"I":20},
    SVC_DV: {},
}
DV_DEFAULT_TIME = 0

def default_time_for(room: str, svc: str) -> int:
    room_type = ""
    for ch in reversed(str(room).strip().upper()):
        if ch.isalpha(): room_type = ch; break
    return DEFAULT_TIMES.get(svc, {}).get(room_type, 70)

PALETTE = [
    ("#5B4FE9","#EEEEFF"),("#0D9488","#ECFDF5"),("#2563EB","#EFF6FF"),
    ("#D97706","#FFFBEB"),("#DC2626","#FFF5F5"),("#7C3AED","#F5F3FF"),
    ("#0891B2","#ECFEFF"),("#EA580C","#FFF7ED"),("#DB2777","#FDF2F8"),
    ("#059669","#F0FDF4"),("#65A30D","#F7FEE7"),("#4F46E5","#EEF2FF"),
    ("#9333EA","#FAF5FF"),("#16A34A","#F0FDF4"),("#E11D48","#FFF1F2"),
    ("#0284C7","#F0F9FF"),("#B45309","#FFFBEB"),("#6D28D9","#F5F3FF"),
    ("#047857","#ECFDF5"),("#B91C1C","#FEF2F2"),
]
SVC_PALETTE = {
    SVC_FC: ("#2563EB","#EFF6FF"),
    SVC_IH: ("#7C3AED","#F5F3FF"),
    SVC_DS: ("#0D9488","#ECFDF5"),
    SVC_DV: ("#D97706","#FFFBEB"),
}
IC = ["#5B4FE9","#0D9488","#D97706","#DC2626","#7C3AED","#0891B2","#EA580C","#DB2777"]
BLD_COLORS = {1:("#2563EB","#EFF6FF"), 2:("#0D9488","#ECFDF5"), 3:("#D97706","#FFFBEB")}

def pal(i): return PALETTE[i % len(PALETTE)]

DEFAULT_HK = {
    1: ["Maricruz","Melissa","ARACELI","Anaberta","Darling","Adrian","Leonardo","Rosibel"],
    2: ["Liliana L","DIANIS","Cecilia Angeles","Elibeth Herrera","Jenifer S.",
        "Norma E","Santos","Yadira","Senia","Gloria R.","Ana Centeno","Camila O","DANIA","Andres"],
    3: ["JENNI CAICEDO","Federico","Nancy","Minoska","Lourdes","AMALIA",
        "Elizabeth","Jorge Luis","Lorena","Nury","Lilliam","Janiris",
        "Luis Urbina","Ana Hernandez","JOSSELIN"],
}
DEFAULT_INSPECTORS = [
    "Sayra","Oralia","Alejandro","Claudia P.","Castor","Hari",
    "Danny R.","Mayra B.","Ana Casia","Bryan","Gustavo","Edward","David S.","Grace",
]

# ══════════════════════════════════════════════════════════════════════════════
#  CSS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=DM+Mono:ital,wght@0,300;0,400;0,500;1,400&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600&display=swap');

:root {
  --bg:#080810; --bg1:#0e0e1a; --bg2:#13131f; --bg3:#1a1a2e;
  --border:rgba(99,102,241,.18); --border-hi:rgba(99,102,241,.45);
  --indigo:#6366f1; --indigo-lo:rgba(99,102,241,.12);
  --cyan:#22d3ee; --cyan-lo:rgba(34,211,238,.1);
  --teal:#14b8a6; --amber:#f59e0b; --rose:#f43f5e;
  --txt:#e2e8f0; --txt2:#94a3b8; --txt3:#475569;
  --glow-i:0 0 24px rgba(99,102,241,.35),0 0 60px rgba(99,102,241,.12);
  --glow-c:0 0 24px rgba(34,211,238,.3),0 0 60px rgba(34,211,238,.1);
  --glow-sm:0 0 12px rgba(99,102,241,.25);
  --radius:14px; --radius-sm:8px;
}
*,*::before,*::after{box-sizing:border-box;}
html,body,[class*="css"]{
  font-family:'DM Sans',sans-serif!important;
  -webkit-font-smoothing:antialiased;
  color:var(--txt)!important;
}
.stApp{
  background:var(--bg)!important;
  background-image:
    radial-gradient(ellipse 80% 50% at 20% -10%,rgba(99,102,241,.12) 0%,transparent 60%),
    radial-gradient(ellipse 60% 40% at 80% 100%,rgba(34,211,238,.07) 0%,transparent 55%)!important;
}
.block-container{padding-top:1.6rem!important;max-width:1440px!important;background:transparent!important;}
::-webkit-scrollbar{width:4px;height:4px;}
::-webkit-scrollbar-track{background:var(--bg1);}
::-webkit-scrollbar-thumb{background:var(--indigo);border-radius:99px;}

/* ── Typography ── */
.pg-title{
  font-family:'Syne',sans-serif!important;font-size:2rem;font-weight:800;letter-spacing:-.04em;
  background:linear-gradient(135deg,#fff 0%,var(--indigo) 45%,var(--cyan) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
  margin:0 0 4px;line-height:1.1;animation:titleReveal .7s cubic-bezier(.16,1,.3,1) both;
}
@keyframes titleReveal{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.pg-sub{font-size:.82rem;color:var(--txt2);margin:0 0 1rem;font-weight:400;animation:titleReveal .7s .1s cubic-bezier(.16,1,.3,1) both;}
.sec{font-family:'DM Mono',monospace!important;font-size:.6rem;font-weight:500;text-transform:uppercase;
  letter-spacing:.16em;color:var(--indigo);padding-bottom:6px;border-bottom:1px solid var(--border);margin:1.2rem 0 .6rem;}

/* ── Sidebar ── */
section[data-testid="stSidebar"]{
  background:rgba(13,13,26,.88)!important;backdrop-filter:blur(20px)!important;
  -webkit-backdrop-filter:blur(20px)!important;border-right:1px solid var(--border)!important;
  box-shadow:4px 0 40px rgba(0,0,0,.5)!important;
  min-width:340px!important;max-width:380px!important;
}
/* Only when EXPLICITLY collapsed (aria-expanded="false") do we zero it out and
   strip the shadow/border/blur so no ghost strip remains. The default rule
   above always gives the sidebar a width, so it can never vanish on load even
   if Streamlit doesn't set aria-expanded="true". */
section[data-testid="stSidebar"][aria-expanded="false"]{
  min-width:0!important;max-width:0!important;width:0!important;
  box-shadow:none!important;
  border-right:none!important;
  backdrop-filter:none!important;
  -webkit-backdrop-filter:none!important;
  background:transparent!important;
  overflow:hidden!important;
}
section[data-testid="stSidebar"][aria-expanded="false"]::before{display:none!important;}
section[data-testid="stSidebar"]::before{
  content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,var(--indigo),var(--cyan));z-index:10;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{font-size:.8rem;color:var(--txt2);}
section[data-testid="stSidebar"] h2{
  font-family:'Syne',sans-serif!important;font-size:1rem!important;font-weight:700!important;
  color:var(--txt)!important;letter-spacing:-.01em;padding-bottom:8px;margin-bottom:8px;
  border-bottom:1px solid var(--border)!important;
}
section[data-testid="stSidebar"] h3{
  font-family:'DM Mono',monospace!important;font-size:.62rem!important;font-weight:500!important;
  text-transform:uppercase;letter-spacing:.14em;color:var(--indigo)!important;margin:12px 0 6px!important;
}
section[data-testid="stSidebar"] hr{border-color:var(--border)!important;}

/* ── Stat cards ── */
.stat-row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:1.2rem;}
.sc{
  flex:1 1 100px;background:rgba(255,255,255,.03)!important;border:1px solid var(--border)!important;
  border-radius:var(--radius)!important;padding:16px 14px;text-align:center;
  backdrop-filter:blur(12px);transition:transform .2s,box-shadow .2s,border-color .2s;
  animation:cardIn .5s cubic-bezier(.16,1,.3,1) both;
}
.sc:hover{transform:translateY(-3px) scale(1.02);border-color:var(--border-hi)!important;box-shadow:var(--glow-sm);}
.sc.hi{background:linear-gradient(135deg,rgba(99,102,241,.25),rgba(99,102,241,.1))!important;border-color:rgba(99,102,241,.4)!important;box-shadow:var(--glow-sm);}
.sc.ds{background:linear-gradient(135deg,rgba(20,184,166,.2),rgba(20,184,166,.06))!important;border-color:rgba(20,184,166,.35)!important;}
.sc.dv{background:linear-gradient(135deg,rgba(245,158,11,.2),rgba(245,158,11,.06))!important;border-color:rgba(245,158,11,.35)!important;}
.sc .n{font-family:'Syne',sans-serif!important;font-size:1.8rem;font-weight:800;color:#fff;line-height:1;margin-bottom:3px;text-shadow:0 0 20px rgba(99,102,241,.5);}
.sc.ds .n{text-shadow:0 0 20px rgba(20,184,166,.5);}
.sc.dv .n{text-shadow:0 0 20px rgba(245,158,11,.5);}
.sc .l{font-family:'DM Mono',monospace!important;font-size:.58rem;color:var(--txt2);text-transform:uppercase;letter-spacing:.1em;font-weight:500;}
@keyframes cardIn{from{opacity:0;transform:translateY(16px) scale(.97)}to{opacity:1;transform:translateY(0) scale(1)}}
.sc:nth-child(1){animation-delay:.05s}.sc:nth-child(2){animation-delay:.1s}.sc:nth-child(3){animation-delay:.15s}
.sc:nth-child(4){animation-delay:.2s}.sc:nth-child(5){animation-delay:.25s}.sc:nth-child(6){animation-delay:.3s}
.sc:nth-child(7){animation-delay:.35s}.sc:nth-child(8){animation-delay:.4s}

/* ── Rules box ── */
.rules-box{background:rgba(99,102,241,.06);border:1px solid var(--border);border-radius:var(--radius);padding:14px 18px;font-size:.81rem;color:var(--txt2);}
.rules-box li{margin-bottom:5px;line-height:1.6;}
.rules-box strong{color:var(--cyan);}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"]{gap:4px;background:rgba(255,255,255,.03)!important;border:1px solid var(--border)!important;border-radius:var(--radius-sm);padding:4px!important;}
.stTabs [data-baseweb="tab"]{border-radius:6px!important;padding:7px 18px!important;font-family:'DM Sans',sans-serif!important;font-size:.78rem!important;font-weight:600!important;color:var(--txt2)!important;border:none!important;background:transparent!important;transition:all .2s!important;}
.stTabs [data-baseweb="tab"]:hover{color:var(--txt)!important;background:rgba(99,102,241,.1)!important;}
.stTabs [aria-selected="true"]{background:rgba(99,102,241,.2)!important;color:var(--cyan)!important;box-shadow:0 0 0 1px rgba(99,102,241,.4),var(--glow-sm)!important;}

/* ── Buttons ── */
.stButton>button{border-radius:var(--radius-sm)!important;font-family:'DM Sans',sans-serif!important;font-weight:600!important;font-size:.82rem!important;border:1px solid var(--border)!important;background:rgba(255,255,255,.04)!important;color:var(--txt)!important;transition:all .2s!important;}
.stButton>button:hover{border-color:var(--border-hi)!important;background:rgba(99,102,241,.1)!important;transform:translateY(-1px);}
.stButton>button[kind="primary"]{background:linear-gradient(135deg,var(--indigo),#818cf8)!important;border:none!important;color:#fff!important;box-shadow:var(--glow-sm),0 4px 20px rgba(99,102,241,.3)!important;font-size:.88rem!important;animation:pulseCTA 2.5s ease-in-out infinite;}
.stButton>button[kind="primary"]:hover{animation:none!important;transform:translateY(-2px)!important;box-shadow:var(--glow-i)!important;}
@keyframes pulseCTA{0%,100%{box-shadow:0 0 12px rgba(99,102,241,.35),0 4px 20px rgba(99,102,241,.2);}50%{box-shadow:0 0 28px rgba(99,102,241,.6),0 4px 30px rgba(99,102,241,.35);}}

/* ── Inputs ── */
.stTextArea textarea,.stTextInput input{background:rgba(255,255,255,.03)!important;border:1px solid var(--border)!important;border-radius:var(--radius-sm)!important;color:var(--txt)!important;font-family:'DM Mono',monospace!important;font-size:.78rem!important;}
.stTextArea textarea:focus,.stTextInput input:focus{border-color:var(--indigo)!important;box-shadow:0 0 0 2px rgba(99,102,241,.2)!important;}
.stTextArea textarea::placeholder{color:var(--txt3)!important;}

/* ── Selects / dropdowns ── */
.stSelectbox [data-baseweb="select"]>div,.stMultiSelect [data-baseweb="select"]>div{background:rgba(255,255,255,.03)!important;border:1px solid var(--border)!important;border-radius:var(--radius-sm)!important;color:var(--txt)!important;}
[data-baseweb="popover"] [role="listbox"],[data-baseweb="menu"]{background:var(--bg2)!important;border:1px solid var(--border)!important;border-radius:var(--radius-sm)!important;}
[data-baseweb="option"]:hover,[aria-selected="true"]{background:rgba(99,102,241,.15)!important;}
[data-baseweb="tag"]{background:rgba(99,102,241,.2)!important;border:1px solid rgba(99,102,241,.4)!important;border-radius:6px!important;color:var(--cyan)!important;}

/* ── Checkboxes / sliders ── */
.stCheckbox label{font-size:.8rem!important;color:var(--txt2)!important;}
.stCheckbox label:hover{color:var(--txt)!important;}
[data-testid="stSlider"] div[role="slider"]{background:var(--indigo)!important;box-shadow:var(--glow-sm)!important;}

/* ── Expander ── */
.streamlit-expanderHeader{background:rgba(255,255,255,.03)!important;border:1px solid var(--border)!important;border-radius:var(--radius-sm)!important;color:var(--txt2)!important;font-size:.8rem!important;font-weight:600!important;}
.streamlit-expanderHeader:hover{border-color:var(--border-hi)!important;color:var(--txt)!important;}
.streamlit-expanderContent{background:rgba(255,255,255,.02)!important;border:1px solid var(--border)!important;border-top:none!important;border-radius:0 0 var(--radius-sm) var(--radius-sm)!important;}

/* ── Alerts ── */
.stAlert{border-radius:var(--radius-sm)!important;border:none!important;}
.stSuccess{background:rgba(20,184,166,.1)!important;border-left:3px solid var(--teal)!important;}
.stWarning{background:rgba(245,158,11,.08)!important;border-left:3px solid var(--amber)!important;}
.stError{background:rgba(244,63,94,.08)!important;border-left:3px solid var(--rose)!important;}
.stInfo{background:rgba(99,102,241,.08)!important;border-left:3px solid var(--indigo)!important;}

/* ── Misc ── */
hr{border:none!important;height:1px!important;background:var(--border)!important;margin:1rem 0!important;}
[data-testid="stSpinner"]>div{border-top-color:var(--indigo)!important;}
footer{visibility:hidden!important;}
#MainMenu{visibility:hidden!important;}
/* Hide the top header bar (leaves a white strip otherwise) */
header[data-testid="stHeader"]{
  background:transparent !important;
  height:0 !important;
  min-height:0 !important;
}
[data-testid="stToolbar"]{display:none !important;}
[data-testid="stDecoration"]{display:none !important;}
/* Hide Streamlit's auto-generated page nav — we use a custom role-based nav */
[data-testid="stSidebarNav"]{display:none !important;}

/* ── Mobile ── */
@media(max-width:768px){
  /* Tighter page padding, full width */
  .block-container{padding:.6rem .4rem!important;max-width:100%!important;}
  .pg-title{font-size:1.35rem!important;line-height:1.1!important;}
  .pg-sub{font-size:.72rem!important;}

  /* Stat cards: 2 per row */
  .stat-row{gap:5px!important;}
  .sc{flex:1 1 calc(50% - 5px)!important;min-width:calc(50% - 5px)!important;padding:9px 7px!important;}
  .sc .n{font-size:1.25rem!important;}
  .sc .l{font-size:.5rem!important;letter-spacing:.04em!important;}

  /* Tabs wrap and shrink */
  .stTabs [data-baseweb="tab-list"]{flex-wrap:wrap!important;gap:3px!important;}
  .stTabs [data-baseweb="tab"]{padding:5px 9px!important;font-size:.68rem!important;}

  /* Sidebar wider on mobile when open; fully off-screen when collapsed
     (identical to the Dashboard page, which collapses correctly) */
  section[data-testid="stSidebar"]{
    min-width:85vw!important;max-width:90vw!important;
  }
  section[data-testid="stSidebar"][aria-expanded="false"]{
    min-width:0!important;max-width:0!important;width:0!important;margin-left:-92vw!important;
  }

  /* Bigger tap targets for buttons */
  .stButton>button{min-height:42px!important;padding:8px 10px!important;}

  /* Inputs full width, easier to tap */
  .stTextInput input,.stTextArea textarea,
  .stSelectbox [data-baseweb="select"]>div,
  .stMultiSelect [data-baseweb="select"]>div{font-size:16px!important;}
  /* ^ 16px prevents iOS auto-zoom on focus */

  /* Expander headers bigger */
  .streamlit-expanderHeader{font-size:.82rem!important;padding:10px!important;}
}

/* ── BIG layout columns: phone-first behavior ── */
@media(max-width:768px){
  /* Default: every multi-column row may wrap instead of squishing */
  [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:6px!important;}
  [data-testid="stHorizontalBlock"]>[data-testid="column"]{min-width:0!important;}

  /* Input areas (room data / front-desk email / add-staff) stack FULL width */
  [data-testid="stHorizontalBlock"]:has(.stTextArea),
  [data-testid="stHorizontalBlock"]:has(.stTextInput){
    flex-direction:column!important;
  }
  [data-testid="stHorizontalBlock"]:has(.stTextArea)>[data-testid="column"],
  [data-testid="stHorizontalBlock"]:has(.stTextInput)>[data-testid="column"]{
    width:100%!important;min-width:100%!important;flex:1 1 100%!important;
  }

  /* Filter bars (Groups tab, Live tab): selectbox / multiselect / checkbox
     columns flow as a 2-up grid instead of 5 squeezed slivers */
  [data-testid="stHorizontalBlock"]:has(.stSelectbox)>[data-testid="column"],
  [data-testid="stHorizontalBlock"]:has(.stMultiSelect)>[data-testid="column"],
  [data-testid="stHorizontalBlock"]:has(.stCheckbox)>[data-testid="column"]{
    flex:1 1 47%!important;min-width:47%!important;width:auto!important;
  }

  /* Button-only rows (status actions) STAY horizontal & equal width —
     thumb-friendly action bars under each room */
  [data-testid="stHorizontalBlock"]:has(.stButton):not(:has(.stTextArea)):not(:has(.stTextInput)):not(:has(.stSelectbox)):not(:has(.stCheckbox)){
    flex-direction:row!important;flex-wrap:nowrap!important;gap:4px!important;
  }
  [data-testid="stHorizontalBlock"]:has(.stButton):not(:has(.stTextArea)):not(:has(.stTextInput)):not(:has(.stSelectbox)):not(:has(.stCheckbox))>[data-testid="column"]{
    flex:1 1 0!important;min-width:0!important;
  }

  /* Sticky tab bar — keep Housekeepers/Inspectors/Groups/Live reachable
     while scrolling long schedules */
  .stTabs [data-baseweb="tab-list"]{
    position:sticky!important;top:0!important;z-index:99!important;
    backdrop-filter:blur(18px)!important;-webkit-backdrop-filter:blur(18px)!important;
  }

  /* Group / staff / inspector cards (iframes) hug the screen edge */
  iframe{width:100%!important;}

  /* Expander internals breathe less */
  .streamlit-expanderContent{padding:8px 6px!important;}

  /* Download + Generate buttons: full-width thumb targets */
  .stDownloadButton>button{width:100%!important;min-height:46px!important;}
}

/* ── Narrow phones ── */
@media(max-width:480px){
  .pg-title{font-size:1.1rem!important;}
  .sc .n{font-size:1.05rem!important;}
  .sc{padding:8px 5px!important;}
  /* 4 stat cards per two rows is still a lot — drop label tracking further */
  .sc .l{font-size:.46rem!important;}
  /* Tab pills shrink to fit all 4 on one line */
  .stTabs [data-baseweb="tab"]{padding:4px 7px!important;font-size:.64rem!important;}
  /* Status action buttons: compact but still ≥40px tall */
  .stButton>button{min-height:40px!important;padding:6px 4px!important;font-size:.72rem!important;}
  /* Section headers tighter */
  .sec{font-size:.55rem!important;margin:.8rem 0 .4rem!important;}
  /* Hide the vertical gap Streamlit adds between stacked widgets */
  [data-testid="stVerticalBlock"]{gap:.45rem!important;}
}
</style>""", unsafe_allow_html=True)

# ── LIGHT THEME OVERRIDE ──────────────────────────────────────────────────────
# When the user picks light mode, override the CSS variables + backgrounds.
# Because every component reads from var(--…), this single block reskins the
# entire app without touching the individual style rules above.
if _THEME == "light":
    st.markdown("""
<style>
/* ════════════════════════════════════════════════════════════════════════
   FORMAL / OFFICE THEME
   A clean corporate look: neutral slate surfaces, one restrained blue accent,
   crisp hairline borders, and soft shadows instead of neon glows. Overrides the
   base design-system variables so every var(--…) consumer reskins at once.
   ════════════════════════════════════════════════════════════════════════ */
:root {
  --bg:#f4f5f7; --bg1:#eceef1; --bg2:#ffffff; --bg3:#f7f8fa;
  --border:#e2e5ea; --border-hi:#c3c9d4;
  --indigo:#2563a8; --indigo-lo:rgba(37,99,168,.07);
  --cyan:#3b7fb8; --cyan-lo:rgba(59,127,184,.07);
  --teal:#0f766e; --amber:#b45309; --rose:#be123c;
  --txt:#1f2733; --txt2:#5b6675; --txt3:#8a93a1;
  --glow-i:0 1px 3px rgba(20,32,54,.08),0 1px 2px rgba(20,32,54,.04);
  --glow-c:0 1px 3px rgba(20,32,54,.08);
  --glow-sm:0 1px 2px rgba(20,32,54,.07);
  --radius:10px; --radius-sm:7px;
}
/* Neutral, distraction-free background — no radial neon washes. */
.stApp{
  background:#f4f5f7!important;
  background-image:none!important;
}
.block-container{padding-top:1.8rem!important;max-width:1360px!important;}

/* Page title: solid, confident slate — no gradient text, no animation flourish. */
.pg-title{
  font-family:'Syne',sans-serif!important;font-weight:700!important;
  font-size:1.7rem!important;letter-spacing:-.02em!important;
  color:#16202e!important;
  -webkit-text-fill-color:#16202e!important;background:none!important;
  animation:none!important;
}
.pg-sub{color:var(--txt2)!important;}
.sec{color:var(--txt2)!important;border-bottom:1px solid var(--border)!important;
  letter-spacing:.14em!important;font-weight:600!important;}

/* Cards & surfaces: white with a hairline border and a soft shadow. */
.sc{
  background:#ffffff!important;
  border:1px solid var(--border)!important;
  box-shadow:0 1px 2px rgba(20,32,54,.06)!important;
}
.sc.hi{background:#ffffff!important;border-left:3px solid var(--indigo)!important;}
.sc.ds{background:#ffffff!important;border-left:3px solid var(--teal)!important;}
.sc.dv{background:#ffffff!important;border-left:3px solid var(--amber)!important;}
.sc .n{color:#16202e!important;text-shadow:none!important;}
.sc .l{color:var(--txt2)!important;}
.rules-box{background:#ffffff!important;border:1px solid var(--border)!important;}

/* Accent top-bars on cards → flat, single tone (no indigo→cyan gradient). */
.sc::before,.rules-box::before{background:var(--indigo)!important;}

/* Sidebar: solid white panel with a clean divider (no blur/glow). */
section[data-testid="stSidebar"]{
  background:#ffffff!important;
  backdrop-filter:none!important;-webkit-backdrop-filter:none!important;
  border-right:1px solid var(--border)!important;
  box-shadow:1px 0 0 rgba(20,32,54,.03)!important;
}
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{color:var(--txt)!important;}

/* Tabs: understated, with a solid accent for the active tab. */
.stTabs [data-baseweb="tab-list"]{background:#ffffff!important;border:1px solid var(--border)!important;}
.stTabs [data-baseweb="tab"]{color:var(--txt2)!important;}
.stTabs [aria-selected="true"]{background:var(--indigo)!important;color:#ffffff!important;}

/* Buttons: clean white default, solid accent on hover/primary. */
.stButton>button{
  background:#ffffff!important;color:var(--txt)!important;
  border:1px solid var(--border-hi)!important;box-shadow:none!important;
}
.stButton>button:hover{
  background:var(--indigo)!important;color:#ffffff!important;
  border-color:var(--indigo)!important;
}

/* Inputs: white fields, subtle border, accent focus ring. */
.stTextArea textarea,.stTextInput input,
.stSelectbox [data-baseweb="select"]>div,
.stMultiSelect [data-baseweb="select"]>div{
  background:#ffffff!important;color:var(--txt)!important;border:1px solid var(--border-hi)!important;
}
.stTextArea textarea:focus,.stTextInput input:focus{
  border-color:var(--indigo)!important;box-shadow:0 0 0 3px var(--indigo-lo)!important;
}
.streamlit-expanderHeader{background:#ffffff!important;border:1px solid var(--border)!important;}
.streamlit-expanderContent{background:#ffffff!important;}
[data-baseweb="popover"] [role="listbox"],[data-baseweb="menu"]{background:#ffffff!important;}

/* Metrics / dataframes read cleanly on white. */
[data-testid="stMetricValue"]{color:#16202e!important;}
[data-testid="stMetricLabel"]{color:var(--txt2)!important;}

/* Scrollbar: neutral, not accent-colored. */
::-webkit-scrollbar-thumb{background:#c3c9d4!important;}
::-webkit-scrollbar-track{background:#eceef1!important;}

/* Primary button: solid accent, flat, no pulsing glow (formal). */
.stButton>button[kind="primary"]{
  background:var(--indigo)!important;border:1px solid var(--indigo)!important;color:#ffffff!important;
  box-shadow:0 1px 2px rgba(20,32,54,.10)!important;animation:none!important;
}
.stButton>button[kind="primary"]:hover{
  background:#1f5697!important;transform:none!important;
  box-shadow:0 2px 6px rgba(20,32,54,.14)!important;
}
/* Card hover: gentle lift, no scale-pop or glow. */
.sc:hover{transform:translateY(-1px)!important;box-shadow:0 2px 6px rgba(20,32,54,.10)!important;}
/* Sidebar collapse control and misc glows flattened. */
[data-testid="stSlider"] div[role="slider"]{box-shadow:none!important;}
</style>""", unsafe_allow_html=True)

# ── LIQUID GLASS THEMES (iOS-style frosted translucency) ─────────────────────
# Two variants: glass-light (bright frosted) and glass-dark (smoked glass).
if _THEME == "glass-light":
    st.markdown("""
<style>
:root {
  --bg:#eef1f7; --bg1:#e8ecf4; --bg2:rgba(255,255,255,.62); --bg3:rgba(255,255,255,.45);
  --border:rgba(255,255,255,.75); --border-hi:rgba(94,92,230,.45);
  --indigo:#5e5ce6; --indigo-lo:rgba(94,92,230,.10);
  --cyan:#0a84c1; --cyan-lo:rgba(10,132,193,.10);
  --teal:#0d9488; --amber:#c77700; --rose:#d6275d;
  --txt:#1c1c1e; --txt2:#5b5b60; --txt3:#9a9aa2;
  --glow-i:0 8px 32px rgba(31,38,135,.10);
  --glow-c:0 8px 32px rgba(31,38,135,.08);
  --glow-sm:0 2px 10px rgba(31,38,135,.06);
}
.stApp{
  background:#eef1f7!important;
  background-image:
    radial-gradient(ellipse 90% 60% at 15% -10%,rgba(94,92,230,.14) 0%,transparent 60%),
    radial-gradient(ellipse 70% 50% at 90% 0%,rgba(10,132,193,.10) 0%,transparent 55%),
    radial-gradient(ellipse 60% 45% at 70% 110%,rgba(255,150,160,.10) 0%,transparent 55%)!important;
  background-attachment:fixed!important;
}
.sc, .rules-box{
  background:rgba(255,255,255,.55)!important;
  backdrop-filter:blur(28px) saturate(180%)!important;
  -webkit-backdrop-filter:blur(28px) saturate(180%)!important;
  border:1px solid rgba(255,255,255,.78)!important;
  border-radius:18px!important;
  box-shadow:0 8px 32px rgba(31,38,135,.10), inset 0 1px 0 rgba(255,255,255,.95)!important;
}
.sc.hi{background:linear-gradient(135deg,rgba(94,92,230,.16),rgba(255,255,255,.5))!important;}
.sc.ds{background:linear-gradient(135deg,rgba(13,148,136,.13),rgba(255,255,255,.5))!important;}
.sc.dv{background:linear-gradient(135deg,rgba(199,119,0,.13),rgba(255,255,255,.5))!important;}
.sc .n{text-shadow:none!important;color:#1c1c1e!important;}
section[data-testid="stSidebar"]{
  background:rgba(255,255,255,.55)!important;
  backdrop-filter:blur(34px) saturate(180%)!important;
  -webkit-backdrop-filter:blur(34px) saturate(180%)!important;
  border-right:1px solid rgba(255,255,255,.7)!important;
  box-shadow:8px 0 32px rgba(31,38,135,.07)!important;
}
section[data-testid="stSidebar"]::before{background:linear-gradient(90deg,#5e5ce6,#0a84c1)!important;}
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{color:var(--txt)!important;}
.stTabs [data-baseweb="tab-list"]{
  background:rgba(255,255,255,.5)!important;border:1px solid rgba(255,255,255,.75)!important;
  backdrop-filter:blur(20px) saturate(170%)!important;-webkit-backdrop-filter:blur(20px) saturate(170%)!important;
  border-radius:14px!important;box-shadow:0 4px 18px rgba(31,38,135,.07)!important;
}
.stTabs [aria-selected="true"]{
  background:rgba(255,255,255,.92)!important;color:var(--indigo)!important;
  box-shadow:0 2px 10px rgba(31,38,135,.12)!important;border-radius:10px!important;
}
.stButton>button{
  background:rgba(255,255,255,.6)!important;color:var(--txt)!important;
  border:1px solid rgba(255,255,255,.8)!important;border-radius:13px!important;
  backdrop-filter:blur(16px) saturate(160%)!important;-webkit-backdrop-filter:blur(16px) saturate(160%)!important;
  box-shadow:0 2px 12px rgba(31,38,135,.07), inset 0 1px 0 rgba(255,255,255,.95)!important;
}
.stButton>button:hover{background:rgba(255,255,255,.85)!important;border-color:rgba(94,92,230,.4)!important;}
.stButton>button[kind="primary"]{
  background:linear-gradient(135deg,rgba(94,92,230,.92),rgba(122,120,255,.88))!important;
  border:1px solid rgba(255,255,255,.5)!important;color:#fff!important;
  box-shadow:0 6px 22px rgba(94,92,230,.35), inset 0 1px 0 rgba(255,255,255,.45)!important;
}
.stTextArea textarea,.stTextInput input,
.stSelectbox [data-baseweb="select"]>div,
.stMultiSelect [data-baseweb="select"]>div{
  background:rgba(255,255,255,.62)!important;color:var(--txt)!important;
  border:1px solid rgba(255,255,255,.85)!important;border-radius:13px!important;
  backdrop-filter:blur(14px)!important;-webkit-backdrop-filter:blur(14px)!important;
}
.streamlit-expanderHeader{background:rgba(255,255,255,.55)!important;border-radius:14px!important;}
.streamlit-expanderContent{background:rgba(255,255,255,.4)!important;}
[data-baseweb="popover"] [role="listbox"],[data-baseweb="menu"]{
  background:rgba(255,255,255,.92)!important;backdrop-filter:blur(28px)!important;
  border:1px solid rgba(255,255,255,.85)!important;border-radius:14px!important;
}
hr{background:rgba(28,28,30,.12)!important;}
</style>""", unsafe_allow_html=True)

elif _THEME == "glass-dark":
    st.markdown("""
<style>
:root {
  --bg:#0b0b0f; --bg1:#101016; --bg2:rgba(38,38,48,.5); --bg3:rgba(48,48,60,.4);
  --border:rgba(255,255,255,.14); --border-hi:rgba(125,122,255,.5);
  --indigo:#7d7aff; --indigo-lo:rgba(125,122,255,.12);
  --cyan:#64d2ff; --cyan-lo:rgba(100,210,255,.10);
  --teal:#2dd4bf; --amber:#ffb340; --rose:#ff6482;
  --txt:#f2f2f7; --txt2:#aeaeb6; --txt3:#6c6c75;
  --glow-i:0 8px 32px rgba(0,0,0,.45);
  --glow-c:0 8px 32px rgba(0,0,0,.4);
  --glow-sm:0 2px 12px rgba(0,0,0,.35);
}
.stApp{
  background:#0b0b0f!important;
  background-image:
    radial-gradient(ellipse 90% 60% at 15% -10%,rgba(125,122,255,.16) 0%,transparent 60%),
    radial-gradient(ellipse 70% 50% at 90% 0%,rgba(100,210,255,.09) 0%,transparent 55%),
    radial-gradient(ellipse 60% 45% at 70% 110%,rgba(255,100,130,.08) 0%,transparent 55%)!important;
  background-attachment:fixed!important;
}
.sc, .rules-box{
  background:rgba(36,36,46,.45)!important;
  backdrop-filter:blur(28px) saturate(160%)!important;
  -webkit-backdrop-filter:blur(28px) saturate(160%)!important;
  border:1px solid rgba(255,255,255,.14)!important;
  border-radius:18px!important;
  box-shadow:0 8px 32px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.10)!important;
}
.sc.hi{background:linear-gradient(135deg,rgba(125,122,255,.2),rgba(36,36,46,.4))!important;}
.sc.ds{background:linear-gradient(135deg,rgba(45,212,191,.14),rgba(36,36,46,.4))!important;}
.sc.dv{background:linear-gradient(135deg,rgba(255,179,64,.13),rgba(36,36,46,.4))!important;}
.sc .n{color:#f2f2f7!important;text-shadow:0 0 22px rgba(125,122,255,.45)!important;}
section[data-testid="stSidebar"]{
  background:rgba(22,22,30,.55)!important;
  backdrop-filter:blur(36px) saturate(160%)!important;
  -webkit-backdrop-filter:blur(36px) saturate(160%)!important;
  border-right:1px solid rgba(255,255,255,.12)!important;
  box-shadow:8px 0 40px rgba(0,0,0,.5)!important;
}
section[data-testid="stSidebar"]::before{background:linear-gradient(90deg,#7d7aff,#64d2ff)!important;}
.stTabs [data-baseweb="tab-list"]{
  background:rgba(36,36,46,.45)!important;border:1px solid rgba(255,255,255,.13)!important;
  backdrop-filter:blur(22px) saturate(150%)!important;-webkit-backdrop-filter:blur(22px) saturate(150%)!important;
  border-radius:14px!important;
}
.stTabs [aria-selected="true"]{
  background:rgba(125,122,255,.25)!important;color:#cfcdff!important;
  box-shadow:0 0 0 1px rgba(125,122,255,.45), inset 0 1px 0 rgba(255,255,255,.16)!important;
  border-radius:10px!important;
}
.stButton>button{
  background:rgba(46,46,58,.5)!important;color:var(--txt)!important;
  border:1px solid rgba(255,255,255,.15)!important;border-radius:13px!important;
  backdrop-filter:blur(18px) saturate(150%)!important;-webkit-backdrop-filter:blur(18px) saturate(150%)!important;
  box-shadow:0 2px 14px rgba(0,0,0,.4), inset 0 1px 0 rgba(255,255,255,.10)!important;
}
.stButton>button:hover{background:rgba(125,122,255,.18)!important;border-color:rgba(125,122,255,.45)!important;}
.stButton>button[kind="primary"]{
  background:linear-gradient(135deg,rgba(125,122,255,.85),rgba(100,210,255,.7))!important;
  border:1px solid rgba(255,255,255,.3)!important;color:#fff!important;
  box-shadow:0 6px 26px rgba(125,122,255,.4), inset 0 1px 0 rgba(255,255,255,.35)!important;
}
.stTextArea textarea,.stTextInput input,
.stSelectbox [data-baseweb="select"]>div,
.stMultiSelect [data-baseweb="select"]>div{
  background:rgba(36,36,46,.5)!important;color:var(--txt)!important;
  border:1px solid rgba(255,255,255,.15)!important;border-radius:13px!important;
  backdrop-filter:blur(14px)!important;-webkit-backdrop-filter:blur(14px)!important;
}
.streamlit-expanderHeader{background:rgba(36,36,46,.5)!important;border-radius:14px!important;}
.streamlit-expanderContent{background:rgba(28,28,36,.4)!important;}
[data-baseweb="popover"] [role="listbox"],[data-baseweb="menu"]{
  background:rgba(30,30,40,.92)!important;backdrop-filter:blur(30px)!important;
  border:1px solid rgba(255,255,255,.16)!important;border-radius:14px!important;
}
hr{background:rgba(255,255,255,.1)!important;}
</style>""", unsafe_allow_html=True)

# ── Theme-aware constants for components.html cards ───────────────────────────
# Cards render inside iframes, which DON'T inherit the parent page's CSS vars,
# so we pass concrete colors based on the active theme. (backdrop-filter can't
# blur the parent page from inside an iframe, so glass cards here use soft
# translucent fills + hairline highlights that read as glass.)
if _THEME == "glass-light":
    _C = {
        "card_bg":   "linear-gradient(135deg,rgba(255,255,255,.94),rgba(247,249,255,.9))",
        "card_br":   "rgba(255,255,255,.95)",
        "card_sh":   "0 8px 28px rgba(31,38,135,.10), inset 0 1px 0 rgba(255,255,255,.98)",
        "txt":       "#1c1c1e",
        "txt2":      "#5b5b60",
        "txt3":      "#9a9aa2",
        "row_br":    "rgba(94,92,230,.10)",
        "th_bg":     "rgba(94,92,230,.05)",
        "tbl_bg":    "rgba(255,255,255,.92)",
        "foot_bg":   "rgba(94,92,230,.04)",
    }
    _BODY_TXT = "#1c1c1e"
elif _THEME == "glass-dark":
    _C = {
        "card_bg":   "linear-gradient(135deg,rgba(40,40,52,.92),rgba(30,30,40,.94))",
        "card_br":   "rgba(255,255,255,.16)",
        "card_sh":   "0 8px 28px rgba(0,0,0,.5), inset 0 1px 0 rgba(255,255,255,.12)",
        "txt":       "#f2f2f7",
        "txt2":      "#aeaeb6",
        "txt3":      "#6c6c75",
        "row_br":    "rgba(255,255,255,.08)",
        "th_bg":     "rgba(255,255,255,.04)",
        "tbl_bg":    "rgba(32,32,42,.92)",
        "foot_bg":   "rgba(255,255,255,.03)",
    }
    _BODY_TXT = "#f2f2f7"
elif _THEME == "light":
    _C = {
        "card_bg":   "#ffffff",
        "card_br":   "#e2e5ea",
        "card_sh":   "0 1px 2px rgba(20,32,54,.06),0 0 0 1px rgba(20,32,54,.02)",
        "txt":       "#16202e",
        "txt2":      "#5b6675",
        "txt3":      "#8a93a1",
        "row_br":    "#eef0f3",
        "th_bg":     "#f4f5f7",
        "tbl_bg":    "#ffffff",
        "foot_bg":   "#f7f8fa",
    }
    _BODY_TXT = "#16202e"
else:
    _C = {
        "card_bg":   "linear-gradient(135deg,rgba(14,14,26,.95),rgba(19,19,31,.98))",
        "card_br":   "rgba(99,102,241,.25)",
        "card_sh":   "0 0 0 1px rgba(255,255,255,.04),0 8px 32px rgba(0,0,0,.4)",
        "txt":       "#e2e8f0",
        "txt2":      "#94a3b8",
        "txt3":      "#475569",
        "row_br":    "rgba(99,102,241,.07)",
        "th_bg":     "rgba(255,255,255,.02)",
        "tbl_bg":    "rgba(13,13,26,.9)",
        "foot_bg":   "rgba(255,255,255,.015)",
    }
    _BODY_TXT = "#e2e8f0"

# ── Micro-interactions: animated buttons & status transitions (all themes) ───
st.markdown("""
<style>
.stButton>button{
  transition:transform .12s cubic-bezier(.34,1.56,.64,1), box-shadow .25s ease,
             background .2s ease, border-color .2s ease, color .2s ease!important;
  will-change:transform;
}
.stButton>button:hover{transform:translateY(-1px);}
.stButton>button:active{
  transform:scale(.93)!important;
  box-shadow:0 0 0 5px rgba(99,102,241,.18)!important;
}
@keyframes statusPop{
  0%{transform:scale(.55);opacity:0}
  60%{transform:scale(1.1)}
  100%{transform:scale(1);opacity:1}
}
@keyframes pulseDot{
  0%,100%{opacity:1;transform:scale(1)}
  50%{opacity:.4;transform:scale(.8)}
}
@keyframes ringPulse{
  0%{box-shadow:0 0 0 0 rgba(34,211,238,.45)}
  70%{box-shadow:0 0 0 7px rgba(34,211,238,0)}
  100%{box-shadow:0 0 0 0 rgba(34,211,238,0)}
}
</style>""", unsafe_allow_html=True)

SHARED_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600&display=swap');
*{box-sizing:border-box;margin:0;padding:0;}
body{
  font-family:'DM Sans',sans-serif;
  background:transparent;
  color:""" + _BODY_TXT + """;
  overflow-x:auto;
  -webkit-overflow-scrolling:touch;
}
@keyframes rowIn{from{opacity:0;transform:translateX(-6px)}to{opacity:1;transform:translateX(0)}}
@keyframes glassIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
table{min-width:0;width:100%;border-collapse:collapse;}
@media(max-width:600px){
  table{font-size:.72rem!important;}
  th,td{padding:5px 7px!important;}
  /* Hide low-value columns on phones — Bld + Service already shown in the
     card header, so the table keeps Room/Guest/Time/Pet/LateOut */
  .m-hide{display:none!important;}
}
</style>"""

# ══════════════════════════════════════════════════════════════════════════════
#  SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════
def _persist_roster():
    """Save the current housekeeper + inspector rosters to the database so all
    changes (add, remove, present-toggle, building move, bulk set) survive page
    reloads, new sessions, and redeploys. Silent no-op if the DB is unreachable."""
    try:
        db.save_roster(st.session_state.get("hk_roster", {}),
                       st.session_state.get("insp_roster", {}))
    except Exception as _ex:
        print(f"[app] _persist_roster failed: {_ex}")

def _init_state():
    if "hk_roster" not in st.session_state:
        # Load the standing roster from the database first — this is what people
        # actually see, so add/remove of staff must persist. Only if nothing has
        # ever been saved do we seed from the hard-coded DEFAULT_HK.
        saved_roster = None
        try:
            saved_roster = db.load_roster()
        except Exception:
            saved_roster = None
        if saved_roster and saved_roster.get("hk_roster"):
            st.session_state["hk_roster"]   = saved_roster["hk_roster"]
            st.session_state["insp_roster"] = saved_roster.get("insp_roster") \
                or {n: True for n in DEFAULT_INSPECTORS}
        else:
            roster = {}
            for bld, names in DEFAULT_HK.items():
                for n in names:
                    roster[n] = {"building": bld, "present": True}
            st.session_state["hk_roster"] = roster
            st.session_state["insp_roster"] = {n: True for n in DEFAULT_INSPECTORS}
    if "insp_roster" not in st.session_state:
        st.session_state["insp_roster"] = {n: True for n in DEFAULT_INSPECTORS}
    for k, default in [("groups_data",None),("total_rooms",None),
                        ("inspectors_data",None),("used_hk_set",None),
                        ("last_email",None),("rqs1",""),("rqs2",""),
                        ("priority_hks",[])]:
        if k not in st.session_state:
            st.session_state[k] = default

_init_state()
auth.init_auth()

# ══════════════════════════════════════════════════════════════════════════════
#  LOGIN GATE
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.get("logged_in"):
    st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400&display=swap');
/* Hide the entire sidebar + nav on the login screen */
section[data-testid="stSidebar"]{display:none !important;}
[data-testid="stSidebarNav"]{display:none !important;}
[data-testid="collapsedControl"]{display:none !important;}
button[kind="header"]{display:none !important;}
.stApp{
  background:#f4f5f7 !important;
  background-image:none !important;
}
.block-container{
  padding-top:0 !important;
  max-width:420px !important;
  margin:0 auto;
}
/* Center vertically */
.block-container > div:first-child {
  min-height:100vh;
  display:flex;
  flex-direction:column;
  justify-content:center;
  padding: 2rem 0;
}
.stButton>button{
  width:100%!important;border-radius:8px!important;font-weight:600!important;
  background:#2563a8!important;border:1px solid #2563a8!important;
  color:#fff!important;padding:12px!important;font-size:.88rem!important;letter-spacing:.01em;
  box-shadow:0 1px 2px rgba(20,32,54,.10)!important;
  transition:all .15s!important;
}
.stButton>button:hover{
  background:#1f5697!important;
  box-shadow:0 2px 6px rgba(20,32,54,.16)!important;
}
.stTextInput input {
  background:#ffffff!important;
  border:1px solid #c3c9d4!important;
  border-radius:8px!important;color:#16202e!important;
  font-family:'DM Sans',sans-serif!important;font-size:.88rem!important;
  padding:12px 14px!important;
  -webkit-text-fill-color:#16202e!important;
}
.stTextInput input:focus{
  border-color:#2563a8!important;
  box-shadow:0 0 0 3px rgba(37,99,168,.12)!important;
  -webkit-text-fill-color:#16202e!important;
}
.stTextInput input::placeholder{color:#8a93a1!important;-webkit-text-fill-color:#8a93a1!important;}
/* Stop browser autofill from forcing an off-color box */
.stTextInput input:-webkit-autofill,
.stTextInput input:-webkit-autofill:hover,
.stTextInput input:-webkit-autofill:focus{
  -webkit-text-fill-color:#16202e!important;
  caret-color:#16202e!important;
  -webkit-box-shadow:0 0 0 1000px #ffffff inset!important;
  box-shadow:0 0 0 1000px #ffffff inset!important;
  transition:background-color 9999s ease-in-out 0s!important;
}
label{color:#5b6675!important;font-size:.78rem!important;font-weight:500!important;font-family:'DM Sans',sans-serif!important;}
footer{visibility:hidden!important;}
</style>""", unsafe_allow_html=True)

    # Logo + title
    st.markdown("""
<div style="text-align:center;margin-bottom:28px">
  <div style="width:52px;height:52px;margin:0 auto 14px;border-radius:12px;
              background:#2563a8;display:flex;align-items:center;justify-content:center;
              box-shadow:0 2px 8px rgba(37,99,168,.25);font-size:1.5rem">🧹</div>
  <div style="font-family:'Syne',sans-serif;font-size:1.5rem;font-weight:700;letter-spacing:-.02em;
              color:#16202e;margin-bottom:5px">Grand Timber GC8</div>
  <div style="font-family:'DM Sans',sans-serif;font-size:.76rem;color:#5b6675;letter-spacing:.06em;
              text-transform:uppercase;font-weight:500">Housekeeping · Scheduling · Live Tracking</div>
</div>
""", unsafe_allow_html=True)

    # Card wrapper
    st.markdown("""
<div style="background:#ffffff;border:1px solid #e2e5ea;
            border-radius:14px;padding:30px 28px 26px;
            box-shadow:0 1px 3px rgba(20,32,54,.08),0 8px 24px rgba(20,32,54,.06)">
  <div style="font-family:'Syne',sans-serif;font-size:1.02rem;font-weight:700;color:#16202e;
              margin-bottom:4px">Welcome back 👋</div>
  <div style="font-family:'DM Sans',sans-serif;font-size:.8rem;color:#5b6675;margin-bottom:24px">
    Sign in with your Grand Timber email
  </div>
""", unsafe_allow_html=True)
    _db_ok = True; _db_msg = ""
    try:
        db.ensure_admin_exists()
    except Exception as _ex:
        _db_ok = False; _db_msg = str(_ex)
    if not _db_ok:
        st.error("⚠️ Cannot connect to database.")
        st.markdown(f"**Error:** `{_db_msg}`\n\n**Fix:** Add `SUPABASE_URL` and `SUPABASE_KEY` to Streamlit Secrets.")
        st.stop()
    with st.form("login_form"):
        _uname = st.text_input("Username")
        _pw    = st.text_input("Password", type="password")
        _sub   = st.form_submit_button("Sign In", type="primary", use_container_width=True)
    if _sub:
        if not _uname or not _pw:
            st.error("Please enter both username and password.")
        else:
            _user = db.authenticate(_uname.strip(), _pw)
            if _user:
                auth.login(_user)
                # Record who signed in and when (best-effort; never blocks login).
                try:
                    db.log_login(_user.get("username",""),
                                 _user.get("display_name") or _user.get("username",""),
                                 _user.get("role",""))
                except Exception:
                    pass
                st.rerun()
            else:
                st.error("Invalid username or password.")

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("""
<div style="text-align:center;margin-top:20px;font-family:'DM Mono',monospace;
            font-size:.65rem;color:#1e293b;letter-spacing:.06em">
  GRAND TIMBER GC8 · CONFIDENTIAL
</div>""", unsafe_allow_html=True)
    st.stop()

# ── Restore today's shared schedule — ONCE per browser session ────────────────
# Runs only on the first script execution of a session. After that the flag
# stays True for the whole session, so generating a new schedule (which sets
# groups_data directly) is never overwritten by a stale DB load.
if not st.session_state.get("_did_initial_restore", False):
    st.session_state["_did_initial_restore"] = True
    try:
        saved = db.load_full_schedule()
        # NOTE: we deliberately do NOT restore hk_roster / insp_roster from the
        # daily schedule here. The authoritative, persistent roster is loaded in
        # _init_state() from db.load_roster(). A day's saved schedule can contain
        # a stale roster (e.g. someone you removed yesterday), and restoring it
        # here would bring removed people back — the exact bug we're fixing.
        if saved and saved.get("groups_data"):
            _loaded_groups = saved.get("groups_data") or []
            # JSON serialization turns sets into lists (or strings). Restore them
            # to sets so sorted(g["blds"]) and set operations work correctly.
            for _g in _loaded_groups:
                _b = _g.get("blds", [])
                if isinstance(_b, str):
                    # e.g. "{1, 2}" → extract digits
                    _b = [int(x) for x in re.findall(r'\d+', _b)]
                _g["blds"] = set(_b) if not isinstance(_b, set) else _b
                _f = _g.get("floors", [])
                if isinstance(_f, str):
                    _f = [int(x) for x in re.findall(r'\d+', _f)]
                _g["floors"] = set(_f) if not isinstance(_f, set) else _f
            st.session_state["groups_data"]     = _loaded_groups
            st.session_state["total_rooms"]     = saved.get("total_rooms", 0)
            st.session_state["inspectors_data"] = saved.get("inspectors_data", [])
            st.session_state["used_hk_set"]     = set(saved.get("used_hk_set", []))
    except Exception:
        pass
# ══════════════════════════════════════════════════════════════════════════════
SKIP_SERVICES = {"p/u models","pu models","p/u model","showcase","model unit","p/u"}

def normalize_service(raw: str) -> str:
    s = re.sub(r'\s+', ' ', str(raw).strip().lower())
    if s in SKIP_SERVICES or "p/u" in s or (s.startswith("p") and "model" in s):
        return "__SKIP__"
    if "daily" in s: return SVC_DS
    # "Full Clean (IH)" / "Full Clean( IH)" / "... IH" -> separate IH stream,
    # packed apart from regular Full Clean and inspected by RQS 2.
    if ("full clean" in s or s.startswith("fc")) and "ih" in s:
        return SVC_IH
    if s.startswith("full clean") or s.startswith("fc"): return SVC_FC
    if "dust" in s or "d&v" in s or "dnv" in s: return SVC_DV
    if "vac" in s: return SVC_DV
    return SVC_FC

def parse_room_code(room: str) -> dict:
    s = str(room).strip()
    try:
        bld   = int(s[0])
        floor = int(s[1]) if len(s)>1 and s[1].isdigit() else 0
        digits = "".join(c for c in s[2:] if c.isdigit())
        num = int(digits) if digits else 0
    except Exception:
        bld, floor, num = 0, 0, 0
    return {"bld": bld, "floor": floor, "num": num}

def get_building(room): return parse_room_code(room)["bld"]

def expand_compound_room(room_str: str) -> list:
    m = re.match(r'^([1-9]\d{3})([A-Z]{2,4})$', room_str.upper())
    if not m: return [room_str.upper()]
    base, suffix = m.group(1), m.group(2)
    if len(suffix) == 2 and ord(suffix[1]) == ord(suffix[0]) + 1:
        return [f"{base}{suffix[0]}", f"{base}{suffix[1]}"]
    return [room_str.upper()]

def expand_rooms(raw_list: list) -> list:
    return [r for s in raw_list for r in expand_compound_room(s)]

def parse_email_notes(text: str) -> dict:
    late_co: dict = {}
    notes:   dict = {}
    if not text or not text.strip():
        return {"late_checkout": late_co, "notes": notes}
    ROOM_RE    = re.compile(r'\b([1-9]\d{3}[A-Z]{1,4})\b')
    TIME_RE    = re.compile(r'\b(\d{1,2}:\d{2}\s*(?:am|pm))\b', re.IGNORECASE)
    SECTION_RE = re.compile(r'^([A-Za-z][A-Za-z &\'/]+):\s*$')
    MOVE_RE    = re.compile(r'([1-9]\d{3}[A-Z]{1,4})\s*[-\u2013]\s*([1-9]\d{3}[A-Z]{1,4})')
    CELEB_RE   = re.compile(r'^(Birthday|Anniversary|Misc\.?)$', re.IGNORECASE)
    DEBULLET   = re.compile(r'^[\s\t]*[*\u2022\u25e6\u2023\u2043\-]?\s*')
    NOTE_LABELS = {
        "vip inspections":"VIP","room moves":"Room Move","stayovers":"Stayover",
        "robes":"Robes","pack n play":"Pack n Play","highchairs":"Highchair",
        "rollaway":"Rollaway","special requests":"Special Request",
        "dogs arriving":"Dog arriving","celebrations":"Celebration",
        "early ins":"Early In","late arrival":"Late Arrival",
    }
    LATE_KEY = "late checkouts"
    section = None; sub_label = None; late_time = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped: continue
        hdr_m = SECTION_RE.match(stripped)
        if hdr_m and not ROOM_RE.search(stripped):
            hdr_key = hdr_m.group(1).strip().lower()
            if hdr_key in NOTE_LABELS or hdr_key == LATE_KEY:
                section = hdr_key; sub_label = None; late_time = None; continue
        content = DEBULLET.sub('', line).strip()
        if not content or content.lower() == "n/a": continue
        if section == LATE_KEY:
            time_m = TIME_RE.search(content)
            rooms  = expand_rooms(ROOM_RE.findall(content.upper()))
            if time_m:
                late_time = re.sub(r'\s+', ' ', time_m.group(1).strip())
                for rm in rooms: late_co[rm] = f"Late Out: {late_time}"
            elif rooms and late_time:
                for rm in rooms: late_co[rm] = f"Late Out: {late_time}"
            continue
        if not section or section not in NOTE_LABELS: continue
        label = NOTE_LABELS[section]
        if section == "room moves":
            for mv in MOVE_RE.finditer(content.upper()):
                for rf in expand_compound_room(mv.group(1)):
                    for rt in expand_compound_room(mv.group(2)):
                        notes.setdefault(rf, []).append(f"Room Move → {rt}")
                        notes.setdefault(rt, []).append(f"Room Move ← {rf}")
            continue
        if section == "celebrations":
            cm = CELEB_RE.match(content)
            if cm:
                t = cm.group(1).strip()
                sub_label = None if t.lower().startswith("misc") else t; continue
            if sub_label: label = f"Celebration ({sub_label})"
        rooms = expand_rooms(ROOM_RE.findall(content.upper()))
        if not rooms: continue
        qty = re.search(r'x(\d+)', content, re.IGNORECASE)
        qty_s = f" x{qty.group(1)}" if qty else ""
        if section == "special requests":
            # Capture the actual request detail (e.g. "2135A - Humidifier" ->
            # "Special Request: Humidifier"). Skip "n/a". Strip the room codes and
            # surrounding punctuation to leave just the request text.
            detail = ROOM_RE.sub('', content.upper() if False else content)
            detail = re.sub(r'\b[1-9]\d{3}[A-Z]{1,4}\b', '', detail)
            detail = detail.strip(" -\u2013:;,\t").strip()
            if detail.lower() in ("n/a","na",""):
                for rm in rooms: notes.setdefault(rm, []).append(f"{label}{qty_s}")
            else:
                for rm in rooms:
                    notes.setdefault(rm, []).append(f"{label}: {detail}{qty_s}")
            continue
        for rm in rooms: notes.setdefault(rm, []).append(f"{label}{qty_s}")
    return {"late_checkout": late_co, "notes": notes}

def excel_to_room_text(file_obj):
    """Convert an uploaded 'Housekeeping Dashboard' .xlsx into the same
    tab-separated text the paste box accepts, so it can flow through the exact
    same parse_rooms() pipeline. Reads only the cleaning-services table and
    stops before the footer/summary sections. Column positions are located by
    header label (not fixed indices) so minor export changes don't misread.
    Returns (tsv_text, n_rooms, sheet_name)."""
    xls = pd.ExcelFile(file_obj)
    sheet = None
    for cand in xls.sheet_names:
        if "housekeeping dashboard" in str(cand).strip().lower():
            sheet = cand; break
    if sheet is None:
        sheet = xls.sheet_names[1] if len(xls.sheet_names) > 1 else xls.sheet_names[0]
    df = pd.read_excel(xls, sheet_name=sheet, header=None)

    # Find the header row (contains both "Room" and "Service").
    hdr = None
    for i in range(min(30, len(df))):
        vals = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        if "room" in vals and "service" in vals:
            hdr = i; break
    if hdr is None:
        raise ValueError("Couldn't find a 'Room'/'Service' header row in the sheet.")

    header_cells = {j: str(v).strip().lower()
                    for j, v in enumerate(df.iloc[hdr]) if pd.notna(v)}
    def find_col(*needles):
        # Prefer an exact header match, then fall back to substring.
        for n in needles:
            for j, name in header_cells.items():
                if name == n: return j
        for n in needles:
            for j, name in header_cells.items():
                if n in name: return j
        return None
    c_room  = find_col("room")
    c_svc   = find_col("service")
    c_time  = find_col("time")
    c_pet   = find_col("pet")
    c_guest = find_col("current guest or status", "current guest", "guest")
    c_late  = find_col("late checkout", "late check")
    c_status= find_col("status")            # exact -> real Status col, not "guest or status"
    c_notes = find_col("notes")
    c_arr   = find_col("arriving guest", "arriving")
    c_rtype = find_col("res type")

    _ROOM_RE = re.compile(r'^[1-9]\d{2,3}[A-Z]{1,4}$')
    order = [("Room", c_room), ("Service", c_svc), ("Time", c_time), ("Pet", c_pet),
             ("Current Guest or Status", c_guest), ("Res Type", c_rtype),
             ("Late Checkout", c_late), ("Status", c_status), ("Notes", c_notes),
             ("Arriving Guest", c_arr)]
    lines = ["\t".join(name for name, _ in order)]
    n_rooms = 0
    for i in range(hdr + 1, len(df)):
        rv = df.iloc[i, c_room] if c_room is not None else None
        if pd.isna(rv): continue
        room = str(rv).strip()
        if not _ROOM_RE.match(room.upper()):
            low = room.lower()
            if any(k in low for k in ("non-clean", "range totals", "daily labor",
                                       "daily housekeeper", "housekeeping hold", "room type")):
                break            # reached the footer — stop reading rooms
            continue             # stray non-room line — skip
        def cell(idx):
            if idx is None: return ""
            v = df.iloc[i, idx]
            if pd.isna(v): return ""
            if isinstance(v, float) and v == int(v): return str(int(v))
            return str(v).strip()
        lines.append("\t".join(cell(idx) for _, idx in order))
        n_rooms += 1
    return "\n".join(lines), n_rooms, sheet

def parse_rooms(text: str) -> pd.DataFrame:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if not lines: return pd.DataFrame()
    rows = [re.split(r"\t", l) for l in lines]
    header = [c.strip().lower() for c in rows[0]]

    def col(*names):
        # Prefer an EXACT header match before falling back to substring, so a
        # query like "status" doesn't accidentally match "current guest or
        # status". Names are tried in priority order.
        for n in names:
            for i, h in enumerate(header):
                if h.strip().lower() == n: return i
        for n in names:
            for i, h in enumerate(header):
                h_clean = h.strip().lower()
                if not h_clean: continue
                if n in h_clean: return i
        return None

    has_header = any(h in ("room","service","time","guest","current guest") for h in header)
    if has_header:
        data_rows = rows[1:]
        i_room = col("room"); i_svc = col("service"); i_time = col("time")
        i_pet  = col("pet");  i_guest = col("current guest","guest")
        i_late = col("late checkout","late check")
        i_status = col("status"); i_notes = col("notes")
        i_arriving = col("arriving guest","arriving"); i_restype = col("res type")
    else:
        data_rows = rows
        i_room,i_svc,i_time,i_pet,i_guest = 0,1,2,3,4
        i_late=i_status=i_notes=i_arriving=i_restype = None

    def get(row, idx, default=""):
        try: return str(row[idx]).strip() if idx is not None and idx<len(row) else default
        except: return default

    records = []
    for row in data_rows:
        room = get(row, i_room); svc = get(row, i_svc)
        ts   = get(row, i_time)
        try:    ti = int(float(ts))
        except: ti = 0
        if not room: continue
        norm_svc = normalize_service(svc)
        # P/U Models used to be dropped (__SKIP__). Now we keep them as a
        # "verify" room (no HK/RQS, pushed to the bottom for manual review).
        is_pu_skip = (norm_svc == "__SKIP__")
        if is_pu_skip:
            norm_svc = SVC_FC   # give it a real service type so it can render
        if ti <= 0:
            if norm_svc == SVC_DV:
                ti = DV_DEFAULT_TIME
            else:
                ti = default_time_for(room, norm_svc)
                if ti <= 0:
                    suffix = room[-1].upper() if room else ""
                    if suffix == "E":        ti = 140
                    elif suffix in ("D","A"):ti = 120
                    else:                    ti = 70
        import re as _re
        raw_guest  = get(row, i_guest)
        norm_guest = _re.sub(r'\s+', ' ', raw_guest.strip())
        status_raw     = get(row, i_status).strip().lower()
        guest_raw      = norm_guest.lower().strip()
        notes_raw_val  = get(row, i_notes).strip().lower()
        svc_raw_lower  = str(svc).strip().lower()
        has_stayover_excel = "stayover" in notes_raw_val or "stay over" in notes_raw_val
        # P/U Models can appear in the service column OR the notes column
        has_pu_models = ("p/u model" in notes_raw_val or "pu model" in notes_raw_val
                         or "p/u model" in svc_raw_lower or "pu model" in svc_raw_lower)
        # "verify" rooms: stayover or P/U models — never auto-assign HK/RQS,
        # pushed to the bottom of the schedule for manual review.
        needs_verify = has_stayover_excel or has_pu_models or is_pu_skip
        row_text = " ".join(str(c).strip().lower() for c in row if c)
        has_pending_anywhere = "pending" in row_text
        is_uncertain = (
            (guest_raw in ("unallocated","---","room, walk","","deposit, deposit") and
             ("pending" in status_raw or has_pending_anywhere))
            or has_stayover_excel
        )
        records.append({
            "Room":get(row,i_room),"Service":norm_svc,"ServiceRaw":svc,
            "Time":ti,"Pet":get(row,i_pet),"Guest":norm_guest,
            "LateCheckout":get(row,i_late),"Status":get(row,i_status),
            "NotesRaw":get(row,i_notes),"ArrivingGuest":get(row,i_arriving),
            "ResType":get(row,i_restype),"uncertain":is_uncertain,
            "verify":needs_verify,
        })
    if not records: return pd.DataFrame()
    df = pd.DataFrame(records)
    pc = df["Room"].apply(parse_room_code)
    df["bld"]   = pc.apply(lambda x: x["bld"])
    df["floor"] = pc.apply(lambda x: x["floor"])
    df["num"]   = pc.apply(lambda x: x["num"])
    return df

# ══════════════════════════════════════════════════════════════════════════════
#  GROUPING LOGIC
# ══════════════════════════════════════════════════════════════════════════════
def bld_ok(blds, b):
    for x in blds:
        if (x==2 and b==3) or (x==3 and b==2): return False
    return True

def same_bld(blds, ublds): return len(blds | ublds) == 1

def proximity_score(group_rooms, unit_rooms):
    if not group_rooms or not unit_rooms: return 999
    total, count = 0, 0
    for gr in group_rooms:
        for ur in unit_rooms:
            gb, ub = gr.get("bld",0), ur.get("bld",0)
            gf, uf = gr.get("floor",0), ur.get("floor",0)
            if gb != ub:   total += 300
            elif gf != uf: total += 30
            else:          total += min(abs(gr.get("num",0)-ur.get("num",0))//10, 9)
            count += 1
    return total // max(count,1)

def can_add_fc(g, unit):
    if g.get("service_type") != SVC_FC: return False
    ut = sum(r["time"] for r in unit)
    if g["time"]+ut > MAX_FC: return False
    for r in unit:
        if not bld_ok(g["blds"], r["bld"]): return False
    new_blds = g["blds"] | set(r["bld"] for r in unit)
    if 2 in new_blds and 3 in new_blds: return False
    u140 = sum(1 for r in unit if r["time"]==140)
    u120 = sum(1 for r in unit if r["time"]==120)
    new_c140 = g["c140"] + u140
    new_c120 = g["c120"] + u120
    if new_c140 > 1: return False
    # A group may not hold a 140 together with MORE THAN ONE 120.
    # 120+140+70 ✓ · 120+120+120 ✓ · 120+120+140 ✗
    if new_c140 >= 1 and new_c120 > 1: return False
    return True

def can_add_ds(g, unit, allow_overflow=False):
    if g.get("service_type") != SVC_DS: return False
    ut = sum(r["time"] for r in unit)
    cap = DS_OVER if allow_overflow else MAX_DS
    if g["time"]+ut > cap: return False
    # Daily Service MAY span all three buildings — housekeepers wheel carts
    # between towers. (Full Clean keeps the stricter B2<->B3 block; DS does not.)
    return True

def unit_ok_fc(unit):
    # A same-guest cluster is only "OK to keep as one chart" if it can actually
    # fit one chart under ALL hard rules. If it can't, pack_rooms splits it into
    # individual rooms so they can be spread across housekeepers.
    if sum(r["time"] for r in unit) > MAX_FC:   # over the 380 cap -> must split
        return False
    blds = set(r["bld"] for r in unit)
    ba = list(blds)
    for i in range(len(ba)):
        for j in range(i+1,len(ba)):
            if (ba[i]==2 and ba[j]==3) or (ba[i]==3 and ba[j]==2): return False
    n140 = sum(1 for r in unit if r["time"]==140)
    n120 = sum(1 for r in unit if r["time"]==120)
    if n140 > 1: return False
    # Same rule as can_add_fc: a 140 may coexist with at most ONE 120.
    if n140 >= 1 and n120 > 1: return False
    return True

def mk(unit, svc):
    return {"rooms":list(unit),"time":sum(r["time"] for r in unit),
            "blds":set(r["bld"] for r in unit),"floors":set(r.get("floor",0) for r in unit),
            "c140":sum(1 for r in unit if r["time"]==140),
            "c120":sum(1 for r in unit if r["time"]==120),
            "service_type":svc}

def absorb(g, unit):
    for r in unit:
        g["rooms"].append(r); g["blds"].add(r["bld"]); g["floors"].add(r.get("floor",0))
    g["time"]  += sum(r["time"] for r in unit)
    g["c140"]  += sum(1 for r in unit if r["time"]==140)
    g["c120"]  += sum(1 for r in unit if r["time"]==120)

def _mix_penalty(g, unit):
    """Steer Full-Clean charts toward the preferred shapes:
        120+120+120  (360)
        140+120+70   (330)
        120+120+70+70(380)
        70x5         (350)
    A chart that already matches (or is a clean prefix of) one of these gets no
    penalty; the further its room-count of each size is from the nearest target
    shape, the higher the penalty. This is a soft preference used to break ties
    in placement, never a hard rule — capacity/guest/building rules still win.
    """
    times = [r["time"] for r in g["rooms"]] + [r["time"] for r in unit]
    if not times: return 0
    n140 = sum(1 for t in times if t == 140)
    n120 = sum(1 for t in times if t == 120)
    n70  = sum(1 for t in times if t <= 70)   # 70s and anything smaller

    # (n140, n120, n70) signatures of the four preferred end-states
    TARGETS = [
        (0,3,0),   # 120+120+120
        (1,1,1),   # 140+120+70
        (0,2,2),   # 120+120+70+70
        (0,0,5),   # 70 x5
    ]
    # Distance to the closest target = sum of size-count mismatches. A chart
    # that is "on the way" to a target (fewer rooms than the target, matching
    # composition so far) is treated as a clean prefix → low penalty.
    best = 99
    for t140,t120,t70 in TARGETS:
        # Over-shooting a size beyond its target is worse than under-shooting.
        over  = max(0,n140-t140)+max(0,n120-t120)+max(0,n70-t70)
        under = max(0,t140-n140)+max(0,t120-n120)+max(0,t70-n70)
        best  = min(best, over*3 + under)   # overshoot weighted heavier
    return best * 25   # scale into "minutes-equivalent" tie-shaping range

def best_fit_generic(groups, unit, can_add_fn, same_bld_only, same_floor_only):
    ub  = set(r["bld"]         for r in unit)
    uf  = set(r.get("floor",0) for r in unit)
    u_t = sum(r["time"]        for r in unit)
    cap = MAX_DS if (unit and unit[0].get("service")==SVC_DS) else MAX_FC
    bi, best_score = -1, float("inf")
    for i, g in enumerate(groups):
        if not can_add_fn(g, unit): continue
        if same_bld_only   and not same_bld(g["blds"], ub):   continue
        if same_floor_only and not (g["floors"] & uf):         continue
        prx = proximity_score(g["rooms"], unit)
        rem = cap - (g["time"] + u_t)
        # mix penalty only matters for Full Clean (DS rooms are all light)
        mix = _mix_penalty(g, unit) if (unit and unit[0].get("service")!=SVC_DS) else 0
        score = prx * 10000 + rem + mix
        if score < best_score: best_score, bi = score, i
    return bi

def _fc_feasible(units_list):
    """True if a set of same-guest units can share one Full-Clean chart under
    all hard rules: 380 cap, no B2+B3 together (B1 is the bridge), at most one
    140, and a 140 may coexist with at most one 120."""
    t = sum(u["time"] for u in units_list)
    if t > MAX_FC: return False
    blds = set()
    for u in units_list: blds |= u["blds"]
    if 2 in blds and 3 in blds: return False
    n140 = sum(u["n140"] for u in units_list)
    n120 = sum(u["n120"] for u in units_list)
    if n140 > 1: return False
    if n140 >= 1 and n120 > 1: return False
    return True

def _fc_spread(units_list):
    """Travel cost of one chart: building span (heaviest), floor span within each
    building, and number of distinct floor-stops. Lower = tighter / less walking."""
    if not units_list: return 0
    blds = set(); floors_by_bld = {}
    for u in units_list:
        blds |= u["blds"]
        for r in u["rooms"]:
            b = r.get("bld", 0)
            floors_by_bld.setdefault(b, set()).add(r.get("floor", 0))
    fspread = sum(max(fs) - min(fs) for fs in floors_by_bld.values())
    nstops  = sum(len(fs) for fs in floors_by_bld.values())
    return (len(blds) - 1) * 100 + fspread * 10 + nstops * 3

def _fc_travel(charts):
    return sum(_fc_spread(c) for c in charts if c)

def _fc_optimize(units, seed=20240601, restarts=14):
    """Two-phase optimizer for Full Clean.
    Phase 1 — minimize the number of housekeepers: best-fit from several seed
      orders + random restarts, each refined by a move/swap local search that
      escapes greedy local optima (this is what matches the manual HK count).
    Phase 2 — with the housekeeper count fixed, reduce room travel: only moves/
      swaps that lower total building+floor spread WITHOUT increasing the chart
      count are accepted, so charts become tight (same building / nearby floors)
      like the manual schedule. Deterministic for a given input (fixed seed)."""
    import random as _rnd
    rng = _rnd.Random(seed)

    def pack_bestfit(order):
        charts = []
        for u in order:
            best, best_rem = None, 10**9
            for ch in charts:
                if _fc_feasible(ch + [u]):
                    rem = MAX_FC - (sum(x["time"] for x in ch) + u["time"])
                    if rem < best_rem: best_rem, best = rem, ch
            if best is None: charts.append([u])
            else: best.append(u)
        return charts

    # ── Phase 1: fewest charts ───────────────────────────────────────────────
    def _spans_two_bld(chart):
        return len(set(b for u in chart for b in u["blds"])) > 1
    def ls_mincount(charts, iters):
        charts = [c[:] for c in charts if c]
        for _ in range(iters):
            ne = [c for c in charts if c]
            if len(ne) < 2: break
            ne.sort(key=lambda c: sum(u["time"] for u in c))
            src = ne[0] if rng.random() < 0.5 else rng.choice(ne)
            if not src: continue
            u = rng.choice(src); order = ne[:]; rng.shuffle(order); moved = False
            for dst in order:
                if dst is src: continue
                if _fc_feasible(dst + [u]):
                    src.remove(u); dst.append(u); moved = True; break
            if not moved:
                for dst in order:
                    if dst is src: continue
                    for v in dst:
                        if _fc_feasible([x for x in src if x is not u] + [v]) and \
                           _fc_feasible([x for x in dst if x is not v] + [u]):
                            src.remove(u); dst.remove(v); src.append(v); dst.append(u)
                            moved = True; break
                    if moved: break
            charts = [c for c in charts if c]
        return [c for c in charts if c]

    orders = [
        sorted(units, key=lambda u: -u["time"]),
        sorted(units, key=lambda u: (-u["n140"], -u["n120"], -u["time"])),
        sorted(units, key=lambda u: ({3:0,1:1,2:2}.get(min(u["blds"]) if u["blds"] else 1, 9), -u["time"])),
    ]
    candidates = [pack_bestfit(o) for o in orders]
    for _ in range(restarts):
        us = units[:]; rng.shuffle(us)
        candidates.append(pack_bestfit(us))

    best_charts, best_n = None, None
    for c in candidates:
        refined = ls_mincount(c, 2500)
        n = len([ch for ch in refined if ch])
        if best_n is None or n < best_n:
            best_n, best_charts = n, refined
    charts = [c for c in best_charts if c]

    # ── Phase 1.5: un-cross cross-building charts (same count) ────────────────
    # Phase 1 minimizes housekeepers but may leave a chart spanning two buildings
    # (a B1 unit packed into a B2 chart, etc.). Removing such a crossing usually
    # needs a rotation: move the foreign unit into a same-building chart and push
    # that chart's displaced unit onward. We try 2-way swaps first, then 3-way
    # rotations, accepting only changes that reduce the number of crossings while
    # keeping the chart count fixed. Deterministic.
    def _nblds(chart):
        return len(set(b for u in chart for b in u["blds"]))
    def _decross(charts):
        charts = [c[:] for c in charts if c]
        for _ in range(40):
            crossed = [c for c in charts if _nblds(c) > 1]
            if not crossed: break
            improved = False
            for a in crossed:
                # foreign = the units belonging to a's minority building
                cnt = {}
                for u in a:
                    for bd in u["blds"]: cnt[bd] = cnt.get(bd, 0) + 1
                minority = min(set().union(*[u["blds"] for u in a]), key=lambda bd: cnt[bd])
                foreign = [u for u in a if minority in u["blds"]]
                for fu in foreign:
                    # 2-way: swap fu with a unit bu from another chart b
                    for b in charts:
                        if b is a: continue
                        for bu in b:
                            na = [x for x in a if x is not fu] + [bu]
                            nb = [x for x in b if x is not bu] + [fu]
                            if not (_fc_feasible(na) and _fc_feasible(nb)): continue
                            if (_nblds(na) + _nblds(nb)) < (_nblds(a) + _nblds(b)):
                                a.remove(fu); a.append(bu); b.remove(bu); b.append(fu)
                                improved = True; break
                        if improved: break
                    if improved: break
                    # 3-way rotation: a gives fu to b, b gives bu to c, c gives cu to a
                    for b in charts:
                        if b is a: continue
                        if not _fc_feasible(b + [fu]): continue
                        b2 = b + [fu]
                        for bu in b:
                            for c in charts:
                                if c is a or c is b: continue
                                if not _fc_feasible(c + [bu]): continue
                                c2 = c + [bu]
                                for cu in c:
                                    na = [x for x in a if x is not fu] + [cu]
                                    nb = [x for x in b2 if x is not bu]
                                    nc = [x for x in c2 if x is not cu]
                                    if not (_fc_feasible(na) and _fc_feasible(nb) and _fc_feasible(nc)):
                                        continue
                                    before = _nblds(a)+_nblds(b)+_nblds(c)
                                    after  = _nblds(na)+_nblds(nb)+_nblds(nc)
                                    if after < before:
                                        a.remove(fu); a.append(cu)
                                        b.remove(bu); b.append(fu)
                                        c.remove(cu); c.append(bu)
                                        improved = True; break
                                if improved: break
                            if improved: break
                        if improved: break
                    if improved: break
                if improved: break
            if not improved: break
        return [c for c in charts if c]
    charts = [c for c in charts if c]

    # ── Phase 2: same chart count, minimize travel ──────────────────────────
    def ls_travel(charts, iters):
        charts = [c[:] for c in charts if c]
        for _ in range(iters):
            ne = [c for c in charts if c]
            if len(ne) < 2: break
            a, b = rng.sample(ne, 2)
            # move a unit a->b if it lowers combined spread and doesn't empty a
            if len(a) > 1:
                u = rng.choice(a)
                if _fc_feasible(b + [u]):
                    a2 = [x for x in a if x is not u]
                    if a2 and _fc_spread(a2) + _fc_spread(b + [u]) < _fc_spread(a) + _fc_spread(b):
                        a.remove(u); b.append(u); continue
            # swap u<->v if it lowers combined spread
            u = rng.choice(a); v = rng.choice(b)
            na = [x for x in a if x is not u] + [v]
            nb = [x for x in b if x is not v] + [u]
            if _fc_feasible(na) and _fc_feasible(nb) and \
               _fc_spread(na) + _fc_spread(nb) < _fc_spread(a) + _fc_spread(b):
                a.remove(u); a.append(v); b.remove(v); b.append(u)
        return [c for c in charts if c]

    charts = _decross(charts)        # remove gratuitous building-crossings
    charts = ls_travel(charts, 15000)
    return [c for c in charts if c]


def pack_rooms(room_list, svc, can_add_fn, unit_ok_fn):
    if not room_list: return []
    import re as _re2
    for r in room_list:
        r["guest"] = _re2.sub(r'\s+', ' ', r.get("guest","").strip())
    gmap = {}
    for r in room_list: gmap.setdefault(r["guest"],[]).append(r)
    seen, unit_lists = set(), []
    for r in room_list:
        if r["guest"] not in seen:
            seen.add(r["guest"]); unit_lists.append(gmap[r["guest"]])

    # ── DAILY SERVICE (and any non-FC): keep the simple best-fit fill ────────
    # DS has no heavy-room / building constraints and a different cap, so the
    # FC optimizer doesn't apply. Behavior here is unchanged.
    if svc != SVC_FC:
        unit_lists.sort(key=lambda u:(
            u[0].get("bld",0), u[0].get("floor",0),
            -sum(r["time"] for r in u), -len(u),
        ))
        groups = []
        for unit in unit_lists:
            i=best_fit_generic(groups,unit,can_add_fn,True,True)
            if i==-1: i=best_fit_generic(groups,unit,can_add_fn,True,False)
            if i==-1: i=best_fit_generic(groups,unit,can_add_fn,False,False)
            if i>=0: absorb(groups[i],unit)
            else: groups.append(mk(unit,svc))
        return [g for g in groups if g["rooms"]]

    # ── FULL CLEAN: global bin-packing optimizer ────────────────────────────
    # A same-guest cluster that itself breaks the rules (too big for one chart,
    # spans B2+B3, too many heavy rooms) can't sit in one chart. Rather than
    # atomizing it into single rooms — which lets the optimizer scatter a guest's
    # rooms across many housekeepers — we split it into the FEWEST legal
    # sub-clusters, keeping as many of the guest's rooms together as the rules
    # allow (same building, <=380, <=one 140, a 140 with <=one 120). This keeps
    # e.g. a guest's two same-floor rooms on one cart instead of two.
    def _split_into_legal_subclusters(unit):
        # Sort rooms so heavy rooms seed sub-clusters and same building/floor
        # rooms stay adjacent, then greedily fill sub-clusters under the rules.
        rooms_sorted = sorted(unit, key=lambda r: (r.get("bld",0), r.get("floor",0), -r["time"]))
        subs = []   # each: {"rooms":[...],"time","blds","n140","n120"}
        for r in rooms_sorted:
            placed = False
            for s in subs:
                nb = s["blds"] | {r["bld"]}
                if 2 in nb and 3 in nb: continue
                n140 = s["n140"] + (1 if r["time"]==140 else 0)
                n120 = s["n120"] + (1 if r["time"]==120 else 0)
                if s["time"] + r["time"] > MAX_FC: continue
                if n140 > 1: continue
                if n140 >= 1 and n120 > 1: continue
                s["rooms"].append(r); s["time"] += r["time"]
                s["blds"] = nb; s["n140"] = n140; s["n120"] = n120
                placed = True; break
            if not placed:
                subs.append({"rooms":[r],"time":r["time"],"blds":{r["bld"]},
                             "n140":1 if r["time"]==140 else 0,
                             "n120":1 if r["time"]==120 else 0})
        return [s["rooms"] for s in subs]

    placeable = []   # each is a list-of-rooms (a locked cluster OR a legal sub-cluster)
    for unit in unit_lists:
        if unit_ok_fn(unit):
            placeable.append(unit)
        else:
            placeable.extend(_split_into_legal_subclusters(unit))

    # Wrap each placeable cluster with packing metadata.
    units = []
    for rooms in placeable:
        units.append({
            "rooms": rooms,
            "time":  sum(r["time"] for r in rooms),
            "blds":  set(r["bld"] for r in rooms),
            "n140":  sum(1 for r in rooms if r["time"]==140),
            "n120":  sum(1 for r in rooms if r["time"]==120),
        })

    charts = _fc_optimize(units)

    # Materialize charts into the standard group dict via mk().
    groups = []
    for chart in charts:
        chart_rooms = [r for u in chart for r in u["rooms"]]
        if chart_rooms: groups.append(mk(chart_rooms, svc))
    return groups

def _bld(r):   return r.get("bld", 0)
def _flr(r):   return r.get("floor", 0)
def _rnum(r):  return r.get("num", 0)

def _norm_guest(r):
    g = re.sub(r'\s+', ' ', str(r.get("guest","")).strip())
    return g if g.lower() not in {"","unallocated","---","deposit, deposit",
                                  "room, walk","p/u models"} else ""

def _cluster_adjacent_same_guest(rooms):
    """HARD same-guest adjacency rule: rooms that share the SAME building, floor
    AND room-number and belong to the same (real) guest are the same physical
    unit and must never be split across housekeepers. Returns a list of "bundles"
    (each a list of room dicts) — a bundle of >1 is locked together; singles pass
    through as one-room bundles. Bundles are only kept together when they can
    still form a legal chart (<=380, <=one 140, 140+<=one 120); if a guest's
    adjacent rooms are collectively too big for one chart, they're split minimally
    so each piece is chart-legal (a genuine no-option case)."""
    from collections import defaultdict
    by_key = defaultdict(list)
    singles = []
    for r in rooms:
        g = _norm_guest(r)
        if g:
            # key on same physical room: building + floor + room number + guest
            by_key[(_bld(r), _flr(r), _rnum(r), g)].append(r)
        else:
            singles.append([r])
    bundles = []
    for key, grp in by_key.items():
        if len(grp) == 1:
            bundles.append(grp); continue
        # keep the adjacent same-guest rooms together, but if they can't legally
        # share one chart, split into the fewest legal sub-bundles.
        if _chart_feasible(grp):
            bundles.append(grp)
        else:
            cur = []
            for r in sorted(grp, key=lambda x: -x["time"]):
                if cur and _chart_feasible(cur + [r]):
                    cur.append(r)
                elif cur:
                    bundles.append(cur); cur = [r]
                else:
                    cur = [r]
            if cur: bundles.append(cur)
    return bundles + singles

def _chart_feasible(chart, single_building=False):
    """Hard rules for a Full Clean / IH chart (list of room dicts)."""
    times = [r["time"] for r in chart]
    if sum(times) > MAX_FC: return False
    if times.count(140) > 1: return False
    if times.count(140) >= 1 and times.count(120) > 1: return False
    blds = set(_bld(r) for r in chart)
    if 2 in blds and 3 in blds: return False          # B2 and B3 never share
    if single_building and len(blds) > 1: return False
    return True

def _chart_nbld(chart): return len(set(_bld(r) for r in chart))
def _chart_spread(chart):
    if not chart: return 0
    fl = [_flr(r) for r in chart]; nm = [_rnum(r) for r in chart]
    # Weight room-number proximity more (walking down a hall) alongside floor
    # changes, so charts group physically close rooms and cut housekeeper travel.
    return (_chart_nbld(chart)-1)*100 + (max(fl)-min(fl))*10 + (max(nm)-min(nm))*2
def _charts_xb(charts):     return sum(1 for c in charts if _chart_nbld(c) > 1)
def _charts_spread(charts): return sum(_chart_spread(c) for c in charts if c)

def _fc_bestfit(order):
    """Best-fit that prefers not introducing a new building into a chart."""
    charts = []
    for r in order:
        best = None; bkey = None
        for c in charts:
            if _chart_feasible(c + [r]):
                rem = MAX_FC - (sum(x["time"] for x in c) + r["time"])
                intro = _chart_nbld(c + [r]) > _chart_nbld(c)
                key = (1 if intro else 0, rem)
                if bkey is None or key < bkey: bkey = key; best = c
        if best is None: charts.append([r])
        else: best.append(r)
    return charts

def _fc_ls_count(charts, iters, rng, avoid_xb=True):
    """Local search to reduce housekeeper count (move/swap). When avoid_xb, don't
    create a new building-crossing unless the move frees a whole housekeeper."""
    charts = [c[:] for c in charts if c]
    for _ in range(iters):
        ne = [c for c in charts if c]
        if len(ne) < 2: break
        ne.sort(key=lambda c: sum(x["time"] for x in c))
        src = ne[0] if rng.random() < 0.5 else rng.choice(ne)
        if not src: continue
        u = rng.choice(src); order = ne[:]; rng.shuffle(order); moved = False
        for dst in order:
            if dst is src: continue
            if _chart_feasible(dst + [u]):
                frees = (len(src) == 1)
                makes = avoid_xb and _chart_nbld(dst + [u]) > _chart_nbld(dst)
                if frees or not makes:
                    src.remove(u); dst.append(u); moved = True; break
        if not moved:
            for dst in order:
                if dst is src: continue
                for v in dst:
                    if _chart_feasible([x for x in src if x is not u] + [v]) and \
                       _chart_feasible([x for x in dst if x is not v] + [u]):
                        ns = [x for x in src if x is not u] + [v]
                        nd = [x for x in dst if x is not v] + [u]
                        if avoid_xb and ((_chart_nbld(ns) > _chart_nbld(src)) or
                                         (_chart_nbld(nd) > _chart_nbld(dst))): continue
                        src.remove(u); dst.remove(v); src.append(v); dst.append(u)
                        moved = True; break
                if moved: break
        charts = [c for c in charts if c]
    return [c for c in charts if c]

def _fc_ls_tidy(charts, iters, rng):
    """Within a fixed housekeeper count, move/swap to reduce travel (spread)."""
    charts = [c[:] for c in charts if c]
    for _ in range(iters):
        ne = [c for c in charts if c]
        if len(ne) < 2: break
        a, b = rng.sample(ne, 2)
        if len(a) > 1:
            u = rng.choice(a)
            if _chart_feasible(b + [u]):
                a2 = [x for x in a if x is not u]
                if a2 and _chart_spread(a2) + _chart_spread(b + [u]) < _chart_spread(a) + _chart_spread(b):
                    a.remove(u); b.append(u); continue
        u = rng.choice(a); v = rng.choice(b)
        na = [x for x in a if x is not u] + [v]; nb = [x for x in b if x is not v] + [u]
        if _chart_feasible(na) and _chart_feasible(nb) and \
           _chart_spread(na) + _chart_spread(nb) < _chart_spread(a) + _chart_spread(b):
            a.remove(u); a.append(v); b.remove(v); b.append(u)
    return [c for c in charts if c]

def _bundle_to_unit(bundle):
    """Collapse a locked bundle of adjacent same-guest rooms into one composite
    'unit' the packer treats atomically. Carries the sub-rooms in _members."""
    if len(bundle) == 1:
        u = dict(bundle[0]); u["_members"] = bundle; return u
    return {
        "room":  bundle[0]["room"],
        "time":  sum(r["time"] for r in bundle),
        "bld":   bundle[0].get("bld", 0),
        "floor": bundle[0].get("floor", 0),
        "num":   bundle[0].get("num", 0),
        "guest": bundle[0].get("guest", ""),
        "_members": bundle,
    }

def _unpack_units(charts):
    """Expand composite units back into their real room dicts."""
    out = []
    for c in charts:
        rooms = []
        for u in c:
            rooms.extend(u.get("_members", [u]))
        out.append(rooms)
    return out

def solve_full_clean(fc_rooms, seed=20240601, restarts=16):
    """Tidy-first, min-count Full Clean solver. Priority: (1) fewest housekeepers,
    (2) tidiest charts (single-building, contiguous) within that count. Adjacent
    same-guest rooms (same building+floor+room#) are locked together as one unit
    and never split. Returns a list of charts (each a list of room dicts).
    Deterministic (fixed seed)."""
    if not fc_rooms: return []
    import random as _rnd
    rng = _rnd.Random(seed)
    # HARD adjacency rule: bundle adjacent same-guest rooms, then pack bundles.
    bundles = _cluster_adjacent_same_guest(fc_rooms)
    units = [_bundle_to_unit(b) for b in bundles]
    BLD = {3:0, 1:1, 2:2}
    orders = [
        sorted(units, key=lambda r: -r["time"]),
        sorted(units, key=lambda r: (-(r["time"]==140), -(r["time"]==120), -r["time"])),
        sorted(units, key=lambda r: (BLD.get(_bld(r),1), _flr(r), _rnum(r))),
    ]
    cands = [_fc_bestfit(o) for o in orders]
    for _ in range(restarts):
        rr = list(units); rng.shuffle(rr); cands.append(_fc_bestfit(rr))
    # Phase 1: building-aware count minimization
    best = None
    for c in cands:
        r = _fc_ls_count(c, 1500, rng, avoid_xb=True)
        nb = len([x for x in r if x])
        key = (nb, _charts_xb(r), _charts_spread(r))
        if best is None or key < best[0]: best = (key, r)
    nb0 = best[0][0]
    # Phase 2: if crossings were forbidden at a cost, retry allowing them to see
    # whether a lower count is reachable (manual bridges B1 only when it saves a HK)
    for c in cands:
        r = _fc_ls_count(c, 1500, rng, avoid_xb=False)
        nb = len([x for x in r if x])
        if nb < nb0:
            key = (nb, _charts_xb(r), _charts_spread(r))
            if key < best[0]: best = (key, r); nb0 = nb
    charts = [c[:] for c in best[1] if c]
    charts = _fc_ls_tidy(charts, 8000, rng)   # tidy within the locked count
    return _unpack_units(charts)

def solve_ih(ih_rooms, seed=20240601):
    """Pack IH rooms into SINGLE-building charts <=380, keeping a guest's rooms
    together where possible. Returns (kept_charts, leftover_rooms). Charts totalling
    >= IH_KEEP_MIN are kept (inspected by RQS 2); genuine scraps spill to Daily
    Service."""
    if not ih_rooms: return [], []
    BLD = {3:0, 1:1, 2:2}
    pool = sorted(ih_rooms, key=lambda r: (BLD.get(_bld(r),1), r.get("guest",""), _flr(r), _rnum(r)))
    used = [False]*len(pool); charts = []
    for i in range(len(pool)):
        if used[i]: continue
        chart = [pool[i]]; used[i] = True
        while sum(r["time"] for r in chart) < MAX_FC:
            best = None
            for j in range(len(pool)):
                if used[j]: continue
                if not _chart_feasible(chart + [pool[j]], single_building=True): continue
                rj = pool[j]
                gj = rj.get("guest","")
                same_g = 0 if any(r.get("guest","")==gj and gj not in ("","Unallocated")
                                  for r in chart) else 1
                d = min(abs(_flr(r)-_flr(rj))*30 + abs(_rnum(r)-_rnum(rj)) for r in chart)
                key = (same_g, d)
                if best is None or key < best[0]: best = (key, j)
            if best is None: break
            used[best[1]] = True; chart.append(pool[best[1]])
        charts.append(chart)
    keep = []; leftover = []
    for c in charts:
        if sum(r["time"] for r in c) >= IH_KEEP_MIN: keep.append(c)
        else: leftover.extend(c)
    return keep, leftover

def split_daily_service(ds_rooms, extra_rooms=None, cap=DS_CAP):
    """Split Daily Service rooms into charts with a HARD cap of `cap` minutes each
    (fill up to cap, never exceed), by building and contiguity. Any extra_rooms
    (leftover IH) are appended. Leftover rooms that don't fit an existing chart
    open a new one; if there aren't enough housekeepers to cover every chart, the
    later charts simply get a blank housekeeper (assigned manually later)."""
    rooms = list(ds_rooms) + list(extra_rooms or [])
    if not rooms: return []
    BLD = {3:0, 1:1, 2:2}
    rooms = sorted(rooms, key=lambda r: (BLD.get(_bld(r),1), _flr(r), _rnum(r)))
    charts = []; cur = []
    for r in rooms:
        if cur and sum(x["time"] for x in cur) + r["time"] > cap:
            charts.append(cur); cur = []
        cur.append(r)
    if cur: charts.append(cur)
    return charts

def build_all_groups(rooms, priority_hks=None):
    verify_rooms = [r for r in rooms if r.get("verify")]
    rooms        = [r for r in rooms if not r.get("verify")]

    fc_rooms = [r for r in rooms if r.get("service")==SVC_FC]
    ih_rooms = [r for r in rooms if r.get("service")==SVC_IH]
    ds_rooms = [r for r in rooms if r.get("service")==SVC_DS]
    dv_rooms = [r for r in rooms if r.get("service")==SVC_DV]

    # ── Stage 1: regular Full Clean — tidy-first, minimum housekeepers ────────
    # (priority_hks preserved: any rooms pre-claimed by a named housekeeper are
    # packed first via the legacy path, the rest go through the new solver.)
    priority_groups = []
    remaining_fc    = list(fc_rooms)
    priority_hks    = priority_hks or []
    if priority_hks:
        try:    roster = st.session_state.get("hk_roster", {})
        except: roster = {}
        for hk_name in priority_hks:
            home_bld = roster.get(hk_name, {}).get("building", 0)
            pool = sorted(remaining_fc, key=lambda r:(
                0 if r.get("bld",0)==home_bld else 1,
                r.get("floor",0), -r.get("time",0)
            ))
            state = {"rooms":[], "time":0, "c140":0, "c120":0, "used":set()}
            def can_add_p(rooms_to_add, s=state):
                t = sum(r["time"] for r in rooms_to_add)
                if s["time"]+t > MAX_FC: return False
                has140 = any(r["time"]==140 for r in rooms_to_add)
                nc140  = s["c140"]+(1 if has140 else 0)
                nc120  = s["c120"]+sum(1 for r in rooms_to_add if r["time"]==120)
                if nc140 > 1: return False
                if nc140>=1 and nc120>=1 and any(r["time"]>70 for r in rooms_to_add): return False
                cur_blds = set(r.get("bld",0) for r in s["rooms"])
                new_blds = cur_blds | set(r.get("bld",0) for r in rooms_to_add)
                if 2 in new_blds and 3 in new_blds: return False
                return True
            def add_p(rooms_to_add, s=state):
                for r in rooms_to_add:
                    s["rooms"].append(r); s["used"].add(id(r))
                    s["time"] += r["time"]
                    s["c140"] += 1 if r["time"]==140 else 0
                    s["c120"] += 1 if r["time"]==120 else 0
            import re as _re3
            guest_map = {}
            for r in pool:
                g = _re3.sub(r'\s+', ' ', r.get("guest","").strip())
                if g.lower() not in {"","unallocated","---","deposit, deposit","room, walk","p/u models"}:
                    guest_map.setdefault(g,[]).append(r)
            seen2 = set()
            for r in pool:
                if id(r) in state["used"]: continue
                g = _re3.sub(r'\s+', ' ', r.get("guest","").strip())
                if g in seen2: continue
                seen2.add(g)
                unit = guest_map.get(g,[r])
                if any(id(u) in state["used"] for u in unit): continue
                if can_add_p(unit): add_p(unit)
                if state["time"] >= MAX_FC: break
            if state["time"] < MAX_FC:
                for r in sorted(pool, key=lambda r:-r["time"]):
                    if id(r) in state["used"]: continue
                    if can_add_p([r]): add_p([r])
                    if state["time"] >= MAX_FC: break
            if state["time"] < 380:
                gap = MAX_FC - state["time"]
                fill_pool = sorted([r for r in remaining_fc if id(r) not in state["used"]],
                                   key=lambda r:abs(r["time"]-gap))
                for r in fill_pool:
                    if id(r) in state["used"]: continue
                    if can_add_p([r]): add_p([r])
                    if state["time"] >= MAX_FC: break
            if state["time"] < 330:
                for r in sorted(remaining_fc, key=lambda r:-r["time"]):
                    if id(r) in state["used"]: continue
                    if can_add_p([r]): add_p([r])
                    if state["time"] >= MAX_FC: break
            if state["rooms"]:
                grp = mk(state["rooms"], SVC_FC)
                grp["priority_hk"] = hk_name
                priority_groups.append(grp)
                used_ids = {id(r) for r in state["rooms"]}
                remaining_fc = [r for r in remaining_fc if id(r) not in used_ids]

    fc_charts = solve_full_clean(remaining_fc)
    fc_groups_normal = [mk(c, SVC_FC) for c in fc_charts]
    fc_groups = priority_groups + fc_groups_normal

    # ── Stage 2: Full Clean (IH) — packed separately, inspected by RQS 2 ──────
    ih_leftover = []
    ih_groups = []
    if ih_rooms:
        ih_charts, ih_leftover = solve_ih(ih_rooms)
        for c in ih_charts:
            g = mk(c, SVC_IH)
            g["ih_group"] = True
            g["rqs"] = IH_RQS          # RQS 2 inspects all IH charts
            ih_groups.append(g)

    # ── Stage 3: Daily Service — HARD 460-min cap per chart, +leftover IH ──────
    if ds_rooms or ih_leftover:
        ds_charts = split_daily_service(ds_rooms, extra_rooms=ih_leftover)
        ds_groups = [mk(c, SVC_DS) for c in ds_charts]
        for g in ds_groups:
            g["ds_overflow"] = g["time"] > DS_CAP   # shouldn't happen with hard cap
    else:
        ds_groups = []

    if dv_rooms:
        # All Dust n Vac goes to RQS 2 (alongside Daily Service + IH inspection),
        # not the Manager.
        dv_groups = [{"rooms":list(dv_rooms),"time":0,"blds":set(r["bld"] for r in dv_rooms),
                      "floors":set(r.get("floor",0) for r in dv_rooms),"c140":0,"c120":0,
                      "service_type":SVC_DV,"dv_rqs2":True}]
    else:
        dv_groups = []
    # Verify group(s): stayover / P-U Models — no HK, no RQS, flagged for review.
    if verify_rooms:
        verify_groups = [{
            "rooms":list(verify_rooms),
            "time":sum(r.get("time",0) for r in verify_rooms),
            "blds":set(r["bld"] for r in verify_rooms),
            "floors":set(r.get("floor",0) for r in verify_rooms),
            "c140":0,"c120":0,"service_type":SVC_FC,
            "verify_group":True,
        }]
    else:
        verify_groups = []
    # Sequencing: Full Clean (regular + IH) first, then Daily Service, then DV.
    return fc_groups + ih_groups + ds_groups + dv_groups + verify_groups

# ══════════════════════════════════════════════════════════════════════════════
#  STAFF ASSIGNMENT
# ══════════════════════════════════════════════════════════════════════════════
def assign_hk_building_aware(groups, present_hk, roster):
    pool = {1:[], 2:[], 3:[]}
    for n in present_hk:
        b = roster.get(n,{}).get("building",0)
        if b in pool: pool[b].append(n)
    available = {1:list(pool[1]), 2:list(pool[2]), 3:list(pool[3])}
    assignment = {}; used = set()
    def hk_can_take(hk_bld, group_blds, is_ds=False):
        # Daily Service: housekeepers may wheel carts across all buildings,
        # so the B2<->B3 block does NOT apply. Full Clean keeps the block.
        if is_ds: return True
        for gb in group_blds:
            if hk_bld==2 and gb==3: return False
            if hk_bld==3 and gb==2: return False
        return True
    # Which buildings a housekeeper from building X is allowed to cover (FC).
    # Movement rule: B1<->B2 ok, B1<->B3 ok, B2<->B3 blocked.
    ADJ = {1:[1,2,3], 2:[2,1], 3:[3,1]}
    def find_hk(group_blds, is_ds=False):
        # A Full Clean group spanning BOTH B2 and B3 is structurally impossible
        # for one housekeeper (B2<->B3 is blocked) — never assign it.
        if not is_ds and (2 in group_blds and 3 in group_blds):
            return "⚠️ No HK available"
        primary = min(group_blds) if group_blds else 1
        # 1) Try a housekeeper whose home building IS the group's primary building.
        for hk in list(available.get(primary,[])):
            if hk_can_take(roster.get(hk,{}).get("building",0), group_blds, is_ds):
                available[primary].remove(hk); return hk
        # 2) Borrow from an ADJACENT allowed building (or any, for DS).
        adj_order = [1,2,3] if is_ds else ADJ.get(primary, [1,2,3])
        for b in adj_order:
            for hk in list(available.get(b,[])):
                if hk_can_take(roster.get(hk,{}).get("building",0), group_blds, is_ds):
                    available[b].remove(hk); return hk
        # 3) Any remaining present housekeeper who can legally take the group.
        for b in [1,2,3]:
            for hk in list(available.get(b,[])):
                if hk_can_take(roster.get(hk,{}).get("building",0), group_blds, is_ds):
                    available[b].remove(hk); return hk
        # 3.5) SHORTAGE fallback. When home/adjacent housekeepers are exhausted,
        #      a housekeeper may be moved cross-building to cover a group, as long
        #      as the GROUP itself spans only an allowed combination — B1&2 or B1&3
        #      (or a single building), NEVER B2&3. This relaxes the per-housekeeper
        #      home-building rule on busy days while keeping the hard B2<->B3 block.
        group_spans_b2b3 = (2 in group_blds and 3 in group_blds)
        if not group_spans_b2b3:
            for b in [1,2,3]:
                if available.get(b):
                    return available[b].pop(0)
        # 4) Truly exhausted — leave clearly unassigned (do NOT reuse a name).
        return "⚠️ No HK available"
    # Priority HKs first
    for g in groups:
        if g.get("verify_group"):       # never assign verify groups
            assignment[g["label"]] = ""; continue
        phk = g.get("priority_hk","")
        if not phk: continue
        if g.get("dv_rqs2"): assignment[g["label"]]=""; continue  # DV -> RQS2 inspector
        for b in [1,2,3]:
            if phk in available.get(b,[]):
                available[b].remove(phk); break
        assignment[g["label"]] = phk; used.add(phk)
    # Everyone else — assign the most CONSTRAINED groups first so they get the
    # scarce building-specific housekeepers. Order: Full Clean (strict building
    # rule) → Dust n Vac → Daily Service (flexible, can take any HK).
    def _order(g):
        st_ = g.get("service_type","")
        return {SVC_FC:0, SVC_IH:1, SVC_DV:2, SVC_DS:3}.get(st_, 4)
    for g in sorted(groups, key=_order):
        if g["label"] in assignment: continue
        if g.get("verify_group"):
            assignment[g["label"]] = ""; continue
        # Dust n Vac is carried by RQS 2 (inspector), not a housekeeper — leave the
        # housekeeper field blank here; assign_inspectors puts it on RQS 2.
        if g.get("dv_rqs2"): assignment[g["label"]]=""; continue
        is_ds = (g.get("service_type") == SVC_DS)
        matched = find_hk(g.get("blds",{1}), is_ds)
        assignment[g["label"]] = matched
        if matched and not matched.startswith("⚠️"): used.add(matched)
    return assignment, used

def _primary_bld(g): return min(g["blds"]) if g["blds"] else 0
def _group_complexity(g): return sum(r.get("time",70)/70 for r in g.get("rooms",[]))
def _batch_complexity(batch): return sum(_group_complexity(g) for g in batch)
def _insp_travel_score(batch):
    # Travel cost = buildings visited + floors visited within those buildings,
    # plus the vertical spread (how many floors apart the highest and lowest
    # rooms are). Keeping an inspector on one floor — or a tight floor band —
    # scores lowest.
    blds=set(); cross=0
    floor_keys=set()      # distinct (building, floor) stops
    floors_by_bld={}
    for g in batch:
        blds |= g["blds"]
        if len(g["blds"])>1: cross += len(g["blds"])-1
        for b in g["blds"]:
            for f in (g.get("floors") or {0}):
                floor_keys.add((b,f))
                floors_by_bld.setdefault(b,set()).add(f)
    # Vertical spread within each building (max floor - min floor)
    spread=0
    for b,fs in floors_by_bld.items():
        if fs: spread += (max(fs)-min(fs))
    # Horizontal spread: how far apart the room numbers are within each building
    # (walking down a long hall). Grouping physically close rooms cuts RQS travel.
    nums_by_bld={}
    for g in batch:
        for b in g["blds"]:
            for r in g.get("rooms",[]):
                if r.get("bld")==b:
                    nums_by_bld.setdefault(b,[]).append(r.get("num",0))
    hspread=0
    for b,ns in nums_by_bld.items():
        if ns: hspread += (max(ns)-min(ns))
    # Weights: building hops are most expensive, then number of distinct
    # floor-stops, then how far apart those floors are. A batch that spans all
    # THREE buildings is very hard to inspect, so it gets a steep extra penalty
    # on top of the linear building cost — we want the optimizer to treat a
    # 3-building inspector as nearly forbidden.
    nbld = len(blds)
    three_bld_penalty = 400 if nbld >= 3 else 0
    return nbld*12 + three_bld_penalty + cross*4 + len(floor_keys)*3 + spread*2 + hspread
def _batch_heavy(batch):
    """Count of big rooms (120/140 min) across a batch — used to spread the
    hard-to-inspect rooms evenly across inspectors."""
    return sum(1 for g in batch for r in g.get("rooms",[]) if r.get("time",70) >= 120)
def _is_heavy_chart(g):
    """A housekeeper's chart is 'heavy' (hard to inspect) when it's loaded with
    big rooms — e.g. 120+120+120 or 140+120+70. Defined as 2+ big rooms AND a
    total at/above 330 min."""
    big = sum(1 for r in g.get("rooms",[]) if r.get("time",70) >= 120)
    return big >= 2 and g.get("time",0) >= 330
def _batch_heavy_charts(batch):
    return sum(1 for g in batch if _is_heavy_chart(g))
def _insp_combined_score(batches):
    tt = sum(_insp_travel_score(b) for b in batches)
    nonempty = [b for b in batches if b]
    if len(nonempty) < 2: return tt
    cx = [_batch_complexity(b)     for b in nonempty]
    hv = [_batch_heavy(b)          for b in nonempty]
    hc = [_batch_heavy_charts(b)   for b in nonempty]
    # Count inspectors forced across all 3 buildings — this is the worst case
    # for an inspector and must be avoided even at the cost of heavy-work
    # balance. Each such batch adds an overriding penalty that dwarfs the
    # balance terms, so the optimizer will almost always restructure to remove
    # a 3-building inspector before worrying about heavy-chart fairness.
    three_bld_batches = sum(1 for b in nonempty
                            if len(set().union(*[g["blds"] for g in b])) >= 3)
    THREE_BLD = three_bld_batches * 10000
    # An inspector must never be sent between Building 2 and Building 3 — they are
    # at opposite ends with Building 1 as the only bridge, so covering both means
    # walking the entire property. Penalize any batch spanning B2 and B3 as hard
    # as a 3-building batch.
    b2b3_batches = sum(1 for b in nonempty
                       if {2,3}.issubset(set().union(*[g["blds"] for g in b])))
    B2B3 = b2b3_batches * 10000
    # Balance terms, in priority order (below the building overrides):
    #  1) heavy-CHART spread — no inspector gets all the 120+120+120 charts.
    #  2) heavy-ROOM spread — even count of individual 120/140 rooms.
    #  3) travel (building + floor aware).
    #  4) overall complexity spread — tie-breaker.
    return (THREE_BLD + B2B3
            + (max(hc)-min(hc))*14
            + (max(hv)-min(hv))*8
            + tt*2
            + (max(cx)-min(cx)))

def assign_inspectors(groups, present_insp, per, rqs1, rqs2):
    # Verify groups (stayover / P-U Models) never get an inspector.
    verify_groups = [g for g in groups if g.get("verify_group")]
    for g in verify_groups: g["inspector"] = ""
    groups = [g for g in groups if not g.get("verify_group")]
    fc_groups = [g for g in groups if g.get("service_type")==SVC_FC]
    ih_groups = [g for g in groups if g.get("service_type")==SVC_IH]
    ds_groups = [g for g in groups if g.get("service_type")==SVC_DS]
    dv_groups = [g for g in groups if g.get("service_type")==SVC_DV]
    inspectors=[]; assigned_names=set()

    # IH groups are always inspected by RQS 2 (regardless of FC/DS load).
    for g in ih_groups:
        g["inspector"] = rqs2 or IH_RQS

    def units(grp_list):  # total rooms across a list of groups
        return sum(len(g["rooms"]) for g in grp_list)

    # ── Dedicated FC inspectors = present inspectors who are NOT rqs1/rqs2 ────
    # These are used FIRST for Full Clean. RQS1/RQS2 only step in for FC when
    # the dedicated inspectors can't cover everything.
    fc_inspectors = [n for n in present_insp if n not in (rqs1, rqs2)]

    # ── Assign dedicated FC inspectors to FC groups first ────────────────────
    fc_sorted=sorted(fc_groups, key=lambda g:(
        _primary_bld(g),
        min(g.get("floors",{0})) if g.get("floors") else 0,
        min(r.get("num",0) for r in g["rooms"]) if g["rooms"] else 0
    ))
    # How many FC batches can the dedicated inspectors cover?
    n_dedicated = len(fc_inspectors)
    coverable   = n_dedicated * per   # FC groups the dedicated inspectors can take
    dedicated_fc = fc_sorted[:coverable]
    leftover_fc  = fc_sorted[coverable:]   # only these need RQS1/RQS2 help

    batches=[dedicated_fc[i:i+per] for i in range(0,len(dedicated_fc),per)]
    # Balance batches to reduce cross-building travel
    improved=True; max_iter=len(batches)*per*2 if batches else 0; iters=0
    while improved and iters<max_iter:
        improved=False; iters+=1
        for bi in range(len(batches)):
            for bj in range(bi+1,len(batches)):
                for gi,ga in enumerate(batches[bi]):
                    for gj,gb in enumerate(batches[bj]):
                        new_bi=batches[bi][:gi]+[gb]+batches[bi][gi+1:]
                        new_bj=batches[bj][:gj]+[ga]+batches[bj][gj+1:]
                        if _insp_combined_score([new_bi,new_bj])<_insp_combined_score([batches[bi],batches[bj]]):
                            batches[bi],batches[bj]=new_bi,new_bj; improved=True; break
                    if improved: break
                if improved: break
    fc_inspectors_q = list(fc_inspectors)
    for batch in batches:
        if not batch: continue
        name=fc_inspectors_q.pop(0) if fc_inspectors_q else f"Inspector {len(inspectors)+1}"
        blds=sorted(set(b for g in batch for b in g["blds"]))
        cx=_batch_complexity(batch)
        entry={"id":len(inspectors)+1,"name":name,"role":"FC",
               "groups":[g["label"] for g in batch],"buildings":blds,
               "travel_warning":len(blds)>2,"heavy_warning":cx>15,"complexity":round(cx,1)}
        for g in batch: g["inspector"]=name
        inspectors.append(entry); assigned_names.add(name)

    # ── RQS role assignment (per operations policy) ──────────────────────────
    #   • RQS 2 carries Daily Service + ALL Dust n Vac, and inspects IH.
    #   • RQS 1 is NOT auto-assigned any rooms — left free for manual assignment
    #     later based on how the day goes.
    #   • Leftover Full Clean that dedicated inspectors can't cover opens extra
    #     inspector slots (never dumped on RQS 1).
    fc_shortage = len(leftover_fc) > 0

    # RQS 2 shares leftover FC only if there genuinely aren't enough inspectors,
    # but its primary load is DS + DV (+ IH already assigned above).
    rqs2_fc_groups = []
    if fc_shortage and rqs2:
        budget = 6
        for g in sorted(leftover_fc, key=lambda g:(len(g["rooms"]), _primary_bld(g))):
            if len(g["rooms"]) <= budget:
                rqs2_fc_groups.append(g); budget -= len(g["rooms"])
            if budget <= 0: break
        leftover_fc = [g for g in leftover_fc if g not in rqs2_fc_groups]

    if (ds_groups or dv_groups or rqs2_fc_groups) and rqs2:
        r2_groups = ds_groups + dv_groups + rqs2_fc_groups
        blds=sorted(set(b for g in r2_groups for b in g["blds"]))
        entry={"id":len(inspectors)+1,"name":rqs2,"role":"RQS2",
               "groups":[g["label"] for g in r2_groups],"buildings":blds}
        for g in r2_groups: g["inspector"]=rqs2
        inspectors.append(entry); assigned_names.add(rqs2)

    # RQS 1: intentionally left with NO auto-assigned rooms.

    # Any leftover FC still unassigned → extra inspector slots (not RQS 1).
    while leftover_fc:
        batch = leftover_fc[:per]; leftover_fc = leftover_fc[per:]
        name = f"Inspector {len(inspectors)+1}"
        blds=sorted(set(b for g in batch for b in g["blds"]))
        cx=_batch_complexity(batch)
        entry={"id":len(inspectors)+1,"name":name,"role":"FC",
               "groups":[g["label"] for g in batch],"buildings":blds,
               "travel_warning":len(blds)>2,"heavy_warning":cx>15,"complexity":round(cx,1)}
        for g in batch: g["inspector"]=name
        inspectors.append(entry)

    # Safety net: if RQS 2 wasn't present, any DV without an inspector falls back
    # to RQS 2's label so it's never silently dropped.
    for g in dv_groups:
        if not g.get("inspector"): g["inspector"] = rqs2 or IH_RQS
    return inspectors

# ══════════════════════════════════════════════════════════════════════════════
#  HTML BUILDERS
# ══════════════════════════════════════════════════════════════════════════════
def _rgba_a(rgba: str, a) -> str:
    """Return the same rgba color with a different alpha. Safe on any input."""
    m = re.match(r"rgba\((\d+),\s*(\d+),\s*(\d+)", str(rgba))
    if not m: return rgba
    return f"rgba({m.group(1)},{m.group(2)},{m.group(3)},{a})"

def group_card_html(g, idx):
    svc = g.get("service_type", SVC_FC)
    cap = MAX_DS if svc==SVC_DS else MAX_FC
    pct = min(int(g["time"]/max(cap,1)*100), 100)
    is_verify = g.get("verify_group", False)

    # Color per service type. In the formal light theme these are muted,
    # professional tones with soft (near-flat) accent bars and no neon glow.
    if _IS_LIGHT:
        SVC_COLORS = {
            SVC_FC: {"accent":"#2563a8","glow":"rgba(37,99,168,.14)","bar":"#2563a8","badge_bg":"rgba(37,99,168,.10)","badge_txt":"#1d4e86"},
            SVC_IH: {"accent":"#6d5bb5","glow":"rgba(109,91,181,.14)","bar":"#6d5bb5","badge_bg":"rgba(109,91,181,.10)","badge_txt":"#574699"},
            SVC_DS: {"accent":"#0f766e","glow":"rgba(15,118,110,.14)","bar":"#0f766e","badge_bg":"rgba(15,118,110,.10)","badge_txt":"#0c5d56"},
            SVC_DV: {"accent":"#b45309","glow":"rgba(180,83,9,.14)","bar":"#b45309","badge_bg":"rgba(180,83,9,.10)","badge_txt":"#8f420a"},
        }
    else:
        SVC_COLORS = {
            SVC_FC: {"accent":"#6366f1","glow":"rgba(99,102,241,.45)","bar":"linear-gradient(90deg,#6366f1,#818cf8)","badge_bg":"rgba(99,102,241,.18)","badge_txt":"#a5b4fc"},
            SVC_IH: {"accent":"#8b5cf6","glow":"rgba(139,92,246,.45)","bar":"linear-gradient(90deg,#8b5cf6,#a78bfa)","badge_bg":"rgba(139,92,246,.18)","badge_txt":"#c4b5fd"},
            SVC_DS: {"accent":"#14b8a6","glow":"rgba(20,184,166,.4)","bar":"linear-gradient(90deg,#14b8a6,#2dd4bf)","badge_bg":"rgba(20,184,166,.15)","badge_txt":"#5eead4"},
            SVC_DV: {"accent":"#f59e0b","glow":"rgba(245,158,11,.4)","bar":"linear-gradient(90deg,#f59e0b,#fbbf24)","badge_bg":"rgba(245,158,11,.15)","badge_txt":"#fcd34d"},
        }
    c = SVC_COLORS.get(svc, SVC_COLORS[SVC_FC])
    # Verify groups use a distinct warning palette (muted in light mode).
    if is_verify:
        if _IS_LIGHT:
            c = {"accent":"#be123c","glow":"rgba(190,18,60,.14)","bar":"#be123c",
                 "badge_bg":"rgba(190,18,60,.10)","badge_txt":"#9f1239"}
        else:
            c = {"accent":"#f43f5e","glow":"rgba(244,63,94,.45)",
                 "bar":"linear-gradient(90deg,#f43f5e,#fb7185)",
                 "badge_bg":"rgba(244,63,94,.18)","badge_txt":"#fda4af"}
    ac = c["accent"]; glow = c["glow"]; bar = c["bar"]

    hk_raw = g.get("housekeeper","") or ""
    no_hk  = not hk_raw or hk_raw.startswith("⚠️")
    if is_verify:
        unassigned_badge = ""   # verify groups intentionally have no HK badge
        hk_raw = ""
    elif no_hk:
        unassigned_badge = f'<span style="background:rgba(244,63,94,.2);color:#fb7185;border-radius:5px;padding:1px 8px;font-size:.66rem;font-weight:700;border:1px solid rgba(244,63,94,.35);letter-spacing:.03em">⚠ NO HK</span>'
        hk_raw = hk_raw.replace("⚠️ ","") if hk_raw else "Unassigned"
    else:
        unassigned_badge = ""

    hk      = e(hk_raw or "—")
    insp    = e(g.get("inspector","") or "—")
    _blds_raw = g.get("blds", set())
    if isinstance(_blds_raw, str):
        _blds_raw = [int(x) for x in re.findall(r'\d+', _blds_raw)]
    bld_str = " · ".join(f"Bldg {b}" for b in sorted(set(_blds_raw)))

    def badge(txt, bg, clr, border="transparent"):
        return f'<span style="background:{bg};color:{clr};border:1px solid {border};border-radius:5px;padding:1px 8px;font-size:.66rem;font-weight:600;letter-spacing:.02em">{txt}</span>'

    if is_verify:
        svc_badge = badge("⚠ VERIFY & ASSIGN","rgba(244,63,94,.2)","#fda4af","rgba(244,63,94,.4)")
    else:
        svc_badge = badge(svc, c["badge_bg"], c["badge_txt"], _rgba_a(c["glow"], ".25"))
    overflow_badge = badge("⚠ DS Overflow","rgba(245,158,11,.15)","#fcd34d","rgba(245,158,11,.3)") if g.get("ds_overflow") else ""
    priority_badge = badge("⭐ Priority","rgba(234,179,8,.15)","#fde047","rgba(234,179,8,.3)") if g.get("priority_hk") else ""
    cross_badge    = badge("Cross-bld","rgba(168,85,247,.15)","#d8b4fe","rgba(168,85,247,.3)") if (g.get("cross_bld") and not is_verify) else ""

    t_col = "#4ade80" if pct<=87 else ("#fbbf24" if pct<=95 else "#f87171")

    rows = ""
    for i, r in enumerate(g["rooms"]):
        notes_lower  = r.get("notes","").lower()
        is_stayover  = "stayover" in notes_lower or "stay over" in notes_lower
        row_bg = "rgba(34,211,238,.06)" if (r.get("uncertain") and is_stayover) else                  "rgba(245,158,11,.06)" if r.get("uncertain") else "transparent"
        pet_badge  = '<span style="background:rgba(244,63,94,.15);color:#fb7185;border-radius:4px;padding:1px 6px;font-size:.64rem;font-weight:600">🐾</span>' if r.get("pet") else ""
        late_co    = e(r.get("late_checkout",""))
        late_badge2= f'<span style="background:rgba(245,158,11,.15);color:#fcd34d;border-radius:4px;padding:1px 6px;font-size:.64rem;font-weight:600">⏰ {late_co}</span>' if late_co else ""
        delay = f"{i*0.04:.2f}s"
        rows += f"""<tr style="background:{row_bg};border-bottom:1px solid {_C["row_br"]};animation:rowIn .3s {delay} both">
          <td style="font-family:'DM Mono',monospace;font-size:.76rem;font-weight:500;color:{ac};padding:8px 10px;white-space:nowrap">{e(r.get("room",""))}</td>
          <td class="m-hide" style="padding:8px 10px;color:#64748b;font-size:.75rem">B{r.get("bld","")}</td>
          <td style="padding:8px 10px;color:{_C["txt"]};font-size:.78rem;font-weight:500;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{e(r.get("guest",""))}</td>
          <td class="m-hide" style="padding:8px 10px;color:{_C["txt2"]};font-size:.73rem">{e(r.get("service",""))}</td>
          <td style="padding:8px 10px;font-family:'DM Mono',monospace;font-weight:500;color:{_C["txt"]};font-size:.76rem">{"—" if r.get("time",0)==0 else str(r.get("time",""))+"m"}</td>
          <td style="padding:8px 10px">{pet_badge}</td>
          <td style="padding:8px 10px">{late_badge2}</td>
        </tr>"""

    lbl = e(g.get("label",""))
    th  = f"padding:6px 10px;text-align:left;font-family:'DM Mono',monospace;font-size:.6rem;font-weight:500;text-transform:uppercase;letter-spacing:.1em;color:{_C["txt3"]};background:{_C["th_bg"]};border-bottom:1px solid {_C["row_br"]}"

    # Verify groups: distinct title, pill text, hidden HK/RQS meta + time meter
    if is_verify:
        title_text   = "⚠ Unsure — verify &amp; assign"
        pill_text    = "VERIFY"
        header_bg    = "linear-gradient(90deg,rgba(244,63,94,.1),transparent)"
        meta_line    = (f'<div style="font-size:.71rem;color:{_C["txt2"]};margin-top:3px;'
                        f'font-family:\'DM Mono\',monospace">{bld_str} &nbsp;·&nbsp; '
                        f'<span style="color:#fda4af">no housekeeper / RQS — assign manually</span></div>')
        time_meter   = ""
    else:
        title_text   = f"Group {lbl}"
        pill_text    = lbl
        header_bg    = "linear-gradient(90deg,rgba(99,102,241,.06),transparent)"
        meta_line    = (f'<div style="font-size:.71rem;color:{_C["txt2"]};margin-top:3px;font-family:\'DM Mono\',monospace">'
                        f'{bld_str} &nbsp;·&nbsp; <span style="color:{_C["txt3"]}">🧑</span> {hk} &nbsp;·&nbsp; '
                        f'<span style="color:{_C["txt3"]}">🔍</span> {insp}</div>')
        time_meter   = (f'<div style="display:flex;align-items:center;gap:8px;flex-shrink:0">'
                        f'<span style="font-family:\'DM Mono\',monospace;font-size:.82rem;font-weight:500;color:{ac};'
                        f'text-shadow:0 0 8px {glow}">{g.get("time","")} <span style="color:#475569;font-size:.7rem">/ {cap}m</span></span>'
                        f'<div style="background:rgba(255,255,255,.06);border-radius:99px;height:5px;width:72px;overflow:hidden;border:1px solid rgba(255,255,255,.06)">'
                        f'<div style="background:{bar};width:{pct}%;height:5px;border-radius:99px;box-shadow:0 0 6px {glow};transition:width .4s"></div>'
                        f'</div></div>')

    return f"""<!DOCTYPE html><html><head>{SHARED_CSS}</head><body>
<div style="border-radius:12px;overflow:hidden;border:1px solid {glow};
            background:{_C["card_bg"]};
            backdrop-filter:blur(16px);margin-bottom:4px;
            box-shadow:{_C["card_sh"]};
            animation:glassIn .35s cubic-bezier(.16,1,.3,1) both">
  <!-- Card header -->
  <div style="padding:10px 14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;
              border-bottom:1px solid rgba(99,102,241,.1);
              background:{header_bg}">
    <!-- Label pill with glow -->
    <div style="background:{ac};color:#fff;border-radius:6px;padding:4px 10px;
                font-family:'Syne',sans-serif;font-weight:800;font-size:.78rem;
                white-space:nowrap;flex-shrink:0;letter-spacing:.04em;
                box-shadow:0 0 12px {glow},0 0 24px {_rgba_a(glow, ".18")}">
      {pill_text}
    </div>
    <!-- Title + badges -->
    <div style="flex:1;min-width:0">
      <div style="display:flex;align-items:center;gap:5px;flex-wrap:wrap">
        <span style="font-family:'Syne',sans-serif;font-weight:700;font-size:.88rem;color:{_C["txt"]}">{title_text}</span>
        {svc_badge} {overflow_badge} {priority_badge} {cross_badge} {unassigned_badge}
      </div>
      {meta_line}
    </div>
    <!-- Time meter -->
    {time_meter}
  </div>
  <!-- Room table -->
  <table>
    <thead><tr>
      <th style="{th}">Room</th><th class="m-hide" style="{th}">Bld</th><th style="{th}">Guest</th>
      <th class="m-hide" style="{th}">Service</th><th style="{th}">Time</th>
      <th style="{th}">Pet</th><th style="{th}">Late Out</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <!-- Footer -->
  <div style="background:{_C["foot_bg"]};padding:6px 12px;display:flex;justify-content:space-between;
              border-top:1px solid {_C["row_br"]};font-family:'DM Mono',monospace;font-size:.68rem;color:{_C["txt3"]}">
    <span>{len(g["rooms"])} rooms &nbsp;·&nbsp; {g.get("c120",0)}×120 &nbsp;·&nbsp; {g.get("c140",0)}×140</span>
    <span style="color:{t_col};font-weight:500">{g.get("time","")}m used</span>
  </div>
</div></body></html>"""

def staff_table_html(rows, cols, cell_fns, row_bg_fn):
    th_s = ("padding:8px 12px;text-align:left;font-family:'DM Mono',monospace;"
            "font-size:.6rem;font-weight:500;text-transform:uppercase;letter-spacing:.1em;"
            f"color:{_C['txt3']};background:{_C['th_bg']};border-bottom:1px solid {_C['row_br']}")
    ths  = "".join(f'<th style="{th_s}">{e(c)}</th>' for c in cols)
    body = ""
    for i, row in enumerate(rows):
        bg  = row_bg_fn(row)
        # Map known status backgrounds to theme-appropriate tints
        if bg == "#f0fdf4": bg = "rgba(20,184,166,.07)" if _IS_LIGHT else "rgba(20,184,166,.08)"
        elif bg == "#fefce8": bg = "rgba(245,158,11,.06)"
        elif bg not in ("transparent","","#fff"): bg = "rgba(99,102,241,.05)"
        elif bg in ("#fff","") : bg = "transparent"
        delay = f"{i*0.03:.2f}s"
        tds = "".join(
            f'<td style="padding:8px 12px;border-bottom:1px solid {_C["row_br"]};'
            f'vertical-align:middle;background:{bg};animation:rowIn .3s {delay} both">{fn(row)}</td>'
            for fn in cell_fns)
        body += f"<tr>{tds}</tr>"
    return f"""<!DOCTYPE html><html><head>{SHARED_CSS}</head><body>
<div style="border-radius:12px;overflow:hidden;border:1px solid {_C['card_br']};
            background:{_C['tbl_bg']};backdrop-filter:blur(12px);
            box-shadow:{_C['card_sh']}">
<table style="width:100%;border-collapse:collapse;font-size:.8rem">
  <thead><tr>{ths}</tr></thead><tbody>{body}</tbody>
</table></div></body></html>"""

def insp_card_html(insp, fg, color):
    name  = e(insp.get("name",""))
    role  = insp.get("role","FC")
    blds  = insp.get("buildings",[])
    BLD_NEON = {
        1: ("rgba(99,102,241,.2)","#a5b4fc","rgba(99,102,241,.4)"),
        2: ("rgba(20,184,166,.18)","#5eead4","rgba(20,184,166,.35)"),
        3: ("rgba(245,158,11,.18)","#fcd34d","rgba(245,158,11,.35)"),
    }
    bld_tags_parts = []
    for b in blds:
        bg3, txt3, bdr3 = BLD_NEON.get(b, ("rgba(99,99,99,.15)","#94a3b8","rgba(99,99,99,.3)"))
        bld_tags_parts.append(
            f'<span style="background:{bg3};color:{txt3};border-radius:5px;padding:2px 8px;'
            f'font-family:\'DM Mono\',monospace;font-size:.65rem;font-weight:500;margin-right:4px;'
            f'border:1px solid {bdr3}">Bldg {b}</span>'
        )
    bld_tags = "".join(bld_tags_parts)
    role_map = {
        "RQS1":("rgba(245,158,11,.18)","#fcd34d","RQS1 · DV"),
        "RQS2":("rgba(20,184,166,.18)","#5eead4","RQS2 · DS"),
        "FC":  ("rgba(99,102,241,.18)","#a5b4fc","Full Clean"),
    }
    rbg,rtxt,rlbl = role_map.get(role,("rgba(99,99,99,.1)","#94a3b8",role))
    role_badge = (f'<span style="background:{rbg};color:{rtxt};border-radius:5px;'
                  f'padding:2px 8px;font-family:\'DM Mono\',monospace;font-size:.65rem;font-weight:500;margin-left:6px">{rlbl}</span>')
    heavy_warn = (f'<span style="background:rgba(244,63,94,.15);color:#fb7185;border-radius:5px;'
                  f'padding:2px 8px;font-size:.66rem;font-weight:600;margin-left:5px">'
                  f'🔴 Heavy {insp.get("complexity",0)}pts</span>') if insp.get("heavy_warning") else ""
    pills = ""; total_t = 0
    for gl in insp["groups"]:
        gobj = next((g for g in fg if g["label"]==gl), None)
        if not gobj: continue
        ac2  = "#6366f1" if gobj.get("service_type")==SVC_FC else ("#14b8a6" if gobj.get("service_type")==SVC_DS else "#f59e0b")
        hk   = e(gobj.get("housekeeper","") or f"Grp {gl}")
        total_t += gobj.get("time",0)
        pills += (f'<span style="display:inline-block;background:rgba(99,102,241,.08);'
                  f'border:1px solid rgba(99,102,241,.25);border-radius:20px;'
                  f'padding:3px 10px;font-size:.73rem;margin:2px 2px;">'
                  f'<span style="font-family:\'DM Mono\',monospace;font-weight:500;color:{ac2};font-size:.72rem">{gl}</span>'
                  f' <span style="color:#64748b">·</span>'
                  f' <span style="color:{_C["txt"]}">{hk}</span></span>')
    return f"""<!DOCTYPE html><html><head>{SHARED_CSS}</head><body>
<div style="border-radius:12px;padding:14px 16px;
            border:1px solid {color}44;
            background:{_C['card_bg']};
            backdrop-filter:blur(16px);
            box-shadow:{_C['card_sh']},0 0 20px {color}18">
  <div style="display:flex;align-items:center;flex-wrap:wrap;gap:5px;margin-bottom:8px">
    <span style="font-family:'Syne',sans-serif;font-weight:700;font-size:.9rem;
                 color:{color}">🔍 {name}</span>
    {role_badge}{heavy_warn}
  </div>
  <div style="margin-bottom:8px;display:flex;flex-wrap:wrap;gap:4px">{bld_tags}</div>
  <div style="line-height:1.8">{pills or f'<span style="color:{_C["txt3"]};font-family:\'DM Mono\',monospace;font-size:.77rem">— no groups —</span>'}</div>
  <div style="margin-top:8px;font-family:'DM Mono',monospace;font-size:.67rem;color:{_C['txt3']};
              border-top:1px solid {_C['row_br']};padding-top:6px">
    {len(insp["groups"])} groups &nbsp;·&nbsp; {total_t} min
  </div>
</div></body></html>"""

# ══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    _cu = auth.current_user()
    _ac, _bg = auth.ROLE_COLORS.get(_cu["role"], ("#6366f1","rgba(99,102,241,.15)"))
    st.markdown(f"""
<div style="background:rgba(99,102,241,.1);border:1px solid rgba(99,102,241,.25);
            border-radius:10px;padding:10px 14px;display:flex;justify-content:space-between;
            align-items:center;margin-bottom:10px;
            box-shadow:0 0 16px rgba(99,102,241,.1)">
  <div>
    <div style="font-family:'Syne',sans-serif;font-weight:700;font-size:.85rem;
                color:#a5b4fc">{_cu["username"]}</div>
    <div style="font-family:'DM Mono',monospace;font-size:.65rem;color:#475569;
                text-transform:uppercase;letter-spacing:.08em">{_cu["role"].title()}</div>
  </div>
  <span style="font-size:1.3rem;opacity:.8">{"👑" if _cu["role"]=="admin" else "🔍" if _cu["role"]=="rqs" else "🧑‍🔧"}</span>
</div>""", unsafe_allow_html=True)
    if st.button("Sign Out", key="btn_logout", use_container_width=True):
        auth.logout(); st.rerun()

    # ── Role-based navigation ──────────────────────────────────────────────
    # admin → Schedule + Dashboard + Admin
    # rqs   → Schedule + Dashboard
    # hk    → nothing (just name/role/signout above)
    _role = _cu["role"]
    if _role in ("admin","rqs"):
        st.markdown("---")
        st.markdown("### 🧭 Navigate")
        st.page_link("cleaning_scheduler.py", label="🧹 Cleaning Schedule")
        try:
            st.page_link("pages/1_Dashboard.py", label="📊 Dashboard")
        except Exception:
            pass
        if _role == "admin":
            try:
                st.page_link("pages/2_Admin.py", label="⚙️ Admin")
            except Exception:
                pass

    # ── Housekeepers: NO attendance/config sidebar ─────────────────────────
    # They only see their name, role, and sign-out above. Everything below
    # (attendance, roster, RQS roles, priority HKs) is admin/rqs only.
    if auth.is_housekeeper():
        present_hk   = [n for n,v in st.session_state["hk_roster"].items() if v["present"]]
        present_insp = [n for n,v in st.session_state["insp_roster"].items() if v]
        rqs1 = st.session_state.get("rqs1","")
        rqs2 = st.session_state.get("rqs2","")
        priority_hks = st.session_state.get("priority_hks",[])
        groups_per_insp = 3
    else:
        st.markdown("## 📅 Daily Attendance")
        st.markdown("---")
        with st.expander("➕ Add / 🗑 Remove Housekeeper"):
            col_a, col_b = st.columns([2,1])
            with col_a: new_hk_name = st.text_input("Name", key="new_hk_inp")
            with col_b: new_hk_bld  = st.selectbox("Bldg", [1,2,3], key="new_hk_bld")
            if st.button("Add HK", key="btn_add_hk"):
                n = new_hk_name.strip()
                if n and n not in st.session_state["hk_roster"]:
                    st.session_state["hk_roster"][n] = {"building":new_hk_bld,"present":True}
                    _persist_roster(); st.success(f"Added {n}")
            rm_hk = st.selectbox("Remove", ["—"]+list(st.session_state["hk_roster"].keys()), key="rm_hk_sel")
            if st.button("Remove", key="btn_rm_hk") and rm_hk != "—":
                del st.session_state["hk_roster"][rm_hk]
                _persist_roster(); st.success(f"Removed {rm_hk}")

        st.markdown("### 🧑‍🔧 Housekeepers")
        st.caption("Check ✅ to mark present. Use ◀▶ buttons to move between buildings.")
        roster = st.session_state["hk_roster"]
        present_hk = []
        import copy as _copy
        _hk_before = _copy.deepcopy(roster)
        for bld in [1,2,3]:
            bld_hks = [n for n,v in roster.items() if v["building"]==bld]
            # Note: we no longer skip empty buildings — the bulk-paste field
            # below lets you populate an empty building from scratch.
            BLD_NEON_SB = {
                1: ("rgba(99,102,241,.15)","#a5b4fc","rgba(99,102,241,.3)"),
                2: ("rgba(20,184,166,.12)","#5eead4","rgba(20,184,166,.3)"),
                3: ("rgba(245,158,11,.12)","#fcd34d","rgba(245,158,11,.3)"),
            }
            bg_b, txt_b, bdr_b = BLD_NEON_SB.get(bld, ("rgba(99,99,99,.1)","#94a3b8","rgba(99,99,99,.2)"))
            n_present = sum(1 for n in bld_hks if roster[n]["present"])
            st.markdown(
                f'<div style="background:{bg_b};color:{txt_b};border-radius:8px;'
                f'padding:6px 12px;font-family:\'DM Mono\',monospace;font-size:.68rem;font-weight:500;'
                f'display:flex;justify-content:space-between;align-items:center;'
                f'margin:8px 0 4px;border:1px solid {bdr_b};'
                f'letter-spacing:.04em;text-transform:uppercase">'
                f'<span>Building {bld}</span>'
                f'<span style="background:{bdr_b};color:{txt_b};border-radius:20px;padding:1px 8px;'
                f'font-size:.62rem">{n_present}/{len(bld_hks)}</span>'
                f'</div>',
                unsafe_allow_html=True)

            # ── Bulk replace: paste a list of names (e.g. from Excel) to replace
            #    ALL housekeepers currently in this building ────────────────────
            with st.expander(f"📋 Bulk set Building {bld} names"):
                _bulk = st.text_area(
                    "Paste names (one per line or comma-separated)",
                    key=f"bulk_hk_b{bld}", height=90,
                    placeholder="Maria Lopez\nAna Garcia\nRosa Diaz",
                    label_visibility="collapsed")
                if st.button(f"Replace Building {bld} list", key=f"bulk_apply_b{bld}",
                             use_container_width=True):
                    # Parse: split on newlines and commas, trim, drop blanks/dupes
                    raw = re.split(r'[\n,]+', _bulk or "")
                    new_names = []
                    seen = set()
                    for nm in raw:
                        nm = re.sub(r'\s+', ' ', nm).strip()
                        if nm and nm.lower() not in seen:
                            seen.add(nm.lower()); new_names.append(nm)
                    if new_names:
                        # Remove every current HK in this building, then add the new
                        # list. Housekeepers in OTHER buildings are untouched.
                        for _n in [n for n,v in roster.items() if v["building"]==bld]:
                            del roster[_n]
                        for _n in new_names:
                            roster[_n] = {"building":bld, "present":True}
                        st.session_state["hk_roster"] = roster
                        _persist_roster()
                        st.toast(f"📋 Building {bld}: set {len(new_names)} housekeepers")
                        st.rerun()
                    else:
                        st.warning("No valid names found to set.")

            for name in bld_hks:
                c_chk, c_name, c_left, c_right = st.columns([0.4,3.2,0.6,0.6])
                with c_chk:
                    checked = st.checkbox("", value=roster[name]["present"], key=f"att_{name}", label_visibility="collapsed")
                    if roster[name]["present"] != checked:
                        roster[name]["present"] = checked
                        _persist_roster()
                    else:
                        roster[name]["present"] = checked
                with c_name:
                    col2 = "inherit" if checked else "#94a3b8"
                    td   = "none"    if checked else "line-through"
                    st.markdown(f'<div style="font-size:.8rem;color:{col2};padding:4px 0;text-decoration:{td}">{e(name)}</div>', unsafe_allow_html=True)
                with c_left:
                    if bld > 1:
                        if st.button("◀", key=f"ml_{name}", use_container_width=True):
                            roster[name]["building"] = bld-1; _persist_roster(); st.rerun()
                with c_right:
                    if bld < 3:
                        if st.button("▶", key=f"mr_{name}", use_container_width=True):
                            roster[name]["building"] = bld+1; _persist_roster(); st.rerun()
                if roster[name]["present"]: present_hk.append(name)

        # Persist HK attendance immediately so it survives logout/login.
        if roster != _hk_before:
            try:
                _existing = db.load_full_schedule() or {}
                _existing["hk_roster"]   = dict(roster)
                _existing["insp_roster"] = dict(st.session_state.get("insp_roster",{}))
                db.save_full_schedule(_existing)
            except Exception:
                pass

        st.markdown("---")
        with st.expander("➕ Add / 🗑 Remove Inspector"):
            new_insp = st.text_input("Name", key="new_insp_inp")
            if st.button("Add Inspector", key="btn_add_insp"):
                n = new_insp.strip()
                if n and n not in st.session_state["insp_roster"]:
                    st.session_state["insp_roster"][n]=True; _persist_roster(); st.success(f"Added {n}")
            rm_insp = st.selectbox("Remove",["—"]+list(st.session_state["insp_roster"].keys()),key="rm_insp_sel")
            if st.button("Remove", key="btn_rm_insp") and rm_insp != "—":
                del st.session_state["insp_roster"][rm_insp]; _persist_roster(); st.success(f"Removed {rm_insp}")

        st.markdown("### 🔍 Inspectors")
        insp_roster = st.session_state["insp_roster"]
        # ── Shuffle RQS order so they pair with different housekeepers ───────
        if st.button("🔀 Shuffle RQS order", key="btn_shuffle_rqs", use_container_width=True,
                     help="Randomize inspector order so RQS get paired with different housekeepers each run"):
            import random as _rnd
            _items = list(insp_roster.items())
            _rnd.shuffle(_items)
            st.session_state["insp_roster"] = dict(_items)
            insp_roster = st.session_state["insp_roster"]
            # clear cached RQS role picks so they re-pick from the new order
            for _k in ("rqs1","rqs2"):
                if _k in st.session_state: st.session_state[_k] = ""
            try:
                _existing = db.load_full_schedule() or {}
                _existing["insp_roster"] = dict(insp_roster)
                _existing["hk_roster"]   = dict(st.session_state.get("hk_roster",{}))
                db.save_full_schedule(_existing)
            except Exception:
                pass
            st.toast("🔀 RQS order shuffled")
            st.rerun()
        present_insp = []
        _insp_before = dict(insp_roster)
        for name in list(insp_roster.keys()):
            insp_roster[name] = st.checkbox(name, value=insp_roster[name], key=f"insp_att_{name}")
            if insp_roster[name]: present_insp.append(name)
        # Persist attendance immediately so it survives logout/login even without
        # regenerating the schedule.
        if insp_roster != _insp_before:
            try:
                _existing = db.load_full_schedule() or {}
                _existing["insp_roster"] = dict(insp_roster)
                _existing["hk_roster"]   = dict(st.session_state.get("hk_roster",{}))
                db.save_full_schedule(_existing)
            except Exception:
                pass

        st.markdown("---")
        st.markdown("### 🎯 RQS Roles Today")
        rqs_opts = ["— none —"] + present_insp
        rqs1_sel = st.selectbox("RQS 1 (Dust & Vac)", rqs_opts, key="rqs1_sel")
        rqs2_sel = st.selectbox("RQS 2 (Daily Service)", rqs_opts, key="rqs2_sel")
        rqs1 = "" if rqs1_sel=="— none —" else rqs1_sel
        rqs2 = "" if rqs2_sel=="— none —" else rqs2_sel
        st.session_state["rqs1"] = rqs1; st.session_state["rqs2"] = rqs2

        st.markdown("---")
        groups_per_insp = st.select_slider("Groups / FC inspector", options=[3,4], value=3)

        st.markdown("---")
        st.markdown("### ⭐ Priority HKs")
        st.caption("Select HKs who need a full 380-min group (productivity recovery).")
        if "priority_hks" not in st.session_state: st.session_state["priority_hks"] = []
        saved_priority = [n for n in st.session_state["priority_hks"] if n in present_hk]
        if saved_priority != st.session_state["priority_hks"]: st.session_state["priority_hks"] = saved_priority
        st.multiselect("Priority HKs", options=present_hk, key="priority_hks",
                       label_visibility="collapsed", placeholder="Choose HKs for priority full groups…")
        priority_hks = st.session_state["priority_hks"]
        if priority_hks:
            st.markdown(f'<div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;'
                        f'padding:7px 11px;font-size:.75rem;color:#92400e">'
                        f'⭐ <b>{len(priority_hks)}</b> HK(s): {", ".join(priority_hks)}</div>',
                        unsafe_allow_html=True)
        st.markdown(f'<div style="background:#f1f5f9;border-radius:8px;padding:9px 11px;font-size:.77rem;color:#475569;margin-top:8px">'
                    f'✅ <b>{len(present_hk)}</b> HKs &nbsp;·&nbsp; <b>{len(present_insp)}</b> inspectors<br>'
                    f'RQS1: <b>{rqs1 or "—"}</b> &nbsp;·&nbsp; RQS2: <b>{rqs2 or "—"}</b></div>',
                    unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN INPUT
# ══════════════════════════════════════════════════════════════════════════════
_cu = auth.current_user()
_disp_name = _cu.get("display_name") or _cu.get("username","")
_first_name = _disp_name.split()[0].title() if _disp_name else "there"
_welcome_msg = auth.get_welcome_msg(_cu["role"])

st.markdown(f'<p class="pg-title">Good morning, {_first_name}! 👋</p>', unsafe_allow_html=True)
st.markdown(f'<p class="pg-sub">{_welcome_msg}</p>', unsafe_allow_html=True)

with st.expander("📋 Rules", expanded=False):
    st.markdown("""<div class="rules-box"><ol>
<li>Full Clean ≤ <strong>380 min</strong> · Daily Service ≤ <strong>560 min</strong></li>
<li>Groups: <strong>Full Clean → Daily Service → Dust & Vac</strong></li>
<li>Building 2 and Building 3 <strong>cannot share a group</strong></li>
<li>Full Clean: max <strong>one 140-min</strong> room per group</li>
<li>Same guest → same group · floor-first packing</li>
<li>B1 HKs can go to B2/B3 · B2 cannot go to B3 · B3 cannot go to B2</li>
</ol></div>""", unsafe_allow_html=True)

st.markdown("---")
col_data, col_cfg = st.columns([5,1], gap="medium")
with col_data:
    st.markdown('<p class="sec">📋 Room Data + Front-Desk Email</p>', unsafe_allow_html=True)
    inp_a, inp_b = st.columns([3,2], gap="small")
    with inp_a:
        # ── Upload the Housekeeping Dashboard .xlsx directly (optional) ────────
        # Alternative to copy-paste: an uploaded file is converted to the same
        # tab-separated text the paste box uses and run through the exact same
        # parser, so nothing downstream changes. We push the converted text into
        # the text-area's session_state (tracking which file we've already read,
        # so re-runs don't clobber manual edits) rather than passing value=,
        # which avoids Streamlit's value/key conflict warning.
        if auth.can("can_paste_input"):
            _xl = st.file_uploader("Upload Housekeeping Dashboard (.xlsx)",
                                   type=["xlsx"], key="room_xlsx",
                                   help="Optional — upload the exported dashboard instead of pasting.")
            if _xl is not None:
                _sig = f"{_xl.name}:{getattr(_xl,'size','?')}"
                if st.session_state.get("_room_xlsx_sig") != _sig:
                    try:
                        _txt, _n_up, _sheet_up = excel_to_room_text(_xl)
                        st.session_state["room_input"] = _txt
                        st.session_state["_room_xlsx_sig"] = _sig
                        st.session_state["_room_xlsx_msg"] = (
                            "ok", f"✅ Read {_n_up} rooms from '{_sheet_up}'. "
                                  f"Click ⚡ Generate to build the schedule.")
                    except ImportError:
                        st.session_state["_room_xlsx_sig"] = _sig
                        st.session_state["_room_xlsx_msg"] = (
                            "err", "The .xlsx reader isn't installed on the server yet "
                                   "(openpyxl). Once the app redeploys it'll work — for "
                                   "now you can copy-paste the data below.")
                    except Exception as _e:
                        st.session_state["_room_xlsx_sig"] = _sig
                        st.session_state["_room_xlsx_msg"] = (
                            "err", f"Couldn't read that file: {_e}. "
                                   f"You can still copy-paste the data below.")
                _msg = st.session_state.get("_room_xlsx_msg")
                if _msg:
                    (st.success if _msg[0] == "ok" else st.error)(_msg[1])
        raw_input = st.text_area("rooms", label_visibility="collapsed", height=230,
            disabled=not auth.can("can_paste_input"),
            placeholder="Room\tService\tTime\tPet\tCurrent Guest or Status\n1020D\tFull Clean\t120\t\tSmith, John",
            key="room_input")
        st.caption("Upload the .xlsx above, or copy-paste from Excel (include header row).")
    with inp_b:
        email_text = st.text_area("email", label_visibility="collapsed", height=230,
            disabled=not auth.can("can_paste_input"),
            placeholder="Paste today's front-desk email...\n\nLate Checkouts:\n* 10:30 am\n   * 1234A",
            key="email_input")
        st.caption("Late checkouts, room moves, notes auto-matched.")
with col_cfg:
    st.markdown('<p class="sec">⚙️</p>', unsafe_allow_html=True)
    _today_bg  = ("rgba(255,255,255,.7)" if _IS_GLASS else "#ffffff") if _IS_LIGHT else ("rgba(40,40,52,.5)" if _IS_GLASS else "rgba(255,255,255,.03)")
    _today_br  = "rgba(99,102,241,.18)"
    _today_hd  = "#0f172a" if _IS_LIGHT else "#e2e8f0"
    _today_tx  = "#475569" if _IS_LIGHT else "#94a3b8"
    st.markdown(f'<div style="background:{_today_bg};border:1px solid {_today_br};border-radius:10px;'
                f'padding:11px 13px;font-size:.78rem;color:{_today_tx};margin-bottom:10px">'
                f'<div style="font-weight:700;color:{_today_hd};margin-bottom:5px">Today</div>'
                f'<div>🧑‍🔧 <b>{len(present_hk)}</b> HKs present</div>'
                f'<div>🔍 <b>{len(present_insp)}</b> inspectors</div></div>', unsafe_allow_html=True)
    _can_gen = auth.can("can_generate")
    run = st.button("⚡ Generate", type="primary", use_container_width=True,
                    disabled=not _can_gen,
                    help="" if _can_gen else "🔒 Housekeeper role — view only")

# ══════════════════════════════════════════════════════════════════════════════
#  SNAPSHOT
# ══════════════════════════════════════════════════════════════════════════════
def _build_snapshot(fg, total_rooms, inspectors):
    from datetime import date
    hk_snap = {}
    for g in fg:
        hk = g.get("housekeeper","")
        if hk and hk != "Manager":
            if hk not in hk_snap:
                hk_snap[hk] = {"time":0,"rooms":0,"rooms_fc":0,"rooms_ds":0,"rooms_dv":0}
            n = len(g.get("rooms",[]))
            hk_snap[hk]["time"]  += g.get("time",0)
            hk_snap[hk]["rooms"] += n
            svc = g.get("service_type","")
            if svc==SVC_FC:  hk_snap[hk]["rooms_fc"] += n
            elif svc==SVC_DS:hk_snap[hk]["rooms_ds"] += n
            elif svc==SVC_DV:hk_snap[hk]["rooms_dv"] += n
    insp_snap = {}
    for insp in inspectors:
        nm = insp.get("name","")
        if nm:
            labels = set(insp.get("groups",[]))
            n_rooms = sum(len(g.get("rooms",[])) for g in fg if g.get("label") in labels)
            insp_snap[nm] = {"rooms":n_rooms,"groups":len(labels),"role":insp.get("role","FC")}
    return {"date":str(date.today()),"total_rooms":total_rooms,"n_groups":len(fg),
            "hk":hk_snap,"inspectors":insp_snap,
            "saved_by":st.session_state.get("username","unknown"),"schema_v":2}

# ══════════════════════════════════════════════════════════════════════════════
#  GENERATE
# ══════════════════════════════════════════════════════════════════════════════
if run:
    st.session_state["last_email"] = email_text
    if not raw_input.strip():
        st.warning("Paste room data first.")
    elif not present_hk:
        st.warning("No housekeepers marked as present.")
    else:
        with st.spinner("⚡ Building schedule…"):
            try:
                df = parse_rooms(raw_input)
                if df.empty:
                    st.error("No valid rows — check tab-separated data with a header row.")
                else:
                    email_data      = parse_email_notes(email_text)
                    late_co_map     = email_data["late_checkout"]
                    email_notes_map = email_data["notes"]
                    if email_text.strip():
                        n_late = len(late_co_map)
                        n_notes= sum(len(v) for v in email_notes_map.values())
                        if n_late > 0:
                            late_rooms = ", ".join(f"{rm} ({t.replace('Late Out: ','')})" for rm,t in sorted(late_co_map.items()))
                            st.success(f"✅ Email parsed: **{n_late}** late checkout(s) · **{n_notes}** note(s)\n\nLate rooms: {late_rooms}")
                        else:
                            st.warning("⚠️ Email parsed but 0 late checkouts found.")
                    records_raw = df.to_dict("records")
                    rds = []
                    for r in records_raw:
                        rm_upper   = str(r["Room"]).strip().upper()
                        excel_late = r.get("LateCheckout","").strip()
                        email_late = late_co_map.get(rm_upper,"")
                        if email_late: late_co = email_late
                        elif excel_late and excel_late.lower() not in ("","late check out","late checkout","late check-out"): late_co = excel_late
                        elif excel_late: late_co = "Late Out"
                        else: late_co = ""
                        notes_parts = []
                        if r.get("NotesRaw","").strip(): notes_parts.append(r["NotesRaw"].strip())
                        if rm_upper in email_notes_map: notes_parts += email_notes_map[rm_upper]
                        has_stayover = (
                            r.get("uncertain",False) or
                            any("stayover" in n.lower() or "stay over" in n.lower() for n in notes_parts)
                        )
                        # verify rooms (stayover / P-U Models): no auto HK/RQS, sent to bottom
                        needs_verify = (
                            r.get("verify",False) or
                            any("stayover" in n.lower() or "stay over" in n.lower()
                                or "p/u model" in n.lower() or "pu model" in n.lower()
                                for n in notes_parts)
                        )
                        rds.append({
                            "room":r["Room"],"service":r["Service"],"time":r["Time"],
                            "pet":r["Pet"],"guest":r["Guest"],
                            "bld":r.get("bld",get_building(r["Room"])),
                            "floor":r.get("floor",0),"num":r.get("num",0),
                            "late_checkout":late_co,"status":r.get("Status",""),
                            "notes":"; ".join(notes_parts),"arriving":r.get("ArrivingGuest",""),
                            "res_type":r.get("ResType",""),"uncertain":has_stayover,
                            "verify":needs_verify,
                        })
                    fg = build_all_groups(rds, priority_hks=st.session_state.get("priority_hks",[]))
                    fc_gs=[g for g in fg if g.get("service_type")==SVC_FC and not g.get("verify_group")]
                    ih_gs=[g for g in fg if g.get("service_type")==SVC_IH and not g.get("verify_group")]
                    ds_gs=[g for g in fg if g.get("service_type")==SVC_DS and not g.get("verify_group")]
                    dv_gs=[g for g in fg if g.get("service_type")==SVC_DV and not g.get("verify_group")]
                    vr_gs=[g for g in fg if g.get("verify_group")]
                    for g,lbl in zip(fc_gs, make_labels("FC",len(fc_gs))): g["label"]=lbl
                    for g,lbl in zip(ih_gs, make_labels("IH",len(ih_gs))): g["label"]=lbl
                    for g,lbl in zip(ds_gs, make_labels("DS",len(ds_gs))): g["label"]=lbl
                    for g,lbl in zip(dv_gs, make_labels("DV",len(dv_gs))): g["label"]=lbl
                    for g,lbl in zip(vr_gs, make_labels("VERIFY",len(vr_gs))): g["label"]=lbl
                    for g in fg: g["cross_bld"] = len(g["blds"])>1

                    # (The new solve_full_clean already consolidates to the fewest
                    # charts, so the legacy tiny-merge pass below is disabled to
                    # avoid undoing its tidy, building-coherent packing.)
                    fg=[g for g in fg if g["rooms"]]
                    p_fc=[g for g in fg if g.get("service_type")==SVC_FC and g.get("priority_hk") and not g.get("verify_group")]
                    n_fc=[g for g in fg if g.get("service_type")==SVC_FC and not g.get("priority_hk") and not g.get("verify_group")]
                    ih2=[g for g in fg if g.get("service_type")==SVC_IH and not g.get("verify_group")]
                    ds2=[g for g in fg if g.get("service_type")==SVC_DS and not g.get("verify_group")]
                    dv2=[g for g in fg if g.get("service_type")==SVC_DV and not g.get("verify_group")]
                    vr2=[g for g in fg if g.get("verify_group")]
                    for g,lbl in zip(p_fc+n_fc, make_labels("FC",len(p_fc)+len(n_fc))): g["label"]=lbl
                    for g,lbl in zip(ih2, make_labels("IH",len(ih2))): g["label"]=lbl
                    for g,lbl in zip(ds2, make_labels("DS",len(ds2))): g["label"]=lbl
                    for g,lbl in zip(dv2, make_labels("DV",len(dv2))): g["label"]=lbl
                    for g,lbl in zip(vr2, make_labels("VERIFY",len(vr2))): g["label"]=lbl
                    for g in fg: g["cross_bld"]=len(g["blds"])>1

                    hk_asgn, used_hk_set = assign_hk_building_aware(fg, present_hk, roster)
                    for g in fg: g["housekeeper"] = hk_asgn.get(g["label"],"")
                    inspectors = assign_inspectors(fg, present_insp, groups_per_insp, rqs1, rqs2)

                    # Store fresh result in session state
                    st.session_state["groups_data"]     = fg
                    st.session_state["total_rooms"]     = len(df)
                    st.session_state["inspectors_data"] = inspectors
                    st.session_state["used_hk_set"]     = used_hk_set

                    # Save to DB for sharing + dashboard (non-blocking)
                    try:
                        db.save_full_schedule({
                            "groups_data": fg, "total_rooms": len(df),
                            "inspectors_data": inspectors,
                            "used_hk_set": list(used_hk_set),
                            "hk_roster": dict(st.session_state.get("hk_roster",{})),
                            "insp_roster": dict(st.session_state.get("insp_roster",{})),
                            "generated_by": st.session_state.get("username","unknown"),
                        })
                    except Exception:
                        pass
                    try:
                        db.save_snapshot(_build_snapshot(fg,len(df),inspectors))
                    except Exception:
                        pass

                    st.success(f"✅ Schedule generated — {len(fg)} groups from {len(df)} rooms.")
            except Exception as ex:
                st.error(f"Error: {ex}")
                import traceback; st.code(traceback.format_exc())

# ══════════════════════════════════════════════════════════════════════════════
#  RESULTS
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.get("groups_data"): st.stop()

fg          = st.session_state["groups_data"]
total_rooms = st.session_state["total_rooms"]
inspectors  = st.session_state["inspectors_data"]
used_hk_set = st.session_state.get("used_hk_set") or set()
present_hk  = [n for n,v in st.session_state["hk_roster"].items() if v["present"]]
present_insp= [n for n,v in st.session_state["insp_roster"].items() if v]

st.markdown("---")
fc_g=[g for g in fg if g.get("service_type")==SVC_FC]
ds_g=[g for g in fg if g.get("service_type")==SVC_DS]
dv_g=[g for g in fg if g.get("service_type")==SVC_DV]
avg_t=sum(g["time"] for g in fg)//max(len(fg),1)
n_free_hk=sum(1 for n in present_hk if n not in used_hk_set)
n_low_hk =sum(1 for g in fg if g.get("housekeeper") and g.get("housekeeper")!="Manager" and g["time"]<LOW_MIN)

st.markdown(f"""<div class="stat-row">
  <div class="sc hi"><div class="n">{len(fg)}</div><div class="l">Total Groups</div></div>
  <div class="sc"><div class="n" style="color:#2563EB">{len(fc_g)}</div><div class="l">Full Clean</div></div>
  <div class="sc ds"><div class="n">{len(ds_g)}</div><div class="l">Daily Service</div></div>
  <div class="sc dv"><div class="n">{len(dv_g)}</div><div class="l">Dust &amp; Vac</div></div>
  <div class="sc"><div class="n">{total_rooms}</div><div class="l">Rooms</div></div>
  <div class="sc"><div class="n">{avg_t}m</div><div class="l">Avg Time</div></div>
  <div class="sc"><div class="n" style="color:{'#059669' if n_free_hk==0 else '#d97706'}">{n_free_hk}</div>
    <div class="l">Free HKs</div></div>
  <div class="sc"><div class="n" style="color:{'#059669' if n_low_hk==0 else '#dc2626'}">{n_low_hk}</div>
    <div class="l">Low-Hour HKs</div></div>
</div>""", unsafe_allow_html=True)

_is_hk   = auth.is_housekeeper()
_my_name = auth.my_display_name()

if _is_hk:
    # ══════════════════════════════════════════════════════════════════════
    #  HOUSEKEEPER VIEW — single "My Schedule" tab, own rooms only
    # ══════════════════════════════════════════════════════════════════════
    _NOW = _now_iso   # shared Mountain-time timestamp helper

    _tmsg_hk = st.session_state.pop("_live_toast", None)
    if _tmsg_hk:
        try: st.toast(_tmsg_hk)
        except Exception: pass

    STATUS_META_HK = {
        "pending":          {"icon":"⬜","label":"Pending",       "color":"#475569","bg":"rgba(71,85,105,.2)","border":"rgba(71,85,105,.35)"},
        "already_clean":    {"icon":"✨","label":"Already Clean", "color":"#34d399","bg":"rgba(52,211,153,.12)","border":"rgba(52,211,153,.35)"},
        "cleaning_started": {"icon":"🧹","label":"In Progress",   "color":"#fbbf24","bg":"rgba(251,191,36,.15)","border":"rgba(251,191,36,.4)"},
        "cleaning_done":    {"icon":"✅","label":"Done",          "color":"#60a5fa","bg":"rgba(96,165,250,.12)","border":"rgba(96,165,250,.35)"},
        "inspected":        {"icon":"🔍","label":"Inspected ✓",  "color":"#a78bfa","bg":"rgba(167,139,250,.15)","border":"rgba(167,139,250,.4)"},
    }

    # Init room statuses
    if "room_statuses" not in st.session_state:
        st.session_state["room_statuses"] = {}
    if not st.session_state.get("_live_loaded"):
        st.session_state["_live_loaded"] = True
        try:
            st.session_state["room_statuses"] = db.get_room_statuses()
        except Exception:
            pass
    rs = st.session_state["room_statuses"]

    def _save_status_hk(room, fields):
        if room not in rs: rs[room] = {"room":room,"status":"pending"}
        rs[room].update(fields)
        rs[room]["updated_by"] = _my_name
        try:
            db.upsert_room_status(room, fields | {"updated_by": _my_name})
        except Exception:
            pass

    # Collect this HK's groups
    my_groups = [g for g in fg if g.get("housekeeper","") == _my_name]

    # Stats
    my_rooms_all = [r for g in my_groups for r in g["rooms"]]
    n_total  = len(my_rooms_all)
    n_done   = sum(1 for r in my_rooms_all if rs.get(r["room"],{}).get("status") in ("already_clean","cleaning_done","inspected"))
    n_active = sum(1 for r in my_rooms_all if rs.get(r["room"],{}).get("status") == "cleaning_started")
    n_insp   = sum(1 for r in my_rooms_all if rs.get(r["room"],{}).get("status") == "inspected")
    pct      = int(n_done / max(n_total,1) * 100)

    # Progress header
    st.markdown(f"""
<div style="background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.2);
            border-radius:14px;padding:16px 20px;margin-bottom:20px">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
    <div>
      <div style="font-family:'Syne',sans-serif;font-size:1.1rem;font-weight:700;color:#e2e8f0">
        Your Rooms Today
      </div>
      <div style="font-family:'DM Mono',monospace;font-size:.7rem;color:#475569;margin-top:2px">
        {n_total} rooms &nbsp;·&nbsp; {len(my_groups)} group{"s" if len(my_groups)!=1 else ""}
      </div>
    </div>
    <div style="display:flex;gap:10px">
      <div style="text-align:center;background:rgba(251,191,36,.1);border:1px solid rgba(251,191,36,.25);border-radius:8px;padding:8px 14px">
        <div style="font-family:'Syne',sans-serif;font-size:1.3rem;font-weight:800;color:#fbbf24">{n_active}</div>
        <div style="font-family:'DM Mono',monospace;font-size:.58rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em">Active</div>
      </div>
      <div style="text-align:center;background:rgba(96,165,250,.1);border:1px solid rgba(96,165,250,.25);border-radius:8px;padding:8px 14px">
        <div style="font-family:'Syne',sans-serif;font-size:1.3rem;font-weight:800;color:#60a5fa">{n_done}</div>
        <div style="font-family:'DM Mono',monospace;font-size:.58rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em">Done</div>
      </div>
      <div style="text-align:center;background:rgba(167,139,250,.1);border:1px solid rgba(167,139,250,.25);border-radius:8px;padding:8px 14px">
        <div style="font-family:'Syne',sans-serif;font-size:1.3rem;font-weight:800;color:#a78bfa">{n_insp}</div>
        <div style="font-family:'DM Mono',monospace;font-size:.58rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em">Inspected</div>
      </div>
    </div>
  </div>
  <div style="margin-top:12px">
    <div style="background:rgba(255,255,255,.05);border-radius:99px;height:7px;overflow:hidden;border:1px solid rgba(255,255,255,.04)">
      <div style="background:linear-gradient(90deg,#6366f1,#22d3ee);width:{pct}%;height:7px;
                  border-radius:99px;box-shadow:0 0 8px rgba(99,102,241,.5);transition:width .5s"></div>
    </div>
    <div style="font-family:'DM Mono',monospace;font-size:.65rem;color:#334155;margin-top:4px">
      {pct}% complete
    </div>
  </div>
</div>""", unsafe_allow_html=True)

    if not my_groups:
        st.markdown("""
<div style="text-align:center;padding:60px 20px;color:#334155;font-family:'DM Mono',monospace">
  <div style="font-size:2rem;margin-bottom:12px">🕐</div>
  <div style="font-size:.9rem">No rooms assigned yet for today.</div>
  <div style="font-size:.75rem;margin-top:6px;color:#1e293b">Check back once the schedule is generated.</div>
</div>""", unsafe_allow_html=True)
    else:
        # Render each group
        for _hgidx, g in enumerate(my_groups):
            g_label = g.get("label","")
            insp_name = g.get("inspector","—")
            g_rooms = g["rooms"]
            g_done = sum(1 for r in g_rooms if rs.get(r["room"],{}).get("status") in ("already_clean","cleaning_done","inspected"))
            g_pct  = int(g_done / max(len(g_rooms),1) * 100)
            g_color = "#6366f1" if g.get("service_type")==SVC_FC else ("#14b8a6" if g.get("service_type")==SVC_DS else "#f59e0b")

            # Group header
            st.markdown(f"""
<div style="background:linear-gradient(135deg,rgba(14,14,26,.95),rgba(19,19,31,.98));
            border:1px solid rgba(99,102,241,.25);border-radius:12px;
            padding:12px 16px;margin-bottom:8px;
            box-shadow:0 0 0 1px rgba(255,255,255,.03),0 4px 20px rgba(0,0,0,.3)">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px">
    <div style="display:flex;align-items:center;gap:10px">
      <div style="background:{g_color};color:#fff;border-radius:6px;padding:4px 10px;
                  font-family:'Syne',sans-serif;font-weight:800;font-size:.78rem;
                  box-shadow:0 0 10px {g_color}66">{g_label}</div>
      <div>
        <div style="font-family:'DM Sans',sans-serif;font-size:.82rem;font-weight:600;color:#e2e8f0">
          {g.get("service_type","")} &nbsp;<span style="color:#334155">·</span>&nbsp;
          <span style="font-family:'DM Mono',monospace;font-size:.72rem;color:#475569">
            Inspector: {insp_name}
          </span>
        </div>
        <div style="font-family:'DM Mono',monospace;font-size:.65rem;color:#334155;margin-top:2px">
          {g_done}/{len(g_rooms)} done
        </div>
      </div>
    </div>
    <div style="display:flex;align-items:center;gap:8px">
      <div style="background:rgba(255,255,255,.04);border-radius:99px;height:5px;width:80px;overflow:hidden;border:1px solid rgba(255,255,255,.05)">
        <div style="background:linear-gradient(90deg,{g_color},{g_color}aa);width:{g_pct}%;height:5px;border-radius:99px"></div>
      </div>
      <span style="font-family:'DM Mono',monospace;font-size:.7rem;color:{g_color}">{g_pct}%</span>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

            # Room rows (dedupe so a room repeated in a group can't collide)
            _seen_hr = set(); _dedup_g_rooms = []
            for r in g_rooms:
                _rc = r.get("room")
                if _rc in _seen_hr: continue
                _seen_hr.add(_rc); _dedup_g_rooms.append(r)
            for _hridx, r in enumerate(_dedup_g_rooms):
                rm = r["room"]
                _hrk = f"{_hgidx}_{_hridx}_{rm}"   # fully unique row key
                # Ensure room is initialised in rs with this HK's info
                if rm not in rs:
                    rs[rm] = {"room":rm,"status":"pending","housekeeper":_my_name,
                              "group_label":g_label,"inspector":insp_name}
                r_state = rs.get(rm, {"status":"pending"})
                cur = r_state.get("status","pending")
                sm  = STATUS_META_HK.get(cur, STATUS_META_HK["pending"])

                _fmt = _fmt_mtn

                pet_icon  = " 🐾" if r.get("pet") else ""
                late_icon = " ⏰" if r.get("late_checkout") else ""
                late_html = (f'<span style="font-family:\'DM Mono\',monospace;font-size:.62rem;'
                             f'color:#f59e0b;background:rgba(245,158,11,.12);border-radius:4px;'
                             f'padding:1px 5px;margin-left:4px">⏰ {r.get("late_checkout","")}</span>'
                             if r.get("late_checkout") else "")
                guest_disp = r.get("guest","")[:22]

                # ── Info line: room + guest + animated status badge ──
                _hk_active = (cur == "cleaning_started")
                _hk_dot = (f'<span style="display:inline-block;width:6px;height:6px;'
                           f'border-radius:50%;background:{sm["color"]};margin-right:5px;'
                           f'vertical-align:middle;'
                           + ('animation:pulseDot 1.1s ease-in-out infinite;' if _hk_active else '')
                           + '"></span>')
                _hk_ring = 'animation:statusPop .35s cubic-bezier(.34,1.56,.64,1) both' \
                           + (',ringPulse 2s ease-out infinite' if _hk_active else '')
                st.markdown(
                    f'<div style="display:flex;align-items:center;justify-content:space-between;'
                    f'gap:8px;flex-wrap:wrap;padding:8px 10px;background:rgba(255,255,255,.02);'
                    f'border:1px solid rgba(99,102,241,.1);border-radius:8px;margin-bottom:4px">'
                    f'  <div style="display:flex;align-items:center;gap:8px;min-width:0;flex:1">'
                    f'    <span style="font-family:\'DM Mono\',monospace;font-size:.85rem;'
                    f'font-weight:600;color:#6366f1;white-space:nowrap">{rm}</span>'
                    f'    <span style="font-size:.78rem;color:#94a3b8;overflow:hidden;'
                    f'text-overflow:ellipsis;white-space:nowrap">{guest_disp}{pet_icon}</span>'
                    f'    {late_html}'
                    f'  </div>'
                    f'  <div style="background:{sm["bg"]};border:1px solid {sm["border"]};'
                    f'border-radius:6px;padding:3px 9px;font-size:.7rem;font-weight:600;'
                    f'color:{sm["color"]};white-space:nowrap;flex-shrink:0;{_hk_ring}">'
                    f'{_hk_dot}{sm["icon"]} {sm["label"]}</div>'
                    f'</div>', unsafe_allow_html=True)

                # ── Action buttons row — compact, equal width, stays horizontal ──
                b1,b2,b3 = st.columns(3)
                with b1:
                    if cur == "pending":
                        if st.button("✨ Clean", key=f"hk_ac_{_hrk}", use_container_width=True):
                            _save_status_hk(rm, {"status":"already_clean","marked_clean_at":_NOW()})
                            st.session_state["_live_toast"] = f"✨ {rm} marked Already Clean"
                            st.rerun()
                    elif cur == "already_clean":
                        if st.button("↩ Undo", key=f"hk_uac_{_hrk}", use_container_width=True):
                            _save_status_hk(rm, {"status":"pending"})
                            st.rerun()
                with b2:
                    if cur == "pending":
                        if st.button("🧹 Start", key=f"hk_s_{_hrk}", use_container_width=True):
                            _save_status_hk(rm, {"status":"cleaning_started","started_at":_NOW()})
                            st.session_state["_live_toast"] = f"🧹 {rm} — cleaning started"
                            st.rerun()
                    elif cur == "cleaning_started":
                        if st.button("✅ Done", key=f"hk_d_{_hrk}", use_container_width=True):
                            _save_status_hk(rm, {"status":"cleaning_done","cleaned_at":_NOW()})
                            st.session_state["_live_toast"] = f"✅ {rm} — done, awaiting inspection"
                            st.rerun()
                with b3:
                    if cur not in ("pending",):
                        if st.button("↩ Reset", key=f"hk_r_{_hrk}", use_container_width=True):
                            _save_status_hk(rm, {"status":"pending","started_at":None,"cleaned_at":None,"inspected_at":None,"marked_clean_at":None})
                            st.rerun()

                # Timestamp trail
                ts_parts = []
                if _fmt(r_state.get("marked_clean_at","")): ts_parts.append(f'✨ {_fmt(r_state.get("marked_clean_at",""))}')
                if _fmt(r_state.get("started_at","")): ts_parts.append(f'🧹 {_fmt(r_state.get("started_at",""))}')
                if _fmt(r_state.get("cleaned_at","")): ts_parts.append(f'✅ {_fmt(r_state.get("cleaned_at",""))}')
                if _fmt(r_state.get("inspected_at","")): ts_parts.append(f'🔍 {_fmt(r_state.get("inspected_at",""))}')
                if ts_parts:
                    st.markdown(
                        f'<div style="font-family:\'DM Mono\',monospace;font-size:.6rem;color:#1e293b;'
                        f'padding:0 0 6px 4px">{"  ·  ".join(ts_parts)}</div>', unsafe_allow_html=True)

            st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)

    # Refresh button
    if st.button("🔄 Refresh Status", key="hk_refresh", use_container_width=False):
        try:
            st.session_state["room_statuses"] = db.get_room_statuses()
        except Exception:
            pass
        st.rerun()

else:
    # ══════════════════════════════════════════════════════════════════════
    #  ADMIN / RQS VIEW — full 4-tab interface
    # ══════════════════════════════════════════════════════════════════════
    tab_hk, tab_insp, tab_grp, tab_live = st.tabs(["🧑‍🔧 Housekeepers","🔍 Inspectors","📋 Groups","⚡ Live"])

    with tab_hk:
        hk_time={}; hk_grps={}
        for g in fg:
            hk=g.get("housekeeper","")
            if hk and hk!="Manager":
                hk_time[hk]=hk_time.get(hk,0)+g["time"]
                hk_grps.setdefault(hk,[]).append(g["label"])
        rows_hk=[]
        for name in present_hk:
            t=hk_time.get(name,0); gs=hk_grps.get(name,[])
            b=st.session_state["hk_roster"].get(name,{}).get("building","?")
            stat="free" if not gs else ("low" if t<LOW_MIN else "ok")
            rows_hk.append({"name":name,"bld":b,"groups":gs,"time":t,"stat":stat})
        rows_hk.sort(key=lambda r:{"free":0,"low":1,"ok":2}[r["stat"]])
        def hk_bld_tag(r):
            ac2,bg2=BLD_COLORS.get(r["bld"],("#888","#eee"))
            return f'<span style="background:{bg2};color:{ac2};border-radius:5px;padding:1px 7px;font-size:.7rem;font-weight:700">Bldg {r["bld"]}</span>'
        def hk_status_tag(r):
            if r["stat"]=="free": return '<span style="background:#dcfce7;color:#15803d;border-radius:5px;padding:2px 8px;font-size:.69rem;font-weight:700">✅ Free</span>'
            if r["stat"]=="low":  return '<span style="background:#fef9c3;color:#a16207;border-radius:5px;padding:2px 8px;font-size:.69rem;font-weight:700">⚠️ Low</span>'
            return ""
        def hk_pills(r):
            if not r["groups"]: return '<span style="color:#94a3b8">—</span>'
            out=""
            for gl in r["groups"]:
                idx=next((j for j,g in enumerate(fg) if g["label"]==gl),-1)
                ac2,bg2=pal(idx) if idx>=0 else ("#888","#eee")
                g_obj=next((g for g in fg if g["label"]==gl),{})
                svc_short={"Full Clean":"FC","Daily Service":"DS","Dust n Vac":"DV"}.get(g_obj.get("service_type",""),"")
                out+=f'<span style="background:{bg2};color:{ac2};border:1px solid {ac2}44;border-radius:5px;padding:1px 7px;font-size:.7rem;font-weight:700;margin-right:3px">{gl} <span style="opacity:.6;font-size:.65rem">{svc_short}</span></span>'
            return out
        def hk_bar(r):
            if not r["time"]: return '<span style="color:#94a3b8">—</span>'
            pct=min(int(r["time"]/380*100),100)
            col="#10b981" if r["stat"]=="ok" else "#f59e0b"
            return (f'<div style="display:flex;align-items:center;gap:7px">'
                    f'<span style="font-weight:600;color:#1e293b;min-width:48px">{r["time"]}m</span>'
                    f'<div style="background:#e5e7eb;border-radius:4px;height:7px;width:75px">'
                    f'<div style="background:{col};width:{pct}%;height:7px;border-radius:4px"></div></div></div>')
        tbl=staff_table_html(rows_hk,["Housekeeper","Building","Status","Groups","Time"],
            [lambda r:f'<span style="font-weight:600;color:{_C["txt"]}">{e(r["name"])}</span>',
             hk_bld_tag,hk_status_tag,hk_pills,hk_bar],
            lambda r:{"free":"#f0fdf4","low":"#fefce8","ok":"#fff"}[r["stat"]])
        components.html(tbl, height=max(70+len(rows_hk)*42,120), scrolling=False)
        if n_free_hk or n_low_hk:
            parts=[]
            if n_free_hk: parts.append(f"**{n_free_hk}** HK(s) unassigned")
            if n_low_hk:  parts.append(f"**{n_low_hk}** HK(s) low hours")
            st.warning("  ·  ".join(parts))

    with tab_insp:
        used_insp={insp.get("name","") for insp in inspectors}
        rows_insp=[]
        for insp in inspectors:
            rows_insp.append({"name":insp.get("name",""),"role":insp.get("role","FC"),
                               "groups":insp["groups"],"buildings":insp.get("buildings",[]),
                               "stat":"","complexity":insp.get("complexity","—"),
                               "heavy_warning":insp.get("heavy_warning",False)})
        for nm in present_insp:
            if nm not in used_insp:
                rows_insp.append({"name":nm,"role":"—","groups":[],"buildings":[],"stat":"free","complexity":"—","heavy_warning":False})
        def insp_role_tag(r):
            rm={"RQS1":("#92400e","#fef3c7","RQS1"),"RQS2":("#15803d","#dcfce7","RQS2"),"FC":("#1d4ed8","#dbeafe","FC"),"—":("#94a3b8","#f1f5f9","—")}
            c2,bg2,lbl=rm.get(r["role"],("#888","#eee",r["role"]))
            return f'<span style="background:{bg2};color:{c2};border-radius:5px;padding:2px 8px;font-size:.69rem;font-weight:700">{lbl}</span>'
        def insp_bld_tags(r):
            out=""
            for b in r["buildings"]:
                ac2,bg2=BLD_COLORS.get(b,("#888","#eee"))
                out+=f'<span style="background:{bg2};color:{ac2};border-radius:4px;padding:1px 6px;font-size:.68rem;font-weight:700;margin-right:3px">Bldg {b}</span>'
            return out or '<span style="color:#94a3b8">—</span>'
        def insp_grp_pills(r):
            if not r["groups"]: return '<span style="color:#94a3b8">—</span>'
            out=""
            for gl in r["groups"]:
                idx=next((j for j,g in enumerate(fg) if g["label"]==gl),-1)
                ac2,bg2=pal(idx) if idx>=0 else ("#888","#eee")
                out+=f'<span style="background:{bg2};color:{ac2};border:1px solid {ac2}44;border-radius:5px;padding:1px 7px;font-size:.7rem;font-weight:700;margin-right:3px">{gl}</span>'
            return out
        def insp_complexity_tag(r):
            c=r.get("complexity","—"); heavy=r.get("heavy_warning",False)
            col="#9b1c1c" if heavy else "#475569"; bg2="#fde8e8" if heavy else "#f1f5f9"
            return f'<span style="background:{bg2};color:{col};border-radius:5px;padding:2px 8px;font-size:.72rem;font-weight:700">{c}{"🔴" if heavy else ""}</span>'
        tbl_i=staff_table_html(rows_insp,
            ["Inspector","Role","Buildings","Groups","Load","Housekeepers"],
            [lambda r:(f'<span style="font-weight:700;color:{_C["txt"]};font-size:.82rem">{e(r["name"])}</span>'
                       +(f'<br><span style="font-size:.68rem;color:{_C["txt3"]}">✅ Free</span>' if r["stat"]=="free" else "")),
             insp_role_tag, insp_bld_tags, insp_grp_pills, insp_complexity_tag,
             lambda r:(f'<span style="font-size:.72rem;line-height:1.6">'
                       +"<br>".join(f'<span style="color:{_C["txt3"]}">{e(gl)}</span> <span style="color:{_C["txt"]};font-weight:600">{e(next((g.get("housekeeper","") for g in fg if g["label"]==gl),"—"))}</span>'
                                    for gl in r["groups"] if any(g["label"]==gl for g in fg))
                       +"</span>" if r["groups"] else f'<span style="color:{_C["txt3"]}">—</span>')],
            lambda r:"#f0fdf4" if r["stat"]=="free" else "#fff")
        components.html(tbl_i, height=max(70+len(rows_insp)*52,120), scrolling=True)
        if inspectors:
            n_cols=min(len(inspectors),3); icols=st.columns(n_cols)
            for i,insp in enumerate(inspectors):
                with icols[i%n_cols]:
                    components.html(insp_card_html(insp,fg,IC[i%len(IC)]), height=140+len(insp["groups"])*26, scrolling=False)

    with tab_grp:
        fc1,fc2,fc3,fc4,fc5,fc6 = st.columns([2,2,2,2,1,1])
        all_hk_names  = sorted(set(g.get("housekeeper","") for g in fg if g.get("housekeeper","")))
        all_rqs_names = sorted(set(g.get("inspector","")   for g in fg if g.get("inspector","")))
        all_blds      = sorted(set(b for g in fg for b in g["blds"]))
        with fc1: sel_hk_name  = st.selectbox("🧑‍🔧 Housekeeper",  ["All"]+all_hk_names,  key="grp_hk_filter")
        with fc2: sel_rqs_name = st.selectbox("🔍 Inspector (RQS)",["All"]+all_rqs_names, key="grp_rqs_filter")
        with fc3: svc_filter   = st.selectbox("🏷 Service",         ["All",SVC_FC,SVC_DS,SVC_DV], key="grp_svc_filter")
        with fc4: bld_sel      = st.selectbox("🏢 Building",        ["All"]+[f"Bldg {b}" for b in all_blds], key="grp_bld_filter")
        with fc5:
            if "grp_pet_only"  not in st.session_state: st.session_state["grp_pet_only"]  = False
            pet_only     = st.checkbox("🐾 Pet",      key="grp_pet_only")
        with fc6:
            if "grp_late_only" not in st.session_state: st.session_state["grp_late_only"] = False
            lateout_only = st.checkbox("⏰ Late Out", key="grp_late_only")
        # HKs only see their own groups
        _is_hk = auth.is_housekeeper()
        _my_name = auth.my_display_name()

        # Render order: normal groups first, verify groups dead last.
        ordered_fg = ([g for g in fg if not g.get("verify_group")] +
                      [g for g in fg if g.get("verify_group")])

        for idx, g in enumerate(ordered_fg):
            hk   = g.get("housekeeper","")
            insp2= g.get("inspector","")
            svc2 = g.get("service_type","")

            # Housekeepers never see verify groups (manager/RQS task)
            if _is_hk and g.get("verify_group"): continue
            # Housekeepers only see their own groups
            if _is_hk and hk != _my_name:
                continue
            if sel_hk_name  != "All" and hk    != sel_hk_name:  continue
            if sel_rqs_name != "All" and insp2 != sel_rqs_name: continue
            if svc_filter   != "All" and svc2  != svc_filter and not g.get("verify_group"): continue
            if bld_sel      != "All":
                sel_b=int(bld_sel.split()[1])
                if sel_b not in g["blds"]: continue
            rooms=g["rooms"]
            if pet_only:     rooms=[r for r in rooms if r.get("pet")]
            if lateout_only: rooms=[r for r in rooms if r.get("late_checkout","")]
            if not rooms: continue
            gd=dict(g); gd["rooms"]=rooms
            components.html(group_card_html(gd,idx), height=135+len(rooms)*42, scrolling=False)

    # ══════════════════════════════════════════════════════════════════════════════
    #  LIVE TAB — Real-time cleaning & inspection tracking
    # ══════════════════════════════════════════════════════════════════════════════
    with tab_live:
        _tmsg = st.session_state.pop("_live_toast", None)
        if _tmsg:
            try: st.toast(_tmsg)
            except Exception: pass
        import json as _json
        _NOW = _now_iso   # shared Mountain-time timestamp helper

        # ── Status pipeline definition ─────────────────────────────────────────
        STATUS_FLOW = ["pending","already_clean","cleaning_started","cleaning_done","inspected"]
        STATUS_META = {
            "pending":         {"icon":"⬜","label":"Pending",         "color":"#334155","bg":"rgba(51,65,85,.25)","border":"rgba(71,85,105,.4)"},
            "already_clean":   {"icon":"✨","label":"Already Clean",   "color":"#34d399","bg":"rgba(52,211,153,.12)","border":"rgba(52,211,153,.35)"},
            "cleaning_started":{"icon":"🧹","label":"Cleaning...",     "color":"#fbbf24","bg":"rgba(251,191,36,.12)","border":"rgba(251,191,36,.35)"},
            "cleaning_done":   {"icon":"✅","label":"Cleaned",         "color":"#60a5fa","bg":"rgba(96,165,250,.12)","border":"rgba(96,165,250,.35)"},
            "inspected":       {"icon":"🔍","label":"Inspected ✓",    "color":"#a78bfa","bg":"rgba(167,139,250,.15)","border":"rgba(167,139,250,.4)"},
        }

        # ── Load / init room statuses ──────────────────────────────────────────
        if "room_statuses" not in st.session_state:
            st.session_state["room_statuses"] = {}

        def _load_statuses():
            try:
                st.session_state["room_statuses"] = db.get_room_statuses()
            except Exception:
                pass  # table may not exist yet — use session-only tracking

        def _save_status(room, fields):
            rs = st.session_state["room_statuses"]
            if room not in rs:
                rs[room] = {"room": room, "status": "pending"}
            rs[room].update(fields)
            rs[room]["updated_by"] = st.session_state.get("username","?")
            try:
                db.upsert_room_status(room, fields | {
                    "updated_by": st.session_state.get("username","?")
                })
            except Exception:
                pass  # persist in session even if DB fails

        def _init_statuses_from_schedule():
            """Pre-populate room_statuses from the schedule if not in DB."""
            rs = st.session_state["room_statuses"]
            for g in fg:
                for r in g["rooms"]:
                    rm = r["room"]
                    if rm not in rs:
                        rs[rm] = {
                            "room": rm,
                            "status": "pending",
                            "group_label": g.get("label",""),
                            "housekeeper": g.get("housekeeper",""),
                            "inspector": g.get("inspector",""),
                            "svc": r.get("service",""),
                            "guest": r.get("guest",""),
                            "pet": r.get("pet",""),
                            "late": r.get("late_checkout",""),
                            "bld": r.get("bld",""),
                        }
                    else:
                        # Always keep schedule info in sync, EXCEPT housekeeper
                        # if the room was swapped (swapped_from set) — keep DB HK.
                        rs[rm]["group_label"]  = g.get("label","")
                        if not rs[rm].get("swapped_from"):
                            rs[rm]["housekeeper"] = g.get("housekeeper","")
                        rs[rm]["inspector"]    = g.get("inspector","")
                        rs[rm]["svc"]          = r.get("service","")
                        rs[rm]["guest"]        = r.get("guest","")
                        rs[rm]["pet"]          = r.get("pet","")
                        rs[rm]["late"]         = r.get("late_checkout","")
                        rs[rm]["bld"]          = r.get("bld","")

        # Load from DB on first visit to this tab, then init from schedule
        if not st.session_state.get("_live_loaded"):
            st.session_state["_live_loaded"] = True
            _load_statuses()
        _init_statuses_from_schedule()

        rs = st.session_state["room_statuses"]

        # ── Header bar ────────────────────────────────────────────────────────
        # Progress summary — only count non-DV rooms consistently
        _live_rooms = [r for r in rs.values() if r.get("svc","") != "Dust n Vac"]
        total_rooms_live = len(_live_rooms)
        n_clean   = sum(1 for r in _live_rooms if r.get("status") in ("already_clean","cleaning_done","inspected"))
        n_insp    = sum(1 for r in _live_rooms if r.get("status") == "inspected")
        n_active  = sum(1 for r in _live_rooms if r.get("status") == "cleaning_started")
        pct_done  = int(n_clean / max(total_rooms_live,1) * 100)

        st.markdown(f"""
    <div style="background:rgba(99,102,241,.08);border:1px solid rgba(99,102,241,.2);
                border-radius:12px;padding:14px 18px;margin-bottom:16px;
                display:flex;align-items:center;gap:20px;flex-wrap:wrap">
      <div style="flex:1;min-width:200px">
        <div style="font-family:'DM Mono',monospace;font-size:.6rem;color:#475569;
                    text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px">Overall Progress</div>
        <div style="background:rgba(255,255,255,.06);border-radius:99px;height:8px;overflow:hidden;border:1px solid rgba(255,255,255,.05)">
          <div style="background:linear-gradient(90deg,#6366f1,#22d3ee);width:{pct_done}%;height:8px;
                      border-radius:99px;box-shadow:0 0 8px rgba(99,102,241,.5);transition:width .4s"></div>
        </div>
        <div style="font-family:'DM Mono',monospace;font-size:.68rem;color:#94a3b8;margin-top:4px">
          {n_clean}/{total_rooms_live} rooms done &nbsp;·&nbsp; {pct_done}%
        </div>
      </div>
      <div style="display:flex;gap:12px;flex-wrap:wrap">
        <div style="text-align:center;background:rgba(251,191,36,.1);border:1px solid rgba(251,191,36,.25);
                    border-radius:8px;padding:8px 14px">
          <div style="font-family:'Syne',sans-serif;font-size:1.4rem;font-weight:800;color:#fbbf24;
                      text-shadow:0 0 10px rgba(251,191,36,.4)">{n_active}</div>
          <div style="font-size:.6rem;color:#94a3b8;font-family:'DM Mono',monospace;text-transform:uppercase;letter-spacing:.06em">Active</div>
        </div>
        <div style="text-align:center;background:rgba(96,165,250,.1);border:1px solid rgba(96,165,250,.25);
                    border-radius:8px;padding:8px 14px">
          <div style="font-family:'Syne',sans-serif;font-size:1.4rem;font-weight:800;color:#60a5fa;
                      text-shadow:0 0 10px rgba(96,165,250,.4)">{n_clean - n_insp}</div>
          <div style="font-size:.6rem;color:#94a3b8;font-family:'DM Mono',monospace;text-transform:uppercase;letter-spacing:.06em">Awaiting Insp</div>
        </div>
        <div style="text-align:center;background:rgba(167,139,250,.1);border:1px solid rgba(167,139,250,.25);
                    border-radius:8px;padding:8px 14px">
          <div style="font-family:'Syne',sans-serif;font-size:1.4rem;font-weight:800;color:#a78bfa;
                      text-shadow:0 0 10px rgba(167,139,250,.4)">{n_insp}</div>
          <div style="font-size:.6rem;color:#94a3b8;font-family:'DM Mono',monospace;text-transform:uppercase;letter-spacing:.06em">Inspected</div>
        </div>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
    """, unsafe_allow_html=True)

        lv1, lv2 = st.columns([1,1])
        with lv1:
            if st.button("🔄 Refresh", key="live_refresh", use_container_width=True):
                # Pull fresh status records from DB and merge onto schedule
                try:
                    fresh = db.get_room_statuses()
                    cur_rs = st.session_state.get("room_statuses", {})
                    for rm_code, rec in fresh.items():
                        if rm_code in cur_rs:
                            # keep schedule metadata, take DB status + timestamps
                            cur_rs[rm_code].update({
                                k: rec.get(k) for k in
                                ("status","started_at","cleaned_at","inspected_at",
                                 "marked_clean_at","housekeeper","swapped_from")
                                if rec.get(k) is not None
                            })
                        else:
                            cur_rs[rm_code] = rec
                    st.session_state["room_statuses"] = cur_rs
                except Exception:
                    pass
                _init_statuses_from_schedule()
                st.rerun()
        with lv2:
            if st.button("🔃 Reset All", key="live_reset", use_container_width=True):
                for rm in rs:
                    if rs[rm].get("status") != "pending":
                        rs[rm]["status"] = "pending"
                        for f in ["started_at","cleaned_at","inspected_at","marked_clean_at"]:
                            rs[rm].pop(f, None)
                st.rerun()

        st.markdown("</div></div>", unsafe_allow_html=True)

        # ── View filter ───────────────────────────────────────────────────────
        lf1, lf2, lf3, lf4 = st.columns([2,2,2,1])
        with lf1:
            live_view_insp = st.selectbox("🔍 Inspector",
                ["All"] + sorted(set(r.get("inspector","") for r in rs.values() if r.get("inspector","")), ),
                key="live_insp_filter")
        with lf2:
            live_view_hk = st.selectbox("🧑‍🔧 Housekeeper",
                ["All"] + sorted(set(r.get("housekeeper","") for r in rs.values() if r.get("housekeeper","")), ),
                key="live_hk_filter")
        with lf3:
            live_status_filter = st.selectbox("📊 Status",
                ["All"] + list(STATUS_META.keys()),
                key="live_status_filter",
                format_func=lambda s: f"{STATUS_META[s]['icon']} {STATUS_META[s]['label']}" if s != "All" else "All Statuses")
        with lf4:
            show_dv = st.checkbox("Show DV", value=False, key="live_show_dv")

        # ── Group rooms by inspector batch ────────────────────────────────────
        # Build inspector → groups → rooms mapping
        insp_groups: dict = {}
        for g in fg:
            if g.get("service_type") == "Dust n Vac" and not show_dv:
                continue
            insp_name = g.get("inspector","—")
            if live_view_insp != "All" and insp_name != live_view_insp: continue
            if insp_name not in insp_groups:
                insp_groups[insp_name] = []
            insp_groups[insp_name].append(g)

        if not insp_groups:
            st.markdown('<div style="text-align:center;padding:40px;color:#334155;font-family:\'DM Mono\',monospace">No groups match the current filters</div>', unsafe_allow_html=True)
        else:
            # Render each inspector section
            for insp_name, groups in sorted(insp_groups.items()):
                # Inspector header
                insp_rooms_all = [r for g in groups for r in g["rooms"]]
                insp_done = sum(1 for r in insp_rooms_all if rs.get(r["room"],{}).get("status") in ("already_clean","cleaning_done","inspected"))
                insp_pct  = int(insp_done / max(len(insp_rooms_all),1) * 100)

                st.markdown(f"""
    <div style="margin:16px 0 8px;display:flex;align-items:center;gap:10px">
      <div style="font-family:'Syne',sans-serif;font-weight:700;font-size:.95rem;color:#a5b4fc">{insp_name}</div>
      <div style="flex:1;background:rgba(255,255,255,.05);border-radius:99px;height:4px;overflow:hidden">
        <div style="background:linear-gradient(90deg,#6366f1,#22d3ee);width:{insp_pct}%;height:4px;border-radius:99px"></div>
      </div>
      <div style="font-family:'DM Mono',monospace;font-size:.65rem;color:#475569">{insp_done}/{len(insp_rooms_all)}</div>
    </div>""", unsafe_allow_html=True)

                # Render each group as a compact card
                for _gidx, g in enumerate(groups):
                    hk_name = g.get("housekeeper","—")
                    g_label = g.get("label","—")
                    _gk = f"{g_label}_{_gidx}"   # unique per-group key prefix

                    # Filter by HK
                    rooms_in_g = g["rooms"]
                    if live_view_hk != "All":
                        rooms_in_g = [r for r in rooms_in_g if rs.get(r["room"],{}).get("housekeeper","") == live_view_hk or g.get("housekeeper","") == live_view_hk]
                    if not rooms_in_g: continue

                    # Filter by status
                    if live_status_filter != "All":
                        rooms_in_g = [r for r in rooms_in_g if rs.get(r["room"],{}).get("status","pending") == live_status_filter]
                    if not rooms_in_g: continue

                    g_done = sum(1 for r in g["rooms"] if rs.get(r["room"],{}).get("status") in ("already_clean","cleaning_done","inspected"))
                    g_pct  = int(g_done / max(len(g["rooms"]),1) * 100)
                    g_color = "#6366f1" if g.get("service_type")==SVC_FC else ("#14b8a6" if g.get("service_type")==SVC_DS else "#f59e0b")

                    with st.expander(f"{g_label}  ·  🧑‍🔧 {hk_name}  ·  {g_done}/{len(g['rooms'])} done", expanded=(g_pct < 100)):

                        # ── Room swap UI ─────────────────────────────────────
                        swap_col, _ = st.columns([3,1])
                        with swap_col:
                            # Collect all HKs in same inspector batch for swap target
                            batch_hks = sorted(set(
                                gg.get("housekeeper","") for gg in fg
                                if gg.get("inspector","") == insp_name and gg.get("housekeeper","")
                            ))
                            if len(batch_hks) > 1:
                                st.markdown(f'<div style="font-family:\'DM Mono\',monospace;font-size:.62rem;color:#475569;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px">↕ Swap rooms to:</div>', unsafe_allow_html=True)
                                swap_target = st.selectbox(
                                    "Swap to HK", ["— select HK —"] + [h for h in batch_hks if h != hk_name],
                                    key=f"swap_target_{_gk}", label_visibility="collapsed"
                                )

                                if swap_target and swap_target != "— select HK —":
                                    # Show swappable rooms (pending or cleaning_started only)
                                    swappable = [r for r in g["rooms"] if rs.get(r["room"],{}).get("status","pending") in ("pending","cleaning_started")]
                                    if swappable:
                                        swap_rooms_sel = st.multiselect(
                                            "Rooms to swap",
                                            [r["room"] for r in swappable],
                                            key=f"swap_rooms_{_gk}",
                                            label_visibility="collapsed",
                                            placeholder="Select rooms to move..."
                                        )
                                        if swap_rooms_sel and st.button(f"↕ Move {len(swap_rooms_sel)} room(s) → {swap_target}", key=f"do_swap_{_gk}", type="primary"):
                                            # Find the target group
                                            tgt_group = next((gg for gg in fg if gg.get("housekeeper","") == swap_target and gg.get("inspector","") == insp_name), None)
                                            if tgt_group:
                                                for rm_code in swap_rooms_sel:
                                                    src_room = next((r for r in g["rooms"] if r["room"] == rm_code), None)
                                                    if src_room:
                                                        # Move room from source to target group in session data
                                                        g["rooms"].remove(src_room)
                                                        tgt_group["rooms"].append(src_room)
                                                        # Update status tracking
                                                        old_hk = rs.get(rm_code,{}).get("housekeeper","")
                                                        _save_status(rm_code, {
                                                            "housekeeper": swap_target,
                                                            "group_label": tgt_group.get("label",""),
                                                            "swapped_from": old_hk,
                                                        })
                                                st.success(f"✅ Moved {len(swap_rooms_sel)} room(s) to {swap_target}")
                                                st.rerun()

                        st.markdown("---")

                        # ── Room status rows ─────────────────────────────────
                        # Dedupe rooms within the group (a room can appear twice
                        # if upstream grouping duplicated it) so widget keys and
                        # the displayed list stay unique.
                        _seen_rm = set(); _dedup_rooms = []
                        for r in rooms_in_g:
                            _rc = r.get("room")
                            if _rc in _seen_rm: continue
                            _seen_rm.add(_rc); _dedup_rooms.append(r)
                        for _ridx, r in enumerate(_dedup_rooms):
                            rm = r["room"]
                            _rk = f"{_gk}_{_ridx}_{rm}"   # fully unique row key
                            r_state = rs.get(rm, {"status":"pending"})
                            cur_status = r_state.get("status","pending")
                            sm = STATUS_META.get(cur_status, STATUS_META["pending"])

                            # Timestamps (shared formatter; keep the ts[:5] fallback)
                            def _fmt_ts(ts):
                                return _fmt_mtn(ts) or (ts[:5] if ts else "")

                            ts_start = _fmt_ts(r_state.get("started_at",""))
                            ts_clean = _fmt_ts(r_state.get("cleaned_at",""))
                            ts_insp  = _fmt_ts(r_state.get("inspected_at",""))
                            ts_ac    = _fmt_ts(r_state.get("marked_clean_at",""))

                            pet_icon  = " 🐾" if r.get("pet") else ""
                            late_html = (f'<span style="font-family:\'DM Mono\',monospace;font-size:.6rem;'
                                         f'color:#f59e0b;background:rgba(245,158,11,.12);border-radius:4px;'
                                         f'padding:1px 5px;margin-left:4px">⏰ {r.get("late_checkout","")}</span>'
                                         if r.get("late_checkout") else "")
                            guest_disp = r.get("guest","")
                            if len(guest_disp) > 22: guest_disp = guest_disp[:21]+"…"

                            # ── Info line: room + guest + animated status pill ──
                            _is_active = (cur_status == "cleaning_started")
                            _dot = (f'<span style="display:inline-block;width:6px;height:6px;'
                                    f'border-radius:50%;background:{sm["color"]};margin-right:5px;'
                                    f'vertical-align:middle;'
                                    + ('animation:pulseDot 1.1s ease-in-out infinite;' if _is_active else '')
                                    + '"></span>')
                            _ring = 'animation:statusPop .35s cubic-bezier(.34,1.56,.64,1) both' \
                                    + (',ringPulse 2s ease-out infinite' if _is_active else '')
                            st.markdown(
                                f'<div style="display:flex;align-items:center;justify-content:space-between;'
                                f'gap:8px;flex-wrap:wrap;padding:7px 10px;background:rgba(255,255,255,.02);'
                                f'border:1px solid rgba(99,102,241,.1);border-radius:8px;margin-bottom:4px">'
                                f'  <div style="display:flex;align-items:center;gap:8px;min-width:0;flex:1">'
                                f'    <span style="font-family:\'DM Mono\',monospace;font-size:.82rem;'
                                f'font-weight:600;color:#6366f1;white-space:nowrap">{rm}</span>'
                                f'    <span style="font-size:.76rem;color:#94a3b8;overflow:hidden;'
                                f'text-overflow:ellipsis;white-space:nowrap">{guest_disp}{pet_icon}</span>'
                                f'    {late_html}'
                                f'  </div>'
                                f'  <div style="background:{sm["bg"]};border:1px solid {sm["border"]};'
                                f'border-radius:6px;padding:3px 9px;font-size:.68rem;font-weight:600;'
                                f'color:{sm["color"]};white-space:nowrap;flex-shrink:0;{_ring}">'
                                f'{_dot}{sm["icon"]} {sm["label"]}</div>'
                                f'</div>', unsafe_allow_html=True)

                            # ── Action button row — 4 equal columns, stays horizontal ──
                            bc1, bc2, bc3, bc4 = st.columns(4)
                            with bc1:
                                if cur_status == "pending":
                                    if st.button("✨ Clean", key=f"ac_{_rk}", use_container_width=True):
                                        _save_status(rm, {"status":"already_clean","marked_clean_at":_NOW()})
                                        st.session_state["_live_toast"] = f"✨ {rm} marked Already Clean"
                                        st.rerun()
                                elif cur_status == "already_clean":
                                    if st.button("↩ Undo", key=f"undo_ac_{_rk}", use_container_width=True):
                                        _save_status(rm, {"status":"pending","marked_clean_at":None})
                                        st.session_state["_live_toast"] = f"↩ {rm} back to Pending"
                                        st.rerun()
                            with bc2:
                                if cur_status == "pending":
                                    if st.button("🧹 Start", key=f"start_{_rk}", use_container_width=True):
                                        _save_status(rm, {"status":"cleaning_started","started_at":_NOW()})
                                        st.session_state["_live_toast"] = f"🧹 {rm} — cleaning started"
                                        st.rerun()
                                elif cur_status == "cleaning_started":
                                    if st.button("✅ Done", key=f"done_{_rk}", use_container_width=True):
                                        _save_status(rm, {"status":"cleaning_done","cleaned_at":_NOW()})
                                        st.session_state["_live_toast"] = f"✅ {rm} — cleaning done, awaiting inspection"
                                        st.rerun()
                            with bc3:
                                if cur_status == "cleaning_done":
                                    if st.button("🔍 Inspect", key=f"insp_{_rk}", use_container_width=True):
                                        _save_status(rm, {"status":"inspected","inspected_at":_NOW()})
                                        st.session_state["_live_toast"] = f"🔍 {rm} inspected ✓"
                                        st.rerun()
                                elif cur_status == "inspected":
                                    st.markdown(f'<div style="font-family:\'DM Mono\',monospace;font-size:.64rem;color:#a78bfa;padding:8px 0;text-align:center">✓ {ts_insp}</div>', unsafe_allow_html=True)
                            with bc4:
                                if cur_status != "pending":
                                    if st.button("↩ Reset", key=f"reset_{_rk}", use_container_width=True, help="Reset to Pending"):
                                        _save_status(rm, {
                                            "status":"pending",
                                            "started_at":None,"cleaned_at":None,
                                            "inspected_at":None,"marked_clean_at":None
                                        })
                                        st.rerun()

                            # Timestamp trail under each room
                            ts_parts = []
                            if ts_ac:    ts_parts.append(f"✨ {ts_ac}")
                            if ts_start: ts_parts.append(f"🧹 {ts_start}")
                            if ts_clean: ts_parts.append(f"✅ {ts_clean}")
                            if ts_insp:  ts_parts.append(f"🔍 {ts_insp}")
                            if ts_parts:
                                st.markdown(
                                    f'<div style="font-family:\'DM Mono\',monospace;font-size:.6rem;'
                                    f'color:#334155;padding:0 0 4px 8px;letter-spacing:.04em">'
                                    f'{"  ·  ".join(ts_parts)}</div>',
                                    unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    export_rows=[]
    for g in fg:
        is_verify = g.get("verify_group", False)
        for r in g["rooms"]:
            export_rows.append({
                "Room":r.get("room",""),"Service":r.get("service",""),
                "Time (min)":r.get("time",""),"Pet":r.get("pet",""),
                "Current Guest or Status":r.get("guest",""),
                "Late Checkout":r.get("late_checkout",""),
                # Verify rooms (stayover / P-U Models) get NO housekeeper or RQS
                "Housekeeper":"" if is_verify else g.get("housekeeper",""),
                "RQS":"" if is_verify else g.get("inspector",""),
                "Notes":r.get("notes",""),"Status":r.get("status",""),
                "Stripping":"","Carpet":"","Arriving Guest":r.get("arriving",""),
                "Group":("VERIFY — assign manually" if is_verify else g["label"]),
                "Service Type":g.get("service_type",""),
                "Building":f"Building {r.get('bld','')}",
                "Group Total (min)":("" if is_verify else g["time"]),
                "Cross-Building":"Yes" if g.get("cross_bld") else "No",
                "Verify":"Yes" if is_verify else "No",
                "Uncertain":"Yes" if r.get("uncertain") else "No",
            })
    export_df = pd.DataFrame(export_rows)
    # Order: confirmed groups first, then uncertain, then verify rooms dead last.
    if not export_df.empty and "Verify" in export_df.columns:
        normal      = export_df[(export_df["Verify"]=="No") & (export_df["Uncertain"]=="No")].sort_values("Group")
        unconfirmed = export_df[(export_df["Verify"]=="No") & (export_df["Uncertain"]=="Yes")].sort_values("Group")
        verify_rows = export_df[export_df["Verify"]=="Yes"]
        export_df   = pd.concat([normal,unconfirmed,verify_rows],ignore_index=True)
    # utf-8-sig adds a BOM so Excel reads emoji/accents correctly (no more mojibake)
    csv = export_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Download CSV", data=csv, file_name="cleaning_schedule.csv", mime="text/csv")
