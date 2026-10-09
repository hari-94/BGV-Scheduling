"""
Health — is everything that runs the morning actually running?

The app leans on a chain of things outside it: the office PC's agent, SSRS,
the OneDrive-synced SharePoint files, a Power Automate flow that saves the
Arrival Report, HotSOS, and Supabase underneath all of it. Any one of them
can stop quietly -- a PC asleep, a sign-in expired after 90 days, a file not
syncing -- and the first anyone hears of it is a wrong morning.

This page reads what each part last reported and says, part by part, OK /
look at this / broken, in words, with what to do. It refreshes itself every
fifteen seconds. Underneath is the agent's own running log.

Everything here is read from app_settings; the page changes nothing.
"""
import datetime as _dt
import html
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, clock, db, ui          # noqa: E402
import hotsos_sync as hs            # noqa: E402

st.set_page_config(page_title="Stats", page_icon="📊", layout="wide")
st.markdown("""<style>
.block-container{max-width:min(1200px,97%);}
[data-testid='stSidebarNav']{display:none!important;}
.hl-banner{border-radius:14px;padding:14px 18px;margin:4px 0 16px;font-size:.95rem;font-weight:600}
.hl-ok{background:#ecf7ee;color:#05603a;border:1px solid #b7e4c4}
.hl-warn{background:#fff8eb;color:#7a4a00;border:1px solid #f6d58e}
.hl-bad{background:#fdecec;color:#9b1c1c;border:1px solid #f5b5b5}
.hl-card{background:#fff;border:1px solid #e6e9ee;border-radius:14px;padding:12px 14px;
         margin-bottom:12px;min-height:118px;border-left-width:5px}
.hl-card.ok{border-left-color:#0ca30c}.hl-card.warn{border-left-color:#fab219}
.hl-card.bad{border-left-color:#d03b3b}.hl-card.idle{border-left-color:#c3c8d0}
.hl-title{font-weight:700;color:#16202e;font-size:.92rem;display:flex;justify-content:space-between}
.hl-state{font-size:.72rem;font-weight:700;padding:1px 8px;border-radius:999px}
.ok .hl-state{background:#ecf7ee;color:#05603a}.warn .hl-state{background:#fff4d6;color:#7a4a00}
.bad .hl-state{background:#fdecec;color:#9b1c1c}.idle .hl-state{background:#f2f3f5;color:#5b6675}
.hl-main{font-size:.86rem;color:#1f2733;margin-top:6px}
.hl-sub{font-size:.76rem;color:#5b6675;margin-top:4px;line-height:1.45}
.hl-fix{font-size:.76rem;color:#7a4a00;margin-top:6px}
.bad .hl-fix{color:#9b1c1c}
.hl-log{background:#fff;border:1px solid #e6e9ee;border-radius:12px;overflow:hidden}
.hl-line{padding:5px 12px;font-size:.78rem;border-bottom:1px solid #f0f2f5;display:flex;gap:12px}
.hl-line:last-child{border-bottom:none}
.hl-line .t{color:#7b8798;min-width:64px;font-family:'DM Mono',monospace}
.hl-line.err{background:#fdf3f3;color:#9b1c1c}
.hl-next{font-size:.82rem;color:#1f2733;line-height:1.8}
</style>""", unsafe_allow_html=True)
auth.require_login()
ui.topnav("Stats")
if not auth.can("can_view_dashboard"):
    st.error("Stats are for RQS and admins.")
    st.stop()

e = html.escape
ICON = {"ok": "✓ OK", "warn": "! Check", "bad": "✕ Down", "idle": "· Waiting"}


def _t(stamp):
    try:
        t = _dt.datetime.fromisoformat(stamp)
        return t if t.tzinfo else t.replace(tzinfo=clock.MTN)
    except Exception:
        return None


def _age(stamp):
    t = _t(stamp)
    return None if t is None else (clock.now() - t).total_seconds()


def _ago(stamp):
    a = _age(stamp)
    if a is None:
        return "never"
    if a < 90:
        return f"{int(a)} s ago"
    if a < 5400:
        return f"{int(a // 60)} min ago"
    if a < 48 * 3600:
        return f"{a / 3600:.1f} h ago"
    return f"{int(a // 86400)} days ago"


def _when(stamp):
    t = _t(stamp)
    if not t:
        return "—"
    t = t.astimezone(clock.MTN)
    day = "today" if t.date() == clock.today() else (
        "tomorrow" if t.date() == clock.today() + _dt.timedelta(days=1) else f"{t:%a %b %d}")
    return f"{day} {t:%I:%M %p}".replace(" 0", " ")


def card(state, title, main, sub="", fix=""):
    return (f'<div class="hl-card {state}"><div class="hl-title"><span>{title}</span>'
            f'<span class="hl-state">{ICON[state]}</span></div>'
            f'<div class="hl-main">{main}</div>'
            + (f'<div class="hl-sub">{sub}</div>' if sub else "")
            + (f'<div class="hl-fix">→ {fix}</div>' if fix else "") + "</div>")


