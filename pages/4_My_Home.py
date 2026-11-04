"""
My Home — one person's own schedule.

This week and next straight from the staff sheet, plus what they have actually
worked. Everyone signed in gets this page, housekeepers included.
"""
import streamlit as st
import sys, os, re, datetime
import html as _html
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, db, clock, i18n, roster_import as ri
import ui
import fresh

# See 3_Roster_Import.py: a deploy can leave a stale roster_import in
# sys.modules, so reload it rather than dying on a helper it does not have yet.
if getattr(ri, "__version__", 0) < 16:
    import importlib
    ri = importlib.reload(ri)

st.set_page_config(page_title="My Home · Cleaning Schedule",
                   page_icon="GC8", layout="wide")
st.markdown("""<style>[data-testid="stSidebarNav"]{display:none !important;}</style>""",
            unsafe_allow_html=True)

# One guard for every page: it restores a signed-in browser from its cookie
# and, failing that, goes to the sign-in screen. The hand-rolled version that
# used to sit here seeded logged_in=False into the session before init_auth
# ran, which made the restore skip itself -- so a refresh on this page could
# never have brought anybody back, cookie or no cookie.
auth.require_login()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto+Flex:opsz,wght@8..144,400;8..144,500;8..144,700&display=swap');
:root{--bg:#f4f5f7;--border:#e4e8ee;--indigo:#2563a8;
  --txt:#1f2733;--txt2:#5b6675;--txt3:#8a93a1;}
*{box-sizing:border-box;}
html,body,[class*="css"]{font-family:'DM Sans',sans-serif!important;color:var(--txt)!important;}
.stApp{background:#f4f5f7!important;}
.block-container{padding-top:1.1rem!important;max-width:1180px;}

.hero{position:relative;overflow:hidden;border-radius:18px;padding:24px 28px;color:#fff;
  margin-bottom:18px;background:linear-gradient(120deg,#16324f 0%,#22598f 48%,#3b7fb8 100%);
  box-shadow:0 10px 30px rgba(22,50,79,.20);animation:rise .45s cubic-bezier(.16,1,.3,1) both}
.hero:after{content:"";position:absolute;right:-70px;top:-90px;width:280px;height:280px;
  border-radius:50%;background:radial-gradient(circle,rgba(255,255,255,.16),transparent 68%)}
.hero h1{font-family:'Syne',sans-serif;font-size:1.8rem;font-weight:800;margin:0 0 3px;
  letter-spacing:-.03em;position:relative}
.hero p{margin:0;font-size:.86rem;opacity:.88;position:relative}
.hero .role{display:inline-block;background:rgba(255,255,255,.2);border-radius:20px;
  padding:3px 13px;font-size:.66rem;font-weight:700;letter-spacing:.09em;
  text-transform:uppercase;margin-top:10px;position:relative}
@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}

.sec{font-family:'DM Mono',monospace!important;font-size:.6rem;font-weight:500;
  text-transform:uppercase;letter-spacing:.16em;color:var(--txt2);
  padding-bottom:6px;border-bottom:1px solid var(--border);margin:1.4rem 0 .8rem}
.lbl{font-family:'DM Mono',monospace;font-size:.6rem;letter-spacing:.13em;
  text-transform:uppercase;color:var(--txt3);margin:14px 0 7px}

.dayrow{display:grid;grid-template-columns:repeat(7,1fr);gap:10px}
.day{background:#fff;border:1px solid var(--border);border-radius:14px;padding:13px 12px;
  min-height:112px;display:flex;flex-direction:column;
  transition:transform .13s ease,box-shadow .13s ease}
.day:hover{transform:translateY(-3px);box-shadow:0 10px 22px rgba(31,39,51,.10)}
.day.today{border-color:#2563a8;box-shadow:0 0 0 2px rgba(37,99,168,.18)}
.day.past{opacity:.62}
.day.empty{background:#fafbfc;border-style:dashed}
.day .dow{font-family:'DM Mono',monospace;font-size:.58rem;letter-spacing:.11em;
  text-transform:uppercase;color:var(--txt3);white-space:nowrap}
.day .num{font-family:'Syne',sans-serif;font-size:1.5rem;font-weight:800;color:#16202e;
  line-height:1.05;margin:2px 0 9px}
.day .what{font-size:.74rem;font-weight:600;border-radius:8px;padding:5px 8px;
  display:block;line-height:1.28;word-break:break-word}
.day .what.none{background:transparent;color:#b6bfcb;font-weight:400;font-style:italic;padding-left:0}
.day .means{font-size:.65rem;color:var(--txt3);margin-top:7px;line-height:1.35}

.nextup{background:#eef4fb;border:1px solid #cddff0;border-radius:10px;padding:9px 14px;
  font-size:.8rem;color:#1c4a78;margin:12px 0 4px}

.kpi{background:#fff;border:1px solid var(--border);border-radius:14px;padding:15px 17px;height:100%}
.kpi .n{font-family:'DM Sans',sans-serif;font-size:1.85rem;font-weight:700;color:#16202e;
  line-height:1;font-variant-numeric:tabular-nums}
.kpi .l{font-family:'DM Mono',monospace;font-size:.58rem;text-transform:uppercase;
  letter-spacing:.12em;color:var(--txt3);margin-top:5px}
.kpi .s{font-size:.7rem;color:var(--txt2);margin-top:6px;padding-top:6px;
  border-top:1px solid #f0f3f7}

.bar{display:flex;align-items:center;gap:10px;margin:4px 0}
.bar .d{width:34px;font-size:.75rem;color:var(--txt2)}
.bar .track{flex:1;background:#eaeef3;border-radius:5px;height:16px;overflow:hidden}
.bar .fill{height:16px;border-radius:5px;transition:width .4s cubic-bezier(.16,1,.3,1)}
.bar .v{width:26px;text-align:right;font-size:.75rem;font-weight:600;
  font-variant-numeric:tabular-nums}
.pill{display:inline-block;border-radius:7px;padding:3px 10px;font-size:.7rem;font-weight:700;
  margin:0 5px 5px 0}
footer{visibility:hidden!important;}#MainMenu{visibility:hidden!important;}
header[data-testid="stHeader"]{background:transparent!important;height:0!important;}
section[data-testid="stSidebar"]{background:#fff!important;border-right:1px solid var(--border)!important;}
@media (max-width:900px){
  .dayrow{grid-template-columns:repeat(4,1fr)}
}
@media (max-width:560px){
  .block-container{padding-left:.5rem!important;padding-right:.5rem!important;}
  .hero h1{font-size:1.35rem}
  .dayrow{grid-template-columns:repeat(2,1fr)}
  .day{min-height:98px}
}

/* ── Material 3 (HP chose it, 4 Nov), matching My Rooms ──
   Tonal surfaces, one type family, and on a phone the week as a list -- one
   short row a day -- instead of a grid of tall cards, and the counts two by
   two instead of one full-width card each. Last, so it wins. */
html,body,[class*="css"]{font-family:'Roboto Flex',Roboto,system-ui,sans-serif!important;}
.stApp{background:#f9f9ff!important;}
.hero{background:#ecedf5;color:#191c20;box-shadow:none;border-radius:28px;padding:20px 22px}
.hero:after{display:none}
.hero h1{font-family:inherit;font-weight:500;letter-spacing:0;font-size:1.5rem}
.hero p{color:#43474e;opacity:1}
.hero .role{background:#d6e3ff;color:#001b3e}
.sec,.lbl,.day .dow,.kpi .l{font-family:inherit!important;letter-spacing:.06em}
.sec{font-size:.75rem;font-weight:500;border-bottom:none;margin:1.2rem 4px .6rem}
.day{border:none;border-radius:16px;box-shadow:0 1px 2px rgba(25,28,32,.08)}
.day .num{font-family:inherit;font-weight:500}
.day.today{box-shadow:0 0 0 2px #005ac1}
.nextup{background:#d6e3ff;border:none;border-radius:16px;color:#001b3e}
.kpi{border:none;border-radius:20px;box-shadow:0 1px 2px rgba(25,28,32,.08)}
.kpi .n{font-family:inherit;font-weight:500}
@media (max-width:560px){
  .dayrow{display:flex;flex-direction:column;gap:0;background:#fff;border-radius:20px;
    overflow:hidden;box-shadow:0 1px 2px rgba(25,28,32,.08)}
  .day{flex-direction:row;align-items:center;gap:12px;min-height:52px;padding:8px 16px;
    border-radius:0;box-shadow:none;border-top:1px solid #eef0f5}
  .day:first-child{border-top:none}
  .day:hover{transform:none;box-shadow:none}
  .day.today{box-shadow:inset 4px 0 0 #005ac1;background:#eef4fb}
  .day .dow{width:96px;flex:0 0 auto;font-size:.8rem;color:#43474e;white-space:nowrap}
  .day .num{order:-1;width:28px;flex:0 0 auto;margin:0;font-size:1.15rem}
  .day .what{display:inline-block}
  .day .means{display:none}
  .day.empty{background:#fff;border-style:none}
  .kpi{padding:12px 14px}
  .kpi .n{font-size:1.5rem}
  /* The four counts, and the four figures under the period, two by two. */
  :is(.st-key-mhkpi,.st-key-mhmet) [data-testid="stHorizontalBlock"]{
    flex-wrap:wrap !important;gap:8px !important}
  :is(.st-key-mhkpi,.st-key-mhmet) [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]{
    min-width:calc(50% - 4px) !important;flex:1 1 calc(50% - 4px) !important;width:auto !important;
    max-width:calc(50% - 4px) !important}
  .st-key-mhkpi [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]{margin-bottom:0 !important}
  .st-key-mhkpi .kpi{margin-bottom:8px}
}
</style>""", unsafe_allow_html=True)

fresh.latest("i18n", "ui")    # the menu as it is on disk, not as first loaded
ui.topnav("My Home")
def e(s): return _html.escape(str(s) if s is not None else "")

def person_label(info, section=None):
    """Name for a picker: the person, their team, and their home property if
    they are visiting from one."""
    txt = f'{info["label"]}  ·  {section or info["sections"][0]}'
    return txt + f'  ·  {info["home"]}' if info.get("home") else txt


# Same brighter palette as the Roster Import grid, so the pages read alike.
KIND_STYLE = {
    ri.KIND_WORKING: ("#a7f0bf", "#08532c", "Working"),
    ri.KIND_DAILY:   ("#93ebe5", "#04504b", "Daily Service"),
    ri.KIND_OTHER:   ("#ffdc73", "#6f3d00", "Working — other duty"),
    ri.KIND_VTO:     ("#b9c2ff", "#1d24a3", "VTO — paid"),
    # Red is reserved for the thing the workbook paints red.
    ri.KIND_NOCALL:  ("#ff8f8f", "#6d0b0b", "No call / no show"),
    ri.KIND_OFF:     ("#e9eef4", "#7d8896", "Off"),
    ri.KIND_UNKNOWN: ("#ddb3ff", "#4c1580", "Check with your lead"),
}

cu = auth.current_user()
me_display = cu.get("display_name") or ""
me_user = cu.get("username", "")

week_keys = db.staff_week_keys()
if not week_keys:
    st.markdown(f'<div class="hero"><h1>{_html.escape(i18n.t("home.hello"))}</h1>'
                f'<p>{_html.escape(i18n.t("home.no_sheet"))}</p></div>', unsafe_allow_html=True)
    st.info(i18n.t("home.no_sheet_body"))
    st.stop()

@st.cache_data(ttl=300, show_spinner=False)
def _all_rows(_token: str):
    return ri.history_rows(db.load_staff_weeks(), db.load_staff_overrides())

meta = db.load_staff_meta() or {}
overrides = db.load_staff_overrides()
rows = _all_rows(f'{meta.get("uploaded_at","")}|{len(week_keys)}|{len(overrides)}')
index = ri.people_index(rows)


def _current_sections(rows):
    """{pid: "Building 3"} -- where each person is listed now: today's row if
    there is one, else the nearest day of this week, else their latest. The
    hero used to show `sections[0]`, the alphabetically first section the
    person had ever been in, so Jennyfer (Building 3 this week, Building 2
    once) was shown Building 2 -- sixteen people were, on 10 Oct. Someone on
    two rows the same day (Nancy: Building 3 and Houseperson PM) gets both."""
    t = clock.today().isoformat()
    best = {}
    for r in rows:
        k = (r["date"] != t, abs((datetime.date.fromisoformat(r["date"]) - clock.today()).days),
             r["date"] > t)
        cur = best.get(r["pid"])
        if cur is None or k < cur[0]:
            best[r["pid"]] = (k, {r["date"]: [r["section"]]})
        elif k == cur[0]:
            cur[1].setdefault(r["date"], []).append(r["section"])
    return {pid: " · ".join(dict.fromkeys(next(iter(v[1].values())))) for pid, v in best.items()}


now_section = _current_sections(rows)

# Sign-in names rarely match the sheet exactly, so try the display name and the
# username, which often carries digits or dots. A login named by a nickname
# ("DIANIS") is first turned into the full name the app's name directory has
# for it -- the nickname alone can match an old spelling with no weeks left.
try:
    import staff_names
    _aliases = staff_names.aliases()
    _dir = {k.lower(): v for k, v in _aliases.items()}
    _full = _dir.get(me_display.strip().lower(), "") if me_display else ""   # "ARACELI" too
except Exception:
    _aliases, _full = {}, ""
# The name directory also says who a bare first name on the sheet is, so
# "Edgar Onofre Moran" is not handed Edgar Martinez's week (23 Oct). A running
# app may still hold a roster_import from before `aliases` existed.
try:
    mine = ri.match_person(index, *[n for n in (_full, me_display) if n], me_user,
                           aliases=_aliases)
except TypeError:
    mine = ri.match_person(index, *[n for n in (_full, me_display) if n], me_user)
# Only admins look up other people. RQS and housekeepers see themselves —
# this page is personal, and the roster pages already cover the whole team.
can_browse = auth.can("can_manage_users")
#: Whose page this is, as opposed to whose schedule is on it: only the person
#: themselves gets the change notice and the link to their rooms.
_me_pid = mine

if mine is None or can_browse:
    order = sorted(index, key=lambda p: index[p]["label"].lower())
    labels = [person_label(index[p], now_section.get(p)) for p in order]
    # Somebody the schedule doesn't know starts on nobody, not on the first
    # name in the list: unmatched, Edgar Onofre Moran was shown Adrian Lopez's
    # week (23 Oct) until he changed it.
    default = order.index(mine) if mine in order else (0 if can_browse else None)
    sel = st.selectbox(
        i18n.t("home.whose") if can_browse else i18n.t("home.pick_yours"),
        labels, index=default, key="mh_person", placeholder=i18n.t("home.pick_name"))
    if sel is None:
        st.info(i18n.t("home.not_listed"))
        st.stop()
    mine = order[labels.index(sel)]
    if _me_pid is None and not can_browse:
        _me_pid = mine

# One person, every row. The sheet keeps somebody who works two sections as
# two rows ("Federico Lopez" and "Federico Lopez · Houseperson PM"), and each
# row was a person of its own here: Federico's 639 PM days, Leonardo's
# overnights and Rosibel's Houseperson AM never reached their pages (23 Oct).
# A day on two rows shows both cells and counts as worked if either does.
def _base(pid):
    return ri.norm_name(str(index[pid]["label"]).split(" · ")[0])


_mine_all = {p for p in index if _base(p) == _base(mine)} | {mine}
if len(_mine_all) > 1:
    _days = {}
    for _r in rows:
        if _r["pid"] not in _mine_all:
            continue
        _r = dict(_r, pid=mine)
        _was = _days.get(_r["date"])
        if _was is None:
            _days[_r["date"]] = _r
        elif _r["worked"] and not _was["worked"]:
            _days[_r["date"]] = _r
        elif _r["worked"] and _was["worked"] and _r["raw"] and _r["raw"] != _was["raw"]:
            _days[_r["date"]] = dict(_was, raw=f'{_was["raw"]} · {_r["raw"]}')
    rows = [r for r in rows if r["pid"] not in _mine_all] + list(_days.values())

info = index[mine]
s_all = ri.summarise_person(rows, pid=mine)
by_date = {r["date"]: r for r in s_all["rows"]}
today = clock.today()
t_iso = today.isoformat()
greet = info["label"].split()[0].title()

# ── The page, in the order people need it (HP, 4 Nov) ──────────────────────
# Today first -- the shift, and the rooms if there are any -- then anything
# that changed on the sheet since it was last read, tomorrow and the next day
# off, the schedule a week at a time, and one month's figures. The counts,
# charts and day-by-day table that used to fill the page sit behind "My full
# record": they answer a manager's question, not the one a housekeeper opens
# the page with. Everything here speaks the reader's language.
T = i18n.t
_ES = i18n.lang() == "es"
_DOW = (["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"])[_ES]
_MON = (["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"])[_ES]
_MONTH = (["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
          ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
           "septiembre", "octubre", "noviembre", "diciembre"])[_ES]

#: What each kind of day is called, in the reader's language.
_KIND_T = {ri.KIND_WORKING: T("home.kind_working"), ri.KIND_DAILY: T("home.kind_daily"),
           ri.KIND_OTHER: T("home.kind_other"), ri.KIND_VTO: T("home.kind_vto"),
           ri.KIND_NOCALL: T("home.kind_nocall"), ri.KIND_OFF: T("home.off"),
           ri.KIND_UNKNOWN: T("home.kind_unknown")}
_SHIFT_T = {"Daily Service": T("home.kind_daily"), "Room cover": T("home.shift_cover"),
            "Other duty": T("home.kind_other"), "Regular": T("home.shift_regular")}


def _day_name(d):
    """'Wed, Nov 4' / 'mié 4 nov'."""
    return (f"{_DOW[d.weekday()]} {d.day} {_MON[d.month - 1]}" if _ES
            else f"{_DOW[d.weekday()]}, {_MON[d.month - 1]} {d.day}")


#: roster_import's task and zone meanings, in Spanish. Kept here, keyed by
#: the English, so a running app's older roster_import still gets them.
_LEGEND_ES = {
    "Breakroom - Bld 2 or 3 (clean and tidy)": "Sala de descanso - Edif. 2 o 3 (limpiar y ordenar)",
    "Linea vieja / mattress pad - check cart closet": "Línea vieja / protector de colchón - revisar el clóset de carritos",
    "Vacuum & cart - keep clean and serviceable": "Aspiradora y carrito - mantener limpios y en buen estado",
    "Amenities bottles - clean, refill, organise": "Botellas de amenidades - limpiar, rellenar, organizar",
    "Garages - pick up trash B1/B2/B3": "Garajes - recoger basura E1/E2/E3",
    "Runner Building 2": "Runner Edificio 2",
    "Lobby": "Lobby",
    "Pool - Building 1": "Piscina - Edificio 1",
    "Runner Building 1": "Runner Edificio 1",
    "Runner Building 3": "Runner Edificio 3",
    "Pool - Building 3": "Piscina - Edificio 3",
    "Plaza - Building 3": "Plaza - Edificio 3",
}

#: The sheet's own words for a day, where they are words rather than codes.
_RAW_ES = {"daily service": "Servicio diario", "daily services": "Servicio diario",
           "vto": "VTO", "sick": "Enfermo/a", "vacation": "Vacaciones",
           "training": "Entrenamiento", "projects": "Proyectos", "garages": "Garajes",
           "touch up": "Retoques", "deep clean": "Limpieza profunda", "maps": "Mapas",
           "stripping linen": "Quitar ropa de cama", "breck inn": "Breck Inn"}

#: A cell that names units is a deep clean of those units ("3141A + 3242B").
_UNITS_RE = re.compile(r"\b\d{4}[A-Ia-i]\b")


def _say(r):
    """(what the cell says, what it means) for one day, in the reader's language."""
    if r is None:
        return T("home.not_on_sheet"), ""
    raw = str(r.get("raw") or "").strip()
    if r["kind"] == ri.KIND_OFF:
        return T("home.off"), ("" if raw.lower() in ("", "off", "r/off", "r off") else raw)
    meaning = ri.legend_for(r, raw)
    if _ES:
        meaning = _LEGEND_ES.get(meaning, meaning)
        raw = _RAW_ES.get(raw.lower(), raw)
    if not meaning and _UNITS_RE.search(raw):
        meaning = T("home.deep_clean")
    return raw or _KIND_T[r["kind"]], meaning


_HEADLINE = {ri.KIND_WORKING: "home.on", ri.KIND_DAILY: "home.on",
             ri.KIND_OTHER: "home.other", ri.KIND_OFF: "home.off_today",
             ri.KIND_VTO: "home.vto_today", ri.KIND_NOCALL: "home.nocall_today"}


@st.cache_data(ttl=60, show_spinner=False)
def _rooms_today(label):
    """Today's rooms for this person, if they have any: how many are done,
    the next one in walking order and the finish time -- My Rooms' numbers."""
    try:
        import assignments
        import roomstatus as rst
        import daystart as day
        charts, sts = assignments.todays_charts()
        hk = assignments.match_name(assignments.housekeepers(charts), label, "")
        rooms = [r for g in charts if hk and g.get("housekeeper") == hk
                 for r in (g.get("rooms") or [])]
        if not rooms:
            return None
        clean = lambda code: rst.is_clean((sts.get(str(code)) or {}).get("status"))
        plan = day.plan_day(rooms)
        return {"done": sum(1 for r in rooms if clean(r.get("room", ""))),
                "total": len(rooms),
                "next": next((b["room"] for b in plan if not clean(b["room"])), None),
                "finish": day.hhmm(day.summary(plan)["finish"]) if plan else ""}
    except Exception as ex:                 # the rooms are a bonus, never the page
        print(f"[my_home] rooms today: {ex}")
        return None


def _hhmm(stamp):
    try:
        t = datetime.datetime.fromisoformat(str(stamp))
        s = t.strftime("%I:%M %p").lstrip("0").lower()
        return s if t.date() == today else f"{_day_name(t.date())}, {s}"
    except Exception:
        return ""


viewing_self = mine == _me_pid
r_today = by_date.get(t_iso)
st.markdown("""<style>
.hm-today{background:#d6e3ff;border-radius:28px;padding:18px 20px;margin:0 0 4px;color:#001b3e}
.hm-top{display:flex;align-items:center;gap:8px}
.hm-over{font-size:.75rem;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:#00458f}
.hm-chip{margin-left:auto;font-size:.75rem;font-weight:600;background:#fff;padding:4px 10px;border-radius:8px}
.hm-head{font-size:1.55rem;font-weight:400;margin-top:10px;line-height:1.25}
.hm-mean{font-size:.88rem;color:#2e4772;margin-top:2px}
.hm-rooms{display:flex;align-items:center;gap:12px;background:#fff;border-radius:16px;
  padding:12px 14px;margin-top:14px;color:#191c20}
.hm-rooms b{display:block;font-size:1rem;font-weight:500}
.hm-rooms span{display:block;font-size:.82rem;color:#43474e}
.st-key-hmrooms [data-testid="stPageLink"],.st-key-hmrooms [data-testid="stPageLink"] a{
  width:100% !important;max-width:none !important}
.st-key-hmrooms [data-testid="stPageLink"] a{background:#005ac1 !important;border-radius:16px !important;
  min-height:48px !important;justify-content:center !important}
.st-key-hmgotit{align-items:flex-end}
.st-key-hmweek [data-testid="stHorizontalBlock"]{flex-direction:row !important;flex-wrap:nowrap !important}
.st-key-hmweek [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]{
  min-width:0 !important;flex:1 1 auto !important;width:auto !important}
.st-key-hmweek [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child{flex:0 0 auto !important}
.st-key-hmrooms [data-testid="stPageLink"] a *{color:#fff !important;font-weight:500 !important}
.hm-chg{background:#ffefc8;border-radius:16px;padding:12px 14px;color:#4a3300}
.hm-chg b{display:block;font-size:.92rem}
.hm-chg div{font-size:.85rem;margin-top:2px}
.st-key-hmgotit button{min-height:36px !important;border:none !important;background:transparent !important;
  color:#4a3300 !important;font-weight:600 !important;margin-top:-6px}
.hm-tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.hm-tile{background:#fff;border-radius:20px;padding:14px;box-shadow:0 1px 2px rgba(25,28,32,.08)}
.hm-tile small{display:block;font-size:.78rem;color:#43474e}
.hm-tile b{display:block;font-size:1.2rem;font-weight:500;margin-top:4px}
.hm-list{background:#fff;border-radius:20px;overflow:hidden;box-shadow:0 1px 2px rgba(25,28,32,.08)}
.hm-row{min-height:52px;padding:6px 16px;display:flex;align-items:center;gap:12px;border-top:1px solid #eef0f5}
.hm-row:first-child{border-top:none}
.hm-row .d{width:62px;flex:0 0 auto;font-size:.82rem;color:#43474e}
.hm-row .d b{font-size:.95rem;font-weight:500;color:#191c20}
.hm-row .w{flex:1 1 auto;min-width:0}
.hm-row .w i{font-style:normal;font-size:.82rem;font-weight:600;padding:3px 10px;border-radius:8px;
  display:inline-block;overflow-wrap:anywhere}
.hm-row .w small{display:block;font-size:.75rem;color:#43474e;margin-top:2px}
.hm-row.past{opacity:.6}
.hm-row.today{background:#eef4fb;box-shadow:inset 4px 0 0 #005ac1}
.hm-tag{font-size:.68rem;font-weight:700;padding:2px 6px;border-radius:6px;white-space:nowrap}
.hm-tag.t{color:#00458f}
.hm-tag.c{color:#6b4a00;background:#ffefc8}
.hm-sum{background:#fff;border-radius:20px;padding:14px 16px;box-shadow:0 1px 2px rgba(25,28,32,.08)}
.hm-sumh{display:flex;align-items:center;font-size:.95rem;font-weight:500}
.hm-sumh span{margin-left:auto;font-size:.82rem;font-weight:400;color:#43474e}
.hm-figs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:10px;text-align:center}
.hm-figs div{background:#f3f4fa;border-radius:14px;padding:10px 4px}
.hm-figs b{display:block;font-size:1.35rem;font-weight:500}
.hm-figs span{display:block;font-size:.75rem;color:#43474e}
.hm-sec{font-size:.95rem;font-weight:500;margin:6px 4px 0}
.st-key-hmweek [data-testid="stButtonGroup"]{justify-content:flex-end}
@media (min-width:821px){.hm-head{font-size:1.8rem}}
</style>""", unsafe_allow_html=True)

# 1. Today: the shift, and the rooms with one tap to them.
_said, _means = _say(r_today)
_head = T(_HEADLINE.get(r_today["kind"], "home.unknown_today")) if r_today else T("home.unknown_today")
_rt = _rooms_today(info["label"].split(" · ")[0])
def _sect_t(s):
    """A sheet section ("Building 2") in the reader's language."""
    s = str(s or "")
    if not _ES:
        return s
    return (s.replace("Building", "Edificio").replace("Overnight Team", "Equipo de noche")
            .replace("Managers", "Gerentes"))


_sect = _sect_t(now_section.get(mine) or info["sections"][0])
_rooms_html = ""
if _rt:
    _arc = 100.5 * _rt["done"] / _rt["total"]
    _sub = " · ".join(x for x in (T("home.next_room", room=_rt["next"]) if _rt["next"] else "",
                                  T("home.finish", t=_rt["finish"]) if _rt["finish"] else "") if x)
    _rooms_html = (
        f'<div class="hm-rooms"><svg width="40" height="40" viewBox="0 0 40 40" role="img" '
        f'aria-label="{e(T("home.rooms_line", done=_rt["done"], total=_rt["total"]))}">'
        f'<circle cx="20" cy="20" r="16" fill="none" stroke="#d6e3ff" stroke-width="5"/>'
        f'<circle cx="20" cy="20" r="16" fill="none" stroke="#005ac1" stroke-width="5" '
        f'stroke-linecap="round" stroke-dasharray="{_arc:.1f} 101" transform="rotate(-90 20 20)"/></svg>'
        f'<div><b>{e(T("home.rooms_line", done=_rt["done"], total=_rt["total"]))}</b>'
        f'<span>{e(_sub)}</span></div></div>')
st.markdown(
    f'<div class="hm-today"><div class="hm-top">'
    f'<span class="hm-over">{e(T("home.today"))} · {e(_day_name(today))}</span>'
    f'<span class="hm-chip">{e(_sect)}{" · " + e(info["home"]) if info.get("home") else ""}</span></div>'
    f'<div class="hm-head">{e(T("home.hi", name=greet))} — {e(_head)}</div>'
    # What the cell says, unless it only says "ON" -- the headline already has.
    + (f'<div class="hm-mean">{e(_said)}{" · " + e(_means) if _means else ""}</div>'
       if r_today and r_today["kind"] != ri.KIND_OFF
       and (_means or _said.strip().upper() not in ("ON", "ON AM", "ON PM")) else "")
    + f'{_rooms_html}</div>', unsafe_allow_html=True)
if _rt and viewing_self:
    with st.container(key="hmrooms"):
        st.page_link("pages/5_My_Rooms.py", label=T("home.open_rooms"), icon=":material/bed:",
                     width="stretch")

# 2. What changed on the sheet since this person last said "got it".
_changed_days = set()
if viewing_self:
    _seen_key = f"staffchg_seen_{me_user or me_display}"
    try:
        _log = (db._load_key("staff_changes") or {}).get("changes") or []
        _seen_at = (db._load_key(_seen_key) or {}).get("at", "")
    except Exception as _ex:
        print(f"[my_home] change log: {_ex}")
        _log, _seen_at = [], ""
    _mine_chg = [c for c in _log
                 if c.get("date", "") >= t_iso and str(c.get("at", "")) > _seen_at
                 and ri.norm_name(str(c.get("name", "")).split(" · ")[0]) == _base(mine)]
    # One line per day, the latest change to it.
    _by_day = {}
    for c in sorted(_mine_chg, key=lambda c: c["at"]):
        _by_day[c["date"]] = c
    if _by_day:
        _changed_days = set(_by_day)

        def _cell(v):
            return str(v).strip() or T("home.off")

        st.markdown(
            f'<div class="hm-chg"><b>{e(T("home.changed"))}</b>'
            + "".join(f'<div>{e(_day_name(datetime.date.fromisoformat(d)))}: '
                      f'{e(_cell(c["old"]))} → {e(_cell(c["new"]))}'
                      f' · {e(T("home.updated", t=_hhmm(c["at"])))}</div>'
                      for d, c in sorted(_by_day.items()))
            + '</div>', unsafe_allow_html=True)

        def _got_it(at):
            try:
                db._upsert_key(_seen_key, {"at": at})
            except Exception as ex:
                print(f"[my_home] could not store the read marker: {ex}")

        with st.container(key="hmgotit"):
            st.button(T("home.got_it"), key="hm_gotit", on_click=_got_it,
                      args=(max(c["at"] for c in _by_day.values()),))

# 3. Tomorrow, and the next change of state: a day off if working, back on if not.
_tom = today + datetime.timedelta(days=1)
_ahead = sorted(d for d in by_date if d > t_iso)
_working_now = bool(r_today and r_today["worked"])
_flip = next((d for d in _ahead if bool(by_date[d]["worked"]) != _working_now), None)
st.markdown(
    f'<div class="hm-tiles">'
    f'<div class="hm-tile"><small>{e(T("home.tomorrow", d=_day_name(_tom)))}</small>'
    f'<b>{e(_say(by_date.get(_tom.isoformat()))[0])}</b></div>'
    f'<div class="hm-tile"><small>{e(T("home.next_off" if _working_now else "home.back_on"))}</small>'
    f'<b>{e(_day_name(datetime.date.fromisoformat(_flip)) if _flip else T("home.none_ahead"))}</b></div>'
    f'</div>', unsafe_allow_html=True)

# 4. The schedule, a week at a time, each code with what it means.
this_sun = today - datetime.timedelta(days=(today.weekday() + 1) % 7)
_wk_opts = ["this", "next"]
with st.container(key="hmweek"):
    _c1, _c2 = st.columns([1, 2], vertical_alignment="center")
    _c1.markdown(f'<div class="hm-sec">{e(T("home.schedule"))}</div>', unsafe_allow_html=True)
    with _c2:
        _which = st.segmented_control(
            T("home.schedule"), _wk_opts, default="this", key="hm_week",
            format_func=lambda k: T("home.this_week" if k == "this" else "home.next_week"),
            label_visibility="collapsed") or "this"
_start = this_sun + datetime.timedelta(days=7 if _which == "next" else 0)
_rows_html = ""
for i in range(7):
    d = _start + datetime.timedelta(days=i)
    iso = d.isoformat()
    r = by_date.get(iso)
    said, means = _say(r)
    bg, fg, _lbl = KIND_STYLE[r["kind"]] if r else ("#f3f4fa", "#43474e", "")
    cls = "hm-row" + (" today" if iso == t_iso else " past" if iso < t_iso else "")
    tag = (f'<span class="hm-tag t">{e(T("home.today_tag"))}</span>' if iso == t_iso else
           f'<span class="hm-tag c">{e(T("home.changed_tag"))}</span>' if iso in _changed_days else
           '<span aria-label="✓">✓</span>' if iso < t_iso and r and r["worked"] else "")
    _rows_html += (f'<div class="{cls}"><span class="d"><b>{e(_DOW[d.weekday()])}</b> {d.day}</span>'
                   f'<span class="w"><i style="background:{bg};color:{fg}">{e(said)}</i>'
                   + (f'<small>{e(means)}</small>' if means else "")
                   + f'</span>{tag}</div>')
st.markdown(f'<div class="hm-list">{_rows_html}</div>', unsafe_allow_html=True)

# 5. This month, in three figures.
wk_s, mo_s, yr_s = ri.period_bounds(today)
wk_e = (this_sun + datetime.timedelta(days=6)).isoformat()
mo_e = ((today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        - datetime.timedelta(days=1)).isoformat()
yr_e = today.replace(month=12, day=31).isoformat()


def tally(start, end):
    """Whole-period total, and how much of it has already happened.

    The headline is the FULL period: on a Wednesday "days this week" should be
    the four days you are down for, not the two you have already done.
    """
    span = [r for r in s_all["rows"] if start <= r["date"] <= end and r["worked"]]
    done = [r for r in span if r["date"] <= t_iso]
    return len(span), len(done), len(span) - len(done)


_mo = ri.summarise_person([r for r in s_all["rows"] if mo_s <= r["date"] <= mo_e], pid=mine)
_mo_total, _mo_done, _ = tally(mo_s, mo_e)
st.markdown(
    f'<div class="hm-sum"><div class="hm-sumh">{e(_MONTH[today.month - 1].title())}'
    f'<span>{e(T("home.week_line", n=tally(wk_s, wk_e)[0]))}</span></div>'
    f'<div class="hm-figs">'
    f'<div><b>{_mo_total}</b><span>{e(T("home.to_work"))}</span>'
    f'<span>{e(T("home.done_n", n=_mo_done))}</span></div>'
    f'<div><b>{_mo["off"]}</b><span>{e(T("home.days_off"))}</span></div>'
    f'<div><b>{_mo["n_paid_off"]}</b><span>VTO</span></div>'
    f'</div></div>', unsafe_allow_html=True)

# 6. Everything else, for whoever wants it.
_record = st.expander(T("home.full_record"))
with _record:
    # The four running counts.
    cols = st.container(key="mhkpi").columns(4)
    cards = [(*tally(wk_s, wk_e), T("home.k_week")),
             (*tally(mo_s, mo_e), T("home.k_month")),
             (*tally(yr_s, yr_e), T("home.k_year")),
             (s_all["n_worked"], s_all["n_worked"], 0, T("home.k_record"))]
    for col, (total, done, ahead, lbl) in zip(cols, cards):
        sub = (f'<div class="s">{e(T("home.so_far", done=done, ahead=ahead))}</div>' if ahead else
               f'<div class="s">{e(T("home.all_complete"))}</div>' if total else '')
        col.markdown(f'<div class="kpi"><div class="n">{total}</div>'
                     f'<div class="l">{e(lbl)}</div>{sub}</div>', unsafe_allow_html=True)

    # The counters above are a fixed summary. Everything below follows this
    # filter, so a pattern can be read for one month or one year.
    all_dates = sorted(r["date"] for r in s_all["rows"])
    f1, f2 = st.columns([2, 3])
    with f1:
        grain = st.radio(T("home.period"), ["Week", "Month", "Year", "All time"],
                         horizontal=True, index=1, key="mh_grain",
                         format_func=lambda g: T("home.g_" + g.split()[0].lower()),
                         label_visibility="collapsed")

    def _week_start(iso):
        d = datetime.date.fromisoformat(iso)
        return (d - datetime.timedelta(days=(d.weekday() + 1) % 7)).isoformat()

    if grain == "Week":
        keys = sorted({_week_start(d) for d in all_dates}, reverse=True)
        fmt = lambda k: T("home.week_of", d=_day_name(datetime.date.fromisoformat(k)))
    elif grain == "Month":
        keys = sorted({d[:7] for d in all_dates}, reverse=True)
        fmt = lambda k: f"{_MONTH[int(k[5:7]) - 1].title()} {k[:4]}"
    elif grain == "Year":
        keys = sorted({d[:4] for d in all_dates}, reverse=True)
        fmt = lambda k: k
    else:
        keys, fmt = ["all"], lambda k: T("home.everything")

    with f2:
        default = 0
        if grain == "Week" and _week_start(t_iso) in keys:
            default = keys.index(_week_start(t_iso))
        elif grain == "Month" and t_iso[:7] in keys:
            default = keys.index(t_iso[:7])
        elif grain == "Year" and t_iso[:4] in keys:
            default = keys.index(t_iso[:4])
        picked = st.selectbox(T("home.which"), keys, index=default, format_func=fmt,
                              key=f"mh_pick_{grain}", label_visibility="collapsed")

    if grain == "Week":
        sel = [r for r in s_all["rows"] if _week_start(r["date"]) == picked]
    elif grain == "Month":
        sel = [r for r in s_all["rows"] if r["date"].startswith(picked)]
    elif grain == "Year":
        sel = [r for r in s_all["rows"] if r["date"].startswith(picked)]
    else:
        sel = list(s_all["rows"])

    s_sel = ri.summarise_person(sel, pid=mine)
    if not sel:
        st.info(T("home.nothing"))
    else:
        m = st.container(key="mhmet").columns(4)
        done_sel = sum(1 for r in s_sel["worked"] if r["date"] <= t_iso)
        m[0].metric(T("home.m_worked"), s_sel["n_worked"],
                    delta=(T("home.n_so_far", n=done_sel) if s_sel["n_worked"] != done_sel else None),
                    delta_color="off")
        m[1].metric(T("home.days_off"), s_sel["off"])
        m[2].metric(T("home.m_nocall"), s_sel["n_no_call"])
        m[3].metric(T("home.m_vto"), s_sel["n_paid_off"])

        # summarise_person names weekdays in English; the reader may not.
        _dw = dict(zip(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], _DOW))
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown(f'<div class="lbl">{e(T("home.days_you_work"))}</div>',
                        unsafe_allow_html=True)
            mx = max(s_sel["by_dow"].values()) or 1
            bars = ""
            for d, n in s_sel["by_dow"].items():
                pct = int(100 * n / mx)
                fill = "#005ac1" if n >= mx * 0.6 else "#cbd5e1"
                bars += (f'<div class="bar"><span class="d">{e(_dw.get(d, d))}</span>'
                         f'<div class="track"><div class="fill" '
                         f'style="width:{max(pct, 2)}%;background:{fill}"></div></div>'
                         f'<span class="v">{n}</span></div>')
            st.markdown(bars, unsafe_allow_html=True)
            if s_sel["usual_days"]:
                st.caption(T("home.usually", days=", ".join(_dw.get(d, d) for d in s_sel["usual_days"])))
        with c2:
            st.markdown(f'<div class="lbl">{e(T("home.roles_shifts"))}</div>', unsafe_allow_html=True)
            chips = ""
            for k2, v2 in list(s_sel["roles"].items())[:4]:
                chips += (f'<span class="pill" style="background:#e7eef8;color:#001b3e">'
                          f'{e(_sect_t(k2))} · {v2}</span>')
            for k2, v2 in s_sel["shifts"].items():
                bg, fg = {"Daily Service": ("#c5f2ef", "#0b5c58"),
                          "Room cover": ("#ede9fe", "#5b21b6"),
                          "Other duty": ("#fdecc4", "#8a5300")}.get(k2, ("#d7f5df", "#14663a"))
                chips += (f'<span class="pill" style="background:{bg};color:{fg}">'
                          f'{e(_SHIFT_T.get(k2, k2))} · {v2}</span>')
            if s_sel["n_no_call"]:
                chips += (f'<span class="pill" style="background:#ffc9c9;color:#8f1414">'
                          f'{e(T("home.m_nocall"))} · {s_sel["n_no_call"]}</span>')
            if s_sel["n_paid_off"]:
                chips += (f'<span class="pill" style="background:#dfe3ff;color:#2f3597">'
                          f'VTO · {s_sel["n_paid_off"]}</span>')
            st.markdown(chips or '<span style="color:#8a93a1">—</span>', unsafe_allow_html=True)
            pctw = 100 * s_sel["n_worked"] / max(s_sel["n_days"], 1)
            st.markdown(f'<div style="margin-top:10px;font-size:.8rem;color:#43474e">'
                        f'{e(T("home.worked_of", n=s_sel["n_worked"], of=s_sel["n_days"], pct="%.0f" % pctw))}'
                        f'</div>', unsafe_allow_html=True)

    # Every day of the period, newest first. Not an expander: one cannot sit
    # inside another.
    st.markdown(f'<div class="lbl">{e(T("home.every_day", p=fmt(picked)))}</div>',
                unsafe_allow_html=True)
    past = sorted([r for r in sel if r["date"] <= t_iso], key=lambda x: x["date"], reverse=True)
    if past:
        st.dataframe(
            pd.DataFrame([{T("home.c_date"): _day_name(datetime.date.fromisoformat(r["date"])),
                           T("home.c_team"): _sect_t(r["section"]),
                           T("home.c_sched"): _say(r)[0] if r["raw"] else "—",
                           T("home.c_status"): _KIND_T[r["kind"]],
                           T("home.c_means"): _say(r)[1] or "—"} for r in past]),
            use_container_width=True, hide_index=True,
            height=min(60 + 33 * len(past), 460))
