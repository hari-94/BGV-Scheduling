"""
Forecast — how many housekeepers and RQS each coming day needs, from SSRS.

The numbers come from the Housekeeping Dashboard report, pulled by
hotsos_agent.py on the office PC (SSRS only opens with a company Windows
login, so the app's server can't fetch it). The PC pulls every two hours
through the day and whenever somebody presses Refresh here.

Bookings move all day, so a headcount on its own doesn't say whether it just
changed. Each pull keeps the one before it, and the page shows the difference
-- "+2 HK since 10:00" is what tells a planner to pick up the phone.

The arithmetic is `staffing.estimate`, the same one Roster Import uses, so the
two pages can't disagree about what a day needs.
"""
import datetime as _dt
import os
import sys
import uuid

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, clock, db, ui          # noqa: E402
import hotsos_sync as hs            # noqa: E402

st.set_page_config(page_title="Forecast", page_icon="📈", layout="wide")
st.markdown("<style>.block-container{max-width:min(1200px,97%);}"
            "[data-testid='stSidebarNav']{display:none!important;}</style>",
            unsafe_allow_html=True)
auth.require_login()
ui.topnav("Forecast")
if not auth.can("can_view_dashboard"):
    st.error("The forecast is for RQS and admins.")
    st.stop()

me = st.session_state.get("display_name") or auth.current_user().get("username", "")
ONLINE_SECONDS = 180


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


st.markdown("## 📈 Staffing forecast")

c1, c2 = st.columns([4, 1])
if c2.button("🔄 Refresh now", type="primary", use_container_width=True):
    db._upsert_key(hs.FORECAST_REQUEST_KEY, {"id": uuid.uuid4().hex, "by": me,
                                             "at": clock.stamp()})


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
                    "this takes about a minute.")
        else:
            st.warning("Refresh asked for, but the office PC isn't connected — it will "
                       "pull as soon as it's back on.")
    elif not online:
        st.warning(f"The office PC isn't connected (last seen {_when(beat.get('at'))}), "
                   "so these numbers won't update until it's back.")

    days = fc.get("days") or []
    if not days:
        st.caption("No forecast yet — it appears after the office PC's first pull.")
        return
    st.caption(f"Housekeeping Dashboard (SSRS), Grand Colorado on Peak 8 · updated "
               f"**{_when(fc.get('pulled_at'))}** · refreshes every two hours from "
               "8 AM to 8 PM, or press Refresh.")

    prev = {d["date"]: d for d in (fc.get("previous") or {}).get("days", [])}
    prev_when = _when((fc.get("previous") or {}).get("pulled_at"))

    def delta(d, key):
        p = prev.get(d["date"])
        if not p or p.get(key) is None or d.get(key) is None:
            return None
        return (d[key] - p[key]) or None      # unchanged: no arrow at all

    # Today and the next two days, the ones a planner can still act on.
    today = clock.today().isoformat()
    upcoming = [d for d in days if d["date"] >= today][:3]
    for col, d in zip(st.columns(len(upcoming)), upcoming):
        name = "Today" if d["date"] == today else \
            f"{pd.Timestamp(d['date']):%A %b %d}".replace(" 0", " ")
        with col.container(border=True):
            st.markdown(f"**{name}**")
            a, b = st.columns(2)
            a.metric("Housekeepers", d.get("hskp"), delta(d, "hskp"),
                     delta_color="inverse",
                     help=f"Full Clean {d.get('hskp_fc')} · Daily Service {d.get('hskp_ds')}")
            b.metric("RQS", d.get("rqs"), delta(d, "rqs"), delta_color="inverse")
            st.caption(f"{d.get('rooms')} rooms · {d.get('checkouts')} checkouts · "
                       f"{d.get('dailies')} daily · {d.get('dustnvac')} dust n vac")
    if prev:
        st.caption(f"Arrows show the change since the previous pull ({prev_when}).")

    def chg(d, key):
        x = delta(d, key)
        return "" if not x else f"{x:+d}"

    df = pd.DataFrame([{
        "Day": f"{pd.Timestamp(d['date']):%a %b %d}",
        "Housekeepers": d.get("hskp"), "HK change": chg(d, "hskp"),
        "HK · Full Clean": d.get("hskp_fc"), "HK · Daily": d.get("hskp_ds"),
        "RQS": d.get("rqs"), "RQS change": chg(d, "rqs"),
        "Rooms": d.get("rooms"), "Checkouts": d.get("checkouts"),
        "Daily svc": d.get("dailies"), "Dust n Vac": d.get("dustnvac"),
        "Minutes": int(d.get("minutes") or 0),
    } for d in days])

    def _shade(v):
        if not v:
            return ""
        return "color:#b42318;font-weight:600" if v.startswith("+") else \
            "color:#067647;font-weight:600"
    st.dataframe(df.style.map(_shade, subset=["HK change", "RQS change"]),
                 hide_index=True, use_container_width=True,
                 height=38 + 35 * len(df))
    for w in fc.get("warnings", []):
        st.warning(w)


forecast_panel()
