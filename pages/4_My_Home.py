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
# An admin's link from account to sheet row beats any guess: a new hire is a
# first name on the sheet ("Janelly") and krafael@ is the sheet's "Enrique".
try:
    import account_links
    fresh.latest("account_links")
    mine = account_links.find_pid(index, account_links.link_for(me_user), _aliases) or mine
except Exception as _ex:
    print(f"[my_home] account link: {_ex}")
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


def _es_time(txt):
    """Spanish says "a la 1:15" but "a las 2:15"; the phrases are written
    with "las", so one o'clock is put right here."""
    return re.sub(r"las (1:\d\d)", r"la ", txt) if _ES else txt


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
           "training": "Entrenamiento", "training with": "Entrenamiento", "projects": "Proyectos", "garages": "Garajes",
           "touch up": "Retoques", "deep clean": "Limpieza profunda", "maps": "Mapas",
           "stripping linen": "Quitar ropa de cama", "breck inn": "Breck Inn"}

_TRAIN_RE = re.compile(r"^training\s+(with|in)\s+(.+)$", re.I)
_TRAIN_ES = {"new employees": "empleados nuevos", "daily services": "servicio diario",
             "daily service": "servicio diario"}


def _raw_t(raw):
    """A sheet cell in the reader's language where it is words, not a code:
    "Training with Grace" reads "Entrenamiento con Grace"; "ON" and "R/OFF"
    stay as the sheet has them."""
    raw = str(raw or "")
    if not _ES:
        return raw
    low = raw.strip().lower()
    if low in _RAW_ES:
        return _RAW_ES[low]
    m = _TRAIN_RE.match(raw.strip())
    if m:
        what = _TRAIN_ES.get(m.group(2).strip().lower(), m.group(2).strip())
        return f"Entrenamiento {'con' if m.group(1).lower() == 'with' else 'en'} {what}"
    return raw


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
        raw = _raw_t(raw)
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
# ── The page's own cards (laid out again 11 Nov, HP: "the metrics should make
# sense", "looks very close") ──
# Phone: one column in the order people need it. Computer: Today and what is
# coming on the left, the week on the right, the day counts across the bottom.
# A markdown block eats the 15px gap under it (Streamlit pulls its container up
# by a rem), so every card that is plain HTML carries its own gap.
st.markdown("""<style>
.hm-chg,.hm-next,.hm-list,.hm-sum{margin:0 0 16px !important}
.hm-over{font-size:.75rem;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:#00458f}

/* Today: the shift, the rooms and the way to them, and who the RQS is -- one
   card. A keyed container rather than one block of HTML, so the My Rooms
   button can sit inside it. */
.st-key-hmtoday{background:#d6e3ff;border-radius:28px;padding:18px 18px 16px;
  gap:12px !important;color:#001b3e;margin-bottom:1px}
.st-key-hmtoday [data-testid="stMarkdownContainer"]{margin-bottom:0 !important}
.hm-top{display:flex;align-items:center;gap:8px}
.hm-chip{margin-left:auto;font-size:.75rem;font-weight:600;background:#fff;padding:4px 10px;
  border-radius:8px;color:#001b3e}
.hm-head{font-size:1.55rem;font-weight:400;margin-top:10px;line-height:1.25;color:#001b3e}
.hm-mean{font-size:.88rem;color:#2e4772;margin-top:2px}
.hm-rooms{display:flex;align-items:center;gap:12px;background:#fff;border-radius:16px;
  padding:12px 14px;margin-top:14px;color:#191c20}
.hm-rooms b{display:block;font-size:1rem;font-weight:500}
.hm-rooms span{display:block;font-size:.82rem;color:#43474e}
.st-key-hmrooms [data-testid="stPageLink"],.st-key-hmrooms [data-testid="stPageLink"] a{
  width:100% !important;max-width:none !important}
.st-key-hmrooms [data-testid="stPageLink"] a{background:#005ac1 !important;border-radius:16px !important;
  min-height:48px !important;justify-content:center !important}
.st-key-hmrooms [data-testid="stPageLink"] a *{color:#fff !important;font-weight:500 !important}
/* Who to ask on the floor today. */
.hm-rqs{display:flex;align-items:center;gap:12px;background:rgba(255,255,255,.62);
  border-radius:16px;padding:10px 14px;color:#191c20}
.hm-rqs svg{flex:0 0 auto}
.hm-rqs .who{flex:1 1 auto;min-width:0}
.hm-rqs small{display:block;font-size:.7rem;font-weight:600;letter-spacing:.07em;
  text-transform:uppercase;color:#00458f}
.hm-rqs b{display:block;font-size:1rem;font-weight:500;overflow-wrap:anywhere}
.hm-rqs b i{font-style:normal;font-size:.72rem;font-weight:600;color:#00458f;background:#d6e3ff;
  border-radius:6px;padding:1px 6px;margin-right:6px;white-space:nowrap}
.hm-rqs .ask{display:block;font-size:.78rem;color:#43474e;margin-top:1px}

.hm-chg{background:#ffefc8;border-radius:20px;padding:12px 16px;color:#4a3300}
.hm-chg b{display:block;font-size:.92rem;font-weight:600}
.hm-chg div{font-size:.86rem;margin-top:2px}

/* Tomorrow and the next change, one card, a line each. */
.hm-next{background:#fff;border-radius:20px;padding:2px 16px;box-shadow:0 1px 2px rgba(25,28,32,.08)}
.hm-next > div{display:flex;align-items:center;gap:12px;min-height:50px;padding:8px 0;
  border-top:1px solid #eef0f5}
.hm-next > div:first-child{border-top:none}
.hm-next span{font-size:.86rem;color:#43474e}
.hm-next b{margin-left:auto;font-size:.98rem;font-weight:500;text-align:right;color:#191c20}
.hm-pill{font-style:normal;font-size:.82rem;font-weight:600;padding:3px 10px;border-radius:8px;
  display:inline-block;overflow-wrap:anywhere}
.hm-next .hm-pill{margin-left:auto;text-align:right}

/* The calendar: one square a day, the sheet's Sunday-first week. */
.hm-cal{background:#fff;border-radius:20px;padding:14px 14px 12px;margin:0 0 16px !important;
  box-shadow:0 1px 2px rgba(25,28,32,.08)}
.hm-calh{display:flex;align-items:baseline;gap:8px;margin:0 2px 10px}
.hm-calh b{font-size:1.05rem;font-weight:500;color:#191c20}
.hm-calh span{margin-left:auto;font-size:.78rem;color:#43474e;text-align:right}
.hm-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:5px}
.hm-dow{font-size:.66rem;font-weight:600;letter-spacing:.05em;text-transform:uppercase;
  color:#5b6170;text-align:center;padding-bottom:2px}
.hm-cell{position:relative;aspect-ratio:1/1;max-height:62px;min-width:0;border-radius:12px;
  display:flex;flex-direction:column;align-items:center;justify-content:center}
.hm-cell b{font-size:1rem;font-weight:500;line-height:1;font-variant-numeric:tabular-nums}
.hm-cell i{font-style:normal;font-size:.5rem;line-height:1;height:.5rem;margin-top:3px;font-weight:700}
.hm-cell u{position:absolute;top:3px;left:0;right:0;text-align:center;text-decoration:none;
  font-size:.5rem;font-weight:600;letter-spacing:.04em;text-transform:uppercase;opacity:.8}
.hm-cell.past{opacity:.5}
.hm-cell.none{background:transparent;color:#8a93a1;box-shadow:inset 0 0 0 1px #e1e4ec}
.hm-cell.today{box-shadow:0 0 0 2px #fff,0 0 0 4px #005ac1}
.hm-cell.today b{font-weight:700}
.hm-leg{display:flex;flex-wrap:wrap;gap:6px 14px;margin:12px 2px 0;font-size:.76rem;color:#43474e}
.hm-leg span{display:inline-flex;align-items:center;gap:6px}
.hm-leg i{width:16px;height:16px;border-radius:5px;display:inline-flex;align-items:center;
  justify-content:center;font-style:normal;font-size:.5rem;font-weight:700}
.hm-leg i.none{box-shadow:inset 0 0 0 1px #c9cedb}
.hm-sec{font-size:.95rem;font-weight:500;margin:2px 4px 8px;color:#191c20}
.hm-row.wk{border-top:6px solid #f3f4fa}

/* Pico. */
.hm-headrow{display:flex;align-items:center;gap:8px;margin-top:6px}
.hm-headrow .hm-head{flex:1 1 auto;min-width:0;margin-top:0}
.hm-pico{flex:0 0 auto;overflow:visible;cursor:pointer;touch-action:manipulation;
  -webkit-tap-highlight-color:transparent;user-select:none}
.hm-pico .jump{transform-box:fill-box;transform-origin:50% 100%;
  transition:transform .8s cubic-bezier(.28,1.9,.42,1)}
.hm-pico:active .jump{transform:translateY(-10px) rotate(-8deg) scale(1.07);transition:transform .07s ease-out}
.hm-pico .bd{transform-box:fill-box;transform-origin:50% 100%;animation:picobreath 3.6s ease-in-out infinite}
.hm-pico .arm{transform-box:view-box;transform-origin:57px 43px;animation:picowave 5.5s ease-in-out infinite}
.hm-pico .eye{transform-box:fill-box;transform-origin:50% 50%;animation:picoblink 4.6s infinite}
.hm-pico .mouth{transform-box:fill-box;transform-origin:50% 0;transition:transform .5s ease}
.hm-pico:active .mouth{transform:scale(1.35,1.6);transition:transform .07s}
.hm-pico .spark{transform-box:fill-box;transform-origin:50% 50%;opacity:0;transform:scale(.3) rotate(0deg);
  transition:opacity .9s ease-out,transform .9s ease-out}
.hm-pico:active .spark{opacity:1;transform:scale(1.25) rotate(40deg);transition:opacity .05s,transform .12s}
@media (hover:hover){
  .hm-pico:hover .jump{transform:translateY(-4px)}
  .hm-pico:hover:active .jump{transform:translateY(-10px) rotate(-8deg) scale(1.07)}
  .hm-pico:hover .arm{animation-duration:1.1s}
  .hm-pico:hover .spark{opacity:.9;transform:scale(1) rotate(20deg)}
}
@keyframes picowave{0%,34%,100%{transform:rotate(0deg)}
  5%,17%,29%{transform:rotate(-24deg)}11%,23%{transform:rotate(12deg)}}
@keyframes picoblink{0%,45%,51%,100%{transform:scaleY(1)}48%{transform:scaleY(.08)}}
@keyframes picobreath{0%,100%{transform:scale(1,1)}50%{transform:scale(1.015,.975)}}
@media (prefers-reduced-motion:reduce){
  .hm-pico *{animation:none !important;transition:none !important}}
@media (max-width:420px){.hm-pico{width:64px;height:57px}}

/* The day counts are drawn in both places; each width shows one. The whole
   element goes where :has() is understood, so no empty gap is left. */
@media (max-width:640px){.hm-wide{display:none}
  [data-testid="stElementContainer"]:has(.hm-wide){display:none !important}}
@media (min-width:641px){.hm-narrow{display:none}
  [data-testid="stElementContainer"]:has(.hm-narrow){display:none !important}
  .hm-wide .hm-days{grid-template-columns:1fr}}
.hm-list{background:#fff;border-radius:20px;overflow:hidden;box-shadow:0 1px 2px rgba(25,28,32,.08)}
.hm-row{min-height:52px;padding:6px 16px;display:flex;align-items:center;gap:12px;border-top:1px solid #eef0f5}
.hm-list > .hm-row:first-child{border-top:none}
.hm-row .d{width:62px;flex:0 0 auto;font-size:.82rem;color:#43474e}
.hm-row .d b{font-size:.95rem;font-weight:500;color:#191c20}
.hm-row .w{flex:1 1 auto;min-width:0}
.hm-row .w small{display:block;font-size:.75rem;color:#43474e;margin-top:2px}
.hm-row.today{background:#eef4fb;box-shadow:inset 4px 0 0 #005ac1}
.hm-tag{font-size:.68rem;font-weight:700;padding:2px 6px;border-radius:6px;white-space:nowrap}
.hm-tag.t{color:#00458f}
.hm-tag.c{color:#6b4a00;background:#ffefc8}

/* The day counts: a line each on a phone, side by side on a computer. */
.hm-sum{background:#fff;border-radius:20px;padding:14px 16px 16px;box-shadow:0 1px 2px rgba(25,28,32,.08)}
.hm-sumh{font-size:.95rem;font-weight:500}
.hm-days{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px;margin-top:10px}
.hm-day{display:flex;align-items:center;gap:12px;background:#f3f4fa;border-radius:14px;
  padding:10px 14px;min-width:0}
.hm-day > div{flex:1 1 auto;min-width:0}
.hm-day b{display:block;font-size:.9rem;font-weight:500;color:#191c20}
.hm-day small{display:block;font-size:.76rem;color:#43474e;margin-top:1px}
.hm-day .n{flex:0 0 auto;font-size:1.45rem;font-weight:500;color:#191c20;white-space:nowrap;
  font-variant-numeric:tabular-nums}
.hm-day .n i{font-style:normal;font-size:.78rem;font-weight:400;color:#43474e;margin-left:4px}
.hm-day.warn{background:#ffe9e6}
.hm-day.vto{background:#e7e9ff}
@media (min-width:821px){.hm-head{font-size:1.8rem}}
</style>""", unsafe_allow_html=True)

