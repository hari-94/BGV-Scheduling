"""
Cleaning Schedule Grouper  v10
"""
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

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
def e(s): return _html.escape(str(s) if s else "")

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

SVC_FC   = "Full Clean"
SVC_DS   = "Daily Service"
SVC_DV   = "Dust n Vac"

DEFAULT_TIMES = {
    SVC_FC: {"A":120,"B":70,"C":70,"D":120,"E":140,"F":70,"G":70,"H":70,"I":70},
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
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,400&family=JetBrains+Mono:wght@400;500&display=swap');
*,*::before,*::after{box-sizing:border-box;}
html,body,[class*="css"]{font-family:'Inter',sans-serif;-webkit-font-smoothing:antialiased;}
.block-container{padding-top:1.4rem!important;max-width:1440px;}
.pg-title{font-size:1.75rem;font-weight:800;letter-spacing:-.8px;
  background:linear-gradient(135deg,#1e293b 0%,#3B4FE4 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text;margin:0 0 3px;line-height:1.15;}
.pg-sub{font-size:.83rem;color:#64748b;margin:0 0 .8rem;font-weight:400}
.sec{font-size:.65rem;font-weight:700;text-transform:uppercase;
  letter-spacing:.12em;color:#94a3b8;padding-bottom:5px;
  border-bottom:1.5px solid #f1f5f9;margin:1.1rem 0 .5rem;}
.stat-row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:1rem}
.sc{flex:1 1 100px;background:#fff;border:1px solid #e8edf5;border-radius:14px;
  padding:14px 13px;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.05);}
.sc.hi{background:linear-gradient(135deg,#5B4FE9,#7C6FF5);border:none}
.sc.ds{background:linear-gradient(135deg,#0D9488,#14B8A6);border:none}
.sc.dv{background:linear-gradient(135deg,#D97706,#F59E0B);border:none}
.sc .n{font-size:1.65rem;font-weight:800;color:#0f172a;line-height:1;margin-bottom:2px}
.sc.hi .n,.sc.hi .l,.sc.ds .n,.sc.ds .l,.sc.dv .n,.sc.dv .l{color:#fff}
.sc .l{font-size:.6rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;font-weight:600}
.rules-box{background:linear-gradient(135deg,#f0f9ff,#e8f4fd);border:1px solid #bae6fd;
  border-radius:12px;padding:14px 18px;font-size:.82rem;color:#0c4a6e;}
.rules-box li{margin-bottom:5px;line-height:1.55}
section[data-testid="stSidebar"]{min-width:360px!important;max-width:400px!important;}
.stTabs [data-baseweb="tab-list"]{gap:4px;background:#f1f5f9;border-radius:10px;padding:3px;border:none!important;}
.stTabs [data-baseweb="tab"]{border-radius:8px!important;padding:6px 16px!important;
  font-size:.78rem!important;font-weight:600!important;color:#64748b!important;
  border:none!important;background:transparent!important;}
.stTabs [aria-selected="true"]{background:#fff!important;color:#1e293b!important;
  box-shadow:0 1px 4px rgba(0,0,0,.1)!important;}
.stButton > button{border-radius:10px!important;font-weight:600!important;font-size:.82rem!important;}
.stButton > button[kind="primary"]{background:linear-gradient(135deg,#5B4FE9,#7C6FF5)!important;
  border:none!important;color:#fff!important;}
</style>""", unsafe_allow_html=True)

SHARED_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');
*{box-sizing:border-box;margin:0;padding:0;font-family:'Inter',sans-serif;}
body{background:transparent;}
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
.block-container{padding-top:4rem!important;max-width:420px!important;}
.stButton>button{width:100%!important;border-radius:10px!important;font-weight:700!important;
  background:linear-gradient(135deg,#5B4FE9,#7C6FF5)!important;border:none!important;
  color:#fff!important;padding:10px!important;}
</style>""", unsafe_allow_html=True)
    st.markdown('<h2 style="text-align:center">🧹 Cleaning Schedule</h2>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center;color:#64748b">Sign in to continue</p>', unsafe_allow_html=True)
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
                auth.login(_user); st.rerun()
            else:
                st.error("Invalid username or password.")
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
#  PARSING HELPERS
# ══════════════════════════════════════════════════════════════════════════════
SKIP_SERVICES = {"p/u models","pu models","p/u model","showcase","model unit","p/u"}

def normalize_service(raw: str) -> str:
    s = re.sub(r'\s+', ' ', str(raw).strip().lower())
    if s in SKIP_SERVICES or "p/u" in s or (s.startswith("p") and "model" in s):
        return "__SKIP__"
    if "daily" in s: return SVC_DS
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
        for rm in rooms: notes.setdefault(rm, []).append(f"{label}{qty_s}")
    return {"late_checkout": late_co, "notes": notes}

def parse_rooms(text: str) -> pd.DataFrame:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    if not lines: return pd.DataFrame()
    rows = [re.split(r"\t", l) for l in lines]
    header = [c.strip().lower() for c in rows[0]]

    def col(*names):
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
        if norm_svc == "__SKIP__": continue
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
        has_stayover_excel = "stayover" in notes_raw_val or "stay over" in notes_raw_val
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
    if g["c140"]+u140 > 1: return False
    if g["c140"]>=1 and g["c120"]>=1 and sum(1 for r in unit if r["time"]!=70)>0: return False
    return True

def can_add_ds(g, unit, allow_overflow=False):
    if g.get("service_type") != SVC_DS: return False
    ut = sum(r["time"] for r in unit)
    cap = DS_OVER if allow_overflow else MAX_DS
    if g["time"]+ut > cap: return False
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
        score = prx * 10000 + rem
        if score < best_score: best_score, bi = score, i
    return bi

def pack_rooms(room_list, svc, can_add_fn, unit_ok_fn):
    if not room_list: return []
    import re as _re2
    for r in room_list:
        r["guest"] = _re2.sub(r'\s+', ' ', r.get("guest","").strip())
    gmap = {}
    for r in room_list: gmap.setdefault(r["guest"],[]).append(r)
    seen, units = set(), []
    for r in room_list:
        if r["guest"] not in seen:
            seen.add(r["guest"]); units.append(gmap[r["guest"]])
    units.sort(key=lambda u:(
        u[0].get("bld",0), u[0].get("floor",0),
        -sum(r["time"] for r in u), -len(u),
    ))
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
    cap2 = MAX_DS if svc == SVC_DS else MAX_FC
    active = [g for g in groups if g["rooms"]]
    for _round in range(5):
        changed = False
        targets = sorted([g for g in active if g["time"] < LOW_FILL], key=lambda g: g["time"])
        for target in targets:
            candidates = []
            target_blds = target["blds"]
            for donor in active:
                if donor is target: continue
                if len(donor["rooms"]) <= 1: continue
                for room in donor["rooms"]:
                    donor_after = donor["time"] - room["time"]
                    if donor_after < 120: continue
                    if can_add_fn(target, [room]):
                        remaining = cap2 - (target["time"] + room["time"])
                        sb2 = room.get("bld",0) in target_blds
                        prx = proximity_score(target["rooms"], [room])
                        score = (0 if sb2 else 500) + prx * 10 + remaining
                        candidates.append((score, remaining, room, donor))
            candidates.sort(key=lambda x: x[0])
            for score, remaining, room, donor in candidates:
                if remaining < 0: continue
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
        if not changed: break
    return [g for g in groups if g["rooms"]]

def build_all_groups(rooms, priority_hks=None):
    fc_rooms = [r for r in rooms if r.get("service")==SVC_FC]
    ds_rooms = [r for r in rooms if r.get("service")==SVC_DS]
    dv_rooms = [r for r in rooms if r.get("service")==SVC_DV]
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
    fc_groups_normal = pack_rooms(remaining_fc, SVC_FC, can_add_fc, unit_ok_fn=lambda u: unit_ok_fc(u))
    fc_groups = priority_groups + fc_groups_normal
    if ds_rooms:
        ds_groups_pre = pack_rooms(ds_rooms, SVC_DS, lambda g,u:can_add_ds(g,u,False), unit_ok_fn=lambda u:True)
        if ds_groups_pre:
            last = ds_groups_pre[-1]
            last["ds_overflow"] = last["time"] > MAX_DS
        ds_groups = ds_groups_pre
    else:
        ds_groups = []
    if dv_rooms:
        dv_groups = [{"rooms":list(dv_rooms),"time":0,"blds":set(r["bld"] for r in dv_rooms),
                      "floors":set(r.get("floor",0) for r in dv_rooms),"c140":0,"c120":0,
                      "service_type":SVC_DV,"dv_manager":True}]
    else:
        dv_groups = []
    return fc_groups + ds_groups + dv_groups

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
    def hk_can_take(hk_bld, group_blds):
        for gb in group_blds:
            if hk_bld==2 and gb==3: return False
            if hk_bld==3 and gb==2: return False
        return True
    def find_hk(group_blds):
        primary = min(group_blds) if group_blds else 1
        for hk in list(available.get(primary,[])):
            if hk_can_take(roster.get(hk,{}).get("building",0), group_blds):
                available[primary].remove(hk); return hk
        for hk in list(available.get(1,[])):
            available[1].remove(hk); return hk
        for b in [1,2,3]:
            for hk in list(available.get(b,[])):
                if hk_can_take(roster.get(hk,{}).get("building",0), group_blds):
                    available[b].remove(hk); return hk
        for b in [1,2,3]:
            if available.get(b): return available[b].pop(0)
        if present_hk:
            return "⚠️ " + (list(used)[0] if used else "Unassigned")
        return "⚠️ Unassigned"
    for g in groups:
        phk = g.get("priority_hk","")
        if not phk: continue
        if g.get("dv_manager"): assignment[g["label"]]="Manager"; continue
        for b in [1,2,3]:
            if phk in available.get(b,[]):
                available[b].remove(phk); break
        assignment[g["label"]] = phk; used.add(phk)
    for g in groups:
        if g["label"] in assignment: continue
        if g.get("dv_manager"): assignment[g["label"]]="Manager"; continue
        matched = find_hk(g.get("blds",{1}))
        assignment[g["label"]] = matched
        if matched: used.add(matched)
    return assignment, used

def _primary_bld(g): return min(g["blds"]) if g["blds"] else 0
def _group_complexity(g): return sum(r.get("time",70)/70 for r in g.get("rooms",[]))
def _batch_complexity(batch): return sum(_group_complexity(g) for g in batch)
def _insp_travel_score(batch):
    blds=set(); cross=0
    for g in batch:
        blds |= g["blds"]
        if len(g["blds"])>1: cross += len(g["blds"])-1
    return len(blds)*10+cross
def _insp_combined_score(batches):
    tt = sum(_insp_travel_score(b) for b in batches)
    cx = [_batch_complexity(b) for b in batches if b]
    if len(cx)<2: return tt
    return tt*3 + (max(cx)-min(cx))

def assign_inspectors(groups, present_insp, per, rqs1, rqs2):
    fc_groups = [g for g in groups if g.get("service_type")==SVC_FC]
    ds_groups = [g for g in groups if g.get("service_type")==SVC_DS]
    dv_groups = [g for g in groups if g.get("service_type")==SVC_DV]
    inspectors=[]; assigned_names=set()
    if ds_groups and rqs2:
        blds=sorted(set(b for g in ds_groups for b in g["blds"]))
        entry={"id":len(inspectors)+1,"name":rqs2,"role":"RQS2","groups":[g["label"] for g in ds_groups],"buildings":blds}
        for g in ds_groups: g["inspector"]=rqs2
        inspectors.append(entry); assigned_names.add(rqs2)
    if dv_groups and rqs1:
        blds=sorted(set(b for g in dv_groups for b in g["blds"]))
        entry={"id":len(inspectors)+1,"name":rqs1,"role":"RQS1","groups":[g["label"] for g in dv_groups],"buildings":blds}
        for g in dv_groups: g["inspector"]=rqs1
        inspectors.append(entry); assigned_names.add(rqs1)
    fc_sorted=sorted(fc_groups, key=lambda g:(
        _primary_bld(g),
        min(g.get("floors",{0})) if g.get("floors") else 0,
        min(r.get("num",0) for r in g["rooms"]) if g["rooms"] else 0
    ))
    batches=[fc_sorted[i:i+per] for i in range(0,len(fc_sorted),per)]
    improved=True; max_iter=len(batches)*per*2; iters=0
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
    remaining=[n for n in present_insp if n not in assigned_names]
    for batch in batches:
        name=remaining.pop(0) if remaining else f"Inspector {len(inspectors)+1}"
        blds=sorted(set(b for g in batch for b in g["blds"]))
        cx=_batch_complexity(batch)
        entry={"id":len(inspectors)+1,"name":name,"role":"FC",
               "groups":[g["label"] for g in batch],"buildings":blds,
               "travel_warning":len(blds)>2,"heavy_warning":cx>15,"complexity":round(cx,1)}
        for g in batch: g["inspector"]=name
        inspectors.append(entry)
    for g in dv_groups:
        if not g.get("inspector"): g["inspector"]="Manager"
    return inspectors

# ══════════════════════════════════════════════════════════════════════════════
#  HTML BUILDERS
# ══════════════════════════════════════════════════════════════════════════════
def group_card_html(g, idx):
    svc  = g.get("service_type", SVC_FC)
    ac, bg = SVC_PALETTE.get(svc, pal(idx))
    cap  = MAX_DS if svc==SVC_DS else MAX_FC
    pct  = min(int(g["time"]/max(cap,1)*100),100)
    hk_raw = g.get("housekeeper","") or ""
    unassigned_badge = ""
    if not hk_raw or hk_raw.startswith("⚠️"):
        unassigned_badge = ('<span style="background:#fee2e2;color:#9b1c1c;border-radius:5px;'
                           'padding:1px 7px;font-size:.67rem;font-weight:700;margin-left:4px">'
                           '⚠️ No HK — needs assignment</span>')
        hk_raw = hk_raw.replace("⚠️ ","") if hk_raw else "Unassigned"
    hk   = e(hk_raw or "—")
    insp = e(g.get("inspector","") or "—")
    bld_str = " · ".join(f"Bldg {b}" for b in sorted(g["blds"]))
    svc_badge = (f'<span style="background:{ac};color:#fff;border-radius:5px;'
                 f'padding:1px 8px;font-size:.67rem;font-weight:700;margin-left:5px">{e(svc)}</span>')
    overflow_badge = ('<span style="background:#fef3c7;color:#92400e;border-radius:5px;'
                      'padding:1px 7px;font-size:.67rem;font-weight:700;margin-left:4px">⚠️ DS Overflow</span>'
                      if g.get("ds_overflow") else "")
    priority_badge = ('<span style="background:#fef9c3;color:#854d0e;border-radius:5px;'
                      'padding:1px 7px;font-size:.67rem;font-weight:700;margin-left:4px">⭐ Priority</span>'
                      if g.get("priority_hk") else "")
    cross = ('<span style="background:#f3e8ff;color:#7c3aed;border-radius:5px;'
             'padding:1px 7px;font-size:.67rem;font-weight:700;margin-left:4px">Cross-bld</span>'
             if g.get("cross_bld") else "")
    t_col = "#16a34a" if pct<=87 else ("#d97706" if pct<=95 else "#dc2626")
    rows = ""
    for r in g["rooms"]:
        pet = ('<span style="background:#fee2e2;color:#b91c1c;border-radius:5px;'
               'padding:1px 6px;font-size:.66rem;font-weight:700">🐾 Pet</span>'
               if r.get("pet") else "")
        late_co = e(r.get("late_checkout",""))
        late_badge = (f'<span style="background:#fef3c7;color:#92400e;border-radius:5px;'
                      f'padding:1px 6px;font-size:.66rem;font-weight:700">⏰ {late_co}</span>'
                      if late_co else "")
        notes_lower = r.get("notes","").lower()
        is_stayover = "stayover" in notes_lower or "stay over" in notes_lower
        if r.get("uncertain") and is_stayover:
            row_bg = "#f0f7ff"
        elif r.get("uncertain"):
            row_bg = "#fffbf0"
        else:
            row_bg = "transparent"
        rows += f"""<tr style="background:{row_bg}">
          <td style="font-family:'JetBrains Mono',monospace;font-size:.77rem;font-weight:600;color:#0f172a;padding:7px 11px">{e(r.get("room",""))}</td>
          <td style="padding:7px 11px;color:#475569">Bldg {r.get("bld","")}</td>
          <td style="padding:7px 11px;color:#1e293b;font-weight:500">{e(r.get("guest",""))}</td>
          <td style="padding:7px 11px;color:#64748b">{e(r.get("service",""))}</td>
          <td style="padding:7px 11px;font-weight:600;color:#1e293b">{"—" if r.get("time",0)==0 else str(r.get("time",""))+" min"}</td>
          <td style="padding:7px 11px">{pet}</td>
          <td style="padding:7px 11px">{late_badge}</td>
        </tr>"""
    th = ("padding:6px 11px;text-align:left;font-size:.66rem;font-weight:700;"
          "text-transform:uppercase;letter-spacing:.07em;color:#94a3b8;"
          "background:#f8fafc;border-bottom:1px solid #f1f5f9")
    lbl = e(g.get("label",""))
    return f"""<!DOCTYPE html><html><head>{SHARED_CSS}</head><body>
<div style="border-radius:14px;overflow:hidden;border:2px solid {ac}33;
            box-shadow:0 2px 10px rgba(0,0,0,.07);background:#fff;margin-bottom:4px">
  <div style="background:{bg};padding:10px 14px;display:flex;align-items:center;
              gap:10px;flex-wrap:wrap;border-bottom:1px solid {ac}22">
    <div style="display:flex;align-items:center;gap:9px;flex:1;min-width:0;flex-wrap:wrap">
      <div style="background:{ac};color:#fff;border-radius:8px;padding:4px 10px;
                  font-weight:800;font-size:.78rem;white-space:nowrap;flex-shrink:0">{lbl}</div>
      <div style="min-width:0">
        <div style="display:flex;align-items:center;gap:5px;flex-wrap:wrap">
          <span style="font-weight:700;font-size:.9rem;color:#0f172a">Group {lbl}</span>
          {svc_badge} {overflow_badge} {priority_badge} {unassigned_badge} {cross}
        </div>
        <div style="font-size:.72rem;color:#64748b;margin-top:2px">
          {bld_str} &nbsp;·&nbsp; 🧑‍🔧 {hk} &nbsp;·&nbsp; 🔍 {insp}
        </div>
      </div>
    </div>
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
      <th style="{th}">Pet</th><th style="{th}">Late Out</th>
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
    role_map = {"RQS1":("#92400e","#fef3c7","RQS1 · DV"),"RQS2":("#15803d","#dcfce7","RQS2 · DS"),"FC":("#1d4ed8","#dbeafe","Full Clean")}
    rc,rbg,rlbl = role_map.get(role,("#64748b","#f1f5f9",role))
    role_badge = (f'<span style="background:{rbg};color:{rc};border-radius:5px;'
                  f'padding:1px 8px;font-size:.68rem;font-weight:700;margin-left:6px">{rlbl}</span>')
    heavy_warn = (f'<span style="background:#fde8e8;color:#9b1c1c;border-radius:5px;'
                  f'padding:1px 8px;font-size:.68rem;font-weight:700;margin-left:5px">'
                  f'🔴 Heavy ({insp.get("complexity",0)}pts)</span>') if insp.get("heavy_warning") else ""
    pills = ""; total_t = 0
    for gl in insp["groups"]:
        gobj = next((g for g in fg if g["label"]==gl), None)
        if not gobj: continue
        idx  = next((j for j,g in enumerate(fg) if g["label"]==gl), 0)
        ac2,bg2 = pal(idx)
        hk = e(gobj.get("housekeeper","") or f"Grp {gl}")
        total_t += gobj.get("time",0)
        pills += (f'<span style="display:inline-block;background:#fff;border:1.5px solid {ac2}55;'
                  f'border-radius:20px;padding:2px 10px;font-size:.74rem;margin:2px">'
                  f'<span style="font-weight:700;color:{ac2}">{gl}</span> · {hk}</span>')
    return f"""<!DOCTYPE html><html><head>{SHARED_CSS}</head><body>
<div style="border-radius:12px;padding:13px 15px;border:1.5px solid {color}44;background:{color}0d">
  <div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;margin-bottom:6px">
    <span style="font-weight:700;font-size:.9rem;color:{color}">🔍 {name}</span>{role_badge}{heavy_warn}
  </div>
  <div style="margin-bottom:6px">{bld_tags}</div>
  <div>{pills or '<span style="color:#94a3b8;font-size:.77rem">No groups</span>'}</div>
  <div style="margin-top:7px;font-size:.7rem;color:{color}99">{len(insp["groups"])} groups · {total_t} min</div>
</div></body></html>"""

# ══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
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
        auth.logout(); st.rerun()

    st.markdown("## 📅 Daily Attendance")
    st.markdown("---")
    with st.expander("➕ Add / 🗑 Remove Housekeeper"):
        col_a, col_b = st.columns([2,1])
        with col_a: new_hk_name = st.text_input("Name", key="new_hk_inp")
        with col_b: new_hk_bld  = st.selectbox("Bldg", [1,2,3], key="new_hk_bld")
        if st.button("Add HK", key="btn_add_hk"):
            n = new_hk_name.strip()
            if n and n not in st.session_state["hk_roster"]:
                st.session_state["hk_roster"][n] = {"building":new_hk_bld,"present":True}; st.success(f"Added {n}")
        rm_hk = st.selectbox("Remove", ["—"]+list(st.session_state["hk_roster"].keys()), key="rm_hk_sel")
        if st.button("Remove", key="btn_rm_hk") and rm_hk != "—":
            del st.session_state["hk_roster"][rm_hk]; st.success(f"Removed {rm_hk}")

    st.markdown("### 🧑‍🔧 Housekeepers")
    st.caption("Check ✅ to mark present. Use ◀▶ buttons to move between buildings.")
    roster = st.session_state["hk_roster"]
    present_hk = []
    for bld in [1,2,3]:
        ac2, bg2 = BLD_COLORS[bld]
        bld_hks = [n for n,v in roster.items() if v["building"]==bld]
        if not bld_hks: continue
        n_present = sum(1 for n in bld_hks if roster[n]["present"])
        st.markdown(
            f'<div style="background:{bg2};color:{ac2};border-radius:10px;'
            f'padding:6px 12px;font-size:.71rem;font-weight:700;'
            f'display:flex;justify-content:space-between;align-items:center;'
            f'margin:8px 0 4px;border:1px solid {ac2}33">'
            f'Building {bld} <span style="background:{ac2};color:#fff;border-radius:20px;'
            f'padding:1px 8px;font-size:.65rem">{n_present}/{len(bld_hks)}</span></div>',
            unsafe_allow_html=True)
        for name in bld_hks:
            c_chk, c_name, c_left, c_right = st.columns([0.4,3.2,0.6,0.6])
            with c_chk:
                checked = st.checkbox("", value=roster[name]["present"], key=f"att_{name}", label_visibility="collapsed")
                roster[name]["present"] = checked
            with c_name:
                col2 = "inherit" if checked else "#94a3b8"
                td   = "none"    if checked else "line-through"
                st.markdown(f'<div style="font-size:.8rem;color:{col2};padding:4px 0;text-decoration:{td}">{name}</div>', unsafe_allow_html=True)
            with c_left:
                if bld > 1:
                    if st.button("◀", key=f"ml_{name}", use_container_width=True):
                        roster[name]["building"] = bld-1; st.rerun()
            with c_right:
                if bld < 3:
                    if st.button("▶", key=f"mr_{name}", use_container_width=True):
                        roster[name]["building"] = bld+1; st.rerun()
            if roster[name]["present"]: present_hk.append(name)

    st.markdown("---")
    with st.expander("➕ Add / 🗑 Remove Inspector"):
        new_insp = st.text_input("Name", key="new_insp_inp")
        if st.button("Add Inspector", key="btn_add_insp"):
            n = new_insp.strip()
            if n and n not in st.session_state["insp_roster"]:
                st.session_state["insp_roster"][n]=True; st.success(f"Added {n}")
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
st.markdown('<p class="pg-title">🧹 Cleaning Schedule</p>', unsafe_allow_html=True)
st.markdown('<p class="pg-sub">Mark attendance · paste room data · auto-group · assign staff · export</p>', unsafe_allow_html=True)

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
        raw_input = st.text_area("rooms", label_visibility="collapsed", height=230,
            disabled=not auth.can("can_paste_input"),
            placeholder="Room\tService\tTime\tPet\tCurrent Guest or Status\n1020D\tFull Clean\t120\t\tSmith, John",
            key="room_input")
        st.caption("Copy from Excel (include header row).")
    with inp_b:
        email_text = st.text_area("email", label_visibility="collapsed", height=230,
            disabled=not auth.can("can_paste_input"),
            placeholder="Paste today's front-desk email...\n\nLate Checkouts:\n* 10:30 am\n   * 1234A",
            key="email_input")
        st.caption("Late checkouts, room moves, notes auto-matched.")
with col_cfg:
    st.markdown('<p class="sec">⚙️</p>', unsafe_allow_html=True)
    st.markdown(f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;'
                f'padding:11px 13px;font-size:.78rem;color:#475569;margin-bottom:10px">'
                f'<div style="font-weight:700;color:#0f172a;margin-bottom:5px">Today</div>'
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
                    st.error("No valid rows — check tab-separated data.")
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
                        rds.append({
                            "room":r["Room"],"service":r["Service"],"time":r["Time"],
                            "pet":r["Pet"],"guest":r["Guest"],
                            "bld":r.get("bld",get_building(r["Room"])),
                            "floor":r.get("floor",0),"num":r.get("num",0),
                            "late_checkout":late_co,"status":r.get("Status",""),
                            "notes":"; ".join(notes_parts),"arriving":r.get("ArrivingGuest",""),
                            "res_type":r.get("ResType",""),"uncertain":has_stayover,
                        })
                    fg = build_all_groups(rds, priority_hks=st.session_state.get("priority_hks",[]))
                    fc_gs=[g for g in fg if g.get("service_type")==SVC_FC]
                    ds_gs=[g for g in fg if g.get("service_type")==SVC_DS]
                    dv_gs=[g for g in fg if g.get("service_type")==SVC_DV]
                    for g,lbl in zip(fc_gs, make_labels("FC",len(fc_gs))): g["label"]=lbl
                    for g,lbl in zip(ds_gs, make_labels("DS",len(ds_gs))): g["label"]=lbl
                    for g,lbl in zip(dv_gs, make_labels("DV",len(dv_gs))): g["label"]=lbl
                    for g in fg: g["cross_bld"] = len(g["blds"])>1

                    changed=True
                    while changed:
                        changed=False
                        tiny_fc=[g for g in fg if g.get("service_type")==SVC_FC and g["time"]<200 and g["rooms"] and not g.get("priority_hk")]
                        for tg in tiny_fc:
                            best_i,best_rem=-1,9999
                            for j,cand in enumerate(fg):
                                if cand is tg or not cand["rooms"]: continue
                                if cand.get("service_type")!=SVC_FC or cand.get("priority_hk"): continue
                                if not can_add_fc(cand,tg["rooms"]): continue
                                rem=MAX_FC-(cand["time"]+tg["time"])
                                if 0<=rem<best_rem: best_rem,best_i=rem,j
                            if best_i>=0:
                                cand=fg[best_i]
                                for r in tg["rooms"]:
                                    cand["rooms"].append(r); cand["blds"].add(r["bld"]); cand["floors"].add(r.get("floor",0))
                                cand["time"]+=tg["time"]; cand["c140"]+=tg["c140"]; cand["c120"]+=tg["c120"]
                                tg["rooms"]=[]; changed=True
                    fg=[g for g in fg if g["rooms"]]
                    p_fc=[g for g in fg if g.get("service_type")==SVC_FC and g.get("priority_hk")]
                    n_fc=[g for g in fg if g.get("service_type")==SVC_FC and not g.get("priority_hk")]
                    ds2=[g for g in fg if g.get("service_type")==SVC_DS]
                    dv2=[g for g in fg if g.get("service_type")==SVC_DV]
                    for g,lbl in zip(p_fc+n_fc, make_labels("FC",len(p_fc)+len(n_fc))): g["label"]=lbl
                    for g,lbl in zip(ds2, make_labels("DS",len(ds2))): g["label"]=lbl
                    for g,lbl in zip(dv2, make_labels("DV",len(dv2))): g["label"]=lbl
                    for g in fg: g["cross_bld"]=len(g["blds"])>1

                    hk_asgn, used_hk_set = assign_hk_building_aware(fg, present_hk, roster)
                    for g in fg: g["housekeeper"] = hk_asgn.get(g["label"],"")
                    inspectors = assign_inspectors(fg, present_insp, groups_per_insp, rqs1, rqs2)
                    st.session_state.update({"groups_data":fg,"total_rooms":len(df),
                                             "inspectors_data":inspectors,"used_hk_set":used_hk_set})
                    try:
                        db.save_snapshot(_build_snapshot(fg,len(df),inspectors))
                        st.toast("✅ Schedule saved!", icon="✅")
                    except Exception as _se:
                        st.toast(f"⚠️ Not saved to DB: {_se}", icon="⚠️")
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

tab_hk, tab_insp, tab_grp = st.tabs(["🧑‍🔧 Housekeepers","🔍 Inspectors","📋 Groups"])

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
        [lambda r:f'<span style="font-weight:600;color:#1e293b">{e(r["name"])}</span>',
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
        [lambda r:(f'<span style="font-weight:700;color:#0f172a;font-size:.82rem">{e(r["name"])}</span>'
                   +(f'<br><span style="font-size:.68rem;color:#94a3b8">✅ Free</span>' if r["stat"]=="free" else "")),
         insp_role_tag, insp_bld_tags, insp_grp_pills, insp_complexity_tag,
         lambda r:(f'<span style="font-size:.72rem;color:#475569;line-height:1.6">'
                   +"<br>".join(f'<span style="color:#64748b">{e(gl)}</span> <span style="color:#0f172a;font-weight:500">{e(next((g.get("housekeeper","") for g in fg if g["label"]==gl),"—"))}</span>'
                                for gl in r["groups"] if any(g["label"]==gl for g in fg))
                   +"</span>" if r["groups"] else '<span style="color:#94a3b8">—</span>')],
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
    for idx, g in enumerate(fg):
        hk=g.get("housekeeper",""); insp2=g.get("inspector",""); svc2=g.get("service_type","")
        if sel_hk_name  != "All" and hk    != sel_hk_name:  continue
        if sel_rqs_name != "All" and insp2 != sel_rqs_name: continue
        if svc_filter   != "All" and svc2  != svc_filter:   continue
        if bld_sel      != "All":
            sel_b=int(bld_sel.split()[1])
            if sel_b not in g["blds"]: continue
        rooms=g["rooms"]
        if pet_only:     rooms=[r for r in rooms if r.get("pet")]
        if lateout_only: rooms=[r for r in rooms if r.get("late_checkout","")]
        if not rooms: continue
        gd=dict(g); gd["rooms"]=rooms
        components.html(group_card_html(gd,idx), height=115+len(rooms)*42, scrolling=False)

# ══════════════════════════════════════════════════════════════════════════════
#  EXPORT
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
export_rows=[]
for g in fg:
    for r in g["rooms"]:
        export_rows.append({
            "Room":r.get("room",""),"Service":r.get("service",""),
            "Time (min)":r.get("time",""),"Pet":r.get("pet",""),
            "Current Guest or Status":r.get("guest",""),
            "Late Checkout":r.get("late_checkout",""),
            "Housekeeper":g.get("housekeeper",""),"RQS":g.get("inspector",""),
            "Notes":r.get("notes",""),"Status":r.get("status",""),
            "Stripping":"","Carpet":"","Arriving Guest":r.get("arriving",""),
            "Group":g["label"],"Service Type":g.get("service_type",""),
            "Building":f"Building {r.get('bld','')}",
            "Group Total (min)":g["time"],
            "Cross-Building":"Yes" if g.get("cross_bld") else "No",
            "Uncertain":"Yes" if r.get("uncertain") else "No",
        })
export_df = pd.DataFrame(export_rows)
if "Uncertain" in export_df.columns:
    confirmed   = export_df[export_df["Uncertain"]=="No"].sort_values("Group")
    unconfirmed = export_df[export_df["Uncertain"]=="Yes"].sort_values("Group")
    export_df   = pd.concat([confirmed,unconfirmed],ignore_index=True)
csv = export_df.to_csv(index=False).encode("utf-8")
st.download_button("⬇️ Download CSV", data=csv, file_name="cleaning_schedule.csv", mime="text/csv")
