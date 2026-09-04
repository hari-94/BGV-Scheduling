"""
Dashboard — today's floor, as a timeline.

One question: where is everybody, and is the day going to land. Each room is a
bar from when it should be started to when it should be finished, coloured by
what has actually been marked, with now drawn through it. The plan comes from
daystart, so the bars are the same times the housekeeper is reading off her
phone rather than a second opinion.
"""
from datetime import date
import pandas as pd
import streamlit as st
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(__file__)))
import db, auth
import ui
import clock
import daystart as _day
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

INK, INK2 = "#16202e", "#5b6675"
GOOD, WARN = "#1a9e4b", "#e0930f"
LEAD = "#dfe4ea"          # getting there, and waiting on a guest
NOT_MARKED = "#c3cbd6"

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');
.stApp{background:#f6f7f9!important;background-image:none!important;}
html,body,[class*="css"]{font-family:'DM Sans',-apple-system,sans-serif!important;color:#16202e!important;}
.block-container{padding-top:1.2rem!important;max-width:1320px;}
header[data-testid="stHeader"]{background:transparent!important;height:0!important;}
footer{visibility:hidden!important;}#MainMenu{visibility:hidden!important;}
[data-testid="stSidebarNav"]{display:none!important;}

.dtitle{font-size:1.5rem;font-weight:700;letter-spacing:-.02em;margin:0 0 2px;}
.dsub{font-size:.85rem;color:#5b6675;margin:0 0 16px;}

.hero{display:flex;align-items:center;gap:20px;background:#fff;border:1px solid #e6e9ee;
      border-radius:16px;padding:16px 22px;margin-bottom:12px;flex-wrap:wrap;}
.ring{width:96px;height:96px;border-radius:50%;flex:0 0 auto;display:grid;place-items:center;position:relative;}
.ring::after{content:"";position:absolute;inset:10px;background:#fff;border-radius:50%;}
.ring b{position:relative;z-index:1;font-size:1.35rem;font-weight:700;font-variant-numeric:tabular-nums;}
.hero .txt{flex:1 1 200px;}
.hero .txt h3{margin:0 0 3px;font-size:1.02rem;font-weight:700;}
.hero .txt p{margin:0;font-size:.84rem;color:#5b6675;}

.krow{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 14px;}
.k{flex:1 1 130px;background:#fff;border:1px solid #e6e9ee;border-radius:13px;
   padding:13px 15px 11px;position:relative;overflow:hidden;}
.k::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:#2f6fc4;}
.k.g::before{background:#1a9e4b}.k.w::before{background:#e0930f}
.k .n{font-size:1.6rem;font-weight:700;line-height:1;font-variant-numeric:tabular-nums;}
.k .l{font-size:.71rem;color:#5b6675;margin-top:5px;font-weight:500;}
.leg{display:flex;gap:15px;flex-wrap:wrap;margin:8px 2px 0;font-size:.74rem;color:#5b6675;}
.leg span{display:inline-flex;align-items:center;gap:6px;}
.leg i{width:10px;height:10px;border-radius:3px;display:inline-block;}
@media (max-width:768px){.k{flex:1 1 calc(50% - 5px);}.k .n{font-size:1.35rem;}
  [data-testid="stHorizontalBlock"]{flex-direction:column!important;}
  [data-testid="stHorizontalBlock"] > [data-testid="column"]{width:100%!important;flex:1 1 100%!important;}}
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

ui.topnav("Dashboard")
TODAY = clock.today_iso()


@st.cache_data(ttl=20, show_spinner=False)
def today_plan(_gen):
    """Today's rooms, each with the times its housekeeper is working to.

    The plan is built per person, exactly as the phone page builds it, so a
    bar here is the same window she is reading there. Building a second,
    prettier plan for the office to look at would be worse than useless.
    """
    sched = db.load_full_schedule() or {}
    by_hk = {}
    for g in (sched.get("groups_data") or []):
        hk = (g.get("housekeeper", "") or "").strip() or "— unassigned —"
        for r in (g.get("rooms") or []):
            if str(r.get("room", "")).strip():
                by_hk.setdefault(hk, []).append(
                    dict(r, _svc=g.get("service_type", "") or "—",
                         _rqs=(g.get("inspector", "") or "").strip() or "—"))
    rows = []
    for hk, rs in by_hk.items():
        try:
            blocks = _day.plan_day(rs)
        except Exception:
            blocks = []
        for b in blocks:
            raw = b["raw"]
            rows.append({
                "room": b["room"], "housekeeper": hk,
                "service": raw.get("_svc", "—"), "rqs": raw.get("_rqs", "—"),
                "guest": (b["guest"] or "").strip(),
                "start": b["start"], "end": b["end"],
                "lead": b["travel"] + b["wait"],
                "minutes": b["minutes"], "why": b["why"],
                "late": b["late"],
            })
    return pd.DataFrame(rows)


gen = st.session_state.get("dsh_gen", 0)
PLAN = today_plan(gen)

if PLAN.empty:
    st.markdown('<p class="dtitle">Nothing scheduled today</p>', unsafe_allow_html=True)
    st.info("Generate today's schedule on the main page and it will appear here.")
    st.stop()

try:
    statuses = db.get_room_statuses()
except Exception:
    statuses = {}
MARK = {k: _rst.normalise(v.get("status")) for k, v in statuses.items()}
DONE = {_rst.DONE, _rst.INSPECTED, _rst.ALREADY_CLEAN}
# An unmarked room is "" rather than None: a column of Nones comes back out of
# pandas as NaN, and NaN is not None, so the lookup below went looking for a
# status called nan.
PLAN["status"] = [MARK.get(r) or "" for r in PLAN["room"]]
PLAN["state"] = [_rst.META[s][0] if s in _rst.META else "Not marked"
                 for s in PLAN["status"]]

n_rooms = len(PLAN)
n_done = int(sum(1 for s in PLAN["status"] if s in DONE))
n_doing = int(sum(1 for s in PLAN["status"] if s == _rst.STARTED))
n_left = n_rooms - n_done - n_doing
pct = round(100 * n_done / max(n_rooms, 1))
people = PLAN[PLAN["housekeeper"] != "— unassigned —"]["housekeeper"].nunique()
finish = PLAN["end"].max()

st.markdown(f'<p class="dtitle">Today</p><p class="dsub">'
            f'{date.fromisoformat(TODAY).strftime("%A %d %B")} · {n_rooms} rooms · '
            f'{people} housekeepers · last room due {_day.hhmm(finish)}</p>',
            unsafe_allow_html=True)

st.markdown(f"""<div class="hero">
  <div class="ring" style="background:conic-gradient({GOOD} 0turn {pct/100:.4f}turn,
       {WARN if n_doing else '#eef1f5'} {pct/100:.4f}turn
       {(pct + 100*n_doing/max(n_rooms,1))/100:.4f}turn, #eef1f5 0)"><b>{pct}%</b></div>
  <div class="txt"><h3>{n_done} of {n_rooms} rooms cleaned</h3>
    <p>{n_doing} being cleaned now · {n_left} still to start</p></div>
</div>
<div class="krow">
  <div class="k g"><div class="n">{n_done}</div><div class="l">Cleaned</div></div>
  <div class="k w"><div class="n">{n_doing}</div><div class="l">In progress</div></div>
  <div class="k"><div class="n">{n_left}</div><div class="l">Not started</div></div>
  <div class="k"><div class="n">{people}</div><div class="l">Housekeepers</div></div>
</div>""", unsafe_allow_html=True)

# ── Filter and sort ───────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns([1.5, 1.2, 1.2, 1.3])
with c1:
    who = st.multiselect("Housekeeper", sorted(PLAN["housekeeper"].unique()),
                         key="f_hk", placeholder="Everyone")
with c2:
    svc = st.multiselect("Service", sorted(PLAN["service"].unique()),
                         key="f_svc", placeholder="All services")
with c3:
    sts = st.multiselect("Status", sorted(PLAN["state"].unique()),
                         key="f_st", placeholder="Any status")
with c4:
    order = st.selectbox("Sort by", ["Housekeeper, then time", "Time due",
                                     "Room number", "Status", "Longest first"],
                         key="f_sort")

view = PLAN
if who:
    view = view[view["housekeeper"].isin(who)]
if svc:
    view = view[view["service"].isin(svc)]
if sts:
    view = view[view["state"].isin(sts)]

if view.empty:
    st.warning("Nothing matches those filters.")
    st.stop()

RANK = {"Not marked": 0}
for i, k in enumerate(_rst.META):
    RANK[_rst.META[k][0]] = i + 1
if order == "Housekeeper, then time":
    view = view.sort_values(["housekeeper", "start"], ascending=[False, False])
elif order == "Time due":
    view = view.sort_values("end", ascending=False)
elif order == "Room number":
    view = view.sort_values("room", ascending=False)
elif order == "Status":
    view = view.assign(_r=[RANK.get(s, 0) for s in view["state"]]) \
               .sort_values(["_r", "start"], ascending=[False, False])
else:
    view = view.sort_values("minutes")

# ── The timeline ──────────────────────────────────────────────────────────────
# Plotly draws the first row at the bottom, so everything above is sorted
# backwards on purpose: the list then reads top-down the way it was asked for.
labels = [f"{r}  " for r in view["room"]]
colours = [_rst.META[s][2] if s in _rst.META else NOT_MARKED
           for s in view["status"]]

fig = go.Figure()
fig.add_trace(go.Bar(
    y=labels, x=view["lead"], base=view["start"] - view["lead"], orientation="h",
    marker=dict(color=LEAD), name="getting there", hoverinfo="skip",
    showlegend=False))
fig.add_trace(go.Bar(
    y=labels, x=view["end"] - view["start"], base=view["start"], orientation="h",
    marker=dict(color=colours), name="cleaning", showlegend=False,
    text=view["room"], textposition="inside", insidetextanchor="middle",
    textfont=dict(size=10, color="#ffffff"), cliponaxis=False,
    customdata=view[["housekeeper", "guest", "state", "service", "why", "rqs"]].values,
    hovertemplate="<b>%{y}</b> · %{customdata[3]}<br>"
                  "%{customdata[0]} · RQS %{customdata[5]}<br>"
                  "%{customdata[1]}<br>"
                  "<b>%{customdata[2]}</b> · %{customdata[4]}<extra></extra>"))

now_min = clock.now().hour * 60 + clock.now().minute
lo = float((view["start"] - view["lead"]).min())
hi = float(view["end"].max())
if lo <= now_min <= hi:
    fig.add_vline(x=now_min, line_color="#c2452f", line_width=2,
                  annotation_text="now", annotation_position="top",
                  annotation_font_color="#c2452f")
fig.add_vline(x=_day._mins(_day.TARGET_END), line_dash="dash",
              line_color=WARN, line_width=1.4,
              annotation_text="3:30", annotation_position="top")

ticks = list(range(int(lo // 60) * 60, int(hi) + 60, 60))
fig.update_layout(
    barmode="stack", bargap=.28,
    height=max(320, len(view) * 21 + 90),
    margin=dict(l=0, r=16, t=26, b=8),
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Sans", size=11, color=INK),
    xaxis=dict(range=[lo - 8, hi + 8], tickvals=ticks,
               ticktext=[_day.hhmm(t) for t in ticks],
               showgrid=True, gridcolor="rgba(128,138,150,.20)", side="top"),
    yaxis=dict(showgrid=False, tickfont=dict(family="DM Mono", size=10),
               autorange=True),
    hoverlabel=dict(bgcolor="#16202e", font_color="#fff", bordercolor="#16202e"))
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

seen = []
for s in list(_rst.META):
    if s in set(x for x in view["status"] if x):
        seen.append(f'<span><i style="background:{_rst.META[s][2]}"></i>'
                    f'{_rst.META[s][0]}</span>')
seen.append(f'<span><i style="background:{NOT_MARKED}"></i>not marked</span>')
seen.append(f'<span><i style="background:{LEAD}"></i>getting there / waiting</span>')
st.markdown(f'<div class="leg">{"".join(seen)}</div>', unsafe_allow_html=True)

if not MARK:
    st.caption("Nothing has been marked on a phone today, so every bar is the "
               "plan rather than the floor.")

b1, b2 = st.columns([1, 4])
with b1:
    if st.button("Refresh", use_container_width=True):
        st.session_state["dsh_gen"] = gen + 1
        st.rerun()
with b2:
    st.caption(f"Showing {len(view)} of {n_rooms} rooms. Bars run from when a "
               f"room should be started to when it should be finished; the pale "
               f"lead-in is walking there, and waiting if a guest has a late "
               f"checkout.")

with st.expander("Data"):
    out = view[["room", "housekeeper", "rqs", "service", "guest", "state",
                "minutes", "why", "late"]].copy()
    out["due"] = [_day.hhmm(t) for t in view["end"]]
    st.download_button("Download today (CSV)",
                       data=out.to_csv(index=False).encode("utf-8"),
                       file_name=f"today_{TODAY}.csv", mime="text/csv")
    st.dataframe(out, use_container_width=True, hide_index=True)