# ── the process, drawn ───────────────────────────────────────────────────────
# Where each step sits (x, y) on a 1180 x 330 canvas, and what it's called.
_NODES = {
    "email":  (20, 20,  "Front desk email", "Arrival Report"),
    "flow":   (200, 20, "Power Automate", "saves it to SharePoint"),
    "arr":    (380, 20, "Arrival Reports", "SharePoint folder"),
    "ssrs":   (20, 135, "SSRS", "Housekeeping Dashboard"),
    "staff":  (20, 250, "Schedule.xlsx", "staff roster"),
    "agent":  (380, 135, "Office PC", "agent"),
    "build":  (560, 135, "5 AM build", "app's Generate"),
    "sheet":  (740, 135, "Daily sheet", "GC8 Daily Schedule"),
    "push":   (920, 135, "Edit → Push", "RQS, when final"),
    "hotsos": (1020, 250, "HotSOS", "room assignments"),
    "db":     (560, 250, "App database", "Supabase"),
    "app":    (740, 250, "App & phones", "charts · forecast"),
}
_EDGES = [("email", "flow"), ("flow", "arr"), ("arr", "agent"), ("ssrs", "agent"),
          ("staff", "agent"), ("agent", "build"), ("build", "sheet"), ("sheet", "push"),
          ("push", "hotsos"), ("agent", "db"), ("db", "app"), ("push", "db")]
_W, _H = 150, 60
_RANK = {"bad": 3, "warn": 2, "idle": 1, "ok": 0, "human": 0}
_COL = {"ok": "#0ca30c", "warn": "#e8a200", "bad": "#d03b3b", "idle": "#9aa3ae", "human": "#2a78d6"}
_WORD = {"ok": "OK", "warn": "Check", "bad": "Down", "idle": "Waiting", "human": "People"}


def flow_svg(state):
    """The morning as a diagram. Healthy links carry moving dots; a link out
    of (or into) a step that's down turns red, stops, and is crossed out --
    so where the chain is broken reads at a glance."""
    parts = []
    for a, b in _EDGES:
        ax, ay = _NODES[a][0] + _W, _NODES[a][1] + _H / 2
        bx, by = _NODES[b][0], _NODES[b][1] + _H / 2
        if b == "hotsos":                      # down from Push into HotSOS
            ax, ay = _NODES[a][0] + _W / 2 + 20, _NODES[a][1] + _H
            bx, by = _NODES[b][0] + _W / 2, _NODES[b][1]
            d = f"M{ax},{ay} C{ax},{ay + 50} {bx},{by - 50} {bx},{by}"
        elif a == "push" and b == "db":        # Push also updates the app's charts
            ax, ay = _NODES[a][0] + 20, _NODES[a][1] + _H
            bx, by = _NODES[b][0] + _W / 2, _NODES[b][1]
            d = f"M{ax},{ay} C{ax},{ay + 30} {bx},{by - 45} {bx},{by}"
        else:
            mx = (ax + bx) / 2
            d = f"M{ax},{ay} C{mx},{ay} {mx},{by} {bx},{by}"
        worst = max(state.get(a, "idle"), state.get(b, "idle"), key=lambda s: _RANK[s])
        cls = {"bad": "e-bad", "warn": "e-warn"}.get(worst, "e-ok")
        parts.append(f'<path class="edge {cls}" d="{d}"/>')
        if worst == "bad":
            cx, cy = (ax + bx) / 2, (ay + by) / 2
            parts.append(f'<g class="x"><circle cx="{cx}" cy="{cy}" r="9"/>'
                         f'<text x="{cx}" y="{cy + 4}">✕</text></g>')
    for k, (x, y, title, sub) in _NODES.items():
        s = state.get(k, "idle")
        col = _COL[s]
        pulse = ' class="pulse"' if s == "bad" else ""
        parts.append(
            f'<g{pulse}><rect x="{x}" y="{y}" width="{_W}" height="{_H}" rx="12" '
            f'fill="#ffffff" stroke="{col}" stroke-width="{3 if s in ("bad", "warn") else 2}"/>'
            f'<circle cx="{x + 16}" cy="{y + 18}" r="5" fill="{col}"/>'
            f'<text class="nt" x="{x + 28}" y="{y + 22}">{html.escape(title)}</text>'
            f'<text class="ns" x="{x + 14}" y="{y + 41}">{html.escape(sub)}</text>'
            f'<text class="nw" x="{x + _W - 10}" y="{y + 52}" fill="{col}" '
            f'text-anchor="end">{_WORD[s]}</text></g>')
    # Returned as a self-contained SVG image: st.html sanitises inline <svg>
    # away, but an <img> of an SVG keeps its own <style> -- animations included.
    svg = ("""<svg xmlns="http://www.w3.org/2000/svg" class="pf" viewBox="0 0 1190 330"
 font-family="DM Sans, Segoe UI, Helvetica, Arial, sans-serif"><style>
.pf{background:#fff}
.pf .edge{fill:none;stroke-width:2.5;stroke-linecap:round}
.pf .e-ok{stroke:#86b6ef;stroke-dasharray:6 8;animation:pf-run 1.1s linear infinite}
.pf .e-warn{stroke:#e8a200;stroke-dasharray:6 8;animation:pf-run 2.6s linear infinite}
.pf .e-bad{stroke:#d03b3b;stroke-dasharray:3 6}
@keyframes pf-run{to{stroke-dashoffset:-28}}
.pf .x circle{fill:#d03b3b}.pf .x text{fill:#fff;font-size:11px;font-weight:700;text-anchor:middle}
.pf .nt{font-size:13px;font-weight:700;fill:#16202e}
.pf .ns{font-size:10.5px;fill:#5b6675}.pf .nw{font-size:10.5px;font-weight:700}
.pf .pulse rect{animation:pf-pulse 1.4s ease-in-out infinite}
@keyframes pf-pulse{0%,100%{stroke-opacity:1}50%{stroke-opacity:.25}}
@media (prefers-reduced-motion:reduce){.pf .edge,.pf .pulse rect{animation:none}}
</style><rect width="1190" height="330" fill="#ffffff"/>"""
           + "".join(parts) + "</svg>")
    import base64
    data = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return (f'<img src="data:image/svg+xml;base64,{data}" alt="The morning process, step by '
            f'step, with the health of each step" style="width:100%;height:auto;'
            f'border:1px solid #e6e9ee;border-radius:14px;background:#fff"/>')

