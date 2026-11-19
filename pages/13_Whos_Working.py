"""
Who's Working — today's working people, team by team, with their shift
(Hari, 14 Nov).

For whoever is RQS 1 or RQS 2 today: they already have the staff workbook for
the whole month, so this is today only, with nothing to pick. The menu link
appears for an RQS only on a day they are RQS 1 or RQS 2; managers can always
open it. Roster Import is managers-only. The rule and the data are
whos_working.py.

Laid out by job (19 Nov): one header card (date, head count, RQS 1/2, team
counts), then Housekeeping by building | Housepersons AM, PM and leads | RQS
and everyone else. A short code sits in a chip beside the name; a longer duty
goes on a line under it ("5 + Deep clean ..." is an HSP 5 chip and the task).
On a phone the zones stack: Housekeeping, RQS, Housepersons, the rest.
"""
import streamlit as st
import sys, os, re, html, datetime
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
    "people working": "personas trabajando",
    "person working": "persona trabajando",
    "Housekeeping": "Camaristas",
    "Also working": "También trabajan",
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
            .replace("Managers", "Gerentes").replace("Ice Rink", "Pista de hielo")
            .replace("PM Leads", "Líderes PM").replace("Sales", "Ventas"))


me = auth.current_user()
if not ww.can_see(me["username"], me["role"], me.get("display_name") or ""):
    st.info(L("This page opens on the days you are RQS 1 or RQS 2."))
    st.stop()

sel = clock.today().isoformat()

st.markdown("""<style>
.block-container{max-width:min(1180px,97%);padding-top:1.1rem!important}
.ww-head{background:#e8f0fe;border-radius:24px;padding:18px 22px 16px;margin-bottom:16px}
.ww-top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.ww-head h1{font-size:1.5rem;font-weight:700;color:#0b2a55;margin:0;padding:0;letter-spacing:-.01em;line-height:1.2}
.ww-head .sub{font-size:.93rem;color:#3c4a5e;margin:3px 0 0}
.ww-head .sub b{color:#0b2a55}
.ww-lead{display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end}
.ww-lead span{background:#fff;border-radius:999px;padding:6px 12px;font-size:.86rem;color:#1f2733;white-space:nowrap}
.ww-lead b{color:#1a56b0;margin-right:6px;font-weight:700}
.ww-tally{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.ww-tally span{display:inline-flex;align-items:center;gap:7px;background:rgba(255,255,255,.75);
  border-radius:999px;padding:4px 12px 4px 10px;font-size:.84rem;color:#3c4a5e}
.ww-tally b{font-size:.98rem;color:#16202e}
.ww-dot{width:8px;height:8px;border-radius:50%;display:inline-block;background:var(--z)}
.ww-cols{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;align-items:start;margin-bottom:16px}
.ww-col{display:flex;flex-direction:column;gap:14px;min-width:0}
.ww-zone{background:#fff;border:1px solid #e3e7ee;border-top:4px solid var(--z);border-radius:18px;padding:12px 14px 6px}
.ww-zone h2{display:flex;justify-content:space-between;align-items:center;font-size:1rem;font-weight:700;
  color:#16202e;margin:0 0 2px;padding:0;line-height:1.3}
.ww-zone h2 .c{background:#eef2f7;color:#3c4a5e;border-radius:999px;padding:1px 10px;font-size:.8rem;font-weight:700}
.ww-sub{display:flex;justify-content:space-between;font-size:.72rem;font-weight:700;text-transform:uppercase;
  letter-spacing:.05em;color:#6a7484;margin:8px 0 0;padding:9px 0 1px;border-top:1px solid #e9edf2}
.ww-zone h2 + .ww-sub{border-top:none;margin-top:2px;padding-top:4px}
.ww-p{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;padding:7px 0;border-top:1px solid #f2f4f7}
.ww-zone h2 + .ww-p,.ww-sub + .ww-p{border-top:none}
.ww-p .who{min-width:0}
.ww-p .nm{font-size:.94rem;color:#1f2733;font-weight:500}
.ww-p .note{display:block;font-size:.8rem;color:#5b6675;margin-top:2px;line-height:1.3}
.ww-chip{flex:0 0 auto;background:#f1f4f9;color:#3c4a5e;border-radius:8px;padding:2px 8px;font-size:.76rem;
  font-weight:600;white-space:nowrap;margin-top:1px}
.ww-chip.rqs{background:#e1ecff;color:#1a56b0}
.ww-chip.ds{background:#e3f6ea;color:#1d6b3a}
.ww-chip.proj{background:#fdf0d8;color:#8a5a00}
@media (max-width:980px){.ww-cols{grid-template-columns:repeat(2,minmax(0,1fr))}}
/* The phone's top bar already says "Who's Working". */
@media (max-width:820px){.ww-head h1{display:none}.ww-head .sub{margin-top:0}}
@media (max-width:640px){
  .ww-top{flex-direction:column}
  .ww-lead{justify-content:flex-start}
  .ww-head{padding:16px}
  .ww-cols{display:flex;flex-direction:column;align-items:stretch;gap:12px}
  .ww-col{display:contents}
  .ww-zone{order:var(--o)}
}
</style>""", unsafe_allow_html=True)

