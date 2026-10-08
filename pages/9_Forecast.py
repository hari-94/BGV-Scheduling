"""
Forecast — how many housekeepers and RQS each coming day needs, from SSRS.

The numbers come from the Housekeeping Dashboard report, pulled by
hotsos_agent.py on the office PC (SSRS only opens with a company Windows
login, so the app's server can't fetch it). The PC pulls every two hours
through the day and whenever somebody presses Refresh here.

The page answers three questions, in this order, and shows nothing that
doesn't serve one of them:
  1. What do today, tomorrow and the worst day ahead need?  (headline cards)
  2. What does the next three weeks look like?              (two bar charts)
  3. Did new bookings just move anything?                    (a short list)
The full numbers are one click away, not on the page.

Housekeepers and RQS are separate charts on purpose: different jobs at
different scales, and one axis per chart. Bookings move all day, so each pull
keeps the one before it and the page says what changed.

The arithmetic is `staffing.estimate`, the same one Roster Import uses, so the
two pages can't disagree about what a day needs.
"""
import datetime as _dt
import os
import sys
import uuid

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, clock, db, ui          # noqa: E402
import hotsos_sync as hs            # noqa: E402

st.set_page_config(page_title="Forecast", page_icon="📈", layout="wide")
st.markdown("""<style>
.block-container{max-width:min(1200px,97%);}
[data-testid='stSidebarNav']{display:none!important;}
.fc-card{background:#fff;border:1px solid #e6e9ee;border-radius:14px;padding:14px 18px;height:100%}
.fc-day{font-size:.78rem;font-weight:600;color:#5b6675;text-transform:uppercase;letter-spacing:.04em}
.fc-big{display:flex;gap:26px;align-items:baseline;margin-top:6px}
.fc-num{font-family:'Syne',sans-serif;font-size:2.1rem;font-weight:700;color:#16202e;line-height:1}
.fc-lab{font-size:.78rem;color:#5b6675;margin-top:3px}
.fc-dl{font-size:.75rem;font-weight:600;margin-left:4px}
.fc-up{color:#b42318}.fc-down{color:#067647}
.fc-sub{font-size:.78rem;color:#5b6675;margin-top:10px}
.fc-chg{font-size:.85rem;color:#1f2733;line-height:1.7;margin-bottom:14px}
</style>""", unsafe_allow_html=True)
auth.require_login()
ui.topnav("Forecast")
if not auth.can("can_view_dashboard"):
    st.error("The forecast is for RQS and admins.")
    st.stop()

me = st.session_state.get("display_name") or auth.current_user().get("username", "")
ONLINE_SECONDS = 180

# Reference palette, categorical slots 1-3 in their fixed order: one colour
# per job, the same job the same colour wherever it appears.
C_FC = "#2a78d6"        # housekeepers on Full Clean
C_DS = "#eb6834"        # housekeepers on Daily Service
C_RQS = "#1baf7a"       # RQS
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


h1, h2 = st.columns([4, 1])
h1.markdown("## 📈 Staffing forecast")
if h2.button("🔄 Refresh now", type="primary", use_container_width=True):
    db._upsert_key(hs.FORECAST_REQUEST_KEY, {"id": uuid.uuid4().hex, "by": me,
                                             "at": clock.stamp()})


def _delta_html(x, unit=""):
    if not x:
        return ""
    cls = "fc-up" if x > 0 else "fc-down"
    arrow = "▲" if x > 0 else "▼"
    return f'<span class="fc-dl {cls}">{arrow}{abs(x)}{unit}</span>'


def _card(title, d, dhk, drqs):
    return f"""<div class="fc-card">
  <div class="fc-day">{title}</div>
  <div class="fc-big">
    <div><div class="fc-num">{d.get('hskp')}{_delta_html(dhk)}</div>
         <div class="fc-lab">housekeepers</div></div>
    <div><div class="fc-num">{d.get('rqs')}{_delta_html(drqs)}</div>
         <div class="fc-lab">RQS</div></div>
  </div>
  <div class="fc-sub">{d.get('checkouts')} checkouts · {d.get('dailies')} daily ·
       {d.get('dustnvac')} dust n vac</div>
</div>"""


def _layout(fig, height):
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=30, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans, sans-serif", size=12, color=INK2),
        bargap=0.28, barcornerradius=4, hovermode="x unified",
        hoverlabel=dict(bgcolor="#fff", bordercolor="#e6e9ee",
                        font=dict(color=INK, size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0,
                    traceorder="normal", font=dict(color=INK, size=12)),
        showlegend=True)
    # A real date axis, not text labels: it thins its own ticks to the width,
    # so a phone shows every few days instead of 22 labels on top of each other.
    fig.update_xaxes(type="date", showgrid=False, linecolor="#d5d9df",
                     tickfont=dict(color=INK2), tickformat="%a<br>%b %-d",
                     hoverformat="%A %b %-d", fixedrange=True)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(color=INK2),
                     fixedrange=True, rangemode="tozero")
    return fig


