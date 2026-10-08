"""
Forecast — how many housekeepers and RQS each coming day needs, against who
the staff schedule actually has on.

Two sources, both kept current by hotsos_agent.py on the office PC:
  * NEED -- the SSRS Housekeeping Dashboard, pulled every two hours through
    the day and whenever somebody presses Refresh, turned into heads by
    `staffing.estimate` (the same arithmetic Roster Import uses).
  * SCHEDULED -- Schedule.xlsx in SharePoint, imported by the agent within a
    minute or two of every save, read with `forecast.scheduled`: who is on
    rooms each day, the way the rest of the app reads a cell.

The page answers, in order: are we short or over, and when (cards, then one
chart of the gap); what does each day need against what's scheduled (two
charts); and did new bookings just move anything (a short list). The numbers
are one click away.

Housekeepers are compared as one total. The sheet rarely says "Daily
service" ahead of the day, so a Full Clean / Daily split of the scheduled
side would report a Daily shortage that isn't one.
"""
import datetime as _dt
import os
import sys
import uuid

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, clock, db, ui          # noqa: E402
import forecast as fcast            # noqa: E402
import hotsos_sync as hs            # noqa: E402

st.set_page_config(page_title="Forecast", page_icon="📈", layout="wide")
st.markdown("""<style>
.block-container{max-width:min(1200px,97%);}
[data-testid='stSidebarNav']{display:none!important;}
.fc-card{background:#fff;border:1px solid #e6e9ee;border-radius:14px;padding:14px 18px;height:100%}
.fc-day{font-size:.78rem;font-weight:600;color:#5b6675;text-transform:uppercase;letter-spacing:.04em}
.fc-big{display:flex;gap:28px;align-items:flex-start;margin-top:6px}
.fc-num{font-family:'Syne',sans-serif;font-size:2.1rem;font-weight:700;color:#16202e;line-height:1}
.fc-lab{font-size:.78rem;color:#5b6675;margin-top:3px}
.fc-have{font-size:.8rem;color:#1f2733;margin-top:6px}
.fc-sub{font-size:.78rem;color:#5b6675;margin-top:10px}
.gap{display:inline-block;border-radius:999px;padding:1px 8px;font-size:.74rem;font-weight:700;margin-left:4px}
.gap-short{background:#fdecec;color:#b42318}
.gap-over{background:#e8f1fc;color:#184f95}
.gap-ok{background:#ecf7ee;color:#067647}
.alert{background:#fff;border:1px solid #f5c2c2;border-left:4px solid #d03b3b;border-radius:12px;
       padding:10px 14px;margin:4px 0 14px;font-size:.88rem;color:#1f2733;line-height:1.7}
.alert b.d{display:inline-block;min-width:96px}
.fc-chg{font-size:.85rem;color:#1f2733;line-height:1.7;margin-bottom:14px}
.fc-dl{font-size:.75rem;font-weight:600;margin-left:4px}
.fc-up{color:#b42318}.fc-down{color:#067647}
</style>""", unsafe_allow_html=True)
auth.require_login()
ui.topnav("Forecast")
if not auth.can("can_view_dashboard"):
    st.error("The forecast is for RQS and admins.")
    st.stop()

me = st.session_state.get("display_name") or auth.current_user().get("username", "")
ONLINE_SECONDS = 180
LOOKAHEAD_ALERT = 14          # days the "short" alert looks ahead

# Reference palette, categorical slots 1-3 in fixed order (one colour per job),
# plus the blue/red diverging pair for short-vs-over.
C_FC, C_DS, C_RQS = "#2a78d6", "#eb6834", "#1baf7a"
C_SHORT, C_OVER = "#e34948", "#2a78d6"
INK, INK2, GRID = "#1f2733", "#5b6675", "#eceef1"


def _parse(stamp):
    try:
        return _dt.datetime.fromisoformat(stamp)
    except Exception:
        return None


def _when(stamp):
    t = _parse(stamp)
    if not t:
        return "never"
    if t.tzinfo:
        t = t.astimezone(clock.MTN)
    day = "today" if t.date() == clock.today() else f"{t:%a %b %d}"
    return f"{day} at {t:%I:%M %p}".replace(" 0", " ")


def _day_name(iso, today_iso):
    d = pd.Timestamp(iso)
    if iso == today_iso:
        return "Today"
    if iso == (clock.today() + _dt.timedelta(days=1)).isoformat():
        return "Tomorrow"
    return f"{d:%a %b} {d.day}"