st.markdown("## 📊 Stats")

# ── live panel: the free plan's three limits, and the floor's pulse ──────────
import calendar                      # noqa: E402
import plotly.graph_objects as go    # noqa: E402
import freetier                      # noqa: E402
import roomstatus as _rs             # noqa: E402

DARK_INK, DARK_INK2, DARK_GRID = "#e6edf7", "#9fb0c7", "#1e2a3d"
# Categorical slots 1-3 of the reference palette, dark steps -- validated on
# this panel's surface (#0b1220): lightness, chroma, CVD and contrast all pass.
C_APP, C_PC, C_FC = "#3987e5", "#d95926", "#199e70"
# Status, reserved for state: the same green / amber / red as the cards below.
S_OK, S_WARN, S_BAD = "#0ca30c", "#fab219", "#d03b3b"

st.markdown("""<style>
.st-key-pulse{background:radial-gradient(1100px 420px at 8% 0%,#15274a 0%,#0b1220 62%);
  border:1px solid #1e2a3d;border-radius:18px;padding:16px 18px 8px;margin:6px 0 18px}
.st-key-pulse [data-testid="stMarkdownContainer"] p,
.st-key-pulse [data-testid="stCaptionContainer"] p{color:#9fb0c7}
.pl-head{display:flex;align-items:center;gap:10px;font-family:'Syne',sans-serif;
  font-size:1.08rem;font-weight:700;color:#e6edf7}
.pl-dot{width:10px;height:10px;border-radius:50%;background:#22c55e;
  box-shadow:0 0 0 0 rgba(34,197,94,.7);animation:pl 1.6s infinite}
@keyframes pl{0%{box-shadow:0 0 0 0 rgba(34,197,94,.7)}
  70%{box-shadow:0 0 0 10px rgba(34,197,94,0)}100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}}
@media (prefers-reduced-motion:reduce){.pl-dot{animation:none}}
.pl-sub{color:#9fb0c7;font-size:.78rem;margin:2px 0 10px}
.pl-sec{color:#e6edf7;font-weight:700;font-size:.86rem;margin:10px 0 0}
.pl-note{color:#9fb0c7;font-size:.74rem;margin:-4px 0 10px;line-height:1.5}
</style>""", unsafe_allow_html=True)

_CFG = {"displayModeBar": False, "responsive": True}


def _dark(fig, height, legend=False):
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(family="DM Sans, sans-serif", size=11,
                                                color=DARK_INK2),
        showlegend=legend, bargap=0.3, barcornerradius=4, hovermode="x unified",
        hoverlabel=dict(bgcolor="#111b2e", bordercolor=DARK_GRID, font=dict(color=DARK_INK)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(color=DARK_INK)))
    fig.update_xaxes(showgrid=False, linecolor=DARK_GRID, tickfont=dict(color=DARK_INK2),
                     fixedrange=True, automargin=True)
    fig.update_yaxes(gridcolor=DARK_GRID, zeroline=False, tickfont=dict(color=DARK_INK2),
                     fixedrange=True, automargin=True)
    return fig


def _waiting(fig, text):
    """An empty chart says why it's empty instead of showing bare axes."""
    fig.add_annotation(text=text, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(color=DARK_INK2, size=12))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _gauge(value, limit, title, unit):
    value = float(value or 0)
    pct = value / limit
    col = S_BAD if pct >= freetier.ACT else S_WARN if pct >= freetier.WARN else S_OK
    state = "near the limit" if pct >= freetier.ACT else "worth watching" if pct >= freetier.WARN \
        else "comfortable"
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value,
        number={"suffix": f" {unit}", "valueformat": ",.0f" if value >= 10 else ",.1f",
                "font": {"color": DARK_INK, "size": 26}},
        title={"text": f"{title}<br><span style='font-size:11px;color:{DARK_INK2}'>"
                       f"{pct:.1%} of the {limit:,.0f} {unit} free plan · {state}</span>",
               "font": {"color": DARK_INK, "size": 13}},
        gauge={"axis": {"range": [0, limit], "tickcolor": DARK_INK2,
                        "tickfont": {"color": DARK_INK2, "size": 9}},
               "bar": {"color": col, "thickness": 0.32}, "bgcolor": "#111b2e",
               "borderwidth": 0,
               "steps": [{"range": [0, limit * freetier.WARN], "color": "#13213a"},
                         {"range": [limit * freetier.WARN, limit * freetier.ACT],
                          "color": "#2a2416"},
                         {"range": [limit * freetier.ACT, limit], "color": "#2d1618"}],
               "threshold": {"line": {"color": S_BAD, "width": 2}, "thickness": 0.85,
                             "value": limit * freetier.ACT}}))
    fig.update_layout(height=200, margin=dict(l=22, r=22, t=56, b=4),
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(color=DARK_INK))
    return fig