_cols = st.container(key="hmcols").columns(2, gap="medium")

#: Pico, the little peak by the greeting (HP, 11 Nov: "a cute animated
#: character near the title to wave at them"). Peak 8's own mountain: it
#: waves and blinks by itself, lifts under a mouse, and hops when tapped --
#: all CSS on an inline SVG, so there is no script and no frame to load.
#: Each press hops again: the hop is a transition back from :active, not an
#: animation that would only play once.
_PICO = (
    '<svg class="hm-pico" viewBox="0 0 76 68" width="76" height="68" role="img" aria-label="%HI%">'
    '<title>%HI%</title>'
    '<g transform="translate(9 16)"><path class="spark" d="M0-5 1.300-1.300 5 0 1.300 1.300 0 5-1.300 1.300-5 0-1.300-1.300Z" fill="#fff"/></g>'
    '<g transform="translate(67 9)"><path class="spark s2" d="M0-4 1-1 4 0 1 1 0 4-1 1-4 0-1-1Z" fill="#fff"/></g>'
    '<g transform="translate(71 40)"><path class="spark s3" d="M0-3.500 .900-.900 3.500 0 .900.900 0 3.500-.900.900-3.500 0-.900-.900Z" fill="#ffb300"/></g>'
    '<ellipse cx="38" cy="64" rx="24" ry="3" fill="#00458f" opacity=".16"/>'
    '<g class="jump"><g class="bd">'
    '<path d="M17 47 8 53" stroke="#2f6fc4" stroke-width="5" stroke-linecap="round" fill="none"/>'
    '<circle cx="7" cy="54" r="4.200" fill="#ffb300"/>'
    '<g class="arm"><path d="M57 43 66 31" stroke="#2f6fc4" stroke-width="5" stroke-linecap="round" fill="none"/>'
    '<circle cx="67" cy="29" r="4.400" fill="#ffb300"/></g>'
    '<ellipse cx="28" cy="61.500" rx="6" ry="3" fill="#1f4f96"/><ellipse cx="48" cy="61.500" rx="6" ry="3" fill="#1f4f96"/>'
    '<path d="M12 60Q7 60 10 55L32 14Q38 5 44 14L66 55Q69 60 64 60Z" fill="#2f6fc4"/>'
    '<path d="M38 7.500Q41.500 8.500 44 14L66 55Q69 60 64 60L47 60Z" fill="#5a93e2" opacity=".5"/>'
    '<path d="M32 14Q38 5 44 14L50 25 45 22 41 27 38 22 34 27 31 22 26 25Z" fill="#fff"/>'
    '<g class="eye"><ellipse cx="31" cy="40" rx="2.700" ry="3.100" fill="#001b3e"/><circle cx="32" cy="38.900" r=".900" fill="#fff"/></g>'
    '<g class="eye"><ellipse cx="45" cy="40" rx="2.700" ry="3.100" fill="#001b3e"/><circle cx="46" cy="38.900" r=".900" fill="#fff"/></g>'
    '<circle cx="25" cy="46.500" r="3.200" fill="#ff8fa8" opacity=".8"/><circle cx="51" cy="46.500" r="3.200" fill="#ff8fa8" opacity=".8"/>'
    '<path class="mouth" d="M33.500 46Q38 51.500 42.500 46" stroke="#001b3e" stroke-width="2.200" stroke-linecap="round" fill="none"/>'
    '</g></g></svg>')

