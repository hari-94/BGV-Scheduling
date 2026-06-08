"""
Dashboard — Cleaning Schedule Performance Tracker
"""
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

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
st.markdown("""""", unsafe_allow_html=True)

for _k,_v in [("logged_in",False),("username",""),("role",""),
              ("groups_data",None),("total_rooms",0),("inspectors_data",[])]:
    if _k not in st.session_state: st.session_state[_k] = _v

auth.init_auth()
if not st.session_state.get("logged_in"):
    st.warning("🔒 Please sign in from the main page.")
    st.stop()
if not auth.can("can_view_dashboard"):
    st.error("⛔ Dashboard requires RQS or Admin role.")
    st.stop()
if not PLOTLY_OK:
    st.error("Install plotly: `pip install plotly`")
    st.stop()

with st.sidebar:
    st.markdown("### 🧭 Navigation")
    st.markdown("---")
    _u = st.session_state.get("username","")
    _r = st.session_state.get("role","")
    if _u: st.caption(f"Signed in as **{_u}** · {_r.title()}")

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
*{box-sizing:border-box;} html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.block-container{padding-top:1.4rem!important;max-width:1440px;}

/* MOBILE RESPONSIVE */
@media (max-width: 768px) {
  .block-container{padding-left:.6rem!important;padding-right:.6rem!important;max-width:100%!important;}
  [data-testid="stHorizontalBlock"]{flex-direction:column!important;}
  [data-testid="stHorizontalBlock"] > [data-testid="column"]{width:100%!important;flex:1 1 100%!important;min-width:100%!important;}
}
.pg-title{font-size:1.6rem;font-weight:800;letter-spacing:-.6px;
  background:linear-gradient(135deg,#1e293b,#3B4FE4);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin:0 0 2px}
.pg-sub{font-size:.82rem;color:#64748b;margin:0 0 .6rem}
.sec{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.12em;
     color:#94a3b8;padding-bottom:4px;border-bottom:1.5px solid #f1f5f9;margin:.9rem 0 .5rem}
.kpi-row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:1rem}
.kpi{flex:1 1 130px;background:#fff;border:1px solid #e8edf5;border-radius:14px;padding:14px;
     box-shadow:0 2px 8px rgba(0,0,0,.05)}
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

# ── Snapshot builder ───────────────────────────────────────────────────────────
def build_snapshot(fg, total_rms, inspectors):
    hk_snap = {}
    insp_snap = {}
    for g in fg:
        hk  = g.get("housekeeper","")
        svc = g.get("service_type","")
        if not hk or hk == "Manager":
            continue
        if hk not in hk_snap:
            hk_snap[hk] = {"time":0,"rooms":0,"rooms_fc":0,"rooms_ds":0,"rooms_dv":0}
        room_list = g.get("rooms",[])
        n = len(room_list)
        hk_snap[hk]["time"]  += g.get("time",0)
        hk_snap[hk]["rooms"] += n
        if svc == "Full Clean":
            hk_snap[hk]["rooms_fc"] += n
        elif svc == "Daily Service":
            hk_snap[hk]["rooms_ds"] += n
        elif svc == "Dust n Vac":
            hk_snap[hk]["rooms_dv"] += n
    for insp in inspectors:
        nm = insp.get("name","")
        if not nm:
            continue
        labels = set(insp.get("groups",[]))
        n_rooms = sum(len(g.get("rooms",[])) for g in fg if g.get("label") in labels)
        insp_snap[nm] = {
            "rooms":   n_rooms,
            "groups":  len(labels),
            "role":    insp.get("role","FC"),
            "buildings": insp.get("buildings",[]),
        }
    return {
        "date":        str(date.today()),
        "total_rooms": total_rms,
        "n_groups":    len(fg),
        "hk":          hk_snap,
        "inspectors":  insp_snap,
        "saved_by":    st.session_state.get("username","unknown"),
        "schema_v":    2,
    }

@st.cache_data(ttl=30)
def get_log():
    try:    return db.load_log()
    except Exception as ex: st.error(f"DB: {ex}"); return []

fg         = st.session_state.get("groups_data")
total_rms  = st.session_state.get("total_rooms",0)
inspectors = st.session_state.get("inspectors_data",[])
if fg:
    try:
        db.save_snapshot(build_snapshot(fg,total_rms,inspectors))
        get_log.clear()
    except Exception:
        pass

log = get_log()

st.markdown('<p class="pg-title">📊 Performance Dashboard</p>', unsafe_allow_html=True)
st.markdown('<p class="pg-sub">Daily · weekly · monthly metrics</p>', unsafe_allow_html=True)

if not log:
    st.info("💡 No data yet. Generate a schedule on the main page first.")
    st.stop()

today     = date.today()
all_dates = sorted({s.get("date","") for s in log if s.get("date")}, reverse=True)

def filter_log(p):
    if p == "Today":      return [s for s in log if s.get("date") == str(today)]
    if p == "This Week":
        c = str(today - timedelta(days=today.weekday()))
        return [s for s in log if s.get("date","") >= c]
    if p == "This Month":
        c = str(today.replace(day=1))
        return [s for s in log if s.get("date","") >= c]
    return log

def agg_hk(snaps):
    out = {}
    for snap in snaps:
        for hk,s in snap.get("hk",{}).items():
            if hk not in out:
                out[hk]={"time":0,"rooms":0,"rooms_fc":0,"rooms_ds":0,"rooms_dv":0,"days":0}
            out[hk]["time"]     += s.get("time",0)
            out[hk]["rooms"]    += s.get("rooms",0)
            out[hk]["rooms_fc"] += s.get("rooms_fc",0)
            out[hk]["rooms_ds"] += s.get("rooms_ds",0)
            out[hk]["rooms_dv"] += s.get("rooms_dv",0)
            out[hk]["days"]     += 1
    return out

def agg_insp(snaps):
    out = {}
    for snap in snaps:
        sv = snap.get("schema_v",1)
        for nm,s in snap.get("inspectors",{}).items():
            rooms = s.get("rooms",0)
            if sv < 2 and rooms == s.get("groups",0)*10:
                rooms = 0
            if nm not in out:
                out[nm]={"rooms":0,"groups":0,"role":"","days":0}
            out[nm]["rooms"]  += rooms
            out[nm]["groups"] += s.get("groups",0)
            out[nm]["role"]    = s.get("role","FC")
            out[nm]["days"]   += 1
    return out

tab_hk, tab_insp, tab_log, tab_manage = st.tabs([
    "🧑‍🔧 Housekeepers","🔍 Inspectors","📅 Daily Log","🗂 Manage"])

# ── HK tab ────────────────────────────────────────────────────────────────────
with tab_hk:
    p = st.radio("Period",["Today","This Week","This Month","All Time"],horizontal=True,key="hkp")
    snaps = filter_log(p)
    hkd   = agg_hk(snaps)
    nd    = len(snaps)

    if not hkd:
        st.info(f"No data for {p}.")
    else:
        tfc = sum(v["rooms_fc"] for v in hkd.values())
        tds = sum(v["rooms_ds"] for v in hkd.values())
        tdv = sum(v["rooms_dv"] for v in hkd.values())
        tot = tfc+tds+tdv
        nh  = len(hkd)
        avt = sum(v["time"] for v in hkd.values())//max(nh*nd,1)

        st.markdown(f"""<div class="kpi-row">
  <div class="kpi pu"><div class="val">{tot}</div><div class="lbl">Total Rooms</div>
    <div class="sub">{nd} day(s)</div></div>
  <div class="kpi bl"><div class="val">{tfc}</div><div class="lbl">Full Clean</div></div>
  <div class="kpi te"><div class="val">{tds}</div><div class="lbl">Daily Service</div></div>
  <div class="kpi am"><div class="val">{tdv}</div><div class="lbl">Dust &amp; Vac</div></div>
  <div class="kpi"><div class="val">{nh}</div><div class="lbl">Active HKs</div></div>
  <div class="kpi"><div class="val">{avt}m</div><div class="lbl">Avg Time/Day</div></div>
</div>""", unsafe_allow_html=True)

        rows = sorted([{"HK":hk,"FC":v["rooms_fc"],"DS":v["rooms_ds"],"DV":v["rooms_dv"],
                         "Total":v["rooms"],"Avg Time":v["time"]//max(v["days"],1),"Days":v["days"]}
                        for hk,v in hkd.items()], key=lambda r:-r["Total"])
        df = pd.DataFrame(rows)

        st.markdown('<p class="sec">Rooms Cleaned by Service Type</p>', unsafe_allow_html=True)
        if df["Total"].sum() == 0:
            st.info("ℹ️ No room data yet. Generate a schedule and revisit.")
        else:
            dfc = df.sort_values("Total",ascending=True)
            fig = go.Figure()
            fig.add_trace(go.Bar(name="Full Clean",y=dfc["HK"],x=dfc["FC"],orientation="h",
                marker_color=BLUE,text=[str(v) if v>0 else "" for v in dfc["FC"]],
                textposition="inside",hovertemplate="<b>%{y}</b> FC: %{x}<extra></extra>"))
            fig.add_trace(go.Bar(name="Daily Service",y=dfc["HK"],x=dfc["DS"],orientation="h",
                marker_color=TEAL,text=[str(v) if v>0 else "" for v in dfc["DS"]],
                textposition="inside",hovertemplate="<b>%{y}</b> DS: %{x}<extra></extra>"))
            fig.add_trace(go.Bar(name="Dust & Vac",y=dfc["HK"],x=dfc["DV"],orientation="h",
                marker_color=AMBER,text=[str(v) if v>0 else "" for v in dfc["DV"]],
                textposition="inside",hovertemplate="<b>%{y}</b> DV: %{x}<extra></extra>"))
            fig.update_layout(barmode="stack",height=max(300,len(dfc)*26+80),
                margin=dict(l=10,r=60,t=30,b=10),
                plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter",size=12),
                legend=dict(orientation="h",y=1.04,x=0),
                xaxis=dict(title="Rooms",showgrid=True,gridcolor="rgba(128,128,128,.15)"),
                yaxis=dict(showgrid=False),hovermode="y unified")
            st.plotly_chart(fig, use_container_width=True)

        st.markdown('<p class="sec">Average Working Time per Day</p>', unsafe_allow_html=True)
        dft = df.sort_values("Avg Time",ascending=True)
        bc  = [TEAL if t>=330 else AMBER if t>=250 else RED for t in dft["Avg Time"]]
        ft  = go.Figure(go.Bar(y=dft["HK"],x=dft["Avg Time"],orientation="h",
            marker_color=bc,opacity=.9,text=[f"{t}m" for t in dft["Avg Time"]],
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>%{x} min/day<extra></extra>"))
        ft.add_vline(x=380,line_dash="dot",line_color=RED,annotation_text="380m cap")
        ft.add_vline(x=330,line_dash="dash",line_color=AMBER,annotation_text="330m min")
        ft.update_layout(height=max(300,len(dft)*26+80),margin=dict(l=10,r=90,t=10,b=10),
            plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter",size=12),showlegend=False,
            xaxis=dict(range=[0,430],showgrid=True,gridcolor="rgba(128,128,128,.15)",ticksuffix="m"),
            yaxis=dict(showgrid=False))
        st.plotly_chart(ft, use_container_width=True)

        st.markdown('<p class="sec">Detail Table</p>', unsafe_allow_html=True)
        mxt = max(int(df["Avg Time"].max()),1)
        st.dataframe(df.rename(columns={"HK":"Housekeeper","FC":"FC Rooms","DS":"DS Rooms",
            "DV":"DV Rooms","Total":"Total Rooms","Avg Time":"Avg Time/Day (min)","Days":"Days Active"}),
            use_container_width=True, hide_index=True,
            column_config={"Avg Time/Day (min)":st.column_config.ProgressColumn(
                "Avg Time/Day",min_value=0,max_value=mxt,format="%d min")})

# ── Inspector tab ─────────────────────────────────────────────────────────────
with tab_insp:
    pi  = st.radio("Period",["Today","This Week","This Month","All Time"],horizontal=True,key="ip")
    si  = filter_log(pi)
    id_ = agg_insp(si)
    ndi = len(si)

    if not id_:
        st.info(f"No data for {pi}.")
    else:
        tir = sum(v["rooms"]  for v in id_.values())
        tig = sum(v["groups"] for v in id_.values())
        ni  = len(id_)
        ari = tir//max(ni*ndi,1)

        st.markdown(f"""<div class="kpi-row">
  <div class="kpi pu"><div class="val">{tir}</div><div class="lbl">Rooms Inspected</div>
    <div class="sub">{ndi} day(s)</div></div>
  <div class="kpi te"><div class="val">{tig}</div><div class="lbl">Groups Inspected</div></div>
  <div class="kpi"><div class="val">{ni}</div><div class="lbl">Active Inspectors</div></div>
  <div class="kpi am"><div class="val">{ari}</div><div class="lbl">Avg Rooms/Insp/Day</div></div>
</div>""", unsafe_allow_html=True)

        RCOL = {"RQS1":AMBER,"RQS2":TEAL,"FC":PURPLE}
        RLBL = {"RQS1":"RQS1","RQS2":"RQS2","FC":"Full Clean"}
        ri   = sorted([{"Inspector":nm,"Rooms":v["rooms"],"Groups":v["groups"],
                         "Role":RLBL.get(v["role"],v["role"]),"Days":v["days"],
                         "Avg/Day":v["rooms"]//max(v["days"],1)}
                        for nm,v in id_.items()], key=lambda r:-r["Rooms"])
        dfi  = pd.DataFrame(ri)

        st.markdown('<p class="sec">Rooms Inspected</p>', unsafe_allow_html=True)
        if dfi["Rooms"].sum() == 0:
            st.info("ℹ️ Inspector room counts are 0. Re-generate the schedule and revisit.")
        else:
            dic = dfi.sort_values("Rooms",ascending=True)
            cr  = [RCOL.get(next((v["role"] for nm,v in id_.items() if nm==r),"FC"),PURPLE)
                   for r in dic["Inspector"]]
            fi2 = go.Figure(go.Bar(y=dic["Inspector"],x=dic["Rooms"],orientation="h",
                marker_color=cr,opacity=.9,text=dic["Rooms"],textposition="outside",
                customdata=dic[["Groups","Role"]].values,
                hovertemplate="<b>%{y}</b><br>Rooms: %{x}<br>Groups: %{customdata[0]}<br>Role: %{customdata[1]}<extra></extra>"))
            fi2.update_layout(height=max(280,len(dic)*30+80),margin=dict(l=10,r=60,t=10,b=10),
                plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter",size=12),showlegend=False,
                xaxis=dict(title="Rooms Inspected",showgrid=True,gridcolor="rgba(128,128,128,.15)"),
                yaxis=dict(showgrid=False))
            st.plotly_chart(fi2, use_container_width=True)

        mxr = max(int(dfi["Rooms"].max()),1)
        st.dataframe(dfi,use_container_width=True,hide_index=True,
            column_config={"Rooms":st.column_config.ProgressColumn(
                "Rooms Inspected",min_value=0,max_value=mxr,format="%d")})

# ── Daily Log tab ─────────────────────────────────────────────────────────────
with tab_log:
    st.markdown('<p class="sec">Schedule History</p>', unsafe_allow_html=True)
    for snap in sorted(log, key=lambda s:s.get("date",""), reverse=True):
        d = snap.get("date","")
        is_today = (d == str(today))
        nr=snap.get("total_rooms",0); ng=snap.get("n_groups",0)
        nh2=len(snap.get("hk",{})); ni2=len(snap.get("inspectors",{}))
        lbl = f"{'📍 TODAY  ' if is_today else ''}📅 {d}  ·  {nr} rooms  ·  {ng} groups  ·  {nh2} HKs  ·  {ni2} inspectors"
        with st.expander(lbl, expanded=is_today):
            c1,c2 = st.columns(2)
            with c1:
                if snap.get("hk"):
                    st.markdown("**Housekeepers**")
                    st.dataframe(pd.DataFrame([
                        {"Name":k,"FC":v.get("rooms_fc",0),"DS":v.get("rooms_ds",0),
                         "DV":v.get("rooms_dv",0),"Total":v.get("rooms",0),"Time":v.get("time",0)}
                        for k,v in snap["hk"].items()
                    ]).sort_values("Total",ascending=False),use_container_width=True,hide_index=True)
            with c2:
                if snap.get("inspectors"):
                    st.markdown("**Inspectors**")
                    st.dataframe(pd.DataFrame([
                        {"Name":k,"Rooms":v.get("rooms",0),"Groups":v.get("groups",0),"Role":v.get("role","")}
                        for k,v in snap["inspectors"].items()
                    ]).sort_values("Rooms",ascending=False),use_container_width=True,hide_index=True)

# ── Manage tab ────────────────────────────────────────────────────────────────
with tab_manage:
    st.markdown('<p class="sec">Data Management</p>', unsafe_allow_html=True)
    m1,m2 = st.columns(2)
    with m1:
        st.markdown("**📥 Export as CSV**")
        ar = []
        for snap in log:
            for hk,s in snap.get("hk",{}).items():
                ar.append({"Date":snap["date"],"Type":"HK","Name":hk,
                    "Time":s.get("time",0),"Total":s.get("rooms",0),
                    "FC":s.get("rooms_fc",0),"DS":s.get("rooms_ds",0),"DV":s.get("rooms_dv",0)})
            for nm,s in snap.get("inspectors",{}).items():
                ar.append({"Date":snap["date"],"Type":"Inspector","Name":nm,
                    "Rooms":s.get("rooms",0),"Groups":s.get("groups",0),"Role":s.get("role","")})
        if ar:
            csv = pd.DataFrame(ar).to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Download CSV",data=csv,
                file_name="schedule_history.csv",mime="text/csv",use_container_width=True)
    with m2:
        if auth.can("can_delete_data"):
            st.markdown("**🗑 Delete a Day**")
            dd = st.selectbox("Date",["— select —"]+all_dates)
            if st.button("Delete",type="secondary") and dd != "— select —":
                db.delete_snapshot(dd); get_log.clear()
                st.success(f"Deleted {dd}. Refresh to update.")
        else:
            st.info("🔒 Only admins can delete data.")
    st.caption(f"Records: {len(log)} day(s)")
