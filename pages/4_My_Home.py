"""
My Home — one person's own schedule.

This week and next straight from the staff sheet, plus what they have actually
worked. Everyone signed in gets this page, housekeepers included.
"""
import streamlit as st
import sys, os, datetime
import html as _html
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, db, roster_import as ri

# See 3_Roster_Import.py: a deploy can leave a stale roster_import in
# sys.modules, so reload it rather than dying on a helper it does not have yet.
if getattr(ri, "__version__", 0) < 10:
    import importlib
    ri = importlib.reload(ri)

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
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500;600;700&display=swap');
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
    st.markdown("---")
    _who = st.session_state.get("display_name","") or st.session_state.get("username","")
    _rl  = st.session_state.get("role","")
    if _who:
        st.caption(f"Signed in as **{_who}** · {_rl.title()}")
    if st.button("Sign Out", key="btn_signout_home", use_container_width=True):
        auth.logout()
        st.switch_page("cleaning_scheduler.py")

def e(s): return _html.escape(str(s) if s is not None else "")

def person_label(info):
    """Name for a picker: the person, their team, and their home property if
    they are visiting from one."""
    txt = f'{info["label"]}  ·  {info["sections"][0]}'
    return txt + f'  ·  {info["home"]}' if info.get("home") else txt


KIND_STYLE = {
    ri.KIND_DAILY:   ("#ccfbf1", "#0f5c55", "Daily Service"),
    ri.KIND_WORKING: ("#dcfce7", "#166534", "Working"),
    ri.KIND_OFF:     ("#f1f5f9", "#94a3b8", "Off"),
    ri.KIND_OTHER:   ("#fef3c7", "#92400e", "Working — other duty"),
    # Red is reserved for the thing the workbook paints red: a no-call/no-show.
    ri.KIND_NOCALL:  ("#fee2e2", "#991b1b", "No call / no show"),
    ri.KIND_VTO:     ("#e0e7ff", "#3730a3", "VTO — paid"),
    ri.KIND_UNKNOWN: ("#faf5ff", "#7e22ce", "Check with your lead"),
}

cu = auth.current_user()
me_display = cu.get("display_name") or ""
me_user = cu.get("username", "")

week_keys = db.staff_week_keys()
if not week_keys:
    st.markdown('<div class="hero"><h1>Hello</h1>'
                '<p>No staff schedule has been loaded yet.</p></div>', unsafe_allow_html=True)
    st.info("Once a manager imports the weekly schedule, your days will show up here.")
    st.stop()

@st.cache_data(ttl=300, show_spinner="Loading your schedule…")
def _all_rows(_token: str):
    return ri.history_rows(db.load_staff_weeks(), db.load_staff_overrides())

meta = db.load_staff_meta() or {}
overrides = db.load_staff_overrides()
rows = _all_rows(f'{meta.get("uploaded_at","")}|{len(week_keys)}|{len(overrides)}')
index = ri.people_index(rows)

# Sign-in names rarely match the sheet exactly, so try the display name and the
# username, which often carries digits or dots.
mine = ri.match_person(index, me_display, me_user)
# Only admins look up other people. RQS and housekeepers see themselves —
# this page is personal, and the roster pages already cover the whole team.
can_browse = auth.can("can_manage_users")

if mine is None or can_browse:
    order = sorted(index, key=lambda p: index[p]["label"].lower())
    labels = [person_label(index[p]) for p in order]
    default = order.index(mine) if mine in order else 0
    sel = st.selectbox(
        "Whose schedule?" if can_browse else
        "We could not match your sign-in to the schedule — pick your name",
        labels, index=default, key="mh_person")
    mine = order[labels.index(sel)]

info = index[mine]
s_all = ri.summarise_person(rows, pid=mine)
by_date = {r["date"]: r for r in s_all["rows"]}
today = datetime.date.today()
t_iso = today.isoformat()
greet = info["label"].split()[0].title()

st.markdown(
    f'<div class="hero"><h1>Hello, {e(greet)}</h1>'
    f'<p>Your schedule, straight from the staff sheet.</p>'
    f'<span class="role">{e(info["sections"][0])}'
    f'{" · " + e(info["home"]) if info.get("home") else ""}</span></div>', unsafe_allow_html=True)

# ── Week strips ───────────────────────────────────────────────────────────────
def strip(start: datetime.date, title: str):
    cards = ""
    for i in range(7):
        d = start + datetime.timedelta(days=i)
        iso = d.isoformat()
        r = by_date.get(iso)
        cls = "day"
        if d == today: cls += " today"
        elif iso < t_iso: cls += " past"
        head = f'<div class="dow">{d:%a}{" · TODAY" if d == today else ""}</div>' \
               f'<div class="num">{d.day}</div>'
        if r is None:
            cards += (f'<div class="{cls} empty">{head}'
                      f'<span class="what none">not on the sheet</span></div>')
            continue
        bg, fg, lbl = KIND_STYLE[r["kind"]]
        means = ri.legend_for(r, r["raw"])
        body = (f'<span class="what" style="background:{bg};color:{fg}">'
                f'{e(r["raw"]) or lbl}</span>')
        if means:
            body += f'<div class="means">{e(means)}</div>'
        cards += f'<div class="{cls}">{head}{body}</div>'
    st.markdown(f'<p class="sec">{e(title)} '
                f'<span style="color:#8a93a1;letter-spacing:0;text-transform:none">'
                f'&nbsp;{e(ri.week_range_text(start.isoformat()))}</span></p>',
                unsafe_allow_html=True)
    st.markdown(f'<div class="dayrow">{cards}</div>', unsafe_allow_html=True)

