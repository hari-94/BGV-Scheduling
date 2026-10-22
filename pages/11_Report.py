"""
Report — who inspected and who cleaned how many rooms, beside the days the
staff schedule had them on.

The rooms come from the team's own record, GC8 Inspections (one tab a day),
which the office PC reads at 4 PM and whenever somebody presses Sync
(report_data, hotsos_agent.sync_report). The days come from the staff
schedule the app already holds. Managers only, as Stats is.

Nothing here touches a workbook. The page writes two things: a sync request
for the office PC, and its own name fixes (report_data.NAMES_KEY).
"""
import datetime as _dt
import hashlib
import html
import json
import os
import sys
import uuid

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, clock, db, ui            # noqa: E402
import fresh                        # noqa: E402
import hotsos_sync as hs              # noqa: E402
import report_data as rd              # noqa: E402
import report_table                   # noqa: E402

# A running app keeps the report_data it imported first -- a deploy doesn't
# reload an imported module (CLAUDE.md) -- and this page calls what later
# versions added. An old copy is reloaded rather than crashing the page.
if getattr(rd, "VERSION", 0) < 3:
    import importlib
    rd = importlib.reload(rd)

st.set_page_config(page_title="Report", page_icon="📋", layout="wide")
st.markdown("""<style>
.block-container{max-width:min(1200px,97%);}
[data-testid='stSidebarNav']{display:none!important;}
.rp-h1{font-size:1.55rem;font-weight:800;color:#16202e;margin:0;line-height:1.2}
.rp-src{font-size:.8rem;color:#5b6675;margin:3px 0 0}
.rp-badges{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 4px}
.rp-b{font-size:.72rem;font-weight:600;padding:3px 10px;border-radius:999px;background:#e8f6ec;
      color:#11692f;border:1px solid #c6ebd1}
.rp-b.warn{background:#fff6e5;color:#7a4b00;border-color:#f6d9a0}
.rp-badges [data-tip]{position:relative;cursor:help;outline:none}
.rp-badges [data-tip]:hover::after,.rp-badges [data-tip]:focus::after{content:attr(data-tip);
  position:absolute;top:calc(100% + 7px);left:0;z-index:40;width:300px;white-space:pre-line;
  font-weight:500;font-size:.76rem;line-height:1.45;color:#1f2733;background:#fff;
  border:1px solid #d5dce6;border-radius:10px;padding:9px 11px;
  box-shadow:0 10px 26px rgba(16,26,42,.16)}
.rp-hint{font-size:.74rem;color:#7b8798;margin:2px 2px 0}
.rp-lo{font-size:.82rem;color:#1f2733;line-height:1.75}
.rp-lo b{color:#16202e}
</style>""", unsafe_allow_html=True)

# The tables are drawn inside the report_table component (components/
# report_table), which sorts them when a column name is clicked; their look
# goes with them, since a component's frame doesn't see the page's styles.
TABLE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700;9..40,800&display=swap');
html,body{margin:0;padding:0;background:transparent}
body{font-family:'DM Sans',system-ui,-apple-system,'Segoe UI',sans-serif;color:#1f2733;
     -webkit-font-smoothing:antialiased}
#root{padding:2px 2px 4px}
.rp-card{background:#fff;border:1px solid #e6e9ee;border-radius:16px;padding:14px 16px 8px;
         box-shadow:0 1px 2px rgba(16,26,42,.04)}