def _gap_html(gap, unit):
    if gap is None:
        return '<span class="gap gap-ok" style="background:#f2f3f5;color:#5b6675">not scheduled</span>'
    if gap < 0:
        return f'<span class="gap gap-short">{-gap} {unit} short</span>'
    if gap > 0:
        return f'<span class="gap gap-over">{gap} over</span>'
    return '<span class="gap gap-ok">✓ covered</span>'


def _layout(fig, height, legend=True):
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=30, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans, sans-serif", size=12, color=INK2),
        bargap=0.28, barcornerradius=4, hovermode="x unified",
        hoverlabel=dict(bgcolor="#fff", bordercolor="#e6e9ee",
                        font=dict(color=INK, size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0,
                    traceorder="normal", font=dict(color=INK, size=12)),
        showlegend=legend)
    # A real date axis, not text labels: it thins its own ticks to the width.
    fig.update_xaxes(type="date", showgrid=False, linecolor="#d5d9df",
                     tickfont=dict(color=INK2), tickformat="%a<br>%b %-d",
                     hoverformat="%A %b %-d", fixedrange=True)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(color=INK2),
                     fixedrange=True)
    return fig


h1, h2 = st.columns([4, 1])
h1.markdown("## 📈 Staffing forecast")
if h2.button("🔄 Refresh now", type="primary", use_container_width=True):
    db._upsert_key(hs.FORECAST_REQUEST_KEY, {"id": uuid.uuid4().hex, "by": me,
                                             "at": clock.stamp()})