data = ww.day(ww.rows(), sel)
e = html.escape

# The four zones: (key, title, accent colour, order on a phone)
ZONES = {"hk": ("Housekeeping", "#1a56b0", 1), "rqs": ("RQS", "#6a4bc4", 2),
         "hp": ("Housepersons", "#0f8a7e", 3), "other": ("Also working", "#8a94a3", 4)}
COLUMNS = (("hk",), ("hp",), ("rqs", "other"))      # left to right on a computer


def zone_of(section: str) -> str:
    s = section.lower()
    if s.startswith("building"):
        return "hk"
    if s == "rqs":
        return "rqs"
    if "houseperson" in s or "lead" in s:
        return "hp"
    return "other"


def split_duty(section: str, shift: str):
    """(chip, note, chip class). A short code is a chip; longer words are a
    note under the name. A houseperson's "5 + Deep clean ..." is HSP 5 and the
    task; a lead's "Lead - Training ..." is Lead and the task."""
    s = (shift or "").strip()
    if not s:
        return "", "", ""
    low = s.lower()
    cls = ("rqs" if s.upper().startswith(("RQS", "RQ1", "RQ2")) else
           "ds" if "daily serv" in low else "proj" if "project" in low else "")
    m = re.match(r"^(\d+)\s*(?:[+\-–]\s*|\s+)(\D.*)$", s)
    if m and "houseperson" in section.lower():
        return f"HSP {m.group(1)}", m.group(2).strip(" -–"), cls
    m = re.match(r"^lead\s*[-–:]\s*(.+)$", s, re.I)
    if m:
        rest = m.group(1).strip()
        return (f"Lead {rest}", "", cls) if len(rest) <= 4 else ("Lead", rest, cls)
    return (s, "", cls) if len(s) <= 16 else ("", s, cls)


def person_html(section, name, shift):
    chip, note, cls = split_duty(section, shift)
    note = note[:1].upper() + note[1:]
    return ('<div class="ww-p"><span class="who">'
            f'<span class="nm">{e(name)}</span>'
            + (f'<span class="note">{e(note)}</span>' if note else "")
            + "</span>"
            + (f'<span class="ww-chip {cls}">{e(chip)}</span>' if chip else "")
            + "</div>")


def zone_people(z):
    secs = [(sec, ppl) for sec, ppl in data["sections"] if zone_of(sec) == z]
    return secs, len({n for _, ppl in secs for n, _ in ppl})


def zone_html(z):
    secs, n = zone_people(z)
    if not secs:
        return ""
    title, colour, order = ZONES[z]
    body = ""
    for sec, ppl in secs:
        if len(secs) > 1 or z == "other":
            body += (f'<div class="ww-sub"><span>{e(section_t(sec))}</span>'
                     f'<span>{len(ppl)}</span></div>')
        body += "".join(person_html(sec, name, shift) for name, shift in ppl)
    return (f'<div class="ww-zone" style="--z:{colour};--o:{order}">'
            f'<h2><span>{e(L(title))}</span><span class="c">{n}</span></h2>{body}</div>')


# ── the header: the day, the head count, RQS 1 and 2, the teams ──
r1, r2 = data["rqs1"], data["rqs2"]
lead = ([("RQS 1 + RQS 2", r1)] if r1 and r1 == r2 else
        [("RQS 1", r1 or L("not set")), ("RQS 2", r2 or L("not set"))])
total = data["total"]
title = e(L("Who's Working"))
tally = "".join(
    f'<span style="--z:{ZONES[z][1]}"><i class="ww-dot"></i><b>{zone_people(z)[1]}</b>'
    f'{e(L(ZONES[z][0]))}</span>'
    for z in ("hk", "rqs", "hp", "other") if zone_people(z)[1])
st.markdown(
    '<div class="ww-head"><div class="ww-top"><div>'
    f'<h1>{title}</h1>'
    f'<p class="sub">{e(L("Today"))} · {e(long_date(datetime.date.fromisoformat(sel)))} · '
    f'<b>{total}</b> {e(L("person working" if total == 1 else "people working"))}</p></div>'
    '<div class="ww-lead">'
    + "".join(f"<span><b>{e(k)}</b>{e(v)}</span>" for k, v in lead)
    + f'</div></div><div class="ww-tally">{tally}</div></div>',
    unsafe_allow_html=True)

if not data["sections"]:
    st.info(L("Nobody is on the staff sheet for this day yet."))
    st.stop()

# ── the teams, by job ──
st.markdown('<div class="ww-cols">' + "".join(
    '<div class="ww-col">' + "".join(zone_html(z) for z in col) + "</div>"
    for col in COLUMNS) + "</div>", unsafe_allow_html=True)

if me["role"] == "rqs":
    st.caption(L("You see this page on the days you are RQS 1 or RQS 2."))