@st.fragment(run_every=5)
def forecast_panel():
    fc = db._load_key(hs.FORECAST_KEY) or {}
    req = db._load_key(hs.FORECAST_REQUEST_KEY) or {}
    beat = db._load_key(hs.HEARTBEAT_KEY) or {}
    beat_t = _parse(beat.get("at"))
    online = beat_t and (clock.now() - beat_t).total_seconds() < ONLINE_SECONDS

    pulled, asked = _parse(fc.get("pulled_at")), _parse(req.get("at"))
    if asked and (not pulled or asked > pulled):
        if online:
            st.info(f"⏳ Pulling fresh numbers from SSRS (asked by {req.get('by')})… "
                    "about a minute.")
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
    st.caption(f"From the SSRS Housekeeping Dashboard, Grand Colorado on Peak 8 · "
               f"updated **{_when(fc.get('pulled_at'))}** · refreshes every two hours "
               "from 8 AM to 8 PM.")

    prev = {d["date"]: d for d in (fc.get("previous") or {}).get("days", [])}

    def delta(d, key):
        p = prev.get(d["date"])
        if not p or p.get(key) is None or d.get(key) is None:
            return 0
        return d[key] - p[key]

    # ── 1. headline cards: today, tomorrow, the busiest day ahead ───────────
    cards = days[:2]
    busiest = max(days[2:] or days, key=lambda d: (d.get("hskp") or 0, d.get("rqs") or 0))
    cols = st.columns(3)
    for col, d, title in ((cols[0], cards[0], _day_name(cards[0]["date"], today_iso)),
                          (cols[1], cards[1] if len(cards) > 1 else None, "Tomorrow"),
                          (cols[2], busiest, "Busiest day ahead · "
                           + _day_name(busiest["date"], today_iso))):
        if d:
            col.markdown(_card(title, d, delta(d, "hskp"), delta(d, "rqs")),
                         unsafe_allow_html=True)

    # ── 2. the next three weeks ─────────────────────────────────────────────
    x = [d["date"] for d in days]
    detail = [f"{d.get('rooms')} rooms · {d.get('checkouts')} checkouts · "
              f"{d.get('dailies')} daily" for d in days]

    st.markdown('<div style="height:18px"></div>', unsafe_allow_html=True)
    st.markdown("#### Housekeepers needed")
    hk = go.Figure()
    hk.add_bar(x=x, y=[d.get("hskp_fc") for d in days], name="Full Clean",
               marker=dict(color=C_FC, line=dict(color="#ffffff", width=1)),
               customdata=detail,
               hovertemplate="Full Clean: <b>%{y}</b><extra></extra>")
    hk.add_bar(x=x, y=[d.get("hskp_ds") for d in days], name="Daily Service",
               marker=dict(color=C_DS, line=dict(color="#ffffff", width=1)),
               customdata=[[d.get("hskp"), detail[i],
                            f"{delta(d, 'hskp'):+d} since last pull" if delta(d, "hskp") else ""]
                           for i, d in enumerate(days)],
               hovertemplate="Daily Service: <b>%{y}</b><br>Total: <b>%{customdata[0]}</b>"
                             " housekeepers<br>%{customdata[1]}<br>%{customdata[2]}"
                             "<extra></extra>")
    # The total, written once above each bar: the number a planner reads.
    hk.add_scatter(x=x, y=[d.get("hskp") for d in days], mode="text",
                   text=[str(d.get("hskp")) for d in days], textposition="top center",
                   textfont=dict(color=INK, size=11), hoverinfo="skip",
                   showlegend=False)
    hk.update_layout(barmode="stack")
    top = max(d.get("hskp") or 0 for d in days)
    hk.update_yaxes(range=[0, top * 1.15 + 1])
    st.plotly_chart(_layout(hk, 300), use_container_width=True,
                    config={"displayModeBar": False})

    st.markdown("#### RQS needed")
    rq = go.Figure()
    rq.add_bar(x=x, y=[d.get("rqs") for d in days], name="RQS",
               marker=dict(color=C_RQS), text=[str(d.get("rqs")) for d in days],
               textposition="outside", textfont=dict(color=INK, size=11),
               customdata=[f"{delta(d, 'rqs'):+d} since last pull" if delta(d, "rqs") else ""
                           for d in days],
               hovertemplate="RQS: <b>%{y}</b><br>%{customdata}<extra></extra>",
               cliponaxis=False)
    rq.update_yaxes(range=[0, max(d.get("rqs") or 0 for d in days) * 1.25 + 1])
    st.plotly_chart(_layout(rq, 200).update_layout(showlegend=False),
                    use_container_width=True, config={"displayModeBar": False})

    # ── 3. what new bookings just moved ─────────────────────────────────────
    moved = [d for d in days if delta(d, "hskp") or delta(d, "rqs")]
    if prev:
        since = _when((fc.get("previous") or {}).get("pulled_at"))
        if moved:
            lines = []
            for d in moved[:8]:
                bits = []
                for key, unit in (("hskp", "housekeeper"), ("rqs", "RQS")):
                    v = delta(d, key)
                    if v:
                        plural = "s" if abs(v) != 1 and unit == "housekeeper" else ""
                        bits.append(f"{_delta_html(v)} {unit}{plural}")
                lines.append(f"<b>{_day_name(d['date'], today_iso)}</b> &nbsp;"
                             + " &nbsp;·&nbsp; ".join(bits))
            more = f"<br>…and {len(moved) - 8} more days" if len(moved) > 8 else ""
            st.markdown(f"#### Changed since {since}")
            st.markdown(f'<div class="fc-chg">{"<br>".join(lines)}{more}</div>',
                        unsafe_allow_html=True)
        else:
            st.caption(f"No change since the previous pull ({since}).")

    # ── the numbers, for whoever wants them ─────────────────────────────────
    with st.expander("See the numbers"):
        st.dataframe(pd.DataFrame([{
            "Day": f"{pd.Timestamp(d['date']):%a %b %d}",
            "Housekeepers": d.get("hskp"), "Full Clean": d.get("hskp_fc"),
            "Daily": d.get("hskp_ds"), "RQS": d.get("rqs"), "Rooms": d.get("rooms"),
            "Checkouts": d.get("checkouts"), "Daily svc": d.get("dailies"),
            "Dust n Vac": d.get("dustnvac"), "Minutes": int(d.get("minutes") or 0),
        } for d in days]), hide_index=True, use_container_width=True)
    for w in fc.get("warnings", []):
        st.warning(w)


forecast_panel()