# 1. Today: the shift, the rooms with one tap to them, and who the RQS is.
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


# Who is RQS 1 and RQS 2 today, for everyone (HP, 11 Nov): a housekeeper or
# houseperson who needs help on the floor knows whom to ask. Read off the staff
# sheet with the in-app edits, the same way the Schedule page fills its RQS
# 1 / RQS 2 boxes ("RQS 1 + RQS 2" is one person doing both).
@st.cache_data(ttl=300, show_spinner=False)
def _rqs_today(iso, _token):
    wk = ri.find_week_key(db.staff_week_keys(), iso)
    if not wk:
        return "", ""
    upd = ri.day_roster(db.load_staff_week(wk), db.load_staff_overrides(), wk, iso)
    return (upd["rqs1"] or "", upd["rqs2"] or "") if upd else ("", "")


try:
    _r1, _r2 = _rqs_today(t_iso, f'{meta.get("uploaded_at", "")}|{len(overrides)}')
except Exception as _ex:
    print(f"[my_home] rqs today: {_ex}")
    _r1 = _r2 = ""
_rqs_html = ""
if _r1 or _r2:
    if _r1 == _r2:
        _who = f'<b>{e(_r1)}</b>'
    else:
        _who = "".join(f'<b><i>{k}</i>{e(v or T("home.rqs_none"))}</b>'
                       for k, v in (("RQS 1", _r1), ("RQS 2", _r2)))
    _rqs_html = (
        '<div class="hm-rqs"><svg width="36" height="36" viewBox="0 0 36 36" aria-hidden="true">'
        '<circle cx="18" cy="18" r="18" fill="#d6e3ff"/><circle cx="18" cy="14" r="5" fill="#00458f"/>'
        '<path d="M8 28c1.6-5 5.4-7 10-7s8.400 2 10 7z" fill="#00458f"/></svg>'
        f'<div class="who"><small>{e(T("home.rqs_both" if _r1 == _r2 else "home.rqs_title"))}</small>'
        f'{_who}<span class="ask">'
        f'{e(T("home.rqs_ask" if (_r1 and _r2 and _r1 != _r2) else "home.rqs_ask1"))}</span></div></div>')