@st.fragment(run_every=30)
def live_stats():
    ft = db._load_key(freetier.STATUS_KEY) or {}
    month = freetier.month_usage()
    daily = freetier.daily_usage()
    mem = db._load_key(freetier.USAGE_PREFIX + "memory_app") or {}
    sync = db._load_key(getattr(hs, "STATUS_SYNC_KEY", "hotsos_status_sync")) or {}
    rooms = db.get_room_statuses() or {}
    now = clock.now()
    days_in = calendar.monthrange(now.year, now.month)[1]

    with st.container(key="pulse"):
        st.markdown(f'<div class="pl-head"><span class="pl-dot"></span>Live · free plan and '
                    f'the floor</div><div class="pl-sub">Refreshes every 30 seconds · '
                    f'{now:%I:%M:%S %p}'.replace(" 0", " ") + '</div>', unsafe_allow_html=True)

        # 1. the three free-plan limits
        g1, g2, g3 = st.columns(3)
        dbm = ft.get("db_mb") or {}
        g1.plotly_chart(_gauge(dbm.get("total", 0), freetier.DB_LIMIT_MB, "Database", "MB"),
                        config=_CFG, use_container_width=True, key="g_db")
        g1.markdown(f'<div class="pl-note">Measured nightly at 2 AM'
                    + (f' — last {_when(ft.get("at"))}' if ft.get("at") else
                       " — first measurement tonight") + "</div>", unsafe_allow_html=True)
        used = month.get("total", 0.0)
        pace = used / max(now.day - 1 + now.hour / 24, 0.25) * days_in
        g2.plotly_chart(_gauge(used, freetier.EGRESS_LIMIT_MB, f"Data sent · {now:%B}", "MB"),
                        config=_CFG, use_container_width=True, key="g_eg")
        g2.markdown(f'<div class="pl-note">At this pace ≈ {pace:,.0f} MB by month end '
                    f'({pace / freetier.EGRESS_LIMIT_MB:.0%}). Estimated from every read, '
                    f'erring high.</div>', unsafe_allow_html=True)
        g3.plotly_chart(_gauge(mem.get("now_mb", 0), freetier.MEMORY_LIMIT_MB, "App memory", "MB"),
                        config=_CFG, use_container_width=True, key="g_mem")
        g3.markdown(f'<div class="pl-note">Peak today {mem.get("peak_mb", 0):,.0f} MB'
                    + (f' · caches cleared {_when(mem.get("caches_cleared"))}'
                       if mem.get("caches_cleared") else "")
                    + ' · drops caches by itself past 85%</div>', unsafe_allow_html=True)

        # 2. data sent per day, by who sent for it; and memory through the day
        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="pl-sec">Data sent per day</div>', unsafe_allow_html=True)
            dates = sorted({d for src in daily.values() for d in src})
            fig = go.Figure()
            for src, col, name in (("app", C_APP, "Cloud app"), ("agent", C_PC, "Office PC"),
                                   ("forecast", C_FC, "Forecast")):
                if src in daily:
                    fig.add_bar(x=dates, y=[daily[src].get(d, 0) for d in dates], name=name,
                                marker=dict(color=col, line=dict(color="#0b1220", width=2)),
                                hovertemplate="%{y:.1f} MB")
            budget = freetier.EGRESS_LIMIT_MB / days_in
            top = max([sum(daily.get(s_, {}).get(d_, 0) for s_ in daily) for d_ in dates] or [0])
            # The budget line only where it can be seen beside the bars; far
            # above them it flattens real use to nothing, so it's said instead.
            if top >= budget * 0.2:
                fig.add_hline(y=budget, line=dict(color=DARK_INK2, dash="dot", width=1),
                              annotation_text=f"daily budget {budget:.0f} MB",
                              annotation_font_color=DARK_INK2, annotation_position="top left")
            fig.update_layout(barmode="stack")
            fig.update_xaxes(type="category")
            fig.update_yaxes(title_text="MB", title_font=dict(color=DARK_INK2))
            if not dates:
                _waiting(fig, "Counting starts with the next reads")
            st.plotly_chart(_dark(fig, 230, legend=bool(dates)), config=_CFG,
                            use_container_width=True, key="c_eg")
            st.markdown(f'<div class="pl-note">Daily budget on the free plan ≈ {budget:.0f} MB'
                        + (f' · busiest day so far {top:.1f} MB' if dates else "")
                        + '</div>', unsafe_allow_html=True)
        with c2:
            st.markdown('<div class="pl-sec">App memory today</div>', unsafe_allow_html=True)
            pts = [(_t(a), v) for a, v in (mem.get("samples") or []) if _t(a)]
            pts = [(t.astimezone(clock.MTN), v) for t, v in pts]
            pts = [(t, v) for t, v in pts if t.date() == now.date()]
            fig = go.Figure()
            if pts:
                fig.add_scatter(x=[t for t, _ in pts], y=[v for _, v in pts],
                                mode="lines+markers", marker=dict(size=5, color=C_APP),
                                line=dict(color=C_APP, width=2, shape="spline"), fill="tozeroy",
                                fillcolor="rgba(57,135,229,.18)", name="memory",
                                hovertemplate="%{y:.0f} MB")
            fig.add_hline(y=freetier.MEMORY_LIMIT_MB * freetier.ACT,
                          line=dict(color=S_BAD, dash="dot", width=1),
                          annotation_text="caches dropped above this",
                          annotation_font_color=DARK_INK2, annotation_position="top left")
            fig.update_yaxes(range=[0, freetier.MEMORY_LIMIT_MB], title_text="MB",
                             title_font=dict(color=DARK_INK2))
            if not pts:
                _waiting(fig, "Samples appear every 10 minutes while the app is in use")
            st.plotly_chart(_dark(fig, 230), config=_CFG, use_container_width=True, key="c_mem")

        # 3. the floor: rooms by HotSOS status, and finished through the day
        c3, c4 = st.columns(2)
        counts = {}
        for v in rooms.values():
            k = _rs.normalise(v.get("status"))
            counts[k] = counts.get(k, 0) + 1
        with c3:
            st.markdown(f'<div class="pl-sec">Rooms right now · {len(rooms)} from HotSOS</div>',
                        unsafe_allow_html=True)
            order = sorted(counts, key=lambda k: (_rs.rank(k), k))
            fig = go.Figure(go.Bar(
                y=[_rs.label(k) for k in order], x=[counts[k] for k in order], orientation="h",
                marker=dict(color=[_rs.colours(k)[0] for k in order],
                            line=dict(color="#0b1220", width=2)),
                text=[counts[k] for k in order], textposition="outside",
                textfont=dict(color=DARK_INK), hovertemplate="%{y}: %{x}<extra></extra>"))
            fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
            fig.update_layout(hovermode="closest")
            st.plotly_chart(_dark(fig, 250), config=_CFG, use_container_width=True, key="c_rooms")
        with c4:
            st.markdown('<div class="pl-sec">Finished through the day</div>',
                        unsafe_allow_html=True)
            fig = go.Figure()
            for col_name, colr, name in (("cleaned_at", C_APP, "Cleaned"),
                                         ("inspected_at", C_FC, "Inspected")):
                ts = sorted(t for t in (_t(v.get(col_name)) for v in rooms.values()) if t)
                ts = [t for t in (x.astimezone(clock.MTN) for x in ts) if t.date() == now.date()]
                if ts:
                    fig.add_scatter(x=ts, y=list(range(1, len(ts) + 1)), mode="lines",
                                    line=dict(color=colr, width=2, shape="hv"), name=name,
                                    hovertemplate=f"{name}: %{{y}}")
            fig.update_yaxes(title_text="rooms", title_font=dict(color=DARK_INK2),
                             range=[0, max(len(rooms), 1)])
            st.plotly_chart(_dark(fig, 250, legend=True), config=_CFG,
                            use_container_width=True, key="c_done")

        # 4. the HotSOS mirror's pulse, and the nightly clean-up
        c5, c6 = st.columns([3, 2])
        with c5:
            hist = sync.get("history") or []
            st.markdown('<div class="pl-sec">HotSOS mirror · changes picked up per 2-minute '
                        'pass</div>', unsafe_allow_html=True)
            fig = go.Figure(go.Bar(
                x=[_t(h.get("at")) for h in hist], y=[h.get("changed", 0) for h in hist],
                width=[60_000] * len(hist),               # a minute wide: a pulse, not a block
                marker=dict(color=[S_BAD if h.get("error") else C_APP for h in hist]),
                hovertemplate="%{y} rooms changed<extra></extra>"))
            if not hist:
                _waiting(fig, "The pulse starts with the office PC's next passes")
            st.plotly_chart(_dark(fig, 170), config=_CFG, use_container_width=True, key="c_sync")
            st.markdown(f'<div class="pl-note">Last pass {_ago(sync.get("at"))}'
                        + (" · <b style='color:#f87171'>error</b>" if sync.get("error") else "")
                        + " · red bars are passes that failed</div>", unsafe_allow_html=True)
        with c6:
            st.markdown('<div class="pl-sec">Nightly clean-up</div>', unsafe_allow_html=True)
            cl = ft.get("cleanup") or {}
            if cl:
                gone = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in
                                 (cl.get("deleted") or {}).items() if v) or "nothing was due"
                st.markdown(
                    f'<div class="pl-note" style="margin-top:6px">{_when(ft.get("at"))}: '
                    f'{html.escape(gone)}. {len(cl.get("archived") or [])} file(s) copied to '
                    f'SharePoint first, in <b>App Archive</b> beside the inspection workbooks.'
                    + (" Retention was halved: the database is past 60%." if cl.get("pressure")
                       else "")
                    + (f"<br><b style='color:#f87171'>Problems:</b> "
                       f"{html.escape('; '.join(cl.get('errors'))[:240])}" if cl.get("errors")
                       else "") + "</div>", unsafe_allow_html=True)
            else:
                st.markdown('<div class="pl-note" style="margin-top:6px">Runs at 2 AM on the '
                            'office PC: old data is copied to SharePoint, checked, then '
                            'removed.</div>', unsafe_allow_html=True)