@st.fragment(run_every=10)
def forecast_panel():
    fc = db._load_key(hs.FORECAST_KEY) or {}
    req = db._load_key(hs.FORECAST_REQUEST_KEY) or {}
    beat = db._load_key(hs.HEARTBEAT_KEY) or {}
    sync = db._load_key(hs.ROSTER_STATUS_KEY) or {}
    beat_t = _parse(beat.get("at"))
    online = beat_t and (clock.now() - beat_t).total_seconds() < ONLINE_SECONDS

    pulled, asked = _parse(fc.get("pulled_at")), _parse(req.get("at"))
    if asked and (not pulled or asked > pulled):
        if online:
            st.info(f"⏳ Pulling fresh numbers from SSRS (asked by {req.get('by')})… about a minute.")
        else:
            st.warning("Refresh asked for, but the office PC isn't connected — it will "
                       "pull as soon as it's back on.")
    elif not online:
        st.warning(f"The office PC isn't connected (last seen {_when(beat.get('at'))}), "
                   "so these numbers won't update until it's back.")

    today_iso = clock.today().isoformat()
    days = [d for d in (fc.get("days") or []) if d["date"] >= today_iso]
    if not days:
        st.caption("No forecast yet — it appears after the office PC's first pull.")
        return
    st.caption(f"**Need**: SSRS Housekeeping Dashboard, updated {_when(fc.get('pulled_at'))} · "
               f"**Scheduled**: Schedule.xlsx in SharePoint, last synced "
               f"{_when(sync.get('at')) if sync.get('at') else 'when it last changed'}")

    weeks, overrides = db.load_staff_weeks(), db.load_staff_overrides()
    for d in days:
        s = fcast.scheduled(weeks, overrides, d["date"])
        d["have"] = s
        d["gap_hk"] = None if s is None else s["hskp"] - (d.get("hskp") or 0)
        d["gap_rqs"] = None if s is None else len(s["rqs"]) - (d.get("rqs") or 0)

    prev = {p["date"]: p for p in (fc.get("previous") or {}).get("days", [])}

    def moved(d, key):
        p = prev.get(d["date"])
        if not p or p.get(key) is None or d.get(key) is None:
            return 0
        return d[key] - p[key]

    # ── 1. short days, in words ─────────────────────────────────────────────
    horizon = days[:LOOKAHEAD_ALERT]
    short = [d for d in horizon if (d["gap_hk"] or 0) < 0 or (d["gap_rqs"] or 0) < 0]
    if short:
        lines = []
        for d in short:
            bits = []
            if (d["gap_hk"] or 0) < 0:
                bits.append(f"<b>{-d['gap_hk']}</b> housekeeper{'s' if d['gap_hk'] < -1 else ''}")
            if (d["gap_rqs"] or 0) < 0:
                bits.append(f"<b>{-d['gap_rqs']}</b> RQS")
            spare = len(d["have"]["other"])
            extra = f" · {spare} on other duties" if spare else ""
            lines.append(f'<b class="d">{_day_name(d["date"], today_iso)}</b> short '
                         + " and ".join(bits)
                         + f' <span style="color:#5b6675">(need {d["hskp"]} HK / {d["rqs"]} RQS, '
                           f'scheduled {d["have"]["hskp"]} / {len(d["have"]["rqs"])}{extra})</span>')
        st.markdown(f'<div class="alert">⚠️ <b>Short on {len(short)} of the next '
                    f'{len(horizon)} days</b><br>' + "<br>".join(lines) + "</div>",
                    unsafe_allow_html=True)
    else:
        st.success(f"Every day in the next {len(horizon)} is covered by the schedule.")

    # ── 2. cards: today, tomorrow, the worst day ahead ──────────────────────
    worst = min([d for d in days[2:] if d["gap_hk"] is not None] or days,
                key=lambda d: ((d["gap_hk"] or 0) + (d["gap_rqs"] or 0), d["date"]))
    picks = [(days[0], _day_name(days[0]["date"], today_iso))]
    if len(days) > 1:
        picks.append((days[1], "Tomorrow"))
    picks.append((worst, ("Tightest day ahead · " if (worst["gap_hk"] or 0) < 0
                          else "Busiest day ahead · ") + _day_name(worst["date"], today_iso)))
    for col, (d, title) in zip(st.columns(len(picks)), picks):
        s = d["have"]
        have_hk = "—" if s is None else s["hskp"]
        have_rq = "—" if s is None else len(s["rqs"])
        col.markdown(f"""<div class="fc-card">
  <div class="fc-day">{title}</div>
  <div class="fc-big">
    <div><div class="fc-num">{d['hskp']}</div><div class="fc-lab">housekeepers needed</div>
         <div class="fc-have">{have_hk} scheduled {_gap_html(d['gap_hk'], 'HK')}</div></div>
    <div><div class="fc-num">{d['rqs']}</div><div class="fc-lab">RQS needed</div>
         <div class="fc-have">{have_rq} scheduled {_gap_html(d['gap_rqs'], 'RQS')}</div></div>
  </div>
  <div class="fc-sub">{d.get('checkouts')} checkouts · {d.get('dailies')} daily ·
       {d.get('dustnvac')} dust n vac</div>
</div>""", unsafe_allow_html=True)

    # ── 3. short or over, every day ─────────────────────────────────────────
    sched_days = [d for d in days if d["gap_hk"] is not None]
    if sched_days:
        st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)
        st.markdown("#### Short or over")
        st.caption("Scheduled minus needed. Below the line is short, above is more than "
                   "the day needs. Days past the last week in Schedule.xlsx aren't shown.")
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.14,
                            subplot_titles=("Housekeepers", "RQS"))
        for row, key, have_key in ((1, "gap_hk", "hskp"), (2, "gap_rqs", "rqs")):
            gaps = [d[key] for d in sched_days]
            hover = []
            for d in sched_days:
                s = d["have"]
                have = s["hskp"] if have_key == "hskp" else len(s["rqs"])
                need = d["hskp"] if have_key == "hskp" else d["rqs"]
                txt = f"need {need}, scheduled {have}"
                if have_key == "hskp" and s["other"]:
                    txt += f"<br>{len(s['other'])} on other duties (deep clean, HSP…)"
                hover.append(txt)
            fig.add_bar(row=row, col=1, x=[d["date"] for d in sched_days], y=gaps,
                        marker_color=[C_SHORT if g < 0 else C_OVER for g in gaps],
                        text=[f"{g:+d}" if g else "" for g in gaps], textposition="outside",
                        textfont=dict(color=INK, size=11), cliponaxis=False,
                        customdata=hover, showlegend=False,
                        hovertemplate="<b>%{y:+d}</b> · %{customdata}<extra></extra>")
            lo = min(gaps + [0]); hi = max(gaps + [0])
            pad = max(2, (hi - lo) * 0.25)
            fig.update_yaxes(row=row, col=1, range=[lo - pad, hi + pad], zeroline=True,
                             zerolinecolor="#9aa3ae", zerolinewidth=1)
        for a in fig.layout.annotations:
            a.update(font=dict(size=12, color=INK), x=0, xanchor="left")
        st.plotly_chart(_layout(fig, 340, legend=False), use_container_width=True,
                        config={"displayModeBar": False})

    # ── 4. need against scheduled ───────────────────────────────────────────
    x = [d["date"] for d in days]
    detail = [f"{d.get('rooms')} rooms · {d.get('checkouts')} checkouts · "
              f"{d.get('dailies')} daily" for d in days]

    st.markdown("#### Housekeepers: needed and scheduled")
    hk = go.Figure()
    hk.add_bar(x=x, y=[d.get("hskp_fc") for d in days], name="Needed · Full Clean",
               marker=dict(color=C_FC, line=dict(color="#ffffff", width=1)),
               hovertemplate="Full Clean: <b>%{y}</b><extra></extra>")
    hk.add_bar(x=x, y=[d.get("hskp_ds") for d in days], name="Needed · Daily Service",
               marker=dict(color=C_DS, line=dict(color="#ffffff", width=1)),
               customdata=[[d.get("hskp"), detail[i]] for i, d in enumerate(days)],
               hovertemplate="Daily Service: <b>%{y}</b><br>Needed: <b>%{customdata[0]}</b>"
                             "<br>%{customdata[1]}<extra></extra>")
    hk.add_scatter(x=[d["date"] for d in sched_days],
                   y=[d["have"]["hskp"] for d in sched_days], name="Scheduled",
                   mode="markers", marker=dict(symbol="diamond", size=11, color=INK,
                                               line=dict(color="#ffffff", width=2)),
                   hovertemplate="Scheduled: <b>%{y}</b><extra></extra>")
    hk.update_layout(barmode="stack")
    top = max([d.get("hskp") or 0 for d in days] + [d["have"]["hskp"] for d in sched_days])
    hk.update_yaxes(range=[0, top * 1.12 + 1])
    st.plotly_chart(_layout(hk, 300), use_container_width=True, config={"displayModeBar": False})

    st.markdown("#### RQS: needed and scheduled")
    rq = go.Figure()
    rq.add_bar(x=x, y=[d.get("rqs") for d in days], name="Needed", marker=dict(color=C_RQS),
               hovertemplate="Needed: <b>%{y}</b><extra></extra>")
    rq.add_scatter(x=[d["date"] for d in sched_days],
                   y=[len(d["have"]["rqs"]) for d in sched_days], name="Scheduled",
                   mode="markers", marker=dict(symbol="diamond", size=11, color=INK,
                                               line=dict(color="#ffffff", width=2)),
                   hovertemplate="Scheduled: <b>%{y}</b><extra></extra>")
    rtop = max([d.get("rqs") or 0 for d in days] + [len(d["have"]["rqs"]) for d in sched_days])
    rq.update_yaxes(range=[0, rtop * 1.15 + 1])
    st.plotly_chart(_layout(rq, 220), use_container_width=True, config={"displayModeBar": False})

    # ── 5. what new bookings just moved ─────────────────────────────────────
    if prev:
        since = _when((fc.get("previous") or {}).get("pulled_at"))
        chg = [d for d in days if moved(d, "hskp") or moved(d, "rqs")]
        if chg:
            lines = []
            for d in chg[:8]:
                bits = []
                for key, unit in (("hskp", "housekeeper"), ("rqs", "RQS")):
                    v = moved(d, key)
                    if v:
                        arrow = "▲" if v > 0 else "▼"
                        cls = "fc-up" if v > 0 else "fc-down"
                        plural = "s" if abs(v) != 1 and unit == "housekeeper" else ""
                        bits.append(f'<span class="fc-dl {cls}">{arrow}{abs(v)}</span> {unit}{plural}')
                lines.append(f"<b>{_day_name(d['date'], today_iso)}</b> &nbsp;"
                             + " &nbsp;·&nbsp; ".join(bits))
            more = f"<br>…and {len(chg) - 8} more days" if len(chg) > 8 else ""
            st.markdown(f"#### Need changed since {since}")
            st.markdown(f'<div class="fc-chg">{"<br>".join(lines)}{more}</div>',
                        unsafe_allow_html=True)
        else:
            st.caption(f"Need unchanged since the previous pull ({since}).")

    # ── the numbers, for whoever wants them ─────────────────────────────────
    with st.expander("See the numbers"):
        st.dataframe(pd.DataFrame([{
            "Day": f"{pd.Timestamp(d['date']):%a %b %d}",
            "HK needed": d.get("hskp"),
            "HK scheduled": None if d["have"] is None else d["have"]["hskp"],
            "HK short/over": d["gap_hk"],
            "RQS needed": d.get("rqs"),
            "RQS scheduled": None if d["have"] is None else len(d["have"]["rqs"]),
            "RQS short/over": d["gap_rqs"],
            "Other duties": None if d["have"] is None else len(d["have"]["other"]),
            "Rooms": d.get("rooms"), "Checkouts": d.get("checkouts"),
            "Daily svc": d.get("dailies"), "Dust n Vac": d.get("dustnvac"),
        } for d in days]), hide_index=True, use_container_width=True)
    for w in fc.get("warnings", []):
        st.warning(w)


forecast_panel()