_sect = _sect_t(now_section.get(mine) or info["sections"][0])
_rooms_html = ""
if _rt:
    _arc = 100.5 * _rt["done"] / _rt["total"]
    _sub = " · ".join(x for x in (T("home.next_room", room=_rt["next"]) if _rt["next"] else "",
                                  _es_time(T("home.finish", t=_rt["finish"])) if _rt["finish"] else "") if x)
    _rooms_html = (
        f'<div class="hm-rooms"><svg width="40" height="40" viewBox="0 0 40 40" role="img" '
        f'aria-label="{e(T("home.rooms_line", done=_rt["done"], total=_rt["total"]))}">'
        f'<circle cx="20" cy="20" r="16" fill="none" stroke="#d6e3ff" stroke-width="5"/>'
        f'<circle cx="20" cy="20" r="16" fill="none" stroke="#005ac1" stroke-width="5" '
        f'stroke-linecap="round" stroke-dasharray="{_arc:.1f} 101" transform="rotate(-90 20 20)"/></svg>'
        f'<div><b>{e(T("home.rooms_line", done=_rt["done"], total=_rt["total"]))}</b>'
        f'<span>{e(_sub)}</span></div></div>')
with _cols[0]:
    with st.container(key="hmtoday"):
        st.markdown(
            f'<div class="hm-today"><div class="hm-top">'
            f'<span class="hm-over">{e(T("home.today"))} · {e(_day_name(today))}</span>'
            f'<span class="hm-chip">{e(_sect)}{" · " + e(info["home"]) if info.get("home") else ""}</span></div>'
            f'<div class="hm-headrow"><div class="hm-head">{e(T("home.hi", name=greet))} — {e(_head)}</div>'
            f'{_PICO.replace("%HI%", e(T("home.pico")))}</div>'
            # What the cell says, unless it only says "ON" -- the headline already has.
            + (f'<div class="hm-mean">{e(_said)}{" · " + e(_means) if _means else ""}</div>'
               if r_today and r_today["kind"] != ri.KIND_OFF
               and (_means or _said.strip().upper() not in ("ON", "ON AM", "ON PM")) else "")
            + f'{_rooms_html}</div>', unsafe_allow_html=True)
        if _rt and viewing_self:
            with st.container(key="hmrooms"):
                st.page_link("pages/5_My_Rooms.py", label=T("home.open_rooms"), icon=":material/bed:",
                             width="stretch")
        if _rqs_html:
            st.markdown(_rqs_html, unsafe_allow_html=True)

