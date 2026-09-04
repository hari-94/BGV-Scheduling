"""
Dashboard — two questions, answered plainly.

Where is the floor right now, and how is each person doing over time. It used
to answer a dozen more and was unreadable for it; anything that was interesting
once rather than every morning has been taken out rather than folded away.
"""
from datetime import date
import json
import pandas as pd
import streamlit as st
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(__file__)))
import db, auth
import ui
import clock
import roomstatus as _rst

try:
    import plotly.graph_objects as go
    PLOTLY_OK = True
except ImportError:
    PLOTLY_OK = False

st.set_page_config(page_title="Dashboard", page_icon="GC8", layout="wide")
st.markdown("""<style>[data-testid="stSidebarNav"]{display:none !important;}</style>""",
            unsafe_allow_html=True)

for _k, _v in [("groups_data", None), ("total_rooms", 0), ("inspectors_data", [])]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

auth.require_login()
if not auth.can("can_view_dashboard"):
    st.error("Dashboard requires RQS or Admin role.")
    st.stop()
if not PLOTLY_OK:
    st.error("Install plotly: `pip install plotly`")
    st.stop()

# ── Look ──────────────────────────────────────────────────────────────────────
# One ink, one accent, one surface. The old sheet was a dark theme forced light
# with overrides on top of it, which is why nothing quite lined up.
INK, INK2, INK3 = "#16202e", "#5b6675", "#8b95a3"
ACCENT, SURF, LINE = "#2f6fc4", "#ffffff", "#e6e9ee"
GOOD, WARN, BAD = "#1a9e4b", "#e0930f", "#c2452f"

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');
.stApp{background:#f6f7f9!important;background-image:none!important;}
html,body,[class*="css"]{font-family:'DM Sans',-apple-system,sans-serif!important;color:#16202e!important;}
.block-container{padding-top:1.2rem!important;max-width:1180px;}
header[data-testid="stHeader"]{background:transparent!important;height:0!important;}
footer{visibility:hidden!important;}#MainMenu{visibility:hidden!important;}
[data-testid="stSidebarNav"]{display:none!important;}

.dtitle{font-size:1.5rem;font-weight:700;letter-spacing:-.02em;margin:0 0 2px;color:#16202e;}
.dsub{font-size:.85rem;color:#5b6675;margin:0 0 18px;}

/* the numbers */
.krow{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 18px;}
.k{flex:1 1 150px;background:#fff;border:1px solid #e6e9ee;border-radius:14px;
   padding:15px 16px 13px;position:relative;overflow:hidden;}
.k::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:#2f6fc4;}
.k.g::before{background:#1a9e4b}.k.w::before{background:#e0930f}.k.b::before{background:#c2452f}
.k .n{font-size:1.85rem;font-weight:700;line-height:1;letter-spacing:-.02em;
      font-variant-numeric:tabular-nums;}
.k .l{font-size:.72rem;color:#5b6675;margin-top:5px;font-weight:500;}
.k .s{font-size:.68rem;color:#8b95a3;margin-top:2px;}

/* the ring */
.hero{display:flex;align-items:center;gap:22px;background:#fff;border:1px solid #e6e9ee;
      border-radius:16px;padding:20px 24px;margin-bottom:18px;flex-wrap:wrap;}
.ring{width:112px;height:112px;border-radius:50%;flex:0 0 auto;display:grid;place-items:center;
      position:relative;}
.ring::after{content:"";position:absolute;inset:11px;background:#fff;border-radius:50%;}
.ring b{position:relative;z-index:1;font-size:1.5rem;font-weight:700;
        font-variant-numeric:tabular-nums;letter-spacing:-.02em;}
.hero .txt{flex:1 1 220px;min-width:200px;}
.hero .txt h3{margin:0 0 4px;font-size:1.05rem;font-weight:700;}
.hero .txt p{margin:0;font-size:.85rem;color:#5b6675;line-height:1.5;}

/* one row per person */
.plist{background:#fff;border:1px solid #e6e9ee;border-radius:16px;padding:6px 18px 12px;}
.prow{display:flex;align-items:center;gap:14px;padding:11px 0;border-bottom:1px solid #f0f2f5;}
.prow:last-child{border-bottom:none;}
.pname{width:132px;flex:0 0 auto;font-size:.86rem;font-weight:600;white-space:nowrap;
       overflow:hidden;text-overflow:ellipsis;}
.pbar{flex:1 1 auto;height:12px;border-radius:99px;background:#eef1f5;overflow:hidden;display:flex;}
.pbar i{display:block;height:100%;transition:width .5s cubic-bezier(.2,.8,.25,1);}
.pnum{width:74px;flex:0 0 auto;text-align:right;font-family:'DM Mono',monospace;
      font-size:.78rem;color:#5b6675;font-variant-numeric:tabular-nums;}
.pmeta{width:64px;flex:0 0 auto;text-align:right;font-size:.72rem;color:#8b95a3;}
.leg{display:flex;gap:16px;flex-wrap:wrap;margin:12px 2px 0;font-size:.74rem;color:#5b6675;}
.leg span{display:inline-flex;align-items:center;gap:6px;}
.leg i{width:10px;height:10px;border-radius:3px;display:inline-block;}

.stTabs [data-baseweb="tab-list"]{gap:6px;background:transparent!important;border:none!important;
  padding:0!important;margin-bottom:6px;}
.stTabs [data-baseweb="tab"]{border-radius:9px!important;padding:8px 18px!important;
  font-size:.86rem!important;font-weight:600!important;color:#5b6675!important;
  background:#eef1f5!important;border:none!important;}
.stTabs [aria-selected="true"]{background:#16202e!important;color:#fff!important;}
.stTabs [data-baseweb="tab-highlight"],.stTabs [data-baseweb="tab-border"]{display:none!important;}

@media (max-width:768px){
  .k{flex:1 1 calc(50% - 6px);} .k .n{font-size:1.45rem;}
  .pname{width:96px;} .pmeta{display:none;}
  [data-testid="stHorizontalBlock"]{flex-direction:column!important;}
  [data-testid="stHorizontalBlock"] > [data-testid="column"]{width:100%!important;flex:1 1 100%!important;}
}
</style>""", unsafe_allow_html=True)


# ── Keep writing the snapshot the rest of the app expects ─────────────────────
def build_snapshot(fg, total_rms, inspectors):
    hk_snap, insp_snap = {}, {}
    for g in fg:
        hk, svc = g.get("housekeeper", ""), g.get("service_type", "")
        if not hk or hk == "Manager":
            continue
        s = hk_snap.setdefault(hk, {"time": 0, "rooms": 0, "rooms_fc": 0,
                                    "rooms_ds": 0, "rooms_dv": 0})
        n = len(g.get("rooms", []))
        s["time"] += g.get("time", 0)
        s["rooms"] += n
        if svc == "Full Clean":
            s["rooms_fc"] += n
        elif svc == "Daily Service":
            s["rooms_ds"] += n
        elif svc == "Dust n Vac":
            s["rooms_dv"] += n
    for insp in inspectors:
        nm = insp.get("name", "")
        if nm:
            labels = set(insp.get("groups", []))
            insp_snap[nm] = {
                "rooms": sum(len(g.get("rooms", [])) for g in fg
                             if g.get("label") in labels),
                "groups": len(labels), "role": insp.get("role", "FC"),
                "buildings": insp.get("buildings", [])}
    return {"date": clock.today_iso(), "total_rooms": total_rms,
            "n_groups": len(fg), "hk": hk_snap, "inspectors": insp_snap,
            "saved_by": st.session_state.get("username", "unknown"), "schema_v": 2}


_fg = st.session_state.get("groups_data")
if _fg:
    try:
        db.save_snapshot(build_snapshot(_fg, st.session_state.get("total_rooms", 0),
                                        st.session_state.get("inspectors_data", [])))
    except Exception:
        pass


# ── The data ──────────────────────────────────────────────────────────────────
def _stored_days():
    """The stored schedules, whichever db module this process happens to hold.

    Streamlit re-reads a *page* file on every rerun but not the modules it
    imports: `import db` comes back from sys.modules. A process that was already
    running when a deploy landed runs the new page against the old db, and a
    page calling a db function added in that same deploy dies with an
    AttributeError until somebody reboots. This page did exactly that once.
    """
    fn = getattr(db, "load_schedule_history", None)
    if fn is not None:
        return fn()
    r = (db._client().table("schedule_full").select("date,payload")
         .order("date", desc=True).execute())
    out = []
    for row in (r.data or []):
        p = row.get("payload")
        if isinstance(p, str):
            p = json.loads(p)
        gs = (p or {}).get("groups_data") or []
        if gs:
            out.append({"date": row["date"], "groups_data": gs})
    return out


@st.cache_data(ttl=300, show_spinner="Reading the schedule history…")
def load_history():
    """One row per room, every stored day. Everything here is a slice of it."""
    rows = []
    for day in _stored_days():
        for g in day["groups_data"]:
            hk = (g.get("housekeeper", "") or "").strip() or "— unassigned —"
            for x in (g.get("rooms") or []):
                code = str(x.get("room", "")).strip().upper()
                if code:
                    rows.append({"date": day["date"], "room": code,
                                 "housekeeper": hk,
                                 "service": g.get("service_type", "") or "—",
                                 "minutes": float(x.get("time") or 0)})
    return pd.DataFrame(rows)


RM = load_history()
ui.topnav("Dashboard")

if RM.empty:
    st.markdown('<p class="dtitle">Dashboard</p>', unsafe_allow_html=True)
    st.info("No schedules stored yet. Generate one on the main page first.")
    st.stop()

TODAY = clock.today_iso()
DAY_MINUTES = 330          # 10:00 to 3:30, the working day

tab_today, tab_people = st.tabs(["Today", "People"])

# ═══════════════════════════════════════════════════════════════════════ TODAY
with tab_today:
    day = RM[RM["date"] == TODAY]
    if day.empty:
        st.markdown('<p class="dtitle">Nothing scheduled today</p>',
                    unsafe_allow_html=True)
        st.info("Generate today's schedule on the main page and it will appear here.")
    else:
        try:
            statuses = db.get_room_statuses()
        except Exception:
            statuses = {}
        mark = {k: _rst.normalise(v.get("status")) for k, v in statuses.items()}
        DONE = {_rst.DONE, _rst.INSPECTED, _rst.ALREADY_CLEAN}

        n_rooms = len(day)
        n_done = sum(1 for r in day["room"] if mark.get(r) in DONE)
        n_doing = sum(1 for r in day["room"] if mark.get(r) == _rst.STARTED)
        n_left = n_rooms - n_done - n_doing
        pct = round(100 * n_done / max(n_rooms, 1))
        people = day[day["housekeeper"] != "— unassigned —"]["housekeeper"].nunique()

        st.markdown(
            f'<p class="dtitle">Today</p>'
            f'<p class="dsub">{date.fromisoformat(TODAY).strftime("%A %d %B")} · '
            f'{n_rooms} rooms · {people} housekeepers</p>',
            unsafe_allow_html=True)

        rest = "still to start" if n_left else "everything is under way"
        st.markdown(f"""<div class="hero">
  <div class="ring" style="background:conic-gradient({GOOD} 0turn {pct/100:.4f}turn,
       {'#f0c980' if n_doing else '#eef1f5'} {pct/100:.4f}turn
       {(pct+100*n_doing/max(n_rooms,1))/100:.4f}turn, #eef1f5 0)">
    <b>{pct}%</b></div>
  <div class="txt"><h3>{n_done} of {n_rooms} rooms cleaned</h3>
    <p>{n_doing} being cleaned now · {n_left} {rest}</p></div>
</div>""", unsafe_allow_html=True)

        st.markdown(f"""<div class="krow">
  <div class="k g"><div class="n">{n_done}</div><div class="l">Cleaned</div></div>
  <div class="k w"><div class="n">{n_doing}</div><div class="l">In progress</div></div>
  <div class="k"><div class="n">{n_left}</div><div class="l">Not started</div></div>
  <div class="k"><div class="n">{people}</div><div class="l">Housekeepers</div></div>
</div>""", unsafe_allow_html=True)

        rows = []
        for hk, grp in day.groupby("housekeeper"):
            codes = list(grp["room"])
            d = sum(1 for c in codes if mark.get(c) in DONE)
            w = sum(1 for c in codes if mark.get(c) == _rst.STARTED)
            rows.append((hk, d, w, len(codes), sum(grp["minutes"])))
        # Furthest along first, and the rooms nobody is on last — the Dust n Vac
        # round has no housekeeper by design, so it is not a person having a bad
        # morning and should not sit among them.
        rows.sort(key=lambda r: (r[0] == "— unassigned —",
                                 -(r[1] / max(r[3], 1)), r[0]))

        bars = ""
        for hk, d, w, tot, mins in rows:
            pd_, pw = 100 * d / max(tot, 1), 100 * w / max(tot, 1)
            bars += (
                f'<div class="prow"><div class="pname" title="{hk}">{hk}</div>'
                f'<div class="pbar" title="{d} cleaned, {w} in progress, '
                f'{tot - d - w} to go">'
                f'<i style="width:{pd_:.1f}%;background:{GOOD}"></i>'
                f'<i style="width:{pw:.1f}%;background:{WARN}"></i></div>'
                f'<div class="pnum">{d}/{tot}</div>'
                f'<div class="pmeta">{mins:.0f}m</div></div>')
        st.markdown(f'<div class="plist">{bars}</div>'
                    f'<div class="leg">'
                    f'<span><i style="background:{GOOD}"></i>cleaned</span>'
                    f'<span><i style="background:{WARN}"></i>in progress</span>'
                    f'<span><i style="background:#eef1f5"></i>to go</span></div>',
                    unsafe_allow_html=True)

        if not mark:
            st.caption("Nothing has been marked on a phone today, so every bar is "
                       "still empty. The room counts are today's schedule.")

# ══════════════════════════════════════════════════════════════════════ PEOPLE
with tab_people:
    st.markdown('<p class="dtitle">People</p>', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 1])
    with c1:
        period = st.selectbox("Period", ["Last 7 days", "Last 30 days",
                                         "Last 90 days", "All time"],
                              index=1, key="dsh_p", label_visibility="collapsed")
    with c2:
        measure = st.selectbox("Measure", ["Minutes a day", "Rooms a day",
                                           "Rooms in total"],
                               key="dsh_m", label_visibility="collapsed")

    dates = sorted(RM["date"].unique(), reverse=True)
    n = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}.get(period)
    keep = set(dates if n is None else dates[:n])
    sub = RM[RM["date"].isin(keep) & (RM["housekeeper"] != "— unassigned —")]

    if sub.empty:
        st.info("Nobody was assigned rooms in that period.")
    else:
        g = sub.groupby("housekeeper").agg(days=("date", "nunique"),
                                           rooms=("room", "count"),
                                           minutes=("minutes", "sum")).reset_index()
        g["mins_day"] = (g["minutes"] / g["days"]).round(0)
        g["rooms_day"] = (g["rooms"] / g["days"]).round(1)

        st.markdown(f"""<div class="krow">
  <div class="k"><div class="n">{len(g)}</div><div class="l">Housekeepers</div>
    <div class="s">over {len(keep)} day(s)</div></div>
  <div class="k"><div class="n">{int(g['rooms'].sum()):,}</div><div class="l">Rooms cleaned</div>
    <div class="s">{g['rooms'].sum()/max(len(keep),1):.0f} a day</div></div>
  <div class="k {'w' if g['mins_day'].mean() > DAY_MINUTES else 'g'}">
    <div class="n">{g['mins_day'].mean():.0f}m</div><div class="l">Average day</div>
    <div class="s">the day holds {DAY_MINUTES}m</div></div>
</div>""", unsafe_allow_html=True)

        col = {"Minutes a day": "mins_day", "Rooms a day": "rooms_day",
               "Rooms in total": "rooms"}[measure]
        gg = g.sort_values(col)
        is_mins = col == "mins_day"
        cols = [BAD if v > 380 else WARN if v > DAY_MINUTES else ACCENT
                for v in gg[col]] if is_mins else ACCENT
        suffix = "m" if is_mins else ""

        fig = go.Figure(go.Bar(
            y=gg["housekeeper"], x=gg[col], orientation="h",
            marker=dict(color=cols),
            text=[f"{v:,.0f}{suffix}" if not isinstance(v, float) or v == int(v)
                  else f"{v:,.1f}{suffix}" for v in gg[col]],
            textposition="outside", cliponaxis=False,
            customdata=gg[["days", "rooms", "mins_day"]].values,
            hovertemplate="<b>%{y}</b><br>%{x:,.0f}" + suffix +
                          "<br>%{customdata[0]} days · %{customdata[1]} rooms"
                          "<extra></extra>"))
        if is_mins:
            fig.add_vline(x=DAY_MINUTES, line_dash="dash", line_color=WARN,
                          line_width=1.5)
        fig.update_layout(
            height=max(260, len(gg) * 30 + 70),
            margin=dict(l=0, r=54, t=8, b=8),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="DM Sans", size=12, color=INK),
            showlegend=False, bargap=.34,
            xaxis=dict(visible=False),
            yaxis=dict(showgrid=False, ticksuffix="  "),
            hoverlabel=dict(bgcolor="#16202e", font_color="#fff",
                            bordercolor="#16202e"))
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})
        if is_mins:
            st.caption(f"The dashed line is a full day's work, {DAY_MINUTES} "
                       "minutes. Amber is over it, red past the 380-minute cap.")

        with st.expander("The numbers"):
            show = g.sort_values("rooms", ascending=False).rename(columns={
                "housekeeper": "Housekeeper", "days": "Days", "rooms": "Rooms",
                "rooms_day": "Rooms a day", "mins_day": "Minutes a day"})[
                ["Housekeeper", "Days", "Rooms", "Rooms a day", "Minutes a day"]]
            st.dataframe(show, use_container_width=True, hide_index=True)

# ── Admin bits, out of the way ────────────────────────────────────────────────
with st.expander("Data"):
    d1, d2 = st.columns(2)
    with d1:
        st.download_button("Download history (CSV)",
                           data=RM.to_csv(index=False).encode("utf-8"),
                           file_name="housekeeping_history.csv", mime="text/csv",
                           use_container_width=True)
    with d2:
        if auth.can("can_delete_data"):
            dd = st.selectbox("Delete a day", ["— select —"] +
                              sorted(RM["date"].unique(), reverse=True))
            if st.button("Delete", type="secondary") and dd != "— select —":
                db.delete_snapshot(dd)
                load_history.clear()
                st.success(f"Deleted {dd}. Refresh to update.")
        else:
            st.caption("Only admins can delete data.")
    st.caption(f"{len(RM):,} room-assignments across {RM['date'].nunique()} "
               f"stored days.")
