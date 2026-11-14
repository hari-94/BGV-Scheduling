"""
Who's Working — today's working people, team by team, with their shift
(Hari, 14 Nov).

For whoever is RQS 1 or RQS 2 today: they already have the staff workbook for
the whole month, so this is today only, with nothing to pick. The menu link
appears for an RQS only on a day they are RQS 1 or RQS 2; managers can always
open it. Roster Import is managers-only. The rule and the data are
whos_working.py.

Phone first: one column of team cards.
"""
import streamlit as st
import sys, os, html, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, clock, i18n
import ui
import fresh

st.set_page_config(page_title="Who's Working", page_icon="GC8", layout="wide")
st.markdown("<style>[data-testid='stSidebarNav']{display:none!important;}</style>",
            unsafe_allow_html=True)
auth.require_login()
fresh.latest("i18n", "ui", "whos_working")    # as they are on disk, not as first loaded
import whos_working as ww                     # noqa: E402
ui.topnav("Who's Working")

ES = i18n.lang() == "es"
_ES = {
    "Who's Working": "Quién trabaja",
    "working": "trabajando",
    "Housekeepers": "Camaristas",
    "Housepersons": "Housepersons",
    "RQS": "RQS",
    "Others": "Otros",
    "Nobody is on the staff sheet for this day yet.": "Todavía no hay nadie en la hoja del personal para este día.",
    "This page opens on the days you are RQS 1 or RQS 2.":
        "Esta página se abre los días que eres RQS 1 o RQS 2.",
    "You see this page on the days you are RQS 1 or RQS 2.":
        "Ves esta página los días que eres RQS 1 o RQS 2.",
    "Today": "Hoy",
    "not set": "sin asignar",
}


def L(text, **kw):
    out = _ES.get(text, text) if ES else text
    return out.format(**kw) if kw else out


_DAYS = (["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"] if ES else
         ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
_MONTHS = (["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
            "septiembre", "octubre", "noviembre", "diciembre"] if ES else
           ["January", "February", "March", "April", "May", "June", "July", "August",
            "September", "October", "November", "December"])


def long_date(d: datetime.date) -> str:
    day, mon = _DAYS[d.weekday()], _MONTHS[d.month - 1]
    return f"{day.capitalize()} {d.day} de {mon}" if ES else f"{day}, {mon} {d.day}"


def section_t(s: str) -> str:
    if not ES:
        return s
    return (s.replace("Building", "Edificio").replace("Overnight Team", "Equipo de noche")
            .replace("Managers", "Gerentes").replace("Ice Rink", "Pista de hielo"))


me = auth.current_user()
if not ww.can_see(me["username"], me["role"], me.get("display_name") or ""):
    st.info(L("This page opens on the days you are RQS 1 or RQS 2."))
    st.stop()

sel = clock.today().isoformat()

st.markdown("""<style>
.block-container{max-width:min(1100px,97%);padding-top:1rem!important}
.ww-hero{background:#e8f0fe;border-radius:24px;padding:20px 22px;margin-bottom:16px}
.ww-hero h1{font-size:1.55rem;font-weight:700;color:#0b2a55;margin:0 0 2px;letter-spacing:-.01em}
.ww-hero .sub{font-size:.95rem;color:#3c4a5e;margin:0 0 12px}
.ww-rqs{display:flex;flex-wrap:wrap;gap:8px}
.ww-rqs span{background:#fff;border-radius:999px;padding:6px 12px;font-size:.88rem;color:#1f2733}
.ww-rqs b{color:#1a56b0;margin-right:6px}
.ww-counts{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px}
.ww-count{background:#fff;border:1px solid #e3e7ee;border-radius:16px;padding:10px 12px}
.ww-count .n{font-size:1.4rem;font-weight:700;color:#16202e;line-height:1.1}
.ww-count .l{font-size:.75rem;color:#5b6675;text-transform:uppercase;letter-spacing:.04em}
.ww-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;margin-bottom:16px}
.ww-card{background:#fff;border:1px solid #e3e7ee;border-radius:18px;padding:12px 14px}
.ww-card h3{display:flex;justify-content:space-between;align-items:center;font-size:.95rem;
  font-weight:700;color:#16202e;margin:0 0 6px;padding:0}
.ww-card h3 .c{background:#eef2f7;color:#3c4a5e;border-radius:999px;padding:1px 9px;font-size:.78rem}
.ww-row{display:flex;justify-content:space-between;align-items:center;gap:10px;
  padding:7px 0;border-top:1px solid #f0f2f5;font-size:.93rem;color:#1f2733}
.ww-row:first-of-type{border-top:none}
.ww-tag{background:#f3f6fb;color:#3c4a5e;border-radius:8px;padding:2px 8px;font-size:.78rem;
  text-align:right;max-width:58%}
.ww-tag.rqs{background:#e1ecff;color:#1a56b0;font-weight:600}
@media (max-width:640px){
  .ww-counts{grid-template-columns:repeat(2,1fr)}
  .ww-hero h1{font-size:1.3rem}
}
</style>""", unsafe_allow_html=True)

data = ww.day(ww.rows(), sel)
e = html.escape
when = L("Today") + " · " + long_date(datetime.date.fromisoformat(sel))

st.markdown(f"""<div class="ww-hero">
  <h1>{e(L("Who's Working"))}</h1>
  <p class="sub">{e(when)} · <b>{data['total']}</b> {e(L("working"))}</p>
  <div class="ww-rqs">
    <span><b>RQS 1</b>{e(data['rqs1'] or L("not set"))}</span>
    <span><b>RQS 2</b>{e(data['rqs2'] or L("not set"))}</span>
  </div>
</div>""", unsafe_allow_html=True)

if not data["sections"]:
    st.info(L("Nobody is on the staff sheet for this day yet."))
    st.stop()


def _bucket(section: str) -> str:
    s = section.lower()
    if s.startswith("building"):
        return "Housekeepers"
    if s == "rqs":
        return "RQS"
    if "houseperson" in s or "lead" in s:
        return "Housepersons"
    return "Others"


counts = {"Housekeepers": 0, "RQS": 0, "Housepersons": 0, "Others": 0}
for sec, ppl in data["sections"]:
    counts[_bucket(sec)] += len(ppl)
st.markdown('<div class="ww-counts">' + "".join(
    f'<div class="ww-count"><div class="n">{n}</div><div class="l">{e(L(k))}</div></div>'
    for k, n in counts.items()) + "</div>", unsafe_allow_html=True)

cards = []
for sec, ppl in data["sections"]:
    rows_html = "".join(
        f'<div class="ww-row"><span>{e(name)}</span>'
        + (f'<span class="ww-tag{" rqs" if shift.upper().startswith(("RQS", "RQ2", "RQ1")) else ""}">'
           f'{e(shift)}</span>' if shift else "")
        + "</div>" for name, shift in ppl)
    cards.append(f'<div class="ww-card"><h3><span>{e(section_t(sec))}</span>'
                 f'<span class="c">{len(ppl)}</span></h3>{rows_html}</div>')
st.markdown('<div class="ww-grid">' + "".join(cards) + "</div>", unsafe_allow_html=True)

if me["role"] == "rqs":
    st.caption(L("You see this page on the days you are RQS 1 or RQS 2."))