# 2. What changed on the sheet for this person -- shown once (HP, 11 Nov). It
# used to stay until "Got it" was pressed, and people who never pressed it saw
# the same notice every time they opened the app. Now the notice is marked
# seen the moment it is drawn. It stays through this visit's reruns (the week
# switch, the language button) from a copy in the session, and is gone on the
# next visit. A visit starts when the full record's period picker (mh_grain,
# drawn on every run, further down) has no state yet: Streamlit drops a
# widget's state when another page is shown.
_changed_days = set()
if viewing_self:
    _seen_key = f"staffchg_seen_{me_user or me_display}"
    if "mh_grain" not in st.session_state or "hm_chg_shown" not in st.session_state:
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
        st.session_state["hm_chg_shown"] = _by_day
        if _by_day:
            try:
                db._upsert_key(_seen_key, {"at": max(c["at"] for c in _by_day.values())})
            except Exception as _ex:
                print(f"[my_home] could not store the read marker: {_ex}")
    _by_day = st.session_state.get("hm_chg_shown") or {}
    if _by_day:
        _changed_days = set(_by_day)

        def _cell(v):
            return _raw_t(str(v).strip()) or T("home.off")

        # No "Got it" button any more: the notice is gone by itself next time.
        _cols[0].markdown(
            f'<div class="hm-chg"><b>{e(T("home.changed"))}</b>'
            + "".join(f'<div>{e(_day_name(datetime.date.fromisoformat(d)))}: '
                      f'{e(_cell(c["old"]))} → {e(_cell(c["new"]))}'
                      f' · {e(T("home.updated", t=_hhmm(c["at"])))}</div>'
                      for d, c in sorted(_by_day.items()))
            + '</div>', unsafe_allow_html=True)


