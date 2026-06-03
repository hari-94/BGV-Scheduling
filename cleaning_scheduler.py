"""
Cleaning Schedule Grouper  v10
════════════════════════════════
HOW TO RUN:
  streamlit run cleaning_scheduler.py

DO NOT run with: python cleaning_scheduler.py
"""
# run with: streamlit run cleaning_scheduler.py
import re, html as _html
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import sys as _sys2, os as _os2
_sys2.path.insert(0, _os2.path.dirname(__file__))
import auth, db

st.set_page_config(
    page_title="Cleaning Schedule",
    page_icon="🧹",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Hide the default auto-generated page navigation items we don't want
# (Login page removed; sidebar nav controlled via CSS)
st.markdown("""<style>
/* Hide any auto-nav items referencing login */
[data-testid="stSidebarNavItems"] a[href$="Login"],
[data-testid="stSidebarNavItems"] a[href$="0_Login"],
[data-testid="stSidebarNavLink"]:has(p:contains("Login")) { display:none!important }
</style>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
def e(s): return _html.escape(str(s) if s else "")

def make_labels(prefix: str, n: int) -> list:
    """Generate labels: FC-A, FC-B ... FC-Z, FC-AA, FC-AB ..."""
    alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    out = []
    # single letters A-Z
    for c in alpha:
        out.append(f"{prefix}-{c}")
        if len(out) >= n: return out
    # double letters AA, AB ...
    for c1 in alpha:
        for c2 in alpha:
            out.append(f"{prefix}-{c1}{c2}")
            if len(out) >= n: return out
    return out
LOW_MIN  = 330
MAX_FC   = 380
MAX_DS   = 460
DS_OVER  = 600   # hard ceiling for overflow last DS group
LOW_FILL = 350   # top-up threshold: groups below this get extra rooms if possible

SVC_FC   = "Full Clean"
SVC_DS   = "Daily Service"
SVC_DV   = "Dust n Vac"

# ── Default times by room type (last letter) × service ───────────────────────
# Derived from property reference data: A/D=large, B/C/F/G/H/I=small, E=suite
DEFAULT_TIMES = {
    SVC_FC: {"A":120,"B":70,"C":70,"D":120,"E":140,"F":70,"G":70,"H":70,"I":70},
    SVC_DS: {"A":35, "B":20,"C":20,"D":35, "E":40, "F":20,"G":20,"H":20,"I":20},
    SVC_DV: {},   # DV has no standard time — kept as 0 / shown as "—"
}
DV_DEFAULT_TIME = 0   # DV rooms are untimed

def default_time_for(room: str, svc: str) -> int:
    """Return the default time for a room based on its last letter and service type."""
    room_type = ""
    for ch in reversed(str(room).strip().upper()):
        if ch.isalpha(): room_type = ch; break
    lookup = DEFAULT_TIMES.get(svc, {})
    return lookup.get(room_type, 70)  # fallback 70 if type unknown

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
    SVC_DS: ("#0D9488","#ECFDF5"),
    SVC_DV: ("#D97706","#FFFBEB"),
}
IC = ["#5B4FE9","#0D9488","#D97706","#DC2626","#7C3AED","#0891B2","#EA580C","#DB2777"]
BLD_COLORS = {1:("#2563EB","#EFF6FF"), 2:("#0D9488","#ECFDF5"), 3:("#D97706","#FFFBEB")}

def pal(i): return PALETTE[i % len(PALETTE)]

# ── Default staff ─────────────────────────────────────────────────────────────
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
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,400&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Reset & base ── */
*,*::before,*::after{box-sizing:border-box;}
html,body,[class*="css"]{font-family:'Inter',sans-serif;-webkit-font-smoothing:antialiased;}
.block-container{padding-top:1.4rem!important;max-width:1440px;}

/* ── Page header ── */
.pg-title{
  font-size:1.75rem;font-weight:800;letter-spacing:-.8px;
  background:linear-gradient(135deg,#1e293b 0%,#3B4FE4 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text;margin:0 0 3px;line-height:1.15;
}
.pg-sub{font-size:.83rem;color:#64748b;margin:0 0 .8rem;font-weight:400}

/* ── Section label ── */
.sec{
  font-size:.65rem;font-weight:700;text-transform:uppercase;
  letter-spacing:.12em;color:#94a3b8;
  padding-bottom:5px;border-bottom:1.5px solid #f1f5f9;
  margin:1.1rem 0 .5rem;
}

/* ── Stat cards ── */
.stat-row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:1rem}
.sc{
  flex:1 1 100px;background:#fff;border:1px solid #e8edf5;
  border-radius:14px;padding:14px 13px;text-align:center;
  box-shadow:0 1px 4px rgba(0,0,0,.05),0 4px 12px rgba(0,0,0,.03);
  transition:transform .15s,box-shadow .15s;
}
.sc:hover{transform:translateY(-1px);box-shadow:0 4px 16px rgba(0,0,0,.08)}
.sc.hi{background:linear-gradient(135deg,#5B4FE9 0%,#7C6FF5 100%);border:none}
.sc.ds{background:linear-gradient(135deg,#0D9488 0%,#14B8A6 100%);border:none}
.sc.dv{background:linear-gradient(135deg,#D97706 0%,#F59E0B 100%);border:none}
.sc .n{font-size:1.65rem;font-weight:800;color:#0f172a;line-height:1;margin-bottom:2px}
.sc.hi .n,.sc.hi .l,.sc.ds .n,.sc.ds .l,.sc.dv .n,.sc.dv .l{color:#fff}
.sc .l{font-size:.6rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;font-weight:600}

/* ── Rules box ── */
.rules-box{
  background:linear-gradient(135deg,#f0f9ff 0%,#e8f4fd 100%);
  border:1px solid #bae6fd;border-radius:12px;
  padding:14px 18px;font-size:.82rem;color:#0c4a6e;
}
.rules-box li{margin-bottom:5px;line-height:1.55}

/* ── Sidebar — works in both light and dark mode ── */
section[data-testid="stSidebar"]{
  min-width:360px!important;max-width:400px!important;
  border-right:1px solid rgba(128,128,128,.15)!important;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{
  font-size:.8rem;
}
section[data-testid="stSidebar"] h2{
  font-size:.9rem!important;font-weight:700!important;
  letter-spacing:-.2px;padding-bottom:6px;margin-bottom:8px;
  border-bottom:1.5px solid rgba(128,128,128,.2);
}
section[data-testid="stSidebar"] h3{
  font-size:.75rem!important;font-weight:700!important;
  text-transform:uppercase;letter-spacing:.08em;
  margin:10px 0 5px!important;opacity:.7;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"]{
  gap:4px;background:#f1f5f9;border-radius:10px;padding:3px;
  border:none!important;
}
.stTabs [data-baseweb="tab"]{
  border-radius:8px!important;padding:6px 16px!important;
  font-size:.78rem!important;font-weight:600!important;
  color:#64748b!important;border:none!important;background:transparent!important;
  transition:all .15s!important;
}
.stTabs [aria-selected="true"]{
  background:#fff!important;color:#1e293b!important;
  box-shadow:0 1px 4px rgba(0,0,0,.1)!important;
}

/* ── Buttons ── */
.stButton > button{
  border-radius:10px!important;font-weight:600!important;
  font-size:.82rem!important;transition:all .15s!important;
  border:1px solid #e2e8f0!important;
}
.stButton > button[kind="primary"]{
  background:linear-gradient(135deg,#5B4FE9,#7C6FF5)!important;
  border:none!important;color:#fff!important;
  box-shadow:0 2px 8px rgba(91,79,233,.35)!important;
  letter-spacing:.01em;
}
.stButton > button[kind="primary"]:hover{
  box-shadow:0 4px 16px rgba(91,79,233,.45)!important;
  transform:translateY(-1px);
}

/* ── Input fields ── */
.stTextArea textarea, .stTextInput input{
  border-radius:10px!important;border:1.5px solid #e2e8f0!important;
  font-family:'JetBrains Mono',monospace!important;font-size:.78rem!important;
  transition:border-color .15s!important;
}
.stTextArea textarea:focus, .stTextInput input:focus{
  border-color:#5B4FE9!important;
  box-shadow:0 0 0 3px rgba(91,79,233,.12)!important;
}

/* ── Multiselect + selectbox ── */
.stMultiSelect [data-baseweb="select"] > div,
.stSelectbox [data-baseweb="select"] > div{
  border-radius:10px!important;border:1.5px solid #e2e8f0!important;
}

/* ── Expander ── */
.streamlit-expanderHeader{
  font-size:.8rem!important;font-weight:600!important;
  color:#475569!important;border-radius:10px!important;
}

/* ── Checkboxes ── */
.stCheckbox label{font-size:.78rem!important;font-weight:500!important;}

/* ── Main area divider ── */
hr{border:none!important;border-top:1.5px solid #f1f5f9!important;margin:1rem 0!important}

/* ── Sidebar building label pills ── */
.bld-pill{
  display:inline-flex;align-items:center;gap:5px;
  border-radius:8px;padding:4px 10px;font-size:.7rem;font-weight:700;
  margin:6px 0 3px;letter-spacing:.03em;
}

/* ── Scrollbar ── */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:10px}
::-webkit-scrollbar-thumb:hover{background:#94a3b8}

/* ── Tab content fade-in ── */
@keyframes fadeSlideIn{
  from{opacity:0;transform:translateY(6px)}
  to{opacity:1;transform:translateY(0)}
}
.stTabs [data-baseweb="tab-panel"]{
  animation:fadeSlideIn .22s ease both;
}

/* ── Generate button pulse on load ── */
@keyframes pulseGlow{
  0%{box-shadow:0 2px 8px rgba(91,79,233,.35)}
  50%{box-shadow:0 4px 20px rgba(91,79,233,.6),0 0 0 4px rgba(91,79,233,.12)}
  100%{box-shadow:0 2px 8px rgba(91,79,233,.35)}
}
.stButton > button[kind="primary"]{
  animation:pulseGlow 2.5s ease-in-out infinite;
}
.stButton > button[kind="primary"]:hover{
  animation:none;
  box-shadow:0 6px 20px rgba(91,79,233,.55)!important;
  transform:translateY(-2px)!important;
}

/* ── Stat card entrance animation ── */
@keyframes cardIn{
  from{opacity:0;transform:translateY(8px) scale(.98)}
  to{opacity:1;transform:translateY(0) scale(1)}
}
.stat-row .sc{
  animation:cardIn .3s ease both;
}
.stat-row .sc:nth-child(1){animation-delay:.02s}
.stat-row .sc:nth-child(2){animation-delay:.05s}
.stat-row .sc:nth-child(3){animation-delay:.08s}
.stat-row .sc:nth-child(4){animation-delay:.11s}
.stat-row .sc:nth-child(5){animation-delay:.14s}
.stat-row .sc:nth-child(6){animation-delay:.17s}
.stat-row .sc:nth-child(7){animation-delay:.20s}
.stat-row .sc:nth-child(8){animation-delay:.23s}

/* ── Sidebar checkbox rows ── */
section[data-testid="stSidebar"] .stCheckbox{
  padding:1px 0;
  transition:background .1s;
  border-radius:6px;
}
section[data-testid="stSidebar"] .stCheckbox:hover{
  background:rgba(91,79,233,.06);
}

/* ── Success/info/warning boxes ── */
.stAlert{border-radius:12px!important;border:none!important;font-size:.82rem!important}

/* ── Expander ── */
.streamlit-expanderContent{
  animation:fadeSlideIn .18s ease both;
}

/* hide login from nav */
section[data-testid='stSidebar'] a[href*='Login']{display:none!important}</style>
""", unsafe_allow_html=True)

SHARED_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');
*{box-sizing:border-box;margin:0;padding:0;font-family:'Inter',sans-serif;-webkit-font-smoothing:antialiased;}
body{background:transparent;}
@keyframes cardFadeIn{
  from{opacity:0;transform:translateY(8px)}
  to{opacity:1;transform:translateY(0)}
}
div[style*="border-radius:14px"]{
  animation:cardFadeIn .25s ease both;
}
</style>"""

# ══════════════════════════════════════════════════════════════════════════════
#  SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════
def _init_state():
    if "hk_roster" not in st.session_state:
        roster = {}
        for bld, names in DEFAULT_HK.items():
            for n in names:
                roster[n] = {"building": bld, "present": True}
        st.session_state["hk_roster"] = roster
    if "insp_roster" not in st.session_state:
        st.session_state["insp_roster"] = {n: True for n in DEFAULT_INSPECTORS}
    for k in ("groups_data","total_rooms","inspectors_data","used_hk_set","last_email",
              "rqs1","rqs2"):
        if k not in st.session_state:
            st.session_state[k] = None

_init_state()
auth.init_auth()

# ══════════════════════════════════════════════════════════════════════════════
#  INLINE LOGIN GATE  (renders login form on this page if not authenticated)
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.get("logged_in"):
    st.markdown("""
<style>
.block-container{padding-top:4rem!important;max-width:420px!important;}
.login-wrap{background:#fff;border:1px solid #e2e8f0;border-radius:20px;
  padding:36px;box-shadow:0 4px 24px rgba(0,0,0,.1);}
.login-title{font-size:1.5rem;font-weight:800;letter-spacing:-.5px;
  background:linear-gradient(135deg,#1e293b,#5B4FE9);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text;text-align:center;margin:0 0 4px}
.login-sub{font-size:.82rem;color:#64748b;text-align:center;margin:0 0 20px}
.stButton>button{width:100%!important;border-radius:10px!important;font-weight:700!important;
  background:linear-gradient(135deg,#5B4FE9,#7C6FF5)!important;border:none!important;
  color:#fff!important;padding:10px!important;box-shadow:0 2px 8px rgba(91,79,233,.3)!important;}
</style>""", unsafe_allow_html=True)

    st.markdown('<p class="login-title">🧹 Cleaning Schedule</p>', unsafe_allow_html=True)
    st.markdown('<p class="login-sub">Sign in to continue</p>', unsafe_allow_html=True)

    # DB connection check
    _db_ok = True
    _db_msg = ""
    try:
        db.ensure_admin_exists()
    except Exception as _ex:
        _db_ok = False
        _db_msg = str(_ex)

    if not _db_ok:
        st.error(f"⚠️ Database not connected. Check `.streamlit/secrets.toml`\n\n`{_db_msg}`")
        st.markdown("""
**Fix:** Edit `.streamlit/secrets.toml` and set:
```toml
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_KEY = "eyJ..."
```""")
        st.stop()

    with st.form("login_form"):
        _uname = st.text_input("Username", placeholder="Enter username")
        _pw    = st.text_input("Password", placeholder="Enter password", type="password")
        _sub   = st.form_submit_button("Sign In", type="primary", use_container_width=True)

    if _sub:
        if not _uname or not _pw:
            st.error("Please enter both username and password.")
        else:
            _user = db.authenticate(_uname.strip(), _pw)
            if _user:
                auth.login(_user)
                st.rerun()
            else:
                st.error("Invalid username or password.")

    st.stop()

# ════════════════════════════════════════════════════════════════════════════
#  PARSING HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def normalize_service(raw: str) -> str:
    # Normalise whitespace and case
    s = re.sub(r'\s+', ' ', str(raw).strip().lower())
    # Daily Service — check before "dust" so "daily" doesn't fall through
    if "daily" in s:
        return SVC_DS
    # Full Clean variants (including IH)
    if s.startswith("full clean") or s.startswith("fc"):
        return SVC_FC
    # Dust n Vac — all known variants
    # exact: "dust n vac", "dust n' vac", "dust & vac", "dust and vac",
    #        "dust vac", "dustvac", "d&v", "dnv", "dust n vac"
    if ("dust" in s or "d&v" in s or "dnv" in s or
            s.startswith("d") and "vac" in s):
        return SVC_DV
    if "vac" in s:
        return SVC_DV
    # Default anything else to Full Clean
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
    """
    Expand compound room numbers into individual rooms.
    3031EF -> [3031E, 3031F]  (consecutive letters)
    3010CD -> [3010C, 3010D]
    3029EG -> [3029EG]        (E and G not consecutive -> single room)
    """
    m = re.match(r'^([1-9]\d{3})([A-Z]{2,4})$', room_str.upper())
    if not m:
        return [room_str.upper()]
    base, suffix = m.group(1), m.group(2)
    if len(suffix) == 2 and ord(suffix[1]) == ord(suffix[0]) + 1:
        return [f"{base}{suffix[0]}", f"{base}{suffix[1]}"]
    return [room_str.upper()]


def expand_rooms(raw_list: list) -> list:
    return [r for s in raw_list for r in expand_compound_room(s)]


def parse_email_notes(text: str) -> dict:
    """
    Robust email parser using pattern-first recognition:
    - Section headers: lines ending with ":" (e.g. "Late Checkouts:", "Dogs Arriving:")
    - Time slots: any line containing HH:MM am/pm — sets current late-checkout time
    - Room numbers: 4-digit + letters, compound rooms (3031EF) expanded to individuals
    - Works regardless of bullet character (*, •, ◦) or indentation level
    """
    late_co: dict = {}
    notes:   dict = {}
    if not text or not text.strip():
        return {"late_checkout": late_co, "notes": notes}

    ROOM_RE    = re.compile(r'\b([1-9]\d{3}[A-Z]{1,4})\b')
    TIME_RE    = re.compile(r'\b(\d{1,2}:\d{2}\s*(?:am|pm))\b', re.IGNORECASE)
    SECTION_RE = re.compile(r'^([A-Za-z][A-Za-z &\'/]+):\s*$')
    MOVE_RE    = re.compile(r'([1-9]\d{3}[A-Z]{1,4})\s*[-\u2013]\s*([1-9]\d{3}[A-Z]{1,4})')
    CELEB_RE   = re.compile(r'^(Birthday|Anniversary|Misc\.?)$', re.IGNORECASE)
    # Strip any leading bullet character and whitespace
    DEBULLET   = re.compile(r'^[\s\t]*[*\u2022\u25e6\u2023\u2043\-]?\s*')

    NOTE_LABELS = {
        "vip inspections":  "VIP",
        "room moves":       "Room Move",
        "stayovers":        "Stayover",
        "robes":            "Robes",
        "pack n play":      "Pack n Play",
        "highchairs":       "Highchair",
        "rollaway":         "Rollaway",
        "special requests": "Special Request",
        "dogs arriving":    "Dog arriving",
        "celebrations":     "Celebration",
        "early ins":        "Early In",
        "late arrival":     "Late Arrival",
    }
    LATE_KEY = "late checkouts"

    section   = None
    sub_label = None   # celebrations sub-type
    late_time = None   # current time slot in late checkouts

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # ── Section header detection ──────────────────────────────────────────
        # A header ends with ":" and contains no room numbers
        hdr_m = SECTION_RE.match(stripped)
        if hdr_m and not ROOM_RE.search(stripped):
            hdr_key = hdr_m.group(1).strip().lower()
            if hdr_key in NOTE_LABELS or hdr_key == LATE_KEY:
                section   = hdr_key
                sub_label = None
                late_time = None
                continue

        # Strip bullet prefix to get clean content
        content = DEBULLET.sub('', line).strip()
        if not content or content.lower() == "n/a":
            continue

        # ── Late Checkouts ────────────────────────────────────────────────────
        if section == LATE_KEY:
            time_m = TIME_RE.search(content)
            rooms  = expand_rooms(ROOM_RE.findall(content.upper()))

            if time_m:
                # Normalise: "11:00  am" -> "11:00 am"
                late_time = re.sub(r'\s+', ' ', time_m.group(1).strip())
                # If rooms also on same line as time, assign immediately
                for rm in rooms:
                    late_co[rm] = f"Late Out: {late_time}"
            elif rooms and late_time:
                for rm in rooms:
                    late_co[rm] = f"Late Out: {late_time}"
            continue

        # ── All other sections ────────────────────────────────────────────────
        if not section or section not in NOTE_LABELS:
            continue

        label = NOTE_LABELS[section]

        # Room moves: "3251H - 3242A"
        if section == "room moves":
            for mv in MOVE_RE.finditer(content.upper()):
                for rf in expand_compound_room(mv.group(1)):
                    for rt in expand_compound_room(mv.group(2)):
                        notes.setdefault(rf, []).append(f"Room Move → {rt}")
                        notes.setdefault(rt, []).append(f"Room Move ← {rf}")
            continue

        # Celebrations sub-type header
        if section == "celebrations":
            cm = CELEB_RE.match(content)
            if cm:
                t = cm.group(1).strip()
                sub_label = None if t.lower().startswith("misc") else t
                continue
            if sub_label:
                label = f"Celebration ({sub_label})"

        rooms = expand_rooms(ROOM_RE.findall(content.upper()))
        if not rooms:
            continue

        qty   = re.search(r'x(\d+)', content, re.IGNORECASE)
        qty_s = f" x{qty.group(1)}" if qty else ""
        for rm in rooms:
            notes.setdefault(rm, []).append(f"{label}{qty_s}")

    return {"late_checkout": late_co, "notes": notes}
def parse_rooms(text: str) -> pd.DataFrame:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if not lines: return pd.DataFrame()
    rows = [re.split(r"\t", l) for l in lines]
    header = [c.strip().lower() for c in rows[0]]

    def col(*names):
        for n in names:
            for i, h in enumerate(header):
                if n in h: return i
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
        if ti <= 0:
            if norm_svc == SVC_DV:
                ti = DV_DEFAULT_TIME  # DV rooms are untimed — keep with 0
            else:
                # Use default time based on room type × service
                ti = default_time_for(room, norm_svc)
                if ti <= 0:
                    continue  # still 0 — skip
        records.append({
            "Room":get(row,i_room),"Service":norm_svc,
            "ServiceRaw":svc,   # keep original for debugging
            "Time":ti,"Pet":get(row,i_pet),"Guest":get(row,i_guest),
            "LateCheckout":get(row,i_late),"Status":get(row,i_status),
            "NotesRaw":get(row,i_notes),"ArrivingGuest":get(row,i_arriving),
            "ResType":get(row,i_restype),
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
            if gr.get("bld",0) != ur.get("bld",0): total += 200
            elif gr.get("floor",0) != ur.get("floor",0): total += 20
            else: total += min(abs(gr.get("num",0)-ur.get("num",0))//10, 9)
            count += 1
    return total // max(count,1)

def can_add_fc(g, unit):
    if g.get("service_type") != SVC_FC: return False
    ut = sum(r["time"] for r in unit)
    if g["time"]+ut > MAX_FC: return False
    for r in unit:
        if not bld_ok(g["blds"], r["bld"]): return False
    u140 = sum(1 for r in unit if r["time"]==140)
    u120 = sum(1 for r in unit if r["time"]==120)
    if g["c140"]+u140 > 1: return False
    if g["c140"]+u140>=1 and g["c120"]+u120>=1:
        if g["c140"]>=1 and g["c120"]>=1 and sum(1 for r in unit if r["time"]!=70)>0:
            return False
    return True

def can_add_ds(g, unit, allow_overflow=False):
    if g.get("service_type") != SVC_DS: return False
    ut = sum(r["time"] for r in unit)
    cap = DS_OVER if allow_overflow else MAX_DS
    if g["time"]+ut > cap: return False
    for r in unit:
        if not bld_ok(g["blds"], r["bld"]): return False
    return True

def can_add_dv(g, unit):
    if g.get("service_type") != SVC_DV: return False
    # DV rooms are untimed (time=0), no cap needed but keep building rules
    for r in unit:
        if not bld_ok(g["blds"], r["bld"]): return False
    return True

def unit_ok_fc(unit):
    blds = set(r["bld"] for r in unit)
    ba = list(blds)
    for i in range(len(ba)):
        for j in range(i+1,len(ba)):
            if (ba[i]==2 and ba[j]==3) or (ba[i]==3 and ba[j]==2): return False
    return sum(1 for r in unit if r["time"]==140) <= 1

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

def best_fit_generic(groups, unit, can_add_fn, same_bld_only, same_floor_only):
    """
    Best-fit with proximity awareness.
    Score = proximity * 10000 + remaining_capacity_after_add
    Lower proximity wins strongly; among equal proximity the group that ends
    up most FULL (least remaining space) wins — maximising HK productivity.
    """
    ub  = set(r["bld"]        for r in unit)
    uf  = set(r.get("floor",0) for r in unit)
    u_t = sum(r["time"]        for r in unit)
    cap = MAX_DS if (unit and unit[0].get("service")==SVC_DS) else MAX_FC

    bi, best_score = -1, float("inf")
    for i, g in enumerate(groups):
        if not can_add_fn(g, unit): continue
        if same_bld_only   and not same_bld(g["blds"], ub):    continue
        if same_floor_only and not (g["floors"] & uf):          continue
        prx = proximity_score(g["rooms"], unit)
        rem = cap - (g["time"] + u_t)          # remaining after adding
        # Combined score: proximity dominates, remaining breaks ties
        score = prx * 10000 + rem
        if score < best_score:
            best_score, bi = score, i
    return bi

def pack_rooms(room_list, svc, can_add_fn, unit_ok_fn):
    if not room_list: return []
    gmap = {}
    for r in room_list: gmap.setdefault(r["guest"],[]).append(r)
    seen, units = set(), []
    for r in room_list:
        if r["guest"] not in seen:
            seen.add(r["guest"]); units.append(gmap[r["guest"]])
    units.sort(key=lambda u:(u[0].get("bld",0),u[0].get("floor",0),-sum(r["time"] for r in u)))
    groups = []
    for unit in units:
        if not unit_ok_fn(unit):
            for r in unit:
                s=[r]
                i=best_fit_generic(groups,s,can_add_fn,True,True)
                if i==-1: i=best_fit_generic(groups,s,can_add_fn,True,False)
                if i==-1: i=best_fit_generic(groups,s,can_add_fn,False,False)
                if i>=0: absorb(groups[i],s)
                else: groups.append(mk(s,svc))
            continue
        i=best_fit_generic(groups,unit,can_add_fn,True,True)
        if i==-1: i=best_fit_generic(groups,unit,can_add_fn,True,False)
        if i==-1: i=best_fit_generic(groups,unit,can_add_fn,False,False)
        if i>=0: absorb(groups[i],unit)
        else: groups.append(mk(unit,svc))
    # ── merge pass: collapse tiny groups into larger ones ────────────────────
    improved=True
    while improved:
        improved=False
        for i in range(len(groups)-1,-1,-1):
            if not groups[i]["rooms"]: continue
            s=groups[i]
            for sf in (True,False):
                for sb in (True,False):
                    if sf and not sb: continue
                    for j in range(len(groups)):
                        if i==j or not groups[j]["rooms"]: continue
                        if not can_add_fn(groups[j],s["rooms"]): continue
                        if sb and not same_bld(groups[j]["blds"],s["blds"]): continue
                        if sf and not (groups[j]["floors"] & s["floors"]): continue
                        absorb(groups[j],s["rooms"]); s["rooms"]=[]; s["time"]=0
                        improved=True; break
                    if improved: break
                if improved: break
            if improved: break

    # ── top-up pass: maximise every group's fill level ─────────────────────────
    cap = MAX_DS if svc == SVC_DS else MAX_FC
    active = [g for g in groups if g["rooms"]]

    # Multiple rounds: keep passing until no more improvement possible
    for _round in range(5):
        changed = False
        # Sort under-filled groups most-empty first so they get first pick
        targets = sorted([g for g in active if g["time"] < LOW_FILL],
                         key=lambda g: g["time"])
        for target in targets:
            # Candidate rooms: from any group that has >1 room and won't
            # drop below LOW_FILL itself by donating
            candidates = []
            for donor in active:
                if donor is target: continue
                if len(donor["rooms"]) <= 1: continue
                for room in donor["rooms"]:
                    # donor still viable after giving this room?
                    donor_after = donor["time"] - room["time"]
                    if donor_after < 120: continue   # don't strip donor too bare
                    if can_add_fn(target, [room]):
                        # Score: prefer room that fills target best without wasting
                        remaining = cap - (target["time"] + room["time"])
                        candidates.append((remaining, room, donor))
            # Pick the room that leaves least remaining space (best fit)
            candidates.sort(key=lambda x: x[0])
            for remaining, room, donor in candidates:
                if remaining < 0: continue
                # Double-check still valid (target may have grown from earlier pick)
                if not can_add_fn(target, [room]): continue
                absorb(target, [room])
                donor["rooms"].remove(room)
                donor["time"]  -= room["time"]
                donor["c140"]  -= (1 if room["time"]==140 else 0)
                donor["c120"]  -= (1 if room["time"]==120 else 0)
                donor["blds"]   = set(r["bld"] for r in donor["rooms"]) if donor["rooms"] else set()
                donor["floors"] = set(r.get("floor",0) for r in donor["rooms"]) if donor["rooms"] else set()
                changed = True
                if target["time"] >= LOW_FILL: break
        if not changed:
            break

    # Remove any groups that became empty after donation
    return [g for g in groups if g["rooms"]]

def build_all_groups(rooms):
    """Build groups in order: Full Clean → Daily Service → Dust n Vac."""
    fc_rooms = [r for r in rooms if r.get("service")==SVC_FC]
    ds_rooms = [r for r in rooms if r.get("service")==SVC_DS]
    dv_rooms = [r for r in rooms if r.get("service")==SVC_DV]

    fc_groups = pack_rooms(fc_rooms, SVC_FC, can_add_fc,
                           unit_ok_fn=lambda u: unit_ok_fc(u))

    # DS: last group can overflow
    if ds_rooms:
        ds_groups_pre = pack_rooms(ds_rooms, SVC_DS,
                                   lambda g,u: can_add_ds(g,u,False),
                                   unit_ok_fn=lambda u: True)
        # Try to absorb leftovers into last group with overflow
        if len(ds_groups_pre) > 1:
            last = ds_groups_pre[-1]
            merged = ds_groups_pre[:-1]
            last["ds_overflow"] = last["time"] > MAX_DS
            ds_groups = merged + [last]
        else:
            ds_groups = ds_groups_pre
            if ds_groups: ds_groups[0]["ds_overflow"] = ds_groups[0]["time"] > MAX_DS
    else:
        ds_groups = []

    # Dust n Vac: always one single group regardless of building —
    # Manager handles all of them, no building constraint applies.
    if dv_rooms:
        dv_group = {
            "rooms":        list(dv_rooms),
            "time":         0,   # DV rooms are untimed
            "blds":         set(r["bld"] for r in dv_rooms),
            "floors":       set(r.get("floor",0) for r in dv_rooms),
            "c140":         0,
            "c120":         0,
            "service_type": SVC_DV,
            "dv_manager":   True,
        }
        dv_groups = [dv_group]
    else:
        dv_groups = []

    return fc_groups + ds_groups + dv_groups

# ══════════════════════════════════════════════════════════════════════════════
#  STAFF ASSIGNMENT
# ══════════════════════════════════════════════════════════════════════════════
def assign_hk_building_aware(groups, present_hk, roster):
    """One HK per group, building-preference matching. No recycling."""
    pool = {1:[], 2:[], 3:[]}
    for n in present_hk:
        b = roster.get(n,{}).get("building",0)
        if b in pool: pool[b].append(n)
    available = {1:list(pool[1]),2:list(pool[2]),3:list(pool[3])}
    assignment = {}; used = set()
    for g in groups:
        if g.get("dv_manager"):
            assignment[g["label"]] = "Manager"; continue
        primary = min(g["blds"]) if g["blds"] else 1
        matched = None
        if available.get(primary): matched = available[primary].pop(0)
        if not matched:
            for b in [1,2,3]:
                if available.get(b): matched = available[b].pop(0); break
        assignment[g["label"]] = matched or ""
        if matched: used.add(matched)
    return assignment, used

def _primary_bld(g):
    """Primary building of a group = lowest building number."""
    return min(g["blds"]) if g["blds"] else 0

def _insp_travel_score(batch):
    """
    Score an inspector batch by how many distinct buildings they must visit.
    Lower = better.  Penalty for cross-building groups too.
    """
    blds = set()
    cross_penalty = 0
    for g in batch:
        blds |= g["blds"]
        if len(g["blds"]) > 1:
            cross_penalty += len(g["blds"]) - 1   # each extra building costs 1
    return len(blds) * 10 + cross_penalty

def assign_inspectors(groups, present_insp, per, rqs1, rqs2):
    """
    Assign inspectors minimising building travel:
    1. RQS2 → Daily Service
    2. RQS1 → Dust n Vac
    3. FC groups → clustered by primary building, then assigned sequentially.
       Cross-building FC groups are placed in the batch whose dominant building
       they already share, not forced into a separate batch that spans 3 buildings.
    """
    fc_groups = [g for g in groups if g.get("service_type")==SVC_FC]
    ds_groups = [g for g in groups if g.get("service_type")==SVC_DS]
    dv_groups = [g for g in groups if g.get("service_type")==SVC_DV]

    inspectors    = []
    assigned_names = set()

    # ── RQS2 → Daily Service ──────────────────────────────────────────────────
    if ds_groups and rqs2:
        blds = sorted(set(b for g in ds_groups for b in g["blds"]))
        entry = {"id":len(inspectors)+1,"name":rqs2,"role":"RQS2",
                 "groups":[g["label"] for g in ds_groups],"buildings":blds}
        for g in ds_groups: g["inspector"] = rqs2
        inspectors.append(entry); assigned_names.add(rqs2)

    # ── RQS1 → Dust n Vac ────────────────────────────────────────────────────
    if dv_groups and rqs1:
        blds = sorted(set(b for g in dv_groups for b in g["blds"]))
        entry = {"id":len(inspectors)+1,"name":rqs1,"role":"RQS1",
                 "groups":[g["label"] for g in dv_groups],"buildings":blds}
        for g in dv_groups: g["inspector"] = rqs1
        inspectors.append(entry); assigned_names.add(rqs1)

    # ── FC groups: proximity-cluster then assign ──────────────────────────────
    # Step 1: Sort FC groups by (primary_bld, floor, room_number)
    # so same-building groups are naturally contiguous.
    fc_sorted = sorted(fc_groups, key=lambda g:(
        _primary_bld(g),
        min(g.get("floors",{0})) if g.get("floors") else 0,
        min(r.get("num",0) for r in g["rooms"]) if g["rooms"] else 0
    ))

    # Step 2: Slice into batches of `per`, then optimise each batch.
    # For each batch we try to swap cross-building groups with single-building
    # groups from adjacent batches if it reduces total travel score.
    batches = [fc_sorted[i:i+per] for i in range(0, len(fc_sorted), per)]

    # Improvement pass: attempt neighbour swaps to reduce multi-building batches
    improved = True
    max_iter = len(batches) * per   # safety limit
    iters    = 0
    while improved and iters < max_iter:
        improved = False; iters += 1
        for bi in range(len(batches)):
            for bj in range(bi+1, len(batches)):
                for gi, ga in enumerate(batches[bi]):
                    for gj, gb in enumerate(batches[bj]):
                        # Swap ga and gb between batches bi and bj
                        new_bi = batches[bi][:gi] + [gb] + batches[bi][gi+1:]
                        new_bj = batches[bj][:gj] + [ga] + batches[bj][gj+1:]
                        old_score = _insp_travel_score(batches[bi]) + _insp_travel_score(batches[bj])
                        new_score = _insp_travel_score(new_bi)       + _insp_travel_score(new_bj)
                        if new_score < old_score:
                            batches[bi], batches[bj] = new_bi, new_bj
                            improved = True; break
                    if improved: break
                if improved: break

    # Step 3: Assign inspectors to optimised batches
    remaining = [n for n in present_insp if n not in assigned_names]
    if rqs1 and rqs1 not in assigned_names and rqs1 in present_insp:
        remaining.append(rqs1)

    for batch in batches:
        name = remaining.pop(0) if remaining else f"Inspector {len(inspectors)+1}"
        blds = sorted(set(b for g in batch for b in g["blds"]))
        n_blds = len(blds)
        entry = {"id":len(inspectors)+1,"name":name,"role":"FC",
                 "groups":[g["label"] for g in batch],"buildings":blds,
                 "travel_warning": n_blds > 2}
        for g in batch: g["inspector"] = name
        inspectors.append(entry)

    # Unassigned DV groups → "Manager"
    for g in dv_groups:
        if not g.get("inspector"): g["inspector"] = "Manager"

    return inspectors

# ══════════════════════════════════════════════════════════════════════════════
#  HTML BUILDERS
# ══════════════════════════════════════════════════════════════════════════════
def group_card_html(g, idx):
    svc  = g.get("service_type", SVC_FC)
    ac, bg = SVC_PALETTE.get(svc, pal(idx))
    cap  = MAX_DS if svc==SVC_DS else MAX_FC
    pct  = min(int(g["time"]/cap*100),100)
    hk   = e(g.get("housekeeper","") or "—")
    insp = e(g.get("inspector","") or "—")
    bld_str = " · ".join(f"Bldg {b}" for b in sorted(g["blds"]))
    svc_badge = (f'<span style="background:{ac};color:#fff;border-radius:5px;'
                 f'padding:1px 8px;font-size:.67rem;font-weight:700;margin-left:5px">{e(svc)}</span>')
    overflow_badge = (
        '<span style="background:#fef3c7;color:#92400e;border-radius:5px;'
        'padding:1px 7px;font-size:.67rem;font-weight:700;margin-left:4px">⚠️ DS Overflow</span>'
        if g.get("ds_overflow") else "")
    cross = ('<span style="background:#f3e8ff;color:#7c3aed;border-radius:5px;'
             'padding:1px 7px;font-size:.67rem;font-weight:700;margin-left:4px">Cross-bld</span>'
             if g.get("cross_bld") else "")
    t_col = "#16a34a" if pct<=87 else ("#d97706" if pct<=95 else "#dc2626")

    rows = ""
    for r in g["rooms"]:
        pet = ('<span style="background:#fee2e2;color:#b91c1c;border-radius:5px;'
               'padding:1px 6px;font-size:.66rem;font-weight:700">🐾 Pet</span>'
               if r.get("pet") else "")
        note140 = ('<span style="background:#fef3c7;color:#92400e;border-radius:5px;'
                   'padding:1px 6px;font-size:.66rem;font-weight:700">140-min</span>'
                   if r.get("time")==140 else "")
        late_co = e(r.get("late_checkout",""))
        late_badge = (f'<span style="background:#fef3c7;color:#92400e;border-radius:5px;'
                      f'padding:1px 6px;font-size:.66rem;font-weight:700">⏰ {late_co}</span>'
                      if late_co else "")
        notes_txt = e(r.get("notes",""))
        notes_badge = (f'<span style="background:#f0f9ff;color:#0369a1;border-radius:5px;'
                       f'padding:1px 6px;font-size:.66rem;font-weight:600">{notes_txt}</span>'
                       if notes_txt else "")
        arriving = e(r.get("arriving",""))
        arr_badge = (f'<span style="background:#ecfdf5;color:#059669;border-radius:5px;'
                     f'padding:1px 6px;font-size:.66rem;font-weight:600">→ {arriving}</span>'
                     if arriving else "")
        rows += f"""<tr>
          <td style="font-family:'JetBrains Mono',monospace;font-size:.77rem;font-weight:600;color:#0f172a;padding:7px 11px">{e(r.get("room",""))}</td>
          <td style="padding:7px 11px;color:#475569">Bldg {r.get("bld","")}</td>
          <td style="padding:7px 11px;color:#1e293b;font-weight:500">{e(r.get("guest",""))}</td>
          <td style="padding:7px 11px;color:#64748b">{e(r.get("service",""))}</td>
          <td style="padding:7px 11px;font-weight:600;color:#1e293b">{"—" if r.get("time",0)==0 else str(r.get("time",""))+" min"}</td>
          <td style="padding:7px 11px">{pet}</td>
          <td style="padding:7px 11px">{late_badge}</td>
          <td style="padding:7px 11px">{notes_badge}{arr_badge}{note140}</td>
        </tr>"""

    th = ("padding:6px 11px;text-align:left;font-size:.66rem;font-weight:700;"
          "text-transform:uppercase;letter-spacing:.07em;color:#94a3b8;"
          "background:#f8fafc;border-bottom:1px solid #f1f5f9")
    lbl    = e(g.get("label",""))
    return f"""<!DOCTYPE html><html><head>{SHARED_CSS}</head><body>
<div style="border-radius:14px;overflow:hidden;border:2px solid {ac}33;
            box-shadow:0 2px 10px rgba(0,0,0,.07);background:#fff;margin-bottom:4px">
  <div style="background:{bg};padding:10px 14px;display:flex;align-items:center;
              gap:10px;flex-wrap:wrap;border-bottom:1px solid {ac}22">

    <!-- LEFT: label pill + title row + meta row -->
    <div style="display:flex;align-items:center;gap:9px;flex:1;min-width:0;flex-wrap:wrap">
      <!-- Label pill — wide enough for "FC-AB" -->
      <div style="background:{ac};color:#fff;border-radius:8px;
                  padding:4px 10px;font-weight:800;font-size:.78rem;
                  white-space:nowrap;flex-shrink:0;letter-spacing:.02em">{lbl}</div>

      <div style="min-width:0">
        <!-- Title row: Group name + service/overflow/cross badges -->
        <div style="display:flex;align-items:center;gap:5px;flex-wrap:wrap">
          <span style="font-weight:700;font-size:.9rem;color:#0f172a">Group {lbl}</span>
          {svc_badge} {overflow_badge} {cross}
        </div>
        <!-- Meta row: building · HK · Inspector -->
        <div style="font-size:.72rem;color:#64748b;margin-top:2px;white-space:nowrap;
                    overflow:hidden;text-overflow:ellipsis">
          {bld_str} &nbsp;·&nbsp; 🧑‍🔧 {hk} &nbsp;·&nbsp; 🔍 {insp}
        </div>
      </div>
    </div>

    <!-- RIGHT: time counter + progress bar -->
    <div style="display:flex;align-items:center;gap:8px;flex-shrink:0">
      <span style="font-size:.84rem;font-weight:700;color:{ac}">{g.get("time","")} / {cap} min</span>
      <div style="background:rgba(0,0,0,.12);border-radius:5px;height:6px;width:80px;overflow:hidden">
        <div style="background:{ac};width:{pct}%;height:6px;border-radius:5px"></div>
      </div>
    </div>
  </div>
  <table style="width:100%;border-collapse:collapse">
    <thead><tr>
      <th style="{th}">Room</th><th style="{th}">Bldg</th><th style="{th}">Guest</th>
      <th style="{th}">Service</th><th style="{th}">Time</th>
      <th style="{th}">Pet</th><th style="{th}">Late Out</th><th style="{th}">Notes / Flags</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <div style="background:#f8fafc;padding:7px 13px;display:flex;justify-content:space-between;
              border-top:1px solid #f1f5f9;font-size:.73rem;color:#94a3b8">
    <span>{len(g["rooms"])} rooms &nbsp;·&nbsp; {g.get("c120",0)} × 120-min &nbsp;·&nbsp; {g.get("c140",0)} × 140-min</span>
    <span style="color:{t_col};font-weight:700">{g.get("time","")} min used</span>
  </div>
</div></body></html>"""


def staff_table_html(rows, cols, cell_fns, row_bg_fn):
    th_s = ("padding:8px 12px;text-align:left;font-size:.67rem;font-weight:700;"
            "text-transform:uppercase;letter-spacing:.08em;color:#64748b;"
            "background:#f1f5f9;border-bottom:1px solid #e2e8f0")
    ths  = "".join(f'<th style="{th_s}">{e(c)}</th>' for c in cols)
    body = ""
    for row in rows:
        bg  = row_bg_fn(row)
        tds = "".join(
            f'<td style="padding:8px 12px;border-bottom:1px solid #f1f5f9;'
            f'vertical-align:middle;background:{bg}">{fn(row)}</td>'
            for fn in cell_fns)
        body += f"<tr>{tds}</tr>"
    return f"""<!DOCTYPE html><html><head>{SHARED_CSS}</head><body>
<div style="border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;
            box-shadow:0 1px 4px rgba(0,0,0,.05)">
<table style="width:100%;border-collapse:collapse;font-size:.8rem">
  <thead><tr>{ths}</tr></thead><tbody>{body}</tbody>
</table></div></body></html>"""


def insp_card_html(insp, fg, color):
    name  = e(insp.get("name",""))
    role  = insp.get("role","FC")
    blds  = insp.get("buildings",[])
    bld_tags = "".join(
        f'<span style="background:{BLD_COLORS.get(b,("#888","#eee"))[1]};'
        f'color:{BLD_COLORS.get(b,("#888","#eee"))[0]};'
        f'border-radius:4px;padding:1px 7px;font-size:.67rem;font-weight:700;margin-right:3px">Bldg {b}</span>'
        for b in blds)
    role_map = {
        "RQS1": ("#92400e","#fef3c7","RQS1 · Dust & Vac"),
        "RQS2": ("#15803d","#dcfce7","RQS2 · Daily Service"),
        "FC":   ("#1d4ed8","#dbeafe","Full Clean"),
    }
    rc,rbg,rlbl = role_map.get(role,("#64748b","#f1f5f9",role))
    role_badge = (f'<span style="background:{rbg};color:{rc};border-radius:5px;'
                  f'padding:1px 8px;font-size:.68rem;font-weight:700;margin-left:6px">{rlbl}</span>')
    travel_warn = ('<span style="background:#fef3c7;color:#92400e;border-radius:5px;'
                   'padding:1px 8px;font-size:.68rem;font-weight:700;margin-left:5px">'
                   '⚠️ 3-bld travel</span>') if insp.get("travel_warning") else ""
    pills = ""; total_t = 0
    for gl in insp["groups"]:
        gobj = next((g for g in fg if g["label"]==gl), None)
        if not gobj: continue
        idx  = next((j for j,g in enumerate(fg) if g["label"]==gl), 0)
        ac,bg2 = pal(idx)
        hk = e(gobj.get("housekeeper","") or f"Grp {gl}")
        total_t += gobj.get("time",0)
        pills += (f'<span style="display:inline-block;background:#fff;border:1.5px solid {ac}55;'
                  f'border-radius:20px;padding:2px 10px;font-size:.74rem;margin:2px">'
                  f'<span style="font-weight:700;color:{ac}">{gl}</span> · {hk}</span>')
    return f"""<!DOCTYPE html><html><head>{SHARED_CSS}</head><body>
<div style="border-radius:12px;padding:13px 15px;border:1.5px solid {color}44;background:{color}0d">
  <div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;margin-bottom:6px">
    <span style="font-weight:700;font-size:.9rem;color:{color}">🔍 {name}</span>{role_badge}{travel_warn}
  </div>
  <div style="margin-bottom:6px">{bld_tags}</div>
  <div>{pills or '<span style="color:#94a3b8;font-size:.77rem">No groups</span>'}</div>
  <div style="margin-top:7px;font-size:.7rem;color:{color}99">{len(insp["groups"])} groups · {total_t} min</div>
</div></body></html>"""

# ══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR — Attendance + drag-to-reassign + RQS selectors
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    # ── User info + logout ───────────────────────────────────────────────────
    _cu = auth.current_user()
    _ac, _bg = auth.ROLE_COLORS.get(_cu["role"], ("#64748b","#f1f5f9"))
    st.markdown(f"""
<div style="background:{_bg};border:1px solid {_ac}33;border-radius:10px;
            padding:8px 12px;display:flex;justify-content:space-between;
            align-items:center;margin-bottom:8px">
  <div>
    <div style="font-weight:700;font-size:.82rem;color:{_ac}">{_cu["username"]}</div>
    <div style="font-size:.68rem;color:{_ac}99">{_cu["role"].title()}</div>
  </div>
  <span style="font-size:1.2rem">{"👑" if _cu["role"]=="admin" else "🔍" if _cu["role"]=="rqs" else "🧑‍🔧"}</span>
</div>""", unsafe_allow_html=True)
    if st.button("Sign Out", key="btn_logout", use_container_width=True):
        auth.logout()
        st.rerun()

    st.markdown("## 📅 Daily Attendance")
    st.markdown("---")

    # ── Add/remove HK ────────────────────────────────────────────────────────
    with st.expander("➕ Add / 🗑 Remove Housekeeper"):
        col_a, col_b = st.columns([2,1])
        with col_a: new_hk_name = st.text_input("Name", key="new_hk_inp")
        with col_b: new_hk_bld  = st.selectbox("Bldg", [1,2,3], key="new_hk_bld")
        if st.button("Add HK", key="btn_add_hk"):
            n = new_hk_name.strip()
            if n and n not in st.session_state["hk_roster"]:
                st.session_state["hk_roster"][n] = {"building":new_hk_bld,"present":True}
                st.success(f"Added {n}")
        rm_hk = st.selectbox("Remove", ["—"]+list(st.session_state["hk_roster"].keys()), key="rm_hk_sel")
        if st.button("Remove", key="btn_rm_hk") and rm_hk != "—":
            del st.session_state["hk_roster"][rm_hk]; st.success(f"Removed {rm_hk}")

    st.markdown("### 🧑‍🔧 Housekeepers")
    st.caption("Check ✅ to mark present. Use ◀▶ buttons to move between buildings.")

    roster = st.session_state["hk_roster"]
    present_hk = []

    for bld in [1, 2, 3]:
        ac2, bg2 = BLD_COLORS[bld]
        bld_hks = [n for n, v in roster.items() if v["building"] == bld]
        if not bld_hks:
            continue
        n_present = sum(1 for n in bld_hks if roster[n]["present"])
        dot_col = ac2
        st.markdown(
            f'<div style="background:{bg2};color:{ac2};border-radius:10px;'
            f'padding:6px 12px;font-size:.71rem;font-weight:700;'
            f'display:flex;justify-content:space-between;align-items:center;'
            f'margin:8px 0 4px;border:1px solid {ac2}33;'
            f'box-shadow:0 1px 4px {ac2}18">'
            f'<span style="display:flex;align-items:center;gap:5px">'
            f'<span style="width:8px;height:8px;border-radius:50%;background:{ac2};display:inline-block"></span>'
            f'Building {bld}</span>'
            f'<span style="background:{ac2};color:#fff;border-radius:20px;padding:1px 8px;'
            f'font-size:.65rem;font-weight:700">{n_present}/{len(bld_hks)}</span>'
            f'</div>',
            unsafe_allow_html=True)
        for name in bld_hks:
            c_chk, c_name, c_left, c_right = st.columns([0.4, 3.2, 0.6, 0.6])
            with c_chk:
                checked = st.checkbox("", value=roster[name]["present"],
                                      key=f"att_{name}", label_visibility="collapsed")
                roster[name]["present"] = checked
            with c_name:
                fw  = "600" if checked else "400"
                col = "inherit" if checked else "#94a3b8"
                td  = "none" if checked else "line-through"
                st.markdown(
                    f'<div style="font-size:.8rem;font-weight:{fw};color:{col};'
                    f'padding:4px 0;line-height:1.3;text-decoration:{td}">{name}</div>',
                    unsafe_allow_html=True)
            with c_left:
                if bld > 1:
                    if st.button("◀", key=f"ml_{name}", help=f"Move to Bldg {bld-1}",
                                 use_container_width=True):
                        roster[name]["building"] = bld - 1
                        st.rerun()
            with c_right:
                if bld < 3:
                    if st.button("▶", key=f"mr_{name}", help=f"Move to Bldg {bld+1}",
                                 use_container_width=True):
                        roster[name]["building"] = bld + 1
                        st.rerun()
            if roster[name]["present"]:
                present_hk.append(name)

    st.markdown("---")

    # ── Add/remove Inspector ──────────────────────────────────────────────────
    with st.expander("➕ Add / 🗑 Remove Inspector"):
        new_insp = st.text_input("Name", key="new_insp_inp")
        if st.button("Add Inspector", key="btn_add_insp"):
            n = new_insp.strip()
            if n and n not in st.session_state["insp_roster"]:
                st.session_state["insp_roster"][n] = True; st.success(f"Added {n}")
        rm_insp = st.selectbox("Remove",["—"]+list(st.session_state["insp_roster"].keys()),key="rm_insp_sel")
        if st.button("Remove", key="btn_rm_insp") and rm_insp != "—":
            del st.session_state["insp_roster"][rm_insp]; st.success(f"Removed {rm_insp}")

    st.markdown("### 🔍 Inspectors")
    insp_roster = st.session_state["insp_roster"]
    present_insp = []
    for name in list(insp_roster.keys()):
        insp_roster[name] = st.checkbox(name, value=insp_roster[name], key=f"insp_att_{name}")
        if insp_roster[name]: present_insp.append(name)

    st.markdown("---")
    st.markdown("### 🎯 RQS Roles Today")
    rqs_opts = ["— none —"] + present_insp
    rqs1_sel = st.selectbox("RQS 1 (Dust & Vac / FC backup)", rqs_opts, key="rqs1_sel")
    rqs2_sel = st.selectbox("RQS 2 (Daily Service)", rqs_opts, key="rqs2_sel")
    rqs1 = "" if rqs1_sel=="— none —" else rqs1_sel
    rqs2 = "" if rqs2_sel=="— none —" else rqs2_sel
    st.session_state["rqs1"] = rqs1; st.session_state["rqs2"] = rqs2

    st.markdown("---")
    groups_per_insp = st.select_slider("Groups / FC inspector", options=[3,4], value=3)
    st.markdown(f"""
<div style="background:#f1f5f9;border-radius:8px;padding:9px 11px;font-size:.77rem;color:#475569">
  ✅ <b>{len(present_hk)}</b> HKs &nbsp;·&nbsp; <b>{len(present_insp)}</b> inspectors<br>
  RQS1: <b>{rqs1 or "—"}</b> &nbsp;·&nbsp; RQS2: <b>{rqs2 or "—"}</b>
</div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN INPUT
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<p class="pg-title">🧹 Cleaning Schedule</p>', unsafe_allow_html=True)
st.markdown('<p class="pg-sub">Mark attendance · paste room data · auto-group · assign staff · export</p>', unsafe_allow_html=True)

# ── Dashboard nav ──────────────────────────────────────────────────────────────
import os as _os
_log_path = _os.path.join(_os.path.dirname(__file__), "schedule_log.json")
_has_log = _os.path.exists(_log_path)
_nav_col1, _nav_col2, _nav_col3 = st.columns([5,1,1])
with _nav_col2:
    st.page_link("pages/1_Dashboard.py", label="📊", help="Dashboard", use_container_width=True)
with _nav_col3:
    if auth.can("can_manage_users"):
        st.page_link("pages/2_Admin.py", label="👑", help="Admin Panel", use_container_width=True)

with st.expander("📋 Rules", expanded=False):
    st.markdown("""<div class="rules-box"><ol>
<li>Full Clean ≤ <strong>380 min</strong> · Daily Service ≤ <strong>460 min</strong> (last DS group may overflow slightly)</li>
<li>Groups built in order: <strong>Full Clean → Daily Service → Dust & Vac</strong></li>
<li>Dust & Vac → assigned to <strong>Manager</strong> (or RQS1 if set)</li>
<li>Building 2 and Building 3 <strong>cannot share a group</strong></li>
<li>Full Clean: max <strong>one 140-min</strong> room; 120+140 → only 70s after</li>
<li>Same guest → same group · proximity-first packing (same floor preferred)</li>
<li>HKs assigned to their <strong>home building first</strong>; one group per HK max</li>
<li>RQS2 → Daily Service · RQS1 → Dust & Vac (+ FC backup if free)</li>
<li>Late checkouts & room move notes parsed from front-desk email</li>
</ol></div>""", unsafe_allow_html=True)

st.markdown("---")

col_data, col_cfg = st.columns([5,1], gap="medium")
with col_data:
    st.markdown('<p class="sec">📋 Room Data  +  Front-Desk Email</p>', unsafe_allow_html=True)
    inp_a, inp_b = st.columns([3,2], gap="small")
    with inp_a:
        raw_input = st.text_area("rooms", label_visibility="collapsed", height=230,
            disabled=not auth.can("can_paste_input"),
            placeholder="Room\tService\tTime\tPet\tCurrent Guest or Status\n1020D\tFull Clean\t120\t\tSmith, John",
            key="room_input")
        st.caption("Copy from Excel (include header row). Full Clean (IH) treated as Full Clean.")
    with inp_b:
        email_text = st.text_area("email", label_visibility="collapsed", height=230,
            disabled=not auth.can("can_paste_input"),
            placeholder="Paste today's front-desk email...\n\nLate Checkouts:\n* 10:30 am\n   * 1234A\nRoom Moves:\n* 3251H - 3242A",
            key="email_input")
        st.caption("Late checkouts, room moves, robes, rollaway, dogs etc. auto-matched to rooms.")

with col_cfg:
    st.markdown('<p class="sec">⚙️</p>', unsafe_allow_html=True)
    st.markdown(f"""
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;
            padding:11px 13px;font-size:.78rem;color:#475569;margin-bottom:10px">
  <div style="font-weight:700;color:#0f172a;margin-bottom:5px">Today</div>
  <div>🧑‍🔧 <b>{len(present_hk)}</b> HKs present</div>
  <div>🔍 <b>{len(present_insp)}</b> inspectors</div>
</div>""", unsafe_allow_html=True)
    _can_gen = auth.can("can_generate")
    run = st.button("⚡ Generate", type="primary", use_container_width=True,
                    disabled=not _can_gen,
                    help="" if _can_gen else "🔒 Housekeeper role — view only")

# ══════════════════════════════════════════════════════════════════════════════
#  SNAPSHOT BUILDER
# ══════════════════════════════════════════════════════════════════════════════
def _build_snapshot(fg, total_rooms, inspectors):
    from datetime import date
    hk_snap = {}
    for g in fg:
        hk = g.get("housekeeper","")
        if hk and hk != "Manager":
            if hk not in hk_snap:
                hk_snap[hk] = {"time":0,"rooms":0,"fc":0,"ds":0,"dv":0,"groups":0}
            hk_snap[hk]["time"]   += g.get("time",0)
            hk_snap[hk]["rooms"]  += len(g.get("rooms",[]))
            hk_snap[hk]["groups"] += 1
            svc = g.get("service_type","")
            if svc == "Full Clean":     hk_snap[hk]["fc"] += 1
            elif svc == "Daily Service":hk_snap[hk]["ds"] += 1
            elif svc == "Dust n Vac":   hk_snap[hk]["dv"] += 1
    insp_snap = {}
    for insp in inspectors:
        nm = insp.get("name","")
        if nm:
            insp_snap[nm] = {
                "groups":    len(insp.get("groups",[])),
                "role":      insp.get("role","FC"),
                "buildings": insp.get("buildings",[]),
            }
    return {
        "date":        str(date.today()),
        "total_rooms": total_rooms,
        "n_groups":    len(fg),
        "hk":          hk_snap,
        "inspectors":  insp_snap,
        "saved_by":    st.session_state.get("username","unknown"),
    }

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
                    st.error("No valid rows — check tab-separated data with numeric Time.")
                else:
                    email_data = parse_email_notes(email_text)
                    late_co_map    = email_data["late_checkout"]
                    email_notes_map= email_data["notes"]
                    if not email_text.strip():
                        st.info("💡 No front-desk email pasted — late checkouts and notes won't be populated.")
                    else:
                        n_late  = len(late_co_map)
                        n_notes = sum(len(v) for v in email_notes_map.values())
                        if n_late > 0:
                            late_rooms = ", ".join(f"{rm} ({t.replace('Late Out: ','')})" 
                                                   for rm, t in sorted(late_co_map.items()))
                            st.success(f"✅ Email parsed: **{n_late}** late checkout(s) · **{n_notes}** note(s)\n\nLate rooms: {late_rooms}")
                        else:
                            st.warning("⚠️ Email parsed but **0 late checkouts** found. Check the email format — ensure 'Late Checkouts:' header and times like '10:30 am' are present.")

                    # ── Build per-room late checkout ─────────────────────────────
                    # Only use direct email match for the specific room listed.
                    # Do NOT propagate to companion rooms — front desk lists exactly
                    # which rooms have late checkouts, not the whole guest stay.
                    records_raw = df.to_dict("records")
                    rds = []
                    for r in records_raw:
                        rm_upper   = str(r["Room"]).strip().upper()
                        excel_late = r.get("LateCheckout","").strip()
                        email_late = late_co_map.get(rm_upper,"")

                        # Priority:
                        # 1. Direct email match (has actual time like "Late Out: 10:30 am")
                        # 2. Non-generic Excel value (has real info, not just the flag)
                        # 3. Excel flagged "Late Check Out" with no time → show flag only
                        # 4. Nothing
                        if email_late:
                            late_co = email_late
                        elif excel_late and excel_late.lower() not in ("", "late check out", "late checkout", "late check-out"):
                            late_co = excel_late
                        elif excel_late:
                            late_co = "Late Out"
                        else:
                            late_co = ""

                        notes_parts = []
                        if r.get("NotesRaw","").strip(): notes_parts.append(r["NotesRaw"].strip())
                        if rm_upper in email_notes_map:
                            notes_parts += email_notes_map[rm_upper]
                        rds.append({
                            "room": r["Room"], "service": r["Service"],
                            "time": r["Time"],  "pet": r["Pet"],
                            "guest": r["Guest"],
                            "bld":   r.get("bld", get_building(r["Room"])),
                            "floor": r.get("floor",0), "num": r.get("num",0),
                            "late_checkout": late_co,
                            "status":  r.get("Status",""),
                            "notes":   "; ".join(notes_parts),
                            "arriving":r.get("ArrivingGuest",""),
                            "res_type":r.get("ResType",""),
                        })

                    # Service mapping debug (hidden — remove comment to re-enable)
                    # raw_map = {}
                    # for rec in df.to_dict("records"):
                    #     raw_map[f"{rec.get('ServiceRaw','')} → {rec.get('Service','')}"] = ...

                    fg = build_all_groups(rds)
                    # Assign prefixed labels per service type
                    fc_gs = [g for g in fg if g.get("service_type")==SVC_FC]
                    ds_gs = [g for g in fg if g.get("service_type")==SVC_DS]
                    dv_gs = [g for g in fg if g.get("service_type")==SVC_DV]
                    for g, lbl in zip(fc_gs, make_labels("FC", len(fc_gs))):
                        g["label"] = lbl
                    for g, lbl in zip(ds_gs, make_labels("DS", len(ds_gs))):
                        g["label"] = lbl
                    for g, lbl in zip(dv_gs, make_labels("DV", len(dv_gs))):
                        g["label"] = lbl
                    for g in fg:
                        g["cross_bld"] = len(g["blds"]) > 1

                    # ── Post-pack rebalance: absorb tiny FC groups (<200m) ────────────
                    changed = True
                    while changed:
                        changed = False
                        tiny_fc = [g for g in fg
                                   if g.get("service_type")==SVC_FC and g["time"]<200 and g["rooms"]]
                        for tg in tiny_fc:
                            best_i, best_rem = -1, 9999
                            for j, cand in enumerate(fg):
                                if cand is tg or not cand["rooms"]: continue
                                if cand.get("service_type") != SVC_FC: continue
                                if not can_add_fc(cand, tg["rooms"]): continue
                                rem = MAX_FC - (cand["time"] + tg["time"])
                                if 0 <= rem < best_rem:
                                    best_rem, best_i = rem, j
                            if best_i >= 0:
                                cand = fg[best_i]
                                for r in tg["rooms"]:
                                    cand["rooms"].append(r)
                                    cand["blds"].add(r["bld"])
                                    cand["floors"].add(r.get("floor",0))
                                cand["time"] += tg["time"]
                                cand["c140"] += tg["c140"]
                                cand["c120"] += tg["c120"]
                                tg["rooms"] = []
                                changed = True
                    fg = [g for g in fg if g["rooms"]]
                    # Re-label after rebalance
                    fc_gs2 = [g for g in fg if g.get("service_type")==SVC_FC]
                    ds_gs2 = [g for g in fg if g.get("service_type")==SVC_DS]
                    dv_gs2 = [g for g in fg if g.get("service_type")==SVC_DV]
                    for g, lbl in zip(fc_gs2, make_labels("FC", len(fc_gs2))): g["label"]=lbl
                    for g, lbl in zip(ds_gs2, make_labels("DS", len(ds_gs2))): g["label"]=lbl
                    for g, lbl in zip(dv_gs2, make_labels("DV", len(dv_gs2))): g["label"]=lbl
                    for g in fg: g["cross_bld"] = len(g["blds"]) > 1

                    hk_asgn, used_hk_set = assign_hk_building_aware(fg, present_hk, roster)
                    for g in fg: g["housekeeper"] = hk_asgn.get(g["label"],"")

                    inspectors = assign_inspectors(fg, present_insp, groups_per_insp, rqs1, rqs2)

                    st.session_state.update({
                        "groups_data": fg, "total_rooms": len(df),
                        "inspectors_data": inspectors, "used_hk_set": used_hk_set,
                    })
                    # Auto-save snapshot to Supabase
                    try:
                        _snap = _build_snapshot(fg, len(df), inspectors)
                        db.save_snapshot(_snap)
                        st.toast("✅ Schedule saved to dashboard!", icon="✅")
                    except Exception as _snap_err:
                        st.toast(f"⚠️ Schedule generated but not saved to DB: {_snap_err}", icon="⚠️")
                    # Labels auto-extend: FC-A..Z, FC-AA.. so no hard cap
            except Exception as ex:
                st.error(f"Error: {ex}")
                import traceback; st.code(traceback.format_exc())

# ══════════════════════════════════════════════════════════════════════════════
#  RESULTS
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.get("groups_data"): st.stop()

fg           = st.session_state["groups_data"]
total_rooms  = st.session_state["total_rooms"]
inspectors   = st.session_state["inspectors_data"]
used_hk_set  = st.session_state.get("used_hk_set") or set()
present_hk   = [n for n,v in st.session_state["hk_roster"].items() if v["present"]]
present_insp = [n for n,v in st.session_state["insp_roster"].items() if v]

st.markdown("---")

fc_g = [g for g in fg if g.get("service_type")==SVC_FC]
ds_g = [g for g in fg if g.get("service_type")==SVC_DS]
dv_g = [g for g in fg if g.get("service_type")==SVC_DV]
avg_t = sum(g["time"] for g in fg)//max(len(fg),1)
n_free_hk = sum(1 for n in present_hk if n not in used_hk_set)
n_low_hk  = sum(1 for g in fg if g.get("housekeeper") and
                g.get("housekeeper")!="Manager" and g["time"]<LOW_MIN)

st.markdown(f"""<div class="stat-row">
  <div class="sc hi"><div class="n">{len(fg)}</div><div class="l">Total Groups</div></div>
  <div class="sc"><div class="n" style="color:#2563EB">{len(fc_g)}</div><div class="l">Full Clean</div></div>
  <div class="sc ds"><div class="n">{len(ds_g)}</div><div class="l">Daily Service</div></div>
  <div class="sc dv"><div class="n">{len(dv_g)}</div><div class="l">Dust &amp; Vac</div></div>
  <div class="sc"><div class="n">{total_rooms}</div><div class="l">Rooms</div></div>
  <div class="sc"><div class="n">{avg_t}m</div><div class="l">Avg Time</div></div>
  <div class="sc" style="border-color:{'#d1fae5' if n_free_hk==0 else '#fef3c7'}">
    <div class="n" style="color:{'#059669' if n_free_hk==0 else '#d97706'}">{n_free_hk}</div>
    <div class="l" style="color:{'#059669' if n_free_hk==0 else '#d97706'}">Free HKs</div>
  </div>
  <div class="sc" style="border-color:{'#d1fae5' if n_low_hk==0 else '#fee2e2'}">
    <div class="n" style="color:{'#059669' if n_low_hk==0 else '#dc2626'}">{n_low_hk}</div>
    <div class="l" style="color:{'#059669' if n_low_hk==0 else '#dc2626'}">Low-Hour HKs</div>
  </div>
</div>""", unsafe_allow_html=True)

tab_hk, tab_insp, tab_grp = st.tabs(["🧑‍🔧 Housekeepers","🔍 Inspectors","📋 Groups"])

# ── HK tab ────────────────────────────────────────────────────────────────────
with tab_hk:
    hk_time={}; hk_grps={}
    for g in fg:
        hk = g.get("housekeeper","")
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
        if r["stat"]=="low":  return f'<span style="background:#fef9c3;color:#a16207;border-radius:5px;padding:2px 8px;font-size:.69rem;font-weight:700">⚠️ Low</span>'
        return ""
    def hk_pills(r):
        if not r["groups"]: return '<span style="color:#94a3b8">—</span>'
        out=""
        for gl in r["groups"]:
            idx=next((j for j,g in enumerate(fg) if g["label"]==gl),-1)
            ac2,bg2=pal(idx) if idx>=0 else ("#888","#eee")
            g_obj=next((g for g in fg if g["label"]==gl),{})
            svc_short={"Full Clean":"FC","Daily Service":"DS","Dust n Vac":"DV"}.get(g_obj.get("service_type",""),"")
            out+=(f'<span style="background:{bg2};color:{ac2};border:1px solid {ac2}44;'
                  f'border-radius:5px;padding:1px 7px;font-size:.7rem;font-weight:700;margin-right:3px">'
                  f'{gl} <span style="opacity:.6;font-size:.65rem">{svc_short}</span></span>')
        return out
    def hk_bar(r):
        if not r["time"]: return '<span style="color:#94a3b8">—</span>'
        pct=min(int(r["time"]/380*100),100)
        col="#10b981" if r["stat"]=="ok" else "#f59e0b"
        return (f'<div style="display:flex;align-items:center;gap:7px">'
                f'<span style="font-weight:600;color:#1e293b;min-width:48px">{r["time"]}m</span>'
                f'<div style="background:#e5e7eb;border-radius:4px;height:7px;width:75px">'
                f'<div style="background:{col};width:{pct}%;height:7px;border-radius:4px"></div></div></div>')

    tbl = staff_table_html(rows_hk,
        ["Housekeeper","Building","Status","Groups","Time"],
        [lambda r:f'<span style="font-weight:600;color:#1e293b">{e(r["name"])}</span>',
         hk_bld_tag, hk_status_tag, hk_pills, hk_bar],
        lambda r:{"free":"#f0fdf4","low":"#fefce8","ok":"#fff"}[r["stat"]])
    components.html(tbl, height=max(70+len(rows_hk)*42,120), scrolling=False)

    if n_free_hk or n_low_hk:
        parts=[]
        if n_free_hk: parts.append(f"**{n_free_hk}** HK(s) unassigned")
        if n_low_hk:  parts.append(f"**{n_low_hk}** HK(s) low hours")
        st.warning("  ·  ".join(parts))

# ── Inspector tab ──────────────────────────────────────────────────────────────
with tab_insp:
    used_insp={insp.get("name","") for insp in inspectors}
    rows_insp=[]
    for insp in inspectors:
        hks=[f"{gl}:{next((g.get('housekeeper','') for g in fg if g['label']==gl),'')} "
             for gl in insp["groups"] if any(g["label"]==gl for g in fg)]
        rows_insp.append({"name":insp.get("name",""),"role":insp.get("role","FC"),
                           "groups":insp["groups"],"hks":hks,
                           "buildings":insp.get("buildings",[]),"stat":""})
    for nm in present_insp:
        if nm not in used_insp:
            rows_insp.append({"name":nm,"role":"—","groups":[],"hks":[],
                              "buildings":[],"stat":"free"})

    def insp_role_tag(r):
        rm={"RQS1":("#92400e","#fef3c7","RQS1"),"RQS2":("#15803d","#dcfce7","RQS2"),
            "FC":("#1d4ed8","#dbeafe","FC"),"—":("#94a3b8","#f1f5f9","—")}
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
    def insp_free_tag(r):
        if r["stat"]=="free": return '<span style="background:#dbeafe;color:#1d4ed8;border-radius:5px;padding:2px 8px;font-size:.69rem;font-weight:700">✅ Free</span>'
        return ""

    tbl_i = staff_table_html(rows_insp,
        ["Inspector","Role","Buildings","Status","Groups","Housekeepers"],
        [lambda r:f'<span style="font-weight:600;color:#1e293b">{e(r["name"])}</span>',
         insp_role_tag, insp_bld_tags, insp_free_tag, insp_grp_pills,
         lambda r:f'<span style="font-size:.73rem;color:#475569">{" · ".join(e(h) for h in r["hks"]) or "—"}</span>'],
        lambda r:"#f0fdf4" if r["stat"]=="free" else "#fff")
    components.html(tbl_i, height=max(70+len(rows_insp)*42,120), scrolling=False)

    if inspectors:
        n_cols=min(len(inspectors),3); icols=st.columns(n_cols)
        for i,insp in enumerate(inspectors):
            with icols[i%n_cols]:
                components.html(insp_card_html(insp,fg,IC[i%len(IC)]),
                                height=140+len(insp["groups"])*26, scrolling=False)

# ── Groups tab ─────────────────────────────────────────────────────────────────
with tab_grp:
    f1,f2,f3,f4,f5=st.columns([2,2,2,1,1])
    with f1: fg_filter=st.multiselect("Group",[g["label"] for g in fg],default=[])
    with f2:
        all_blds=sorted(set(b for g in fg for b in g["blds"]))
        bld_filter=st.multiselect("Building",[f"Bldg {b}" for b in all_blds],default=[])
    with f3:
        svc_filter=st.multiselect("Service",[SVC_FC,SVC_DS,SVC_DV],default=[])
    with f4: pet_only    = st.checkbox("🐾 Pet",    value=False)
    with f5: lateout_only= st.checkbox("⏰ Late Out",value=False)

    sel_g=set(fg_filter) if fg_filter else None
    sel_b=set(int(b.split()[1]) for b in bld_filter) if bld_filter else None
    sel_s=set(svc_filter) if svc_filter else None

    for idx,g in enumerate(fg):
        if sel_g and g["label"] not in sel_g: continue
        if sel_s and g.get("service_type") not in sel_s: continue
        rooms=g["rooms"]
        if sel_b:        rooms=[r for r in rooms if r.get("bld") in sel_b]
        if pet_only:     rooms=[r for r in rooms if r.get("pet")]
        if lateout_only: rooms=[r for r in rooms if r.get("late_checkout","")]
        if not rooms: continue
        gd=dict(g); gd["rooms"]=rooms
        components.html(group_card_html(gd,idx), height=115+len(rooms)*42, scrolling=False)

# ── Export ─────────────────────────────────────────────────────────────────────
st.markdown("---")
export_rows=[]
for g in fg:
    for r in g["rooms"]:
        export_rows.append({
            "Room":r.get("room",""), "Service":r.get("service",""),
            "Time (min)":r.get("time",""), "Pet":r.get("pet",""),
            "Current Guest or Status":r.get("guest",""),
            "Late Checkout":r.get("late_checkout",""),
            "Housekeeper":g.get("housekeeper",""),
            "RQS":g.get("inspector",""),
            "Notes":r.get("notes",""), "Status":r.get("status",""),
            "Stripping":"","Carpet":"",
            "Arriving Guest":r.get("arriving",""),
            "Group":g["label"], "Service Type":g.get("service_type",""),
            "Building":f"Building {r.get('bld','')}",
            "Group Total (min)":g["time"],
            "Cross-Building":"Yes" if g.get("cross_bld") else "No",
        })
csv=pd.DataFrame(export_rows).to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Download CSV", data=csv,
                   file_name="cleaning_schedule.csv", mime="text/csv")