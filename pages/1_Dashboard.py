"""
Dashboard — Cleaning Schedule Performance Tracker
"""
import json, os, html as _html
from datetime import date, timedelta
import pandas as pd
import streamlit as st
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(__file__)))
import db, auth

try:
    import plotly.graph_objects as go
    PLOTLY_OK = True
except ImportError:
    PLOTLY_OK = False

st.set_page_config(page_title="Dashboard · Cleaning Schedule", page_icon="📊", layout="wide")

st.markdown("""<style>
[data-testid="stSidebarNav"],[data-testid="stSidebarNavItems"],
[data-testid="stSidebarNavSeparator"]{display:none!important}
</style>""", unsafe_allow_html=True)

for _k, _v in [("logged_in",False),("username",""),("role",""),
               ("groups_data",None),("total_rooms",0),("inspectors_data",[])]:
    if _k not in st.session_state: st.session_state[_k] = _v

auth.init_auth()
if not st.session_state.get("logged_in"):
    st.warning("🔒 Please sign in from the main page.")
    st.page_link("cleaning_scheduler.py", label="← Sign In")
    st.stop()
if not auth.can("can_view_dashboard"):
    st.error("⛔ Dashboard requires RQS or Admin role.")
    st.stop()
if not PLOTLY_OK:
    st.error("Install plotly: `pip install plotly`")
    st.stop()