this_sun = today - datetime.timedelta(days=(today.weekday() + 1) % 7)
strip(this_sun, "This week")

nxt = [d for d in sorted(by_date) if d > t_iso and by_date[d]["worked"]]
if nxt:
    nd = datetime.date.fromisoformat(nxt[0])
    st.markdown(f'<div class="nextup">Next working day &nbsp;<b>{nd:%A, %B %d}</b>'
                f'&nbsp;·&nbsp; {e(by_date[nxt[0]]["raw"] or "scheduled")}</div>',
                unsafe_allow_html=True)
else:
    st.markdown('<div class="nextup">No further working days in the stored weeks.</div>',
                unsafe_allow_html=True)

strip(this_sun + datetime.timedelta(days=7), "Next week")

# ── Totals ────────────────────────────────────────────────────────────────────
st.markdown('<p class="sec">Your days</p>', unsafe_allow_html=True)
wk_s, mo_s, yr_s = ri.period_bounds(today)
wk_e = (this_sun + datetime.timedelta(days=6)).isoformat()
# Last day of this month = day before the first of next month.
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

cols = st.columns(4)
cards = [(*tally(wk_s, wk_e), "days this week"),
         (*tally(mo_s, mo_e), "days this month"),
         (*tally(yr_s, yr_e), "days this year"),
         (s_all["n_worked"], s_all["n_worked"], 0, "days on record")]
for col, (total, done, ahead, lbl) in zip(cols, cards):
    sub = (f'<div class="s">{done} so far · {ahead} to come</div>' if ahead else
           '<div class="s">all complete</div>' if total else '')
    col.markdown(f'<div class="kpi"><div class="n">{total}</div>'
                 f'<div class="l">{lbl}</div>{sub}</div>', unsafe_allow_html=True)

c1, c2 = st.columns([3, 2])
with c1:
    st.markdown('<div class="lbl">Days you usually work</div>', unsafe_allow_html=True)
    mx = max(s_all["by_dow"].values()) or 1
    bars = ""
    for d, n in s_all["by_dow"].items():
        pct = int(100 * n / mx)
        hot = n >= mx * 0.6
        fill = "linear-gradient(90deg,#2563a8,#4a90cc)" if hot else "#cbd5e1"
        bars += (f'<div class="bar"><span class="d">{d}</span>'
                 f'<div class="track"><div class="fill" '
                 f'style="width:{max(pct, 2)}%;background:{fill}"></div></div>'
                 f'<span class="v">{n}</span></div>')
    st.markdown(bars, unsafe_allow_html=True)
    if s_all["usual_days"]:
        st.caption("Usually: " + ", ".join(s_all["usual_days"]))
with c2:
    st.markdown('<div class="lbl">Roles and shifts</div>', unsafe_allow_html=True)
    chips = ""
    for k2, v2 in list(s_all["roles"].items())[:4]:
        chips += f'<span class="pill" style="background:#eef2ff;color:#3730a3">{e(k2)} · {v2}</span>'
    for k2, v2 in s_all["shifts"].items():
        bg, fg = {"Daily Service": ("#ccfbf1", "#0f5c55"),
                  "Room cover": ("#ede9fe", "#5b21b6"),
                  "Other duty": ("#fef3c7", "#92400e")}.get(k2, ("#dcfce7", "#166534"))
        chips += f'<span class="pill" style="background:{bg};color:{fg}">{e(k2)} · {v2}</span>'
    if s_all["n_no_call"]:
        chips += (f'<span class="pill" style="background:#fee2e2;color:#991b1b">'
                  f'No call · {s_all["n_no_call"]}</span>')
    if s_all["n_paid_off"]:
        chips += (f'<span class="pill" style="background:#e0e7ff;color:#3730a3">'
                  f'VTO · {s_all["n_paid_off"]}</span>')
    st.markdown(chips or '<span style="color:#8a93a1">—</span>', unsafe_allow_html=True)
    pctw = 100 * s_all["n_worked"] / max(s_all["n_days"], 1)
    st.markdown(f'<div style="margin-top:10px;font-size:.8rem;color:#5b6675">'
                f'Worked <b>{s_all["n_worked"]}</b> of {s_all["n_days"]} recorded days '
                f'({pctw:.0f}%)</div>', unsafe_allow_html=True)

with st.expander("Every day on record"):
    past = sorted([r for r in s_all["rows"] if r["date"] <= t_iso],
                  key=lambda x: x["date"], reverse=True)
    st.dataframe(
        pd.DataFrame([{"Date": r["date"], "Day": r["dow"], "Team": r["section"],
                       "Scheduled": r["raw"] or "—",
                       "Status": KIND_STYLE[r["kind"]][2],
                       "Means": ri.legend_for(r, r["raw"]) or "—"} for r in past]),
        use_container_width=True, hide_index=True,
        height=min(60 + 33 * len(past), 460))