def _worked(n):
    """'2 worked' / '1 trabajado': Spanish counts one differently."""
    return T("home.worked_1") if n == 1 else T("home.worked_n", n=n)


def _pill(r):
    """A day's cell as the coloured pill the week list uses."""
    bg, fg, _lbl = KIND_STYLE[r["kind"]] if r else ("#f3f4fa", "#43474e", "")
    return f'<i class="hm-pill" style="background:{bg};color:{fg}">{e(_say(r)[0])}</i>'


# 3. Tomorrow, and the next change after it: the next day off if tomorrow is a
# work day, back to work if it is not. It used to compare with today, so
# somebody off tomorrow read "Tomorrow: Off" beside "Next day off: tomorrow".
_tom = today + datetime.timedelta(days=1)
_r_tom = by_date.get(_tom.isoformat())
_tom_on = bool(_r_tom and _r_tom["worked"])
_after = sorted(d for d in by_date if d > _tom.isoformat())
_flip = next((d for d in _after if bool(by_date[d]["worked"]) != _tom_on), None)
_cols[0].markdown(
    f'<div class="hm-next">'
    f'<div><span>{e(T("home.tomorrow", d=_day_name(_tom)))}</span>{_pill(_r_tom)}</div>'
    f'<div><span>{e(T("home.next_off" if _tom_on else "home.back_on"))}</span>'
    f'<b>{e(_day_name(datetime.date.fromisoformat(_flip)) if _flip else T("home.none_ahead"))}</b></div>'
    f'</div>', unsafe_allow_html=True)

# 4. The schedule: every day that is posted (HP, 11 Nov: "this is going to be
# their only source to see on which day they are working ... show as many
# dates as possible"). It was one week at a time behind a switch. Now a
# calendar gives the shape of it -- this month from its first week to the
# last day posted, a work day and a rest day told apart at a glance -- and
# under it every day from today on with what the sheet says.
this_sun = today - datetime.timedelta(days=(today.weekday() + 1) % 7)
_first = today.replace(day=1)
_cal_start = _first - datetime.timedelta(days=(_first.weekday() + 1) % 7)
_posted = [d for d in by_date if d >= _cal_start.isoformat()]
_last_day = max([datetime.date.fromisoformat(max(_posted))] if _posted else [], default=today)
_last_day = max(_last_day, today)
_cal_end = _last_day + datetime.timedelta(days=(5 - _last_day.weekday()) % 7)   # its Saturday
# Never more than ten weeks: a sheet with a stray far-off date must not
# draw a year of empty squares.
_cal_end = min(_cal_end, _cal_start + datetime.timedelta(days=69))