.rp-ct{font-size:1.12rem;font-weight:800;color:#16202e}
.rp-cs{font-size:.8rem;color:#5b6675;margin:2px 0 10px}
.rp-cs b{color:#16202e}
.rp-scroll{overflow-x:auto}
.rp-tab{min-width:1000px}
.rp-grid{display:grid;align-items:center;column-gap:8px}
.rp-hdr{background:#f3f6fa;border-radius:10px;padding:7px 8px;row-gap:3px}
.rp-hdr .h{font-size:.64rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
           color:#4b5667;text-align:right;line-height:1.25}
.rp-hdr .h.l{text-align:left}
.rp-hdr .h.s{cursor:pointer;user-select:none;border-radius:6px;padding:3px 4px;margin:-3px -4px;
             outline:none;transition:background .12s,color .12s}
.rp-hdr .h.s:hover,.rp-hdr .h.s:focus-visible{background:#e2e9f2;color:#16202e}
.rp-hdr .h.on{color:#1c4a78;background:#e8eff8}
.rp-hdr .h .ar{display:inline-block;margin-left:4px;font-size:.66rem;color:#aab3bf;letter-spacing:0}
/* What each number counts: rooms (blue) or days (green), under its name. */
.rp-hdr .uw{display:block;margin-top:3px;line-height:1}
.u{display:inline-block;padding:2px 5px;border-radius:5px;font-size:.55rem;font-weight:800;
   letter-spacing:.06em;text-transform:uppercase;line-height:1.1}
.u.r{background:#e3edfa;color:#1d5aa0}
.u.d{background:#e2f4e7;color:#156b37}
.u.rd{background:#eee9fb;color:#55369f}
.rp-units{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.74rem;color:#5b6675;margin:-4px 0 10px}
.rp-units .u{margin-right:5px}
.rp-hdr .h.on .ar{color:#2563a8}
.rp-hdr .g{font-size:.6rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
           color:#7b8798;text-align:center;border-bottom:1px solid #d5dce6;padding-bottom:3px}
details.rp-p{border-bottom:1px solid #eef1f5}
details.rp-p:last-child{border-bottom:none}
details.rp-p>summary{list-style:none;cursor:pointer;padding:7px 8px;border-radius:8px}
details.rp-p>summary::-webkit-details-marker{display:none}
details.rp-p>summary:hover{background:#f6f8fb}
details.rp-p[open]>summary{background:#eef4fb}
.rp-c{font-size:.84rem;color:#16202e;text-align:right;font-variant-numeric:tabular-nums;
      font-family:'DM Mono',ui-monospace,SFMono-Regular,Menlo,monospace}
.rp-c.z{color:#a9b1bd}
.rp-c.rk{color:#7b8798}
.rp-c.nm{text-align:left;font-family:inherit;font-weight:600;display:flex;align-items:center;
         min-width:0}
/* A long name gives way, never the tag beside it. */
.rp-c.nm .nmt{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.rp-c.nm .rp-left{flex:none}
.rp-c.nm .chev{display:inline-block;flex:none;color:#9aa5b4;margin-left:6px;transition:transform .15s}
details[open] .chev{transform:rotate(90deg)}
.rp-bar{display:flex;align-items:center;gap:8px}
.rp-trk{flex:1;height:9px;background:#eef1f5;border-radius:5px;overflow:hidden}
.rp-fil{display:block;height:9px;background:#3b82d6;border-radius:5px}
.rp-bar b{min-width:48px;text-align:right;font-weight:700}
.rp-nc{display:inline-block;min-width:22px;padding:0 7px;border-radius:999px;background:#fdecec;
       color:#b42318;font-weight:700;text-align:center}
.rp-more{padding:10px 8px 16px 46px}
.rp-facts{display:flex;flex-wrap:wrap;gap:5px 20px;font-size:.8rem;color:#3b4554;margin-bottom:10px}
.rp-facts b{color:#16202e}
.rp-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.rp-k{background:#f7f9fc;border:1px solid #e6e9ee;border-radius:12px;padding:8px 10px}
.rp-k .kt{font-size:.68rem;font-weight:700;color:#5b6675;text-transform:uppercase;letter-spacing:.05em}
.rp-k .kv{font-size:1.15rem;font-weight:800;color:#16202e;margin:1px 0 2px}
.rp-k .kv small{font-size:.7rem;font-weight:600;color:#5b6675;margin-left:4px}
.rp-k .kl{font-size:.74rem;color:#3b4554;line-height:1.5}
.rp-k.empty{opacity:.5}
.rp-k .nc{color:#b42318;font-weight:700}
/* Someone who no longer works here: kept, for the record, but greyed. */
.rp-left{display:inline-block;margin-left:7px;padding:1px 7px;border-radius:999px;
         background:#eceff3;color:#5f6b7a;font-size:.64rem;font-weight:700;letter-spacing:.04em;
         text-transform:uppercase;vertical-align:1px}
.rp-left.soon{background:#fff3df;color:#8a5300}
details.rp-p.left>summary .rp-c{color:#8a94a3}
details.rp-p.left>summary .rp-c.nm{color:#5f6b7a}
details.rp-p.left .rp-fil{background:#b9c3cf}
details.rp-p.left .rp-nc{background:#f0f2f5;color:#8a94a3}
"""
auth.require_login()
fresh.latest("i18n", "ui")    # the menu as it is on disk, not as first loaded
ui.topnav("Report")
# Managers only, the same permission Stats uses: auth is an imported module and
# a running app keeps its old copy after a deploy, so no new permission name.
if not auth.can("can_manage_users"):
    st.error("The report is for managers.")
    st.stop()

e = html.escape
me = st.session_state.get("display_name") or auth.current_user().get("username", "")


def tip(text) -> str:
    """A note for a data-tip attribute. Its line breaks go in as &#10;: a
    blank line inside st.markdown's HTML ends the HTML block, and the rest of
    the table came out as text."""
    return e(text).replace("\n", "&#10;")


def _md5(obj) -> str:
    return hashlib.md5(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _t(stamp):
    try:
        t = _dt.datetime.fromisoformat(str(stamp))
        return t if t.tzinfo else t.replace(tzinfo=clock.MTN)
    except Exception:
        return None


def _when(stamp) -> str:
    t = _t(stamp)
    if not t:
        return "—"
    t = t.astimezone(clock.MTN)
    day = "today" if t.date() == clock.today() else f"{t:%a %b} {t.day}"
    return f"{day} at {t:%I:%M %p}".replace(" 0", " ").lower().replace("am", "AM").replace("pm", "PM")


def _d(iso) -> str:
    d = _dt.date.fromisoformat(iso)
    return f"{d:%b} {d.day}"


def _long(iso) -> str:
    d = _dt.date.fromisoformat(iso)
    return f"{d:%b} {d.day}, {d.year}"


def per_week(r, start, end):
    """(days a week, weeks counted): over the part of the period the person
    was on the schedule -- Luis M, gone on 14 Feb, isn't averaged over the
    whole year, nor someone hired in July over January."""
    cut = rd.active((res or {}).get("span", {}).get(r["person"]), start, end) or (start, end)
    weeks = max(rd.weeks_in(*cut), 1)
    return r.get("sched", 0) / weeks, weeks


def gone(p):
    """("Left" | "Leaving", their last day on the schedule) for someone marked
    as no longer working here, else None. "Leaving" while the schedule still
    has shifts for them ahead."""
    if p not in left:
        return None
    last_day = (res or {}).get("last_day", {}).get(p)
    soon = bool(last_day) and last_day > clock.today().isoformat()
    return ("Leaving" if soon else "Left"), last_day


# ── the numbers ──────────────────────────────────────────────────────────────
@st.cache_resource(max_entries=2, show_spinner="Counting every day on the sheet…")
def _built(sync_token, roster_token, names_token, _weeks, _ov, _fixes, _aliases):
    import roster_import as ri
    import staff_names
    days = rd.load_days(db)
    if not days:
        return None
    first, last = min(days), max(days)
    # The schedule as far ahead as it goes, for each person's last shift;
    # the counting itself stops at the last synced day.
    ahead = last
    for w in _weeks:
        try:
            ahead = max(ahead, (_dt.date.fromisoformat(w) + _dt.timedelta(days=6)).isoformat())
        except ValueError:
            pass
    roster, visiting = rd.roster_days(_weeks, _ov, first, ahead)
    directory = rd.Directory(list(roster), [a["label"] for a in staff_names.attendants()],
                             _aliases, _fixes, ri.NAME_ALIASES)
    span = rd.worked_span(roster, directory)
    roster = {n: {iso: v for iso, v in d.items() if iso <= last} for n, d in roster.items()}
    res = rd.build(days, roster, visiting, directory)
    res.update(first=first, last=last, names=directory.names, span=span,
               last_day={p: s[1] for p, s in span.items()},
               tabs={iso: d["tab"] for iso, d in days.items()})
    return res


# ── Timing: when each room was marked in HotSOS (report_timing) ──────────────
# Its own tab, HP 18 Oct: "so we know if someone is not marking in timely
# manner". It reads the HotSOS mirror, not the sheet, so it needs no sync.
import report_timing as rtm           # noqa: E402
if getattr(rtm, "VERSION", 0) < 2:
    import importlib
    rtm = importlib.reload(rtm)

TM_INK, TM_BLUE, TM_AMBER, TM_RED, TM_GREEN, TM_GREY = (
    "#16202e", "#3b82d6", "#d97706", "#c2452f", "#2f855a", "#9aa5b4")


@st.cache_data(ttl=120, max_entries=12, show_spinner="Reading the HotSOS marks…")
def _tm_marks(start_iso, end_iso):
    return rtm.load(db, _dt.date.fromisoformat(start_iso), _dt.date.fromisoformat(end_iso))


def _tm_axis(fig, lo, hi, now_min=None):
    """A time-of-day x axis, an hour a tick, with 10:00 and 3:30 marked."""
    ticks = list(range(int(lo // 60) * 60, int(hi) + 60, 60))
    for m in (600, 930):                  # carts roll; the floor done
        if lo <= m <= hi:
            fig.add_vline(x=m, line_dash="dash", line_color=TM_GREY, line_width=1.2)
    if now_min is not None and lo <= now_min <= hi:
        fig.add_vline(x=now_min, line_color=TM_RED, line_width=1.6, annotation_text="now",
                      annotation_position="top", annotation_font=dict(size=10, color=TM_RED))
    fig.update_xaxes(range=[lo, hi], tickvals=ticks, side="top",
                     ticktext=[rtm._clock(t) for t in ticks],
                     showgrid=True, gridcolor="rgba(128,138,150,.20)", zeroline=False)


def _tm_layout(fig, n_rows):
    fig.update_layout(
        barmode="overlay", bargap=.35, height=max(260, n_rows * 30 + 110),
        margin=dict(l=0, r=16, t=40, b=8),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", size=11, color=TM_INK),
        legend=dict(orientation="h", yanchor="top", y=-0.02, xanchor="left", x=0,
                    font=dict(size=11)),
        hoverlabel=dict(bgcolor=TM_INK, font_color="#fff", bordercolor=TM_INK))
    fig.update_yaxes(autorange="reversed", showgrid=False, ticklen=0, automargin=True,
                     tickfont=dict(family="DM Sans", size=13, color=TM_INK))


def _tm_hk_chart(recs, people, now):
    """One row per housekeeper: a bar from each room's start to its done."""
    import plotly.graph_objects as go
    order = [p["name"] for p in sorted(people, key=lambda p: (p["first"] is None, p["first"] or now))]
    xs = [x for x in recs if x["hk"] in order]
    today = now.date().isoformat()
    m = rtm._mins

    def bars(sel, name, colour, end_of=lambda x: m(x["done"])):
        sel = [x for x in sel if x["start"]]
        if not sel:
            return
        fig.add_trace(go.Bar(
            y=[x["hk"] for x in sel], x=[max(end_of(x) - m(x["start"]), 1) for x in sel],
            base=[m(x["start"]) for x in sel], orientation="h", name=name,
            marker=dict(color=colour, line=dict(color="#ffffff", width=1)),
            text=[x["room"] for x in sel], textposition="inside", insidetextanchor="middle",
            textfont=dict(size=9, color="#ffffff"), constraintext="inside",
            customdata=[[x["room"], x["service"] or "?", x["std"], rtm._hhmm(x["start"]),
                         rtm._hhmm(x["done"]) or "not yet", x["dur"] if x["dur"] is not None else "–",
                         x["rqs"] or "–", rtm._hhmm(x["inspected"]) or "not yet"] for x in sel],
            hovertemplate="<b>%{customdata[0]}</b> · %{customdata[1]} · %{customdata[2]} min<br>"
                          "started %{customdata[3]} · done %{customdata[4]} "
                          "(%{customdata[5]} min)<br>RQS %{customdata[6]} · inspected "
                          "%{customdata[7]}<extra></extra>"))

    fig = go.Figure()
    bars([x for x in xs if x["done"] and not x["together"] and not x["left_open"]],
         "Cleaning: start → done", TM_BLUE)
    bars([x for x in xs if x["left_open"]], "Left open: done tapped long after", TM_AMBER)
    bars([x for x in xs if x["start"] and not x["done"] and not x["inspected"]
          and x["date"] == today], "In progress", "#a9c8ee", end_of=lambda x: m(now))
    tog = [x for x in xs if x["together"]]
    if tog:
        fig.add_trace(go.Scatter(
            y=[x["hk"] for x in tog], x=[m(x["done"]) for x in tog], mode="markers",
            name="Marked together: start and done at once",
            marker=dict(symbol="x-thin", size=12, color=TM_RED, line=dict(width=2.4, color=TM_RED)),
            customdata=[[x["room"], x["service"] or "?", x["std"], rtm._hhmm(x["done"])] for x in tog],
            hovertemplate="<b>%{customdata[0]}</b> · %{customdata[1]} · %{customdata[2]} min<br>"
                          "start and done both at %{customdata[3]}<extra></extra>"))
    nod = [x for x in xs if x["no_done"]]
    if nod:
        fig.add_trace(go.Scatter(
            y=[x["hk"] for x in nod], x=[m(x["inspected"]) for x in nod], mode="markers",
            name="Inspected with no done mark",
            marker=dict(symbol="circle-open", size=10, color=TM_INK, line=dict(width=2)),
            customdata=[[x["room"], rtm._hhmm(x["inspected"]), x["rqs"] or "–"] for x in nod],
            hovertemplate="<b>%{customdata[0]}</b> · never marked done<br>inspected "
                          "%{customdata[1]} by %{customdata[2]}<extra></extra>"))
    # The housekeepers' own marks set the span; an inspection at 7pm would
    # squash their day into the left half.
    times = [m(t) for x in xs for t in (x["start"], x["done"]) if t] +             [m(x["inspected"]) for x in nod]
    if not times:
        return None
    now_min = m(now) if any(x["date"] == today for x in xs) else None
    hi = max(times + ([now_min] if now_min else []))
    _tm_axis(fig, min(times + [600]) - 15, hi + 15, now_min)
    fig.update_yaxes(categoryorder="array", categoryarray=order)
    _tm_layout(fig, len(order))
    return fig


def _tm_rqs_chart(recs, people):
    """One row per RQS: a dot per room at how long it waited, done to inspected."""
    import plotly.graph_objects as go
    order = [p["name"] for p in people]
    xs = [x for x in recs if x["rqs"] in order]
    fig = go.Figure()
    for lo, hi, name, colour in ((None, rtm.WAIT_SOON, f"Within {rtm.WAIT_SOON} min", TM_GREEN),
                                 (rtm.WAIT_SOON, rtm.WAIT_LATE,
                                  f"{rtm.WAIT_SOON}–{rtm.WAIT_LATE} min", TM_AMBER),
                                 (rtm.WAIT_LATE, None, f"Over {rtm.WAIT_LATE} min", TM_RED)):
        sel = [x for x in xs if x["wait"] is not None and (lo is None or x["wait"] > lo)
               and (hi is None or x["wait"] <= hi)]
        if not sel:
            continue
        fig.add_trace(go.Scatter(
            y=[x["rqs"] for x in sel], x=[x["wait"] for x in sel], mode="markers", name=name,
            marker=dict(size=10, color=colour, opacity=.85, line=dict(color="#ffffff", width=1.5)),
            customdata=[[x["room"], x["hk"] or "–", rtm._hhmm(x["done"]), rtm._hhmm(x["inspected"]),
                         x["wait"], x["date"]] for x in sel],
            hovertemplate="<b>%{customdata[0]}</b> · %{customdata[5]}<br>%{customdata[1]} done "
                          "%{customdata[2]} · inspected %{customdata[3]}<br>"
                          "<b>waited %{customdata[4]} min</b><extra></extra>"))
    still = [x for x in xs if x["waiting"] is not None]
    if still:
        fig.add_trace(go.Scatter(
            y=[x["rqs"] for x in still], x=[x["waiting"] for x in still], mode="markers",
            name="Done, still waiting now",
            marker=dict(symbol="circle-open", size=11, color=TM_RED, line=dict(width=2.2)),
            customdata=[[x["room"], x["hk"] or "–", rtm._hhmm(x["done"]), x["waiting"]] for x in still],
            hovertemplate="<b>%{customdata[0]}</b> · %{customdata[1]} done %{customdata[2]}<br>"
                          "<b>waiting %{customdata[3]} min so far</b><extra></extra>"))
    med = [p for p in people if p["median"] is not None]
    if med:
        fig.add_trace(go.Scatter(
            y=[p["name"] for p in med], x=[p["median"] for p in med], mode="markers",
            name="Median wait", marker=dict(symbol="line-ns", size=22, color=TM_INK,
                                            line=dict(width=3, color=TM_INK)),
            hovertemplate="%{y}: median %{x} min<extra></extra>"))
    waits = [x["wait"] for x in xs if x["wait"] is not None] + [x["waiting"] for x in still]
    if not waits:
        return None
    for v in (rtm.WAIT_SOON, rtm.WAIT_LATE):
        fig.add_vline(x=v, line_dash="dash", line_color=TM_GREY, line_width=1.2)
    fig.update_xaxes(range=[-5, max(waits + [rtm.WAIT_LATE]) + 10], side="top", dtick=30,
                     title=dict(text="minutes from done to inspected", font=dict(size=11)),
                     showgrid=True, gridcolor="rgba(128,138,150,.20)", zeroline=False)
    fig.update_yaxes(categoryorder="array", categoryarray=order)
    _tm_layout(fig, len(order))
    return fig


TM_CSS = """<style>
.tm-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px;margin:12px 0 10px}
.tm-k{background:#f7f9fc;border:1px solid #e6e9ee;border-radius:12px;padding:9px 12px}
.tm-k .kt{font-size:.68rem;font-weight:700;color:#5b6675;text-transform:uppercase;letter-spacing:.05em}
.tm-k .kv{font-size:1.3rem;font-weight:800;color:#16202e;margin:2px 0;font-variant-numeric:tabular-nums}
.tm-k .kv small{font-size:.72rem;font-weight:600;color:#5b6675;margin-left:5px}
.tm-k .kl{font-size:.74rem;color:#3b4554;line-height:1.45}
.tm-note{font-size:.76rem;color:#5b6675;margin:-6px 2px 10px}
</style>"""


def timing_tab():
    st.markdown(TM_CSS, unsafe_allow_html=True)
    st.markdown('<div class="rp-h1">⏱️ Timing</div><div class="rp-src">When each room was '
                'started, marked done and inspected, from <b>HotSOS</b> — the app copies its '
                'marks every two minutes, from 9 October · the RQS is the one typed on the '
                'GC8 Inspections sheet</div>', unsafe_allow_html=True)
    today = clock.today()
    c1, c2, c3 = st.columns([2.3, 2.2, 2.2], vertical_alignment="bottom")
    with c1:
        mode = st.segmented_control("Period", ["Day", "Last 7 days", "Date range"],
                                    default="Day", key="tm_mode") or "Day"
    with c2:
        if mode == "Day":
            start = end = st.date_input("Day", value=today, min_value=rtm.SINCE,
                                        max_value=today, key="tm_day", format="MM/DD/YYYY")
        elif mode == "Last 7 days":
            start, end = today - _dt.timedelta(days=6), today
            st.markdown(f'<div class="rp-src">{start:%b} {start.day} – {end:%b} {end.day}</div>',
                        unsafe_allow_html=True)
        else:
            rng = st.date_input("From – to", value=(today - _dt.timedelta(days=6), today),
                                min_value=rtm.SINCE, max_value=today, key="tm_rng",
                                format="MM/DD/YYYY")
            rng = rng if isinstance(rng, (list, tuple)) else (rng,)
            start, end = (rng[0], rng[-1]) if rng else (today, today)
    with c3:
        who = st.segmented_control("Show", ["Both", "RQS", "Housekeepers"], default="Both",
                                   key="tm_team") or "Both"
    rows, plan = _tm_marks(start.isoformat(), end.isoformat())
    now = clock.now()
    recs = rtm.rooms(rows, plan, now)
    one = start == end
    span = f"{start:%a %b} {start.day}" if one else f"{start:%b} {start.day} – {end:%b} {end.day}"
    if not recs:
        st.info(f"No HotSOS marks for {span}.")
        return
    hks, rqs = rtm.housekeepers(recs), rtm.inspectors(recs)

    timed = [x for x in recs if x["std"] > 0 and "dust" not in x["service"].lower()]
    n_tog = sum(1 for x in recs if x["together"])
    waits = [x["wait"] for x in recs if x["wait"] is not None]
    still = [x for x in recs if x["waiting"] is not None]
    firsts = [p["first_avg"] for p in hks if p["first_avg"] is not None]
    late_firsts = sum(p["late_starts"] for p in hks)
    import statistics as _stats
    cards = [
        ("Rooms marked done", f"{sum(1 for x in recs if x['done'] or x['inspected'])}"
                              f"<small>of {len(recs)}</small>", span),
        ("First start", rtm._clock(_stats.median(firsts)) if firsts else "–",
         f"median housekeeper · {late_firsts} after {rtm._hhmm(_dt.datetime.combine(today, rtm.FIRST_START_LATE))}"),
        ("Marked together", f"{n_tog}<small>{round(100 * n_tog / len(timed)) if timed else 0}%</small>",
         f"start and done within {rtm.TOGETHER_MIN} min — marked after the fact"),
        ("Wait for RQS", f"{round(_stats.median(waits)) if waits else '–'}<small>min median</small>",
         f"{sum(1 for w in waits if w > rtm.WAIT_LATE)} rooms waited over {rtm.WAIT_LATE} min"),
    ]
    if still:
        cards.append(("Waiting now", f"{len(still)}<small>rooms</small>",
                      f"done, not inspected · longest {max(x['waiting'] for x in still)} min"))
    st.markdown('<div class="tm-cards">' + "".join(
        f'<div class="tm-k"><div class="kt">{e(t)}</div><div class="kv">{v}</div>'
        f'<div class="kl">{e(s)}</div></div>' for t, v, s in cards) + "</div>",
        unsafe_allow_html=True)

    import pandas as pd
    if who in ("Both", "Housekeepers"):
        st.markdown(f"#### 🧹 Housekeepers · {span}")
        if one:
            fig = _tm_hk_chart(recs, hks, now)
            if fig is not None:
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False},
                                key="tm_hk_fig")
                st.markdown('<div class="tm-note">Dashed lines: carts roll at 10:00, the floor '
                            'done by 3:30. Hover a bar or a mark for the room.</div>',
                            unsafe_allow_html=True)
        hk_df = pd.DataFrame([{
            "Housekeeper": p["name"],
            **({"Days": p["days"]} if not one else {}),
            "Rooms": p["rooms"], "Done": p["done"],
            "First start": (rtm._hhmm(p["first"]) if one else rtm._clock(p["first_avg"]))
                           + (" ⚠" if p["late_starts"] else ""),
            **({"Late starts": p["late_starts"]} if not one else {"Last done": rtm._hhmm(p["last"])}),
            "Marked together": p["together"],
            "Together %": round(100 * p["together"] / p["timed"]) if p["timed"] else 0,
            "Left open": p["left_open"], "No done mark": p["no_done"],
            "Pace": round(100 * p["pace"]) if p["pace"] is not None else None,
        } for p in hks])
        st.dataframe(hk_df, hide_index=True, width="stretch", key="tm_hk_tab",
                     column_config={
                         "Together %": st.column_config.ProgressColumn(
                             "Together %", min_value=0, max_value=100, format="%d%%",
                             help="Share of their timed rooms marked start and done at once"),
                         "Pace": st.column_config.NumberColumn(
                             "Pace", format="%d%%",
                             help="Median minutes from start to done as a share of the room's "
                                  "minutes on the sheet (marked-together rooms left out)"),
                         "First start": st.column_config.TextColumn(
                             help=f"⚠ = after {rtm._hhmm(_dt.datetime.combine(today, rtm.FIRST_START_LATE))}"
                                  + ("" if one else " on at least one day; the time is their average")),
                         "Left open": st.column_config.NumberColumn(
                             help=f"Done pressed more than {rtm.LONG_OPEN:g}× the room's minutes "
                                  "after start"),
                         "No done mark": st.column_config.NumberColumn(
                             help="Inspected, but never marked done in HotSOS"),
                     })
    if who in ("Both", "RQS"):
        st.markdown(f"#### 🔍 RQS · {span}")
        fig = _tm_rqs_chart(recs, rqs)
        if fig is not None:
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False},
                            key="tm_rqs_fig")
        rq_df = pd.DataFrame([{
            "RQS": p["name"], **({"Days": p["days"]} if not one else {}),
            "Rooms done": p["ready"], "Inspected": p["inspected"],
            "Median wait": p["median"], "Longest": p["longest"],
            f"Over {rtm.WAIT_LATE} min": p["late"],
            **({"Waiting now": p["waiting"]} if still else {}),
            **({"Last inspection": rtm._hhmm(p["last"])} if one else {}),
        } for p in rqs])
        st.dataframe(rq_df, hide_index=True, width="stretch", key="tm_rq_tab",
                     column_config={
                         "Median wait": st.column_config.NumberColumn(
                             format="%d min", help="Minutes from the housekeeper's done to inspected"),
                         "Longest": st.column_config.NumberColumn(format="%d min"),
                         "Rooms done": st.column_config.NumberColumn(
                             help="Their rooms marked done (or inspected) by a housekeeper"),
                     })

    with st.expander(f"Every room · {span} ({len(recs)})"):
        flags = lambda x: " · ".join(f for f, on in (
            ("marked together", x["together"]), ("left open", x["left_open"]),
            ("no done mark", x["no_done"]),
            (f"waited {x['wait']} min", x["wait"] is not None and x["wait"] > rtm.WAIT_LATE),
            (f"waiting {x['waiting']} min", x["waiting"] is not None)) if on)
        st.dataframe(pd.DataFrame([{
            "Day": x["date"], "Room": x["room"], "Service": x["service"], "Minutes": x["std"] or None,
            "Housekeeper": x["hk"], "Started": rtm._hhmm(x["start"]), "Done": rtm._hhmm(x["done"]),
            "Took": x["dur"], "RQS": x["rqs"], "Inspected": rtm._hhmm(x["inspected"]),
            "Waited": x["wait"], "Flags": flags(x)} for x in sorted(
                recs, key=lambda x: (x["date"], x["hk"], x["start"] or now))]),
            hide_index=True, width="stretch", key="tm_all_tab",
            column_config={"Took": st.column_config.NumberColumn(format="%d min"),
                           "Waited": st.column_config.NumberColumn(format="%d min")})
    with st.expander("How these are measured"):
        st.markdown(
            f"- **Started / done** are HotSOS's own times, off each housekeeper's timeline.\n"
            f"- **Inspected** is when the app first saw the room inspected in HotSOS — HotSOS "
            f"keeps no time for it — so it is right to about two minutes.\n"
            f"- **Marked together**: start and done pressed within {rtm.TOGETHER_MIN} minutes of "
            f"each other on a room with minutes on the sheet. The room was cleaned, then marked, "
            f"so its real start and finish aren't known.\n"
            f"- **Left open**: done pressed more than {rtm.LONG_OPEN:g} times the room's minutes "
            f"after its start — usually the done tap came late.\n"
            f"- **First start ⚠**: the day's first room started after "
            f"{rtm._hhmm(_dt.datetime.combine(today, rtm.FIRST_START_LATE))} (carts roll at 10).\n"
            f"- **Wait for RQS**: from the housekeeper's done to inspected. HotSOS doesn't record "
            f"who inspected, so the RQS is the one typed on the sheet: the office PC copies the "
            f"sheet's RQS into the app every ten minutes through the day, and from the 4 PM sync "
            f"on the sheet's own record is used.\n"
            f"- Dust n Vac rooms have no minutes, so they aren't judged for marking. Only rooms on "
            f"the app's charts are copied from HotSOS, and a day the office PC was off has gaps.")


view = st.segmented_control("View", ["📋 Rooms", "⏱️ Timing"], default="📋 Rooms",
                            key="rp_view", label_visibility="collapsed")
if view == "⏱️ Timing":
    timing_tab()
    st.stop()

sync = db._load_key(rd.SYNC_KEY) or {}
req = db._load_key(rd.REQUEST_KEY) or {}
fixes = db._load_key(rd.NAMES_KEY) or {}
left = db._load_key(rd.LEFT_KEY) or {}
try:
    import staff_names
    aliases = staff_names.aliases()
except Exception:
    aliases = {}
weeks = db.load_staff_weeks()
overrides = db.load_staff_overrides()
res = _built(f"{sync.get('at')}|{_md5(sync.get('months') or {})}",
             f"{getattr(db, '_WEEKS', {}).get('v')}|{len(weeks)}|{_md5(overrides)}",
             _md5([fixes, aliases]), weeks, overrides, fixes, aliases)


# ── header: where the numbers come from, and Sync ────────────────────────────
def _pending(s, r) -> bool:
    if s.get("status") == "running":
        t = _t(s.get("started_at"))
        return bool(t) and (clock.now() - t).total_seconds() < 900
    ra = _t(r.get("at"))
    if not ra or (clock.now() - ra).total_seconds() > 900:
        return False
    done = [x for x in (_t(s.get("at")), _t(s.get("failed_at"))) if x]
    return not done or ra > max(done)


h1, h2 = st.columns([5, 1.2], vertical_alignment="bottom")
with h1:
    src = []
    if sync.get("at"):
        src.append(f"Synced {_when(sync['at'])} — {e(sync.get('source') or '')}")
        if sync.get("file_saved_at"):
            src.append(f"sheet last saved {_when(sync['file_saved_at'])}"
                       + (f" by {e(sync['file_by'])}" if sync.get("file_by") else ""))
    st.markdown(f'<div class="rp-h1">📋 Report</div><div class="rp-src">Rooms from '
                f'<b>GC8 Inspections</b>, read every day at 4 PM · days from the staff schedule'
                f'{"<br>" + " · ".join(src) if src else ""}</div>', unsafe_allow_html=True)
with h2:
    if st.button("🔄 Sync now", use_container_width=True,
                 help="Ask the office PC to read GC8 Inspections again now — for a "
                      "correction somebody just made. It takes about a minute."):
        db._upsert_key(rd.REQUEST_KEY, {"id": uuid.uuid4().hex, "by": me, "at": clock.stamp()})
        req = db._load_key(rd.REQUEST_KEY) or {}

if _pending(sync, req):
    @st.fragment(run_every=5)
    def _watch():
        s = db._load_key(rd.SYNC_KEY) or {}
        if not _pending(s, db._load_key(rd.REQUEST_KEY) or {}):
            st.rerun()
        beat = _t((db._load_key(hs.HEARTBEAT_KEY) or {}).get("at"))
        if beat and (clock.now() - beat).total_seconds() < 180:
            st.info("⏳ The office PC is reading GC8 Inspections — the numbers update by "
                    "themselves in about a minute.")
        else:
            st.warning("Sync asked for, but the office PC isn't connected. It will read the "
                       "sheet as soon as it's back on.")
    _watch()
elif sync.get("status") == "error":
    st.error(f"The last sync failed ({_when(sync.get('failed_at'))}): {sync.get('error')}. "
             "The numbers below are from the sync before it.")

if not res:
    st.info("Nothing synced yet. Press **Sync now** and the office PC will read the sheet.")
    st.stop()

# Workbook-wide checks, as badges.
chk = sync.get("checks") or {}
badges = []
two = chk.get("two_tabs") or {}
badges.append(("", "✓ One tab per date",
               "Where two tabs claim a date, the one filled in more is used:\n" +
               "\n".join(f"{_d(d)}: '{v['used']}' (not {', '.join(repr(x) for x in v['not used'])})"
                         for d, v in sorted(two.items())) if two else "Every date has a single tab."))
if chk.get("app_copies"):
    badges.append(("", "✓ The app's own copies left out",
                   "Tabs the app made to compare with the team's: " + ", ".join(chk["app_copies"])))
badges.append(("", f"✓ Repeated rows removed ({chk.get('repeats_removed', 0)})",
               "A room listed twice for the same job on one tab is counted once."))
if chk.get("redated"):
    badges.append(("", f"✓ {len(chk['redated'])} tab(s) dated by their place",
                   "A tab whose name doesn't give its day is read by where it sits between "
                   "the days around it:\n" +
                   "\n".join(f"'{n}' → {_d(iso)}" for n, iso in sorted(chk["redated"].items(),
                                                                        key=lambda x: x[1]))))
if chk.get("columns_found"):
    badges.append(("", f"✓ {len(chk['columns_found'])} blank or mistyped header(s) read",
                   "A column whose header label was blank or mistyped, found by what it holds:\n"
                   + "\n".join(chk["columns_found"])))
badges.append(("" if not chk.get("copied_tabs") else "warn",
               "✓ No copied tabs" if not chk.get("copied_tabs") else
               f"! {len(chk['copied_tabs'])} tab(s) look copied",
               "A tab identical to another day's would carry that day's names." +
               ("\n" + "\n".join(chk["copied_tabs"]) if chk.get("copied_tabs") else "")))
if chk.get("unreadable"):
    badges.append(("warn", f"! {len(chk['unreadable'])} tab(s) couldn't be read",
                   "No Service/RQS header row found:\n" + "\n".join(chk["unreadable"])))
if chk.get("missing_dates"):
    badges.append(("warn", f"! {len(chk['missing_dates'])} date(s) have no tab",
                   "No tab anywhere in the workbook for: " + ", ".join(_d(d) for d in chk["missing_dates"])))
st.markdown('<div class="rp rp-badges">' + "".join(
    f'<span class="rp-b {c} tl" data-tip="{tip(t_)}" tabindex="0">{e(lab)}</span>'
    for c, lab, t_ in badges) + "</div>", unsafe_allow_html=True)


# ── filters ──────────────────────────────────────────────────────────────────
first = _dt.date.fromisoformat(res["first"])
last = _dt.date.fromisoformat(res["last"])
f1, f2, f3 = st.columns([2.3, 2.2, 2.2], vertical_alignment="bottom")
with f1:
    mode = st.segmented_control("Period", ["Week", "Month", "Year", "Date range"],
                                default="Year", key="rp_mode") or "Year"
with f2:
    if mode == "Date range":
        rng = st.date_input("From – to", value=(last.replace(day=1), last), min_value=first,
                            max_value=last, key="rp_range", format="MM/DD/YYYY")
        a = rng[0] if rng else last
        b = rng[1] if isinstance(rng, (tuple, list)) and len(rng) > 1 else a
    else:
        pick = st.date_input("Any day in it", value=last, min_value=first, max_value=last,
                             key="rp_pick", format="MM/DD/YYYY")
        if mode == "Week":
            a = pick - _dt.timedelta(days=(pick.weekday() + 1) % 7)
            b = a + _dt.timedelta(days=6)
        elif mode == "Month":
            a = pick.replace(day=1)
            b = (a.replace(day=28) + _dt.timedelta(days=4)).replace(day=1) - _dt.timedelta(days=1)
        else:
            a, b = pick.replace(month=1, day=1), pick.replace(month=12, day=31)
with f3:
    team = st.segmented_control("Show", ["Both", "RQS", "Housekeepers"], default="Both",
                                key="rp_team") or "Both"
start, end = max(a, first).isoformat(), min(b, last).isoformat()
if start > end:
    st.info("No synced days in that period.")
    st.stop()
so_far = " (so far)" if b > last else ""
s0, e0 = _dt.date.fromisoformat(start), _dt.date.fromisoformat(end)
period = (f"{s0:%b} {s0.day} – {e0:%b} {e0.day}, {e0.year}" if s0.year == e0.year
          else f"{s0:%b} {s0.day}, {s0.year} – {e0:%b} {e0.day}, {e0.year}")
if s0 == e0:
    period = f"{s0:%a %b} {s0.day}, {s0.year}"


# ── the tables ───────────────────────────────────────────────────────────────
MORE, LESS, NEITHER = "\n\n▲ More is better.", "\n\n▼ Less is better — 0 is the goal.", "\n\n◆ Neither better nor worse: it explains the other numbers."
RQS_COLS = [
    # key, group, label, tip
    ("rank", None, "#", "Rank by rooms inspected in this period. The same number shared means the same count."),
    ("person", None, "Name", "Click a name for their day-of-week habits and month-by-month cards."),
    ("in", None, "Rooms inspected",
     "Full Clean rooms with this person's name in the RQS column — check-outs, in-house full "
     "cleans, early outs and deep cleans. The first name in the cell counts (\"Oralia/Josseling\" "
     "is Oralia with a trainee). Daily Service rooms are not counted: RQS 2 looks at those on a "
     "round, not one by one. Read it with Days on the schedule." + MORE),
    ("fc", "Rooms they cleaned", "Full Clean",
     "Full Clean rooms with this person's name in the HSKP column: rooms an RQS cleaned "
     "themselves. A room two people cleaned counts for both." + NEITHER +
     " A high number means they were pulled off inspecting to clean."),
    ("ds", "Rooms they cleaned", "Daily Service",
     "Daily Service rooms (stayovers, exchanges) with this person's name in the HSKP column." +
     NEITHER),
    ("days_in", None, "Days inspecting",
     "Days with at least one inspected room on the sheet. The gap to the days on the schedule "
     "is RQS 2 days (Daily Service and Dust n Vac rounds), other work, and days nobody wrote a "
     "name." + MORE),
    ("per_day", None, "Rooms per day",
     "Rooms inspected ÷ days inspecting: the size of an ordinary day. 12–13 is a full round."
     "\n\n▲ Higher means a heavier day — but very high can mean rushed inspections."),
    ("sched", "Days on the schedule", "Total",
     "Days the staff schedule had them working on the RQS team, other work included, up to the "
     "last synced day." + MORE),
    ("rqs1", "Days on the schedule", "RQS 1",
     "Days the staff schedule named them RQS 1 (\"RQS 1\", or \"RQS 1 + RQS 2\" — counted for "
     "both). RQS 1 gets no rooms of its own on the charts. Most RQS days only say ON: an "
     "ordinary Full Clean inspecting day, counted in Total but in neither role." + NEITHER),
    ("rqs2", "Days on the schedule", "RQS 2",
     "Days the staff schedule named them RQS 2: the Daily Service and Dust n Vac round, which "
     "is why those days have few Full Clean inspections." + NEITHER),
    ("project", "Days on the schedule", "Other work",
     "Days on their RQS row that weren't inspecting: projects, ENG, ULLR, rollaways…" + NEITHER),
    ("nocall", None, "Last minute inform",
     "Days the staff schedule marks red (or NCNS typed in): they let us know at the last minute "
     "that they weren't coming." + LESS),
]
HK_COLS = [
    ("rank", None, "#", "Rank by rooms cleaned in this period. The same number shared means the same count."),
    ("person", None, "Name", "Click a name for their day-of-week habits and month-by-month cards."),
    ("cleaned", None, "Rooms cleaned",
     "Every room with this person's name in the HSKP column: Full Clean and Daily Service "
     "together. A room two people cleaned counts for both. Read it with the days on the "
     "schedule — a Full Clean takes 70–140 minutes, a Daily Service about 30." + MORE),
    ("fc", "Rooms cleaned by service", "Full Clean",
     "Check-outs, in-house full cleans, early outs and deep cleans. Four or five is a full day."
     + MORE),
    ("ds", "Rooms cleaned by service", "Daily Service",
     "Stayovers, sheet and towel exchanges. Ten to thirteen is a full day." + MORE),
    ("main", "Days on the schedule", "Full Clean",
     "Days the staff schedule had them on Full Clean charts (a building number or ON)." + MORE),
    ("ds_days", "Days on the schedule", "Daily Service",
     "Days the staff schedule had them on Daily Service." + NEITHER),
    ("project", "Days on the schedule", "Other work",
     "Days on their row that were other work: projects, garages, food, HSP cover, stripping "
     "linen…" + NEITHER),
    ("nocall", None, "Last minute inform",
     "Days the staff schedule marks red (or NCNS typed in): they let us know at the last minute "
     "that they weren't coming." + LESS),
]
GRID = {"rqs": "36px minmax(165px,1.3fr) minmax(140px,1.6fr) 64px 64px 72px 62px 56px 54px 54px 64px 78px",
        "hk": "36px minmax(185px,1.4fr) minmax(170px,1.8fr) 72px 72px 74px 74px 66px 84px"}
#: What a column's number counts, shown under its name: rooms, or days.
UNIT = {"in": "rooms", "fc": "rooms", "ds": "rooms", "cleaned": "rooms", "per_day": "rooms/day",
        "days_in": "days", "sched": "days", "rqs1": "days", "rqs2": "days", "project": "days",
        "main": "days", "ds_days": "days", "nocall": "days"}
UNIT_CLASS = {"rooms": "r", "days": "d", "rooms/day": "rd"}
UNITS_KEY = ('<div class="rp-units"><span><span class="u r">rooms</span> a count of rooms</span>'
             '<span><span class="u d">days</span> a number of days</span></div>')


def _num(v, key):
    if v is None:
        return '<div class="rp-c z">—</div>'
    if key == "nocall":
        return (f'<div class="rp-c"><span class="rp-nc">{v}</span></div>' if v
                else '<div class="rp-c z">0</div>')
    txt = f"{v:,}" if isinstance(v, int) else f"{v}"
    return f'<div class="rp-c{" z" if not v else ""}">{txt}</div>'


def _header(cols, role):
    """Column names that sort the table when clicked (report_table does the
    sorting): numbers most first, names A to Z, a second click reverses."""
    cells, groups = [], {}
    for i, (k, g, lab, _note) in enumerate(cols, 1):
        left = " l" if k in ("person", "in", "cleaned") else ""
        first = "asc" if k in ("rank", "person") else "desc"
        if g:
            groups.setdefault(g, []).append(i)
            pos = f"grid-row:2;grid-column:{i}"
        else:
            pos = f"grid-row:1/span 2;grid-column:{i}"
        unit = UNIT.get(k)
        cells.append(f'<div class="h s{left}" style="{pos}" data-col="{k}" data-first="{first}" '
                     f'role="button" tabindex="0" aria-label="Sort by {e(lab)}">'
                     # The arrow travels with the last word rather than
                     # wrapping onto a line of its own in a narrow column.
                     f'{e(lab).rsplit(" ", 1)[0] + " " if " " in lab else ""}'
                     f'<span style="white-space:nowrap">{e(lab.rsplit(" ", 1)[-1])}'
                     f'<span class="ar">⇅</span></span>'
                     + (f'<span class="uw"><span class="u {UNIT_CLASS[unit]}">{unit}</span></span>'
                        if unit else "") + '</div>')
    for g, idx in groups.items():
        cells.append(f'<div class="g" style="grid-row:1;grid-column:{idx[0]}/span {len(idx)}">'
                     f'{e(g)}</div>')
    return (f'<div class="rp-grid rp-hdr" style="grid-template-columns:{GRID[role]}">'
            + "".join(cells) + "</div>")


def _facts(r, role, start, end):
    out = []
    g = gone(r["person"])
    if g:
        out.append(f"<b>{g[0]}</b> — " + (f"last day on the schedule <b>{_long(g[1])}</b>"
                                           if g[1] else "no longer works here"))
    ud = rd.usual_days(r.get("dows") or {})
    if ud:
        per_wk, weeks = per_week(r, start, end)
        out.append(f"Usually works <b>{' · '.join(ud)}</b>")
        out.append(f"<b>{per_wk:.1f}</b> days a week on average "
                   f"({r.get('sched', 0)} days in {weeks:.1f} weeks)")
    if role == "rqs":
        on = r.get("main", 0) - r.get("role_days", 0)
        out.append(f"Days on the schedule: RQS 1 <b>{r.get('rqs1', 0)}</b> · RQS 2 "
                   f"<b>{r.get('rqs2', 0)}</b> · inspecting (ON) <b>{max(on, 0)}</b> · "
                   f"other work <b>{r.get('project', 0)}</b>")
        if r.get("dv"):
            out.append(f"Dust n Vac inspected <b>{r['dv']:,}</b> rooms")
    else:
        out.append(f"Rooms on the sheet on <b>{r.get('days_clean', 0)}</b> days")
        if r.get("in"):
            out.append(f"Inspected <b>{r['in']}</b> rooms")
    if r.get("projects"):
        top = sorted(r["projects"].items(), key=lambda x: -x[1])[:5]
        out.append("Other work (days): " + " · ".join(f"{e(k)} <b>{v}</b>" for k, v in top))
    if r.get("other_team"):
        teams = ", ".join(e(t) for t in r.get("teams") or {})
        out.append(f"Worked with another team on <b>{r['other_team']}</b> days ({teams})")
    if r.get("vto"):
        out.append(f"VTO <b>{r['vto']}</b> days")
    return "".join(f"<span>{x}</span>" for x in out)


def _card(label, t, role):
    def n(v, one, many):
        return f"{v} {one if v == 1 else many}"
    if role == "rqs":
        main = f'{t.get("in", 0):,}<small>rooms inspected</small>'
        lines = [f'{t["per_day"]} rooms a day · {n(t.get("days_in", 0), "day", "days")} inspecting'
                 if t.get("per_day") else "",
                 f'Cleaned {t.get("fc", 0)} FC · {t.get("ds", 0)} DS rooms'
                 if t.get("fc") or t.get("ds") else "",
                 f'{n(t.get("sched", 0), "day", "days")} on the schedule'
                 + (f' · {t["project"]} other work' if t.get("project") else ""),
                 f'RQS 1: {t.get("rqs1", 0)} · RQS 2: {t.get("rqs2", 0)} days'
                 if t.get("rqs1") or t.get("rqs2") else ""]
    else:
        main = f'{t.get("cleaned", 0):,}<small>rooms cleaned</small>'
        lines = [f'{t.get("fc", 0)} FC · {t.get("ds", 0)} DS rooms',
                 f'Days: {t.get("main", 0)} FC · {t.get("ds_days", 0)} DS'
                 + (f' · {t["project"]} other work' if t.get("project") else "")]
    if t.get("nocall"):
        lines.append(f'<span class="nc">Last minute inform: {n(t["nocall"], "day", "days")}</span>')
    empty = not (t.get("sched") or t.get("in") or t.get("cleaned") or t.get("nocall"))
    return (f'<div class="rp-k{" empty" if empty else ""}"><div class="kt">{e(label)}</div>'
            f'<div class="kv">{main}</div>'
            + "".join(f'<div class="kl">{x}</div>' for x in lines if x) + "</div>")


def table_html(rows, role, start, end, title, sub):
    cols = RQS_COLS if role == "rqs" else HK_COLS
    bar_key = "in" if role == "rqs" else "cleaned"
    top = max([r.get(bar_key, 0) for r in rows] + [1])
    parts = [f'<div class="rp-card" data-table="{role}"><div class="rp-ct">{e(title)}</div>'
             f'<div class="rp-cs">{sub}</div>{UNITS_KEY}<div class="rp-scroll"><div class="rp-tab">',
             _header(cols, role), '<div class="rp-body">']
    cuts = rd.slices(start, end)
    for r in rows:
        # What each column sorts on, as numbers ("per day" stays blank, not 0,
        # for someone with no inspections, and sorts last).
        sort_on = {k: (r.get(k) if k in ("per_day", "person") else r.get(k, 0))
                   for k, *_ in cols}
        g = gone(r["person"])
        cells = []
        for k, _g, _lab, _tip in cols:
            if k == "rank":
                cells.append(f'<div class="rp-c rk">{r["rank"]}</div>')
            elif k == "person":
                tag = (f'<span class="rp-left{" soon" if g[0] == "Leaving" else ""}">{g[0]}</span>'
                       if g else "")
                cells.append(f'<div class="rp-c nm"><span class="nmt">{e(r["person"])}</span>{tag}'
                             f'<span class="chev">›</span></div>')
            elif k == bar_key:
                v = r.get(k, 0)
                cells.append(f'<div class="rp-c rp-bar"><span class="rp-trk"><span class="rp-fil" '
                             f'style="width:{100 * v / top:.1f}%"></span></span><b>{v:,}</b></div>')
            else:
                cells.append(_num(r.get(k, 0) if k != "per_day" else r.get(k), k))
        by_day = res["days"].get(r["person"], {})
        # Months (weeks, days) before someone started or after they left
        # would only be cards of zeros.
        mine = res.get("span", {}).get(r["person"])
        cards = "".join(_card(lab, rd.tally(by_day, a_, b_, role), role) for lab, a_, b_ in cuts
                        if not mine or rd.active(mine, a_, b_))
        parts.append(f'<details class="rp-p{" left" if g else ""}" data-s="{e(json.dumps(sort_on))}">'
                     f'<summary class="rp-grid" '
                     f'style="grid-template-columns:{GRID[role]}">{"".join(cells)}</summary>'
                     f'<div class="rp-more"><div class="rp-facts">{_facts(r, role, start, end)}</div>'
                     f'<div class="rp-cards">{cards}</div></div></details>')
    parts.append("</div></div></div></div>")
    return "".join(parts)


def show(role):
    rows = rd.rows_for(res, start, end, role)
    label = "RQS" if role == "rqs" else "Housekeepers"
    if not rows:
        st.info(f"No {label.lower()} on the sheet or the schedule for {period}.")
        return
    n_gone = sum(1 for r in rows if gone(r["person"]))
    people = f"{len(rows)} people" + (f" ({n_gone} no longer here)" if n_gone else "")
    if role == "rqs":
        tot = sum(r.get("in", 0) for r in rows)
        sub = (f"{people} · <b>{tot:,}</b> rooms inspected · "
               f"{sum(r.get('nocall', 0) for r in rows)} days of last minute inform")
    else:
        tot = sum(r.get("cleaned", 0) for r in rows)
        sub = (f"{people} · <b>{tot:,}</b> rooms cleaned "
               f"({sum(r.get('fc', 0) for r in rows):,} Full Clean · "
               f"{sum(r.get('ds', 0) for r in rows):,} Daily Service) · "
               f"{sum(r.get('nocall', 0) for r in rows)} days of last minute inform")
    report_table.table(html=table_html(rows, role, start, end, f"{label} · {period}{so_far}", sub),
                       css=TABLE_CSS, key=f"rp_table_{role}")
    st.markdown('<div class="rp-hint">Click a column name to sort by it — again to reverse · '
                'click a name for their months.</div>', unsafe_allow_html=True)
    with st.expander(f"What each {'RQS' if role == 'rqs' else 'housekeeper'} column means"):
        st.markdown("\n".join(
            f"- **{e(g) + ' · ' if g else ''}{e(lab)}**"
            f"{' (' + UNIT[k] + ')' if k in UNIT else ''} — "
            f"{e(note).replace(chr(10) + chr(10), ' ').replace(chr(10), ' ')}"
            for k, g, lab, note in (RQS_COLS if role == "rqs" else HK_COLS)
            if k not in ("person",)))


if team in ("Both", "RQS"):
    show("rqs")
if team in ("Both", "Housekeepers"):
    show("hk")


# ── download ─────────────────────────────────────────────────────────────────
EXCEL = {
    "rqs": [("Rank", "rank"), ("Name", "person"), ("Rooms inspected (rooms)", "in"),
            ("Cleaned: Full Clean (rooms)", "fc"), ("Cleaned: Daily Service (rooms)", "ds"),
            ("Days inspecting (days)", "days_in"), ("Rooms per day", "per_day"),
            ("On the schedule: total (days)", "sched"), ("RQS 1 (days)", "rqs1"),
            ("RQS 2 (days)", "rqs2"), ("Other work (days)", "project"),
            ("Last minute inform (days)", "nocall"), ("Dust n Vac inspected (rooms)", "dv"),
            ("With another team (days)", "other_team"), ("VTO (days)", "vto")],
    "hk": [("Rank", "rank"), ("Name", "person"), ("Rooms cleaned (rooms)", "cleaned"),
           ("Full Clean (rooms)", "fc"), ("Daily Service (rooms)", "ds"),
           ("On the schedule: Full Clean (days)", "main"),
           ("On the schedule: Daily Service (days)", "ds_days"), ("Other work (days)", "project"),
           ("Last minute inform (days)", "nocall"), ("Rooms on the sheet (days)", "days_clean"),
           ("With another team (days)", "other_team"), ("VTO (days)", "vto")],
}


@st.cache_data(max_entries=8, show_spinner="Making the file…")
def _excel(who, start, end, token):
    roles = ["rqs", "hk"] if who in ("Both", "RQS", "Housekeepers") else None
    person = None
    if who == "RQS":
        roles = ["rqs"]
    elif who == "Housekeepers":
        roles = ["hk"]
    elif roles is None:
        person = who
        roles = [res["people"][who]["role"]]
    sheets, by_month, by_day = {}, [], []
    for role in roles:
        rows = [r for r in rd.rows_for(res, start, end, role) if not person or r["person"] == person]
        cols = EXCEL[role]
        def status(p):
            g = gone(p)
            if not g:
                return "Working"
            return g[0] + (f" — last day on the schedule {_long(g[1])}" if g[1] else "")
        sheets["RQS" if role == "rqs" else "Housekeepers"] = (
            [c for c, _ in cols] + ["Usual days", "Days a week (avg)", "Status"],
            [[r.get(k) if k in ("person", "per_day") else r.get(k, 0) for _, k in cols]
             + [" ".join(rd.usual_days(r.get("dows") or {})),
                round(per_week(r, start, end)[0], 1), status(r["person"])] for r in rows])
        for r in rows:
            by_d = res["days"].get(r["person"], {})
            for lab, a_, b_ in rd.slices(start, end):
                t = rd.tally(by_d, a_, b_, role)
                by_month.append([r["person"], "RQS" if role == "rqs" else "Housekeeper", lab, a_, b_,
                                 t.get("in", 0), t.get("per_day"), t.get("cleaned", 0), t.get("fc", 0),
                                 t.get("ds", 0), t.get("sched", 0), t.get("main", 0),
                                 t.get("ds_days", 0), t.get("project", 0), t.get("nocall", 0),
                                 t.get("rqs1", 0) if role == "rqs" else "",
                                 t.get("rqs2", 0) if role == "rqs" else ""])
            for iso in sorted(d for d in by_d if start <= d <= end):
                slot = by_d[iso]
                sched = [c for g, _s, k, c in slot.get("sched", ()) if g == role and c]
                nc = any(k == "no_call" for _g, _s, k, _c in slot.get("sched", ()))
                if not (sched or slot.get("in") or slot.get("fc") or slot.get("ds") or nc):
                    continue
                d = _dt.date.fromisoformat(iso)
                by_day.append([r["person"], "RQS" if role == "rqs" else "Housekeeper", iso,
                               f"{d:%a}", " / ".join(sched), res["tabs"].get(iso, ""),
                               len(slot.get("in", ())), " ".join(slot.get("in", ())),
                               len(slot.get("fc", ())), " ".join(slot.get("fc", ())),
                               len(slot.get("ds", ())), " ".join(slot.get("ds", ())),
                               len(slot.get("dv", ())), "yes" if nc else ""])
    span = rd.weeks_in(start, end) * 7
    if span > 7:                          # a week's slices are its days: "By day" has them
        sheets["By month" if span > 35 else "By week"] = (
            ["Name", "Role", "Period", "From", "To", "Rooms inspected (rooms)", "Rooms per day",
             "Rooms cleaned (rooms)", "Full Clean cleaned (rooms)",
             "Daily Service cleaned (rooms)", "On the schedule (days)",
             "Full Clean / RQS (days)", "Daily Service (days)", "Other work (days)",
             "Last minute inform (days)", "RQS 1 (days)", "RQS 2 (days)"], by_month)
    sheets["By day"] = (["Name", "Role", "Date", "Day", "On the schedule", "Sheet tab",
                         "Rooms inspected (rooms)", "Inspected rooms",
                         "Full Clean cleaned (rooms)", "Full Clean rooms",
                         "Daily Service cleaned (rooms)", "Daily Service rooms",
                         "Dust n Vac inspected (rooms)", "Last minute inform"], by_day)
    lo = rd.loose_for(res, start, end)
    notes = [f"BGV Peak 8 report — {who} — {start} to {end}",
             f"Rooms: GC8 Inspections, synced {sync.get('at', '')} ({sync.get('source', '')}). "
             f"Days: the staff schedule (Schedule.xlsx as the app holds it, in-app edits included).",
             "", "What the numbers mean:"]
    for role in roles:
        for k, g, lab, note in (RQS_COLS if role == "rqs" else HK_COLS):
            if k not in ("rank", "person"):
                notes.append(f"{'RQS' if role == 'rqs' else 'Housekeepers'} — {(g + ': ') if g else ''}"
                             f"{lab}: {note.replace(chr(10), ' ')}")
    notes += ["", "Not counted for anyone in this period:",
              f"Full Clean rooms with no RQS named: {lo.get('in_none', 0)}",
              f"Rooms with no housekeeper named: {lo.get('cl_none', 0)}",
              "Inspected by staff who aren't RQS: " + ", ".join(
                  f"{k} {v}" for k, v in sorted((lo.get('in_other') or {}).items(), key=lambda x: -x[1])),
              "Names on the sheet not matched to anyone: " + ", ".join(
                  f"{k} {v}" for k, v in sorted({**(lo.get('in_unknown') or {}),
                                                 **(lo.get('cl_unknown') or {})}.items(),
                                                key=lambda x: -x[1]))]
    return rd.to_excel(sheets, notes)


st.markdown("#### ⬇️ Download")
people_opts = sorted((p for p, i in res["people"].items() if i.get("role") in ("rqs", "hk")),
                     key=str.lower)
GROUPS = {"Both": "RQS and housekeepers", "RQS": "RQS only", "Housekeepers": "Housekeepers only"}


def _who_label(x):
    if x in GROUPS:
        return GROUPS[x]
    g = gone(x)
    return (f"{x} ({'RQS' if res['people'][x]['role'] == 'rqs' else 'housekeeper'}"
            f"{', ' + g[0].lower() if g else ''})")


d1, d2 = st.columns([2.5, 1.5], vertical_alignment="bottom")
with d1:
    who = st.selectbox("What to download", list(GROUPS) + people_opts, format_func=_who_label,
                       key="rp_dl_who",
                       help="The period above, as an Excel file: the table, each month (or week, "
                            "or day) per person, every day with the room numbers, and what each "
                            "column means.")
with d2:
    data = _excel(who, start, end, f"{sync.get('at')}|{_md5([fixes, aliases, left])}|"
                                    f"{getattr(db, '_WEEKS', {}).get('v')}|{_md5(overrides)}")
    st.download_button("Download Excel", data, use_container_width=True, type="primary",
                       file_name=f"BGV report - {who} - {start} to {end}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ── what the numbers leave out ───────────────────────────────────────────────
lo = rd.loose_for(res, start, end)
unknown = {**(lo.get("in_unknown") or {})}
for k, v in (lo.get("cl_unknown") or {}).items():
    unknown[k] = unknown.get(k, 0) + v
n_out = (lo.get("in_none", 0) + sum((lo.get("in_other") or {}).values())
         + sum(unknown.values()))
with st.expander(f"What these numbers leave out — {period}", expanded=False):
    def _top(d, n=12):
        items = sorted(d.items(), key=lambda x: -x[1])
        txt = ", ".join(f"{e(k)} <b>{v}</b>" for k, v in items[:n])
        return txt + (f" and {len(items) - n} more" if len(items) > n else "") if items else "none"
    st.markdown(
        f'<div class="rp-lo">'
        f'<b>Full Clean rooms with no RQS named:</b> {lo.get("in_none", 0):,}<br>'
        f'<b>Inspected by staff who aren\'t RQS</b> (managers, leads, housekeepers): '
        f'{_top(lo.get("in_other") or {})}<br>'
        f'<b>Rooms with no housekeeper named:</b> {lo.get("cl_none", 0):,}<br>'
        f'<b>Cleaned by other staff</b> (housepersons, leads): {_top(lo.get("cl_other") or {})}<br>'
        f'<b>Cleaned by help from another property:</b> {_top(lo.get("cl_visiting") or {})}<br>'
        f'<b>Names on the sheet not matched to anyone:</b> {_top(unknown)}</div>',
        unsafe_allow_html=True)
    st.caption("A name that can mean two people (\"David\", \"Ana\") goes to the one the column is "
               "about, then to the one the schedule had at work that day; if that still leaves "
               "two, it isn't counted. Tell the report who a name is below and it counts from "
               "the next refresh of this page.")
    every = {}
    for iso_lo in res["loose"].values():
        for k in ("in_unknown", "cl_unknown"):
            for n, v in (iso_lo.get(k) or {}).items():
                every[n] = every.get(n, 0) + v
    names = sorted(every, key=lambda n: -every[n])
    if names:
        n1, n2, n3 = st.columns([2, 2, 1], vertical_alignment="bottom")
        typed = n1.selectbox("Name on the sheet", names, key="rp_fix_typed",
                             format_func=lambda n: f"{n} ({every[n]} rooms this year)")
        target = n2.selectbox("Is", res["names"], key="rp_fix_person", index=None,
                              placeholder="Pick the person")
        if n3.button("Save", use_container_width=True, disabled=not target, key="rp_fix_save"):
            fixes = dict(fixes, **{typed: target})
            db._upsert_key(rd.NAMES_KEY, fixes)
            st.rerun()
    if fixes:
        st.markdown("**Names you've told the report:**")
        for k, v in sorted(fixes.items()):
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            c1.markdown(f"{e(k)} → **{e(v)}**")
            if c2.button("Remove", key=f"rp_fix_rm_{k}"):
                fixes = {x: y for x, y in fixes.items() if x != k}
                db._upsert_key(rd.NAMES_KEY, fixes)
                st.rerun()


# ── people who no longer work here ───────────────────────────────────────────
with st.expander(f"People who no longer work here ({len(left)})"):
    st.caption("They stay in the report — the rooms they did were real — but greyed, with a "
               "Left tag and their last day on the staff schedule. Someone still on the "
               "schedule for days ahead shows as Leaving until then.")
    everyone = sorted(set(people_opts) | set(left), key=str.lower)

    def _with_last_day(p):
        d = res["last_day"].get(p)
        return p + (f" — last day {_long(d)}" if d else "")

    picked = st.multiselect("No longer working here", everyone, default=sorted(left, key=str.lower),
                            format_func=_with_last_day, key="rp_left_pick",
                            label_visibility="collapsed")
    if st.button("Save", key="rp_left_save", disabled=set(picked) == set(left)):
        keep = {p: left[p] for p in picked if p in left}
        for p in picked:
            keep.setdefault(p, {"by": me, "at": clock.stamp()})
        db._upsert_key(rd.LEFT_KEY, keep)
        st.rerun()