# ── Manual sidebar nav ─────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🧭 Navigation")
    st.page_link("cleaning_scheduler.py", label="🧹 Schedule")
    st.page_link("pages/1_Dashboard.py",  label="📊 Dashboard")
    if st.session_state.get("role") == "admin":
        st.page_link("pages/2_Admin.py",  label="👑 Admin")
    st.markdown("---")
    _u = st.session_state.get("username","")
    _r = st.session_state.get("role","")
    if _u: st.caption(f"Signed in as **{_u}** · {_r.title()}")

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
*,*::before,*::after{box-sizing:border-box;}
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.block-container{padding-top:1.4rem!important;max-width:1440px;}
.pg-title{font-size:1.6rem;font-weight:800;letter-spacing:-.6px;
  background:linear-gradient(135deg,#1e293b,#3B4FE4);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin:0 0 2px}
.pg-sub{font-size:.82rem;color:#64748b;margin:0 0 .6rem}
.sec{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.12em;
     color:#94a3b8;padding-bottom:4px;border-bottom:1.5px solid #f1f5f9;margin:.9rem 0 .5rem}
.kpi-row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:1rem}
.kpi{flex:1 1 130px;background:#fff;border:1px solid #e8edf5;border-radius:14px;
     padding:14px;box-shadow:0 2px 8px rgba(0,0,0,.05)}
.kpi.pu{background:linear-gradient(135deg,#5B4FE9,#7C6FF5);border:none}
.kpi.te{background:linear-gradient(135deg,#0D9488,#14B8A6);border:none}
.kpi.am{background:linear-gradient(135deg,#D97706,#F59E0B);border:none}
.kpi.bl{background:linear-gradient(135deg,#2563EB,#3B82F6);border:none}
.kpi .val{font-size:1.7rem;font-weight:800;color:#0f172a;line-height:1;margin-bottom:3px}
.kpi .lbl{font-size:.6rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;font-weight:600}
.kpi .sub{font-size:.7rem;color:#64748b;margin-top:3px}
.kpi.pu .val,.kpi.pu .lbl,.kpi.pu .sub,
.kpi.te .val,.kpi.te .lbl,.kpi.te .sub,
.kpi.am .val,.kpi.am .lbl,.kpi.am .sub,
.kpi.bl .val,.kpi.bl .lbl,.kpi.bl .sub{color:#fff}
.stTabs [data-baseweb="tab-list"]{gap:4px;background:#f1f5f9;border-radius:10px;padding:3px;border:none!important}
.stTabs [data-baseweb="tab"]{border-radius:8px!important;padding:6px 18px!important;font-size:.78rem!important;
  font-weight:600!important;color:#64748b!important;border:none!important;background:transparent!important}
.stTabs [aria-selected="true"]{background:#fff!important;color:#1e293b!important;
  box-shadow:0 1px 4px rgba(0,0,0,.1)!important}
</style>""", unsafe_allow_html=True)

PURPLE="#5B4FE9"; TEAL="#0D9488"; AMBER="#D97706"; BLUE="#2563EB"; RED="#DC2626"

# ══════════════════════════════════════════════════════════════════════════════
#  SNAPSHOT BUILDER — called when schedule exists in session
# ══════════════════════════════════════════════════════════════════════════════
def build_snapshot(fg, total_rms, inspectors):
    """Build accurate snapshot from current schedule groups."""
    today_str = str(date.today())
    hk_snap   = {}
    insp_snap = {}

    for g in fg:
        hk  = g.get("housekeeper", "")
        svc = g.get("service_type", "")
        if not hk or hk == "Manager":
            continue
        if hk not in hk_snap:
            hk_snap[hk] = {"time":0, "rooms":0,
                            "rooms_fc":0, "rooms_ds":0, "rooms_dv":0}
        room_list = g.get("rooms", [])
        n = len(room_list)
        hk_snap[hk]["time"]  += g.get("time", 0)
        hk_snap[hk]["rooms"] += n
        if   svc == "Full Clean":     hk_snap[hk]["rooms_fc"] += n
        elif svc == "Daily Service":  hk_snap[hk]["rooms_ds"] += n
        elif svc == "Dust n Vac":     hk_snap[hk]["rooms_dv"] += n

    for insp in inspectors:
        nm = insp.get("name", "")
        if not nm:
            continue
        # Count rooms in every group this inspector is assigned to
        insp_labels = set(insp.get("groups", []))
        n_rooms = sum(
            len(g.get("rooms", []))
            for g in fg
            if g.get("label") in insp_labels
        )
        insp_snap[nm] = {
            "rooms":     n_rooms,
            "groups":    len(insp_labels),
            "role":      insp.get("role", "FC"),
            "buildings": insp.get("buildings", []),
        }

    return {
        "date":        today_str,
        "total_rooms": total_rms,
        "n_groups":    len(fg),
        "hk":          hk_snap,
        "inspectors":  insp_snap,
        "saved_by":    st.session_state.get("username", "unknown"),
        "schema_v":    2,   # version flag so we know this has correct fields
    }

# ── Auto-save today if schedule is loaded ─────────────────────────────────────
fg         = st.session_state.get("groups_data")
total_rms  = st.session_state.get("total_rooms", 0)
inspectors = st.session_state.get("inspectors_data", [])

@st.cache_data(ttl=30)
def get_log():
    try:    return db.load_log()
    except Exception as ex: st.error(f"DB: {ex}"); return []

if fg:
    snap = build_snapshot(fg, total_rms, inspectors)
    try:
        db.save_snapshot(snap)
        get_log.clear()
    except Exception:
        pass

log = get_log()

# ── Header ─────────────────────────────────────────────────────────────────────
h1, h2 = st.columns([5,1])
with h1:
    st.markdown('<p class="pg-title">📊 Performance Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class="pg-sub">Daily · weekly · monthly metrics</p>', unsafe_allow_html=True)
with h2:
    st.page_link("cleaning_scheduler.py", label="← Scheduler", use_container_width=True)

if not log:
    st.info("💡 No data yet. Generate a schedule on the main page first.")
    st.stop()

today = date.today()
all_dates = sorted({s.get("date","") for s in log if s.get("date")}, reverse=True)

# ── Period filter ──────────────────────────────────────────────────────────────
def filter_log(period):
    if period == "Today":
        return [s for s in log if s.get("date") == str(today)]
    elif period == "This Week":
        cutoff = str(today - timedelta(days=today.weekday()))
        return [s for s in log if s.get("date","") >= cutoff]
    elif period == "This Month":
        cutoff = str(today.replace(day=1))
        return [s for s in log if s.get("date","") >= cutoff]
    return log

# ── Aggregators ────────────────────────────────────────────────────────────────
def agg_hk(snaps):
    out = {}
    for snap in snaps:
        for hk, s in snap.get("hk", {}).items():
            if hk not in out:
                out[hk] = {"time":0,"rooms":0,"rooms_fc":0,"rooms_ds":0,"rooms_dv":0,"days":0}
            out[hk]["time"]     += s.get("time", 0)
            out[hk]["rooms"]    += s.get("rooms", 0)
            out[hk]["rooms_fc"] += s.get("rooms_fc", 0)
            out[hk]["rooms_ds"] += s.get("rooms_ds", 0)
            out[hk]["rooms_dv"] += s.get("rooms_dv", 0)
            out[hk]["days"]     += 1
    return out

def agg_insp(snaps):
    out = {}
    for snap in snaps:
        for nm, s in snap.get("inspectors", {}).items():
            # Skip migrated/estimated data (schema_v < 2 means old snapshot)
            if snap.get("schema_v", 1) < 2 and s.get("rooms", 0) == s.get("groups", 0) * 10:
                rooms_val = 0   # don't show bad estimate
            else:
                rooms_val = s.get("rooms", 0)
            if nm not in out:
                out[nm] = {"rooms":0,"groups":0,"role":"","days":0}
            out[nm]["rooms"]  += rooms_val
            out[nm]["groups"] += s.get("groups", 0)
            out[nm]["role"]    = s.get("role", "FC")
            out[nm]["days"]   += 1
    return out

# ═══════════════════════════════════════════════════════════════════════════════
#  TABS
# ═══════════════════════════════════════════════════════════════════════════════
tab_hk, tab_insp, tab_log, tab_manage = st.tabs([
    "🧑‍🔧 Housekeepers", "🔍 Inspectors", "📅 Daily Log", "🗂 Manage"
])

# ══════════════════════════════════════════════════════════════════════════════
#  HOUSEKEEPER TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_hk:
    period_hk = st.radio("Period", ["Today","This Week","This Month","All Time"],
                          horizontal=True, key="hk_p")
    snaps_hk  = filter_log(period_hk)
    hk_data   = agg_hk(snaps_hk)
    n_days    = len(snaps_hk)

    if not hk_data:
        st.info(f"No housekeeper data for {period_hk}.")
    else:
        # KPI cards
        total_fc = sum(v["rooms_fc"] for v in hk_data.values())
        total_ds = sum(v["rooms_ds"] for v in hk_data.values())
        total_dv = sum(v["rooms_dv"] for v in hk_data.values())
        total_all= total_fc + total_ds + total_dv
        n_hks    = len(hk_data)
        avg_time = sum(v["time"] for v in hk_data.values()) // max(n_hks * n_days, 1)

        st.markdown(f"""<div class="kpi-row">
  <div class="kpi pu"><div class="val">{total_all}</div>
    <div class="lbl">Total Rooms</div><div class="sub">{n_days} day(s)</div></div>
  <div class="kpi bl"><div class="val">{total_fc}</div>
    <div class="lbl">Full Clean</div></div>
  <div class="kpi te"><div class="val">{total_ds}</div>
    <div class="lbl">Daily Service</div></div>
  <div class="kpi am"><div class="val">{total_dv}</div>
    <div class="lbl">Dust &amp; Vac</div></div>
  <div class="kpi"><div class="val">{n_hks}</div>
    <div class="lbl">Active HKs</div></div>
  <div class="kpi"><div class="val">{avg_time}m</div>
    <div class="lbl">Avg Time/Day</div></div>
</div>""", unsafe_allow_html=True)

        # Build df sorted by total rooms desc
        rows = sorted([
            {"HK": hk,
             "FC": v["rooms_fc"], "DS": v["rooms_ds"], "DV": v["rooms_dv"],
             "Total": v["rooms"],
             "Avg Time": v["time"] // max(v["days"], 1),
             "Days": v["days"]}
            for hk, v in hk_data.items()
        ], key=lambda r: -r["Total"])
        df = pd.DataFrame(rows)

        # ── Rooms chart: stacked horizontal bars ──────────────────────────────
        st.markdown('<p class="sec">Rooms Cleaned by Service Type</p>', unsafe_allow_html=True)

        if df["Total"].sum() == 0:
            st.info("ℹ️ Room counts are 0 for this period. "
                    "Go to the Scheduler, generate a schedule, then come back.")
        else:
            # Sort ascending so highest is at top of horizontal chart
            df_c = df.sort_values("Total", ascending=True)
            fig = go.Figure()
            fig.add_trace(go.Bar(
                name="Full Clean", y=df_c["HK"], x=df_c["FC"],
                orientation="h", marker_color=BLUE,
                text=[f"{v}" if v > 0 else "" for v in df_c["FC"]],
                textposition="inside", insidetextanchor="middle",
                hovertemplate="<b>%{y}</b> — Full Clean: %{x} rooms<extra></extra>",
            ))
            fig.add_trace(go.Bar(
                name="Daily Service", y=df_c["HK"], x=df_c["DS"],
                orientation="h", marker_color=TEAL,
                text=[f"{v}" if v > 0 else "" for v in df_c["DS"]],
                textposition="inside", insidetextanchor="middle",
                hovertemplate="<b>%{y}</b> — Daily Service: %{x} rooms<extra></extra>",
            ))
            fig.add_trace(go.Bar(
                name="Dust & Vac", y=df_c["HK"], x=df_c["DV"],
                orientation="h", marker_color=AMBER,
                text=[f"{v}" if v > 0 else "" for v in df_c["DV"]],
                textposition="inside", insidetextanchor="middle",
                hovertemplate="<b>%{y}</b> — Dust & Vac: %{x} rooms<extra></extra>",
            ))
            fig.update_layout(
                barmode="stack",
                height=max(320, len(df_c) * 26 + 80),
                margin=dict(l=10,r=60,t=10,b=10),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter", size=12),
                legend=dict(orientation="h", y=1.04, x=0, bgcolor="rgba(0,0,0,0)"),
                xaxis=dict(title="Rooms", showgrid=True, gridcolor="rgba(128,128,128,.15)"),
                yaxis=dict(showgrid=False),
                hovermode="y unified",
            )
            st.plotly_chart(fig, use_container_width=True)

        # ── Avg time bar ──────────────────────────────────────────────────────
        st.markdown('<p class="sec">Average Working Time per Day</p>', unsafe_allow_html=True)
        df_t = df.sort_values("Avg Time", ascending=True)
        bar_c = [TEAL if t >= 330 else AMBER if t >= 250 else RED for t in df_t["Avg Time"]]
        fig_t = go.Figure(go.Bar(
            y=df_t["HK"], x=df_t["Avg Time"],
            orientation="h", marker_color=bar_c, opacity=.9,
            text=[f"{t}m" for t in df_t["Avg Time"]], textposition="outside",
            hovertemplate="<b>%{y}</b><br>Avg time: %{x} min/day<extra></extra>",
        ))
        fig_t.add_vline(x=380, line_dash="dot", line_color=RED,
                        annotation_text="380m cap", annotation_position="top right")
        fig_t.add_vline(x=330, line_dash="dash", line_color=AMBER,
                        annotation_text="330m min", annotation_position="bottom right")
        fig_t.update_layout(
            height=max(320, len(df_t) * 26 + 80),
            margin=dict(l=10,r=90,t=10,b=10),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter", size=12),
            xaxis=dict(range=[0,430], showgrid=True,
                       gridcolor="rgba(128,128,128,.15)", ticksuffix="m"),
            yaxis=dict(showgrid=False),
            showlegend=False,
        )
        st.plotly_chart(fig_t, use_container_width=True)

        # ── Table ─────────────────────────────────────────────────────────────
        st.markdown('<p class="sec">Detail Table</p>', unsafe_allow_html=True)
        max_time = max(int(df["Avg Time"].max()), 1)
        st.dataframe(
            df.rename(columns={"HK":"Housekeeper","FC":"FC Rooms","DS":"DS Rooms",
                                "DV":"DV Rooms","Total":"Total Rooms",
                                "Avg Time":"Avg Time/Day (min)","Days":"Days Active"}),
            use_container_width=True, hide_index=True,
            column_config={
                "Avg Time/Day (min)": st.column_config.ProgressColumn(
                    "Avg Time/Day", min_value=0, max_value=max_time, format="%d min"),
            }
        )

# ══════════════════════════════════════════════════════════════════════════════
#  INSPECTOR TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_insp:
    period_i = st.radio("Period", ["Today","This Week","This Month","All Time"],
                         horizontal=True, key="insp_p")
    snaps_i  = filter_log(period_i)
    insp_data= agg_insp(snaps_i)
    n_days_i = len(snaps_i)

    if not insp_data:
        st.info(f"No inspector data for {period_i}.")
    else:
        total_ir = sum(v["rooms"]  for v in insp_data.values())
        total_ig = sum(v["groups"] for v in insp_data.values())
        n_insps  = len(insp_data)
        avg_rpi  = total_ir // max(n_insps * n_days_i, 1)

        st.markdown(f"""<div class="kpi-row">
  <div class="kpi pu"><div class="val">{total_ir}</div>
    <div class="lbl">Rooms Inspected</div><div class="sub">{n_days_i} day(s)</div></div>
  <div class="kpi te"><div class="val">{total_ig}</div>
    <div class="lbl">Groups Inspected</div></div>
  <div class="kpi"><div class="val">{n_insps}</div>
    <div class="lbl">Active Inspectors</div></div>
  <div class="kpi am"><div class="val">{avg_rpi}</div>
    <div class="lbl">Avg Rooms/Inspector/Day</div></div>
</div>""", unsafe_allow_html=True)

        ROLE_COLORS = {"RQS1": AMBER, "RQS2": TEAL, "FC": PURPLE}
        ROLE_LABEL  = {"RQS1":"RQS1 – DV","RQS2":"RQS2 – DS","FC":"Full Clean"}

        rows_i = sorted([
            {"Inspector": nm,
             "Rooms":  v["rooms"],
             "Groups": v["groups"],
             "Role":   ROLE_LABEL.get(v["role"], v["role"]),
             "Days":   v["days"],
             "Avg/Day":v["rooms"] // max(v["days"], 1)}
            for nm, v in insp_data.items()
        ], key=lambda r: -r["Rooms"])
        df_i = pd.DataFrame(rows_i)

        st.markdown('<p class="sec">Rooms Inspected</p>', unsafe_allow_html=True)

        if df_i["Rooms"].sum() == 0:
            st.info("ℹ️ Inspector room counts are 0 for this period. "
                    "Re-generate the schedule and revisit to record accurate data.")
        else:
            df_ic = df_i.sort_values("Rooms", ascending=True)
            colors = [ROLE_COLORS.get(
                next((v["role"] for nm, v in insp_data.items() if nm == r), "FC"),
                PURPLE) for r in df_ic["Inspector"]]

            fig_i = go.Figure(go.Bar(
                y=df_ic["Inspector"], x=df_ic["Rooms"],
                orientation="h", marker_color=colors, opacity=.9,
                text=df_ic["Rooms"], textposition="outside",
                customdata=df_ic[["Groups","Role"]].values,
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Rooms inspected: %{x}<br>"
                    "Groups: %{customdata[0]}<br>"
                    "Role: %{customdata[1]}<extra></extra>"
                ),
            ))
            fig_i.update_layout(
                height=max(280, len(df_ic) * 30 + 80),
                margin=dict(l=10,r=60,t=10,b=10),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter", size=12),
                xaxis=dict(title="Rooms Inspected", showgrid=True,
                           gridcolor="rgba(128,128,128,.15)"),
                yaxis=dict(showgrid=False),
                showlegend=False,
            )
            # Role legend
            for role_key, col in ROLE_COLORS.items():
                fig_i.add_trace(go.Bar(
                    x=[None], y=[None], orientation="h",
                    name=ROLE_LABEL.get(role_key, role_key),
                    marker_color=col, showlegend=True,
                ))
            fig_i.update_layout(
                legend=dict(orientation="h", y=1.06, x=0, bgcolor="rgba(0,0,0,0)"),
            )
            st.plotly_chart(fig_i, use_container_width=True)

        st.markdown('<p class="sec">Detail Table</p>', unsafe_allow_html=True)
        max_r = max(int(df_i["Rooms"].max()), 1)
        st.dataframe(
            df_i.rename(columns={"Inspector":"Inspector","Rooms":"Rooms Inspected",
                                  "Groups":"Groups","Role":"Role",
                                  "Days":"Days Active","Avg/Day":"Avg Rooms/Day"}),
            use_container_width=True, hide_index=True,
            column_config={
                "Rooms Inspected": st.column_config.ProgressColumn(
                    "Rooms Inspected", min_value=0, max_value=max_r, format="%d"),
            }
        )

# ══════════════════════════════════════════════════════════════════════════════
#  DAILY LOG TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_log:
    st.markdown('<p class="sec">Schedule History</p>', unsafe_allow_html=True)
    for snap in sorted(log, key=lambda s:s.get("date",""), reverse=True):
        d        = snap.get("date","")
        is_today = d == str(today)
        n_rooms  = snap.get("total_rooms",0)
        n_groups = snap.get("n_groups",0)
        n_hks    = len(snap.get("hk",{}))
        n_insps  = len(snap.get("inspectors",{}))
        label    = f"{'📍 TODAY  ' if is_today else ''}📅 {d}  ·  {n_rooms} rooms  ·  {n_groups} groups  ·  {n_hks} HKs  ·  {n_insps} inspectors"

        with st.expander(label, expanded=is_today):
            c1, c2 = st.columns(2)
            with c1:
                if snap.get("hk"):
                    st.markdown("**Housekeepers**")
                    st.dataframe(pd.DataFrame([
                        {"Name":k, "FC":v.get("rooms_fc",0), "DS":v.get("rooms_ds",0),
                         "DV":v.get("rooms_dv",0), "Total":v.get("rooms",0),
                         "Time (min)":v.get("time",0)}
                        for k,v in snap["hk"].items()
                    ]).sort_values("Total", ascending=False),
                    use_container_width=True, hide_index=True)
            with c2:
                if snap.get("inspectors"):
                    st.markdown("**Inspectors**")
                    st.dataframe(pd.DataFrame([
                        {"Name":k, "Rooms":v.get("rooms",0),
                         "Groups":v.get("groups",0), "Role":v.get("role","")}
                        for k,v in snap["inspectors"].items()
                    ]).sort_values("Rooms", ascending=False),
                    use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
#  MANAGE TAB
# ══════════════════════════════════════════════════════════════════════════════
with tab_manage:
    st.markdown('<p class="sec">Data Management</p>', unsafe_allow_html=True)
    m1, m2 = st.columns(2)
    with m1:
        st.markdown("**📥 Export as CSV**")
        all_rows = []
        for snap in log:
            for hk, s in snap.get("hk", {}).items():
                all_rows.append({"Date":snap["date"],"Type":"HK","Name":hk,
                    "Time":s.get("time",0),"Total Rooms":s.get("rooms",0),
                    "FC Rooms":s.get("rooms_fc",0),"DS Rooms":s.get("rooms_ds",0),
                    "DV Rooms":s.get("rooms_dv",0)})
            for nm, s in snap.get("inspectors", {}).items():
                all_rows.append({"Date":snap["date"],"Type":"Inspector","Name":nm,
                    "Rooms Inspected":s.get("rooms",0),
                    "Groups":s.get("groups",0),"Role":s.get("role","")})
        if all_rows:
            csv = pd.DataFrame(all_rows).to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Download CSV", data=csv,
                               file_name="schedule_history.csv", mime="text/csv",
                               use_container_width=True)
    with m2:
        if auth.can("can_delete_data"):
            st.markdown("**🗑 Delete a Day**")
            del_date = st.selectbox("Date", ["— select —"] + all_dates)
            if st.button("Delete", type="secondary") and del_date != "— select —":
                db.delete_snapshot(del_date)
                get_log.clear()
                st.success(f"Deleted {del_date}. Refresh to update.")
        else:
            st.info("🔒 Only admins can delete data.")
    st.caption(f"Records: {len(log)} day(s) · Schema v2")