#: (mark in the square, legend words) per kind of day. The mark is there for
#: anyone who cannot tell the colours apart.
_CAL = {ri.KIND_WORKING: ("●", "home.lg_work"), ri.KIND_DAILY: ("●", "home.lg_daily"),
        ri.KIND_OTHER: ("◆", "home.lg_other"), ri.KIND_VTO: ("V", "home.lg_vto"),
        ri.KIND_NOCALL: ("!", "home.lg_nocall"), ri.KIND_OFF: ("", "home.lg_off"),
        ri.KIND_UNKNOWN: ("?", "home.lg_unknown")}
_dow_sun = [_DOW[6]] + _DOW[:6]                    # the sheet's week starts on Sunday
_cells = "".join(f'<div class="hm-dow">{e(x)}</div>' for x in _dow_sun)
_kinds_seen, _unposted = [], False
_d = _cal_start
while _d <= _cal_end:
    iso = _d.isoformat()
    r = by_date.get(iso)
    cls = "hm-cell" + (" today" if iso == t_iso else " past" if iso < t_iso else "")
    # The month's name on a square that belongs to another month.
    _mo_tag = (f'<u>{e(_MON[_d.month - 1])}</u>'
               if _d.month != today.month and (_d.day == 1 or _d == _cal_start) else "")
    if r:
        bg, fg, _lbl = KIND_STYLE[r["kind"]]
        if r["kind"] not in _kinds_seen:
            _kinds_seen.append(r["kind"])
        _cells += (f'<div class="{cls}" style="background:{bg};color:{fg}" '
                   f'title="{e(_day_name(_d))}: {e(_say(r)[0])}">{_mo_tag}<b>{_d.day}</b>'
                   f'<i>{_CAL[r["kind"]][0]}</i></div>')
    else:
        _unposted = _unposted or iso > t_iso
        _cells += (f'<div class="{cls} none" title="{e(_day_name(_d))}: {e(T("home.lg_none"))}">'
                   f'{_mo_tag}<b>{_d.day}</b><i></i></div>')
    _d += datetime.timedelta(days=1)
_legend = "".join(
    f'<span><i style="background:{KIND_STYLE[k][0]};color:{KIND_STYLE[k][1]}">{_CAL[k][0]}</i>'
    f'{e(T(_CAL[k][1]))}</span>'
    for k in (ri.KIND_WORKING, ri.KIND_DAILY, ri.KIND_OTHER, ri.KIND_OFF, ri.KIND_VTO,
              ri.KIND_NOCALL, ri.KIND_UNKNOWN) if k in _kinds_seen)
if _unposted:
    _legend += f'<span><i class="none"></i>{e(T("home.lg_none"))}</span>'
_cal_title = _MONTH[today.month - 1].title()
if _posted and _last_day.month != today.month:
    _cal_title += " – " + _MONTH[_last_day.month - 1].title()
_ahead = sorted(d for d in by_date if d >= t_iso)
_cols[1].markdown(
    f'<div class="hm-cal"><div class="hm-calh"><b>{e(_cal_title)}</b>'
    + (f'<span>{e(T("home.posted_to", d=_day_name(datetime.date.fromisoformat(_ahead[-1]))))}</span>'
       if _ahead else "")
    + f'</div><div class="hm-grid">{_cells}</div><div class="hm-leg">{_legend}</div></div>',
    unsafe_allow_html=True)

# Every day from today to the last one posted, with what the sheet says.
_rows_html = ""
for iso in _ahead:
    d = datetime.date.fromisoformat(iso)
    r = by_date[iso]
    means = _say(r)[1]
    tag = (f'<span class="hm-tag t">{e(T("home.today_tag"))}</span>' if iso == t_iso else
           f'<span class="hm-tag c">{e(T("home.changed_tag"))}</span>' if iso in _changed_days else "")
    # A rule above each Sunday, where the sheet's week turns.
    _rows_html += (f'<div class="hm-row{" today" if iso == t_iso else ""}'
                   f'{" wk" if d.weekday() == 6 and iso != _ahead[0] else ""}">'
                   f'<span class="d"><b>{e(_DOW[d.weekday()])}</b> {d.day}'
                   + (f' {e(_MON[d.month - 1])}' if d.month != today.month else "")
                   + f'</span><span class="w">{_pill(r)}'
                   + (f'<small>{e(means)}</small>' if means else "")
                   + f'</span>{tag}</div>')