live_stats()
st.caption("Every part of the morning, as it last reported. Refreshes every 15 seconds.")


@st.fragment(run_every=30)          # 30 s, not 15: every refresh is free-plan transfer
def health():
    try:
        beat = db._load_key(hs.HEARTBEAT_KEY) or {}
        hl = db._load_key(hs.HEALTH_KEY) or {}
        fc = db._load_key(hs.FORECAST_KEY) or {}
        rs = db._load_key(hs.ROSTER_STATUS_KEY) or {}
        build = db._load_key("daily_build_status") or {}
        ahead = db._load_key("daily_build_status_ahead") or {}
        last = db._load_key(hs.LAST_KEY) or {}
        cur = db._load_key(hs.RESULT_KEY) or {}
        att = db._load_key("hotsos_attendants") or {}
        events = (db._load_key(hs.EVENTS_KEY) or {}).get("events") or []
        sched = db.load_full_schedule() or {}
        db_ok, db_err = True, ""
    except Exception as ex:
        db_ok, db_err = False, str(ex)
        beat = hl = fc = rs = build = ahead = last = cur = att = sched = {}
        events = []

    now = clock.now()
    today = clock.today_iso()
    tomorrow = (clock.today() + _dt.timedelta(days=1)).isoformat()
    cards = []

    # ── the office PC ───────────────────────────────────────────────────────
    a = _age(beat.get("at"))
    if a is not None and a < 180:
        cards.append(card("ok", "Office PC agent", f"<b>{e(beat.get('host', ''))}</b> is running",
                          f"checked in {_ago(beat.get('at'))} · up since {_when(hl.get('started_at'))}"))
    elif a is not None and a < 900:
        cards.append(card("warn", "Office PC agent", f"Quiet for {_ago(beat.get('at'))}",
                          "It checks in every minute.", "If this lasts, check the PC is awake."))
    else:
        cards.append(card("bad", "Office PC agent", f"Not heard from {_ago(beat.get('at'))}",
                          "Nothing below can update: forecast, roster sync, 5 AM build, pushes.",
                          "Wake the office PC and log in; the agent starts on its own."))

    # ── database ────────────────────────────────────────────────────────────
    cards.append(card("ok", "App database", "Supabase answering", "app_settings and schedules readable")
                 if db_ok else card("bad", "App database", "Supabase not answering", e(db_err[:160]),
                                    "Check the Supabase project is up."))

    # ── SSRS forecast ───────────────────────────────────────────────────────
    a = _age(fc.get("pulled_at"))
    in_hours = 8 <= now.hour <= 21
    limit = 2.5 * 3600 if in_hours else 12 * 3600
    if a is not None and a < limit:
        cards.append(card("ok", "SSRS forecast", f"Pulled {_ago(fc.get('pulled_at'))}",
                          f"{len(fc.get('days') or [])} days · next pull {_when((hl.get('next') or {}).get('forecast'))}"))
    else:
        cards.append(card("warn" if a and a < 2 * limit else "bad", "SSRS forecast",
                          f"Last pulled {_ago(fc.get('pulled_at'))}", "Should refresh every 2 hours, 8 AM–8 PM.",
                          "Press Refresh on the Forecast page; if it fails, check this PC can open SSRS."))

    # ── staff schedule sync ─────────────────────────────────────────────────
    f = ((hl.get("files") or {}).get("Schedule.xlsx") or {})
    if rs.get("error"):
        cards.append(card("bad", "Staff schedule sync", "Last import failed", e(rs["error"][:200]),
                          "Open Schedule.xlsx and check it saves; the next save retries."))
    elif not f.get("exists"):
        cards.append(card("bad", "Staff schedule sync", "Schedule.xlsx not on the office PC",
                          "The SharePoint Schedules folder isn't syncing.",
                          "Open OneDrive on the office PC and check it's signed in and syncing."))
    else:
        waiting = _t(f.get("modified")) and _t(rs.get("at")) and \
            (_t(f["modified"]) - _t(rs["at"])).total_seconds() > 300
        cards.append(card("warn" if waiting else "ok", "Staff schedule sync",
                          "Saved changes not imported yet" if waiting else "Up to date",
                          f"Schedule.xlsx saved {_when(f.get('modified'))} · last import "
                          f"{_when(rs.get('at')) if rs.get('at') else '—'}"
                          + (f" ({rs.get('changed_cells', 0)} cells)" if rs.get("at") else ""),
                          "It imports a minute after the file stops changing." if waiting else ""))

    # ── today's 5 AM build ──────────────────────────────────────────────────
    if build.get("date") == today and build.get("status") == "done":
        arr_ok = bool(build.get("arrival"))
        dv = build.get("dv_unassigned")
        st_ = "ok" if arr_ok and not dv else "warn"
        cards.append(card(st_, "Today's 5 AM sheet",
                          f"Tab <b>{e(str(build.get('tab')))}</b> · {build.get('rooms')} rooms, "
                          f"{build.get('charts')} charts",
                          f"built {_when(build.get('finished_at'))} by {e(str(build.get('by')))} · "
                          + ("Arrival Report ✓" if arr_ok else "no Arrival Report")
                          + (f" · {dv} Dust n Vac rooms without RQS 2" if dv else ""),
                          "" if st_ == "ok" else
                          ("Add notes by hand / check the flow. " if not arr_ok else "")
                          + ("Fill RQS 2 on the Dust n Vac rows." if dv else "")))
    elif build.get("date") == today and build.get("status") == "error":
        cards.append(card("bad", "Today's 5 AM sheet", "Build failed", e(str(build.get("error"))[:220]),
                          "Press “Build today's sheet” on the HotSOS page, or build in the app."))
    elif now.hour < 5:
        cards.append(card("idle", "Today's 5 AM sheet", "Not yet — builds at 5:00 AM"))
    elif not build or build.get("status") == "test":
        # Never built for real yet: the morning run is new, not broken.
        cards.append(card("idle", "Today's 5 AM sheet", "First run tomorrow at 5:00 AM",
                          "The morning build hasn't run for real yet."))
    else:
        cards.append(card("bad", "Today's 5 AM sheet", "Not built today",
                          "The 5 AM run didn't happen (PC off or asleep at 5?).",
                          "Press “Build today's sheet” on the HotSOS page."))

    # ── tomorrow's look-ahead ───────────────────────────────────────────────
    if ahead.get("date") == tomorrow and ahead.get("status") == "done":
        cards.append(card("ok", "Tomorrow's draft", f"Tab <b>{e(str(ahead.get('tab')))}</b> · "
                          f"{ahead.get('rooms')} rooms, {ahead.get('charts')} charts",
                          f"built {_when(ahead.get('finished_at'))} · refreshed at 5 AM with the "
                          "Arrival Report unless edited"))
    elif ahead.get("date") == tomorrow and ahead.get("status") == "error":
        cards.append(card("warn", "Tomorrow's draft", "Look-ahead failed", e(str(ahead.get("error"))[:200])))
    else:
        cards.append(card("idle", "Tomorrow's draft", "Not built", "Built at 5 AM on the day."))

    # ── Arrival Report flow ─────────────────────────────────────────────────
    reps = hl.get("arrival_reports") or {}
    t_rep, n_rep = reps.get(today), reps.get(tomorrow)
    if n_rep:
        cards.append(card("ok", "Arrival Report (Power Automate)", f"Tomorrow's report is in",
                          f"{e(n_rep['name'])} · received {_when(n_rep.get('modified'))}"))
    elif t_rep:
        late = now.hour >= 23
        cards.append(card("warn" if late else "ok", "Arrival Report (Power Automate)",
                          "Today's report received" + ("; tomorrow's not yet" if late else ""),
                          f"{e(t_rep['name'])} · received {_when(t_rep.get('modified'))} · "
                          "tomorrow's usually arrives the night before",
                          "If it was sent, check the flow's run history in Power Automate." if late else ""))
    else:
        cards.append(card("warn", "Arrival Report (Power Automate)", "No report for today or tomorrow",
                          "The 5 AM sheet is built without late checkouts and room notes.",
                          "Check the email reached your inbox, then the flow's run history "
                          "(an expired sign-in shows as “Unauthorized”)."))

    # ── HotSOS ──────────────────────────────────────────────────────────────
    if cur.get("status") == "error":
        cards.append(card("bad", "HotSOS", f"Last {e(str(cur.get('mode')))} failed",
                          e(str(cur.get("error"))[:200]),
                          "If it's a sign-in problem, re-run setup on the office PC."))
    elif last:
        cards.append(card("ok", "HotSOS", f"Last {e(last.get('mode', ''))}: {_when(last.get('finished_at'))}",
                          f"{e(str(last.get('tab', '')))} · "
                          + (f"{last.get('sent', 0)} rooms sent · " if last.get("mode") == "push" else "")
                          + f"{len(att.get('attendants') or [])} attendants known, list from "
                          f"{_when(att.get('pulled_at'))}"))
    else:
        cards.append(card("idle", "HotSOS", "No preview or push yet"))

    # ── room statuses mirrored from HotSOS ──────────────────────────────────
    sync = db._load_key(getattr(hs, "STATUS_SYNC_KEY", "hotsos_status_sync")) or {}
    _hour = clock.now().hour
    _sa = _age(sync.get("at"))
    if sync.get("error"):
        cards.append(card("bad", "Room status from HotSOS", "Last read failed",
                          e(str(sync["error"])[:200]),
                          "Usually a HotSOS sign-in hiccup; it retries every 2 minutes."))
    elif not sync.get("at"):
        cards.append(card("idle", "Room status from HotSOS", "Not read yet",
                          "Every 2 minutes from 6 AM to 8 PM."))
    elif 6 <= _hour < 20 and _sa and _sa > 10 * 60:
        cards.append(card("warn", "Room status from HotSOS", f"Last read {_ago(sync.get('at'))}",
                          "Should be every 2 minutes during the day."))
    else:
        _c = sync.get("counts") or {}
        cards.append(card("ok", "Room status from HotSOS", f"Read {_ago(sync.get('at'))}",
                          f"{sync.get('rooms', 0)} rooms · "
                          + " · ".join(f"{v} {k.replace('_', ' ')}" for k, v in
                                       sorted(_c.items(), key=lambda x: -x[1])[:4])
                          + (f" · new HotSOS state: {e(', '.join(sync['unknown']))}"
                             if sync.get("unknown") else "")))

    # ── synced files ────────────────────────────────────────────────────────
    files = hl.get("files") or {}
    missing = [n for n, v in files.items() if not (v or {}).get("exists")
               and n != "GC8 Daily Schedule.xlsx"]
    lines = " · ".join(f"{e(n)}: {'✓ ' + _when(v.get('modified')) if (v or {}).get('exists') else '—'}"
                       for n, v in files.items())
    cards.append(card("bad" if missing else "ok", "SharePoint files on the office PC",
                      "All synced" if not missing else f"Missing: {e(', '.join(missing))}", lines,
                      "Check OneDrive is signed in and syncing on the office PC." if missing else ""))

    # ── the app's own schedule ──────────────────────────────────────────────
    g = sched.get("groups_data") or []
    if g:
        upd = sched.get("updated_from_sheet_at")
        cards.append(card("ok", "Today's charts in the app", f"{len(g)} charts",
                          f"made by {e(str(sched.get('generated_by')))}"
                          + (f" · matched to the pushed sheet {_when(upd)}" if upd else
                             " · not yet matched to a pushed sheet")))
    else:
        cards.append(card("warn" if now.hour >= 6 else "idle", "Today's charts in the app",
                          "No schedule for today yet", "Phones (My Rooms) have nothing to show.",
                          "Generate on the Schedule page, or wait for the 5 AM build."))

    # ── banner, cards, what's next, log ─────────────────────────────────────
    states = [c.split('"hl-card ')[1].split('"')[0] for c in cards]
    bad, warn = states.count("bad"), states.count("warn")
    if bad:
        st.markdown(f'<div class="hl-banner hl-bad">✕ {bad} part{"s" if bad > 1 else ""} down'
                    + (f", {warn} to check" if warn else "") + "</div>", unsafe_allow_html=True)
    elif warn:
        st.markdown(f'<div class="hl-banner hl-warn">! Everything is running — {warn} '
                    f'thing{"s" if warn > 1 else ""} to check</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="hl-banner hl-ok">✓ Everything is running</div>',
                    unsafe_allow_html=True)
    # The cards are made in a fixed order; name them for the diagram.
    # (The room-status mirror's card sits after HotSOS's; adding it without
    # naming it here broke this page on 9 Oct.)
    (agent_s, db_s, ssrs_s, sync_s, build_s, _ahead_s, arr_s, hot_s, mirror_s,
     files_s, app_s) = states
    _sev = {"bad": 3, "warn": 2, "ok": 1}
    hotsos_s = max((hot_s, mirror_s), key=lambda x: _sev.get(x, 0))
    st.markdown(flow_svg({
        "email": arr_s, "flow": arr_s, "arr": files_s, "ssrs": ssrs_s, "staff": sync_s,
        "agent": agent_s, "build": build_s, "sheet": build_s, "push": "human",
        "hotsos": hotsos_s, "db": db_s, "app": app_s}), unsafe_allow_html=True)
    st.caption("Moving lines: data flowing normally · amber: worth a look · red ✕: broken "
               "there — see that step's card below.")
    cols = st.columns(3)
    for i, c in enumerate(cards):
        cols[i % 3].markdown(c, unsafe_allow_html=True)

    nxt = hl.get("next") or {}
    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown("#### Next up")
        st.markdown(f'<div class="hl-next">📈 Forecast pull · {_when(nxt.get("forecast"))}<br>'
                    f'📄 Morning sheet build · {_when(nxt.get("build"))}<br>'
                    f'🔄 Schedule.xlsx · on every save<br>'
                    f'📧 Arrival Report · when the front desk sends it</div>',
                    unsafe_allow_html=True)
    with c2:
        st.markdown("#### Office PC log")
        if not events:
            st.caption("No log lines yet.")
        else:
            rows = []
            for ev in reversed(events[-25:]):
                t = _t(ev.get("at"))
                ts = t.astimezone(clock.MTN).strftime("%H:%M") if t else ""
                if t and t.date() != clock.today():
                    ts = t.astimezone(clock.MTN).strftime("%a %H:%M")
                cls = " err" if ev.get("level") == "error" else ""
                rows.append(f'<div class="hl-line{cls}"><span class="t">{ts}</span>'
                            f'<span>{e(ev.get("msg", ""))}</span></div>')
            st.markdown('<div class="hl-log">' + "".join(rows) + "</div>", unsafe_allow_html=True)


health()