if _rows_html:
    _cols[1].markdown(f'<div class="hm-sec">{e(T("home.from_today"))}</div>'
                      f'<div class="hm-list">{_rows_html}</div>', unsafe_allow_html=True)

# 5. The day counts people ask about (HP, 11 Nov): how many days this week,
# how many next week, and how many worked this month so far. "7 Days off" was
# read as seven days taken off, so rest days are no longer a headline here --
# they are in the full record. VTO and no-call days show only when there are any.
wk_s, mo_s, yr_s = ri.period_bounds(today)
wk_e = (this_sun + datetime.timedelta(days=6)).isoformat()
mo_e = ((today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        - datetime.timedelta(days=1)).isoformat()
yr_e = today.replace(month=12, day=31).isoformat()


def tally(start, end, today_done=True):
    """Whole-period total, and how much of it has already happened.

    The headline is the FULL period: on a Wednesday "days this week" should be
    the four days you are down for, not the two you have already done.
    `today_done=False` leaves today among the days still to work: at nine in
    the morning "3 days, all worked" was wrong for somebody with rooms ahead.
    """
    span = [r for r in s_all["rows"] if start <= r["date"] <= end and r["worked"]]
    done = [r for r in span if r["date"] < t_iso or (today_done and r["date"] == t_iso)]
    return len(span), len(done), len(span) - len(done)


def _n_days(n):
    return f'{n}<i>{e(T("home.day_1" if n == 1 else "home.day_n"))}</i>'


_mo_rows = [r for r in s_all["rows"] if mo_s <= r["date"] <= mo_e]
_mo = ri.summarise_person(_mo_rows, pid=mine)
_mo_total, _mo_done, _mo_left = tally(mo_s, mo_e, today_done=False)
_wk_total, _wk_done, _wk_left = tally(wk_s, wk_e, today_done=False)
_nx_s = this_sun + datetime.timedelta(days=7)
_nx_e = this_sun + datetime.timedelta(days=13)
_nx_posted = any(_nx_s.isoformat() <= r["date"] <= _nx_e.isoformat() for r in s_all["rows"])
_nx_total = tally(_nx_s.isoformat(), _nx_e.isoformat())[0]
# The month is only as long as the weeks posted: say where the sheet stops, so
# "more scheduled" is not read as the whole month.
_mo_last = max((r["date"] for r in _mo_rows), default="")
_month = _MONTH[today.month - 1]
_through = _day_name(datetime.date.fromisoformat(_mo_last)) if _mo_last else ""
_days = [("", T("home.d_week"),
          T("home.d_none") if not _wk_total else
          f'{_worked(_wk_done)} · {T("home.left_n", n=_wk_left)}' if _wk_left else
          T("home.d_all_done"),
          _n_days(_wk_total)),
         ("", T("home.d_next"),
          f"{_day_name(_nx_s)} – {_day_name(_nx_e)}" if _nx_posted else T("home.d_not_posted"),
          _n_days(_nx_total) if _nx_posted else "—"),
         ("", T("home.d_month", month=_month),
          T("home.d_more_1" if _mo_left == 1 else "home.d_more", n=_mo_left, d=_through)
          if _mo_left and _through else "",
          _n_days(_mo_done))]
if _mo["n_paid_off"]:
    _days.append(("vto", T("home.d_vto", month=_month), T("home.d_vto_sub"),
                  _n_days(_mo["n_paid_off"])))
if _mo["n_no_call"]:
    _days.append(("warn", T("home.d_nocall", month=_month), T("home.d_nocall_sub"),
                  _n_days(_mo["n_no_call"])))
_days_html = (
    f'<div class="hm-sumh">{e(T("home.d_title"))}</div><div class="hm-days">'
    + "".join(f'<div class="hm-day {cls}"><div><b>{e(lbl[:1].upper() + lbl[1:])}</b>'
              + (f'<small>{e(sub)}</small>' if sub else "") + f'</div><span class="n">{n}</span></div>'
              for cls, lbl, sub, n in _days)
    + '</div>')
# Drawn twice and shown once: beside the schedule on a computer, where the
# left column has the room, and under the schedule on a phone, where the
# schedule comes first.
_cols[0].markdown(f'<div class="hm-sum hm-wide">{_days_html}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="hm-sum hm-narrow">{_days_html}</div>', unsafe_allow_html=True)

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
        m[1].metric(T("home.m_rest"), s_sel["off"])
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
