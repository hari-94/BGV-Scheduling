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

st.set_page_config(page_title="Health", page_icon="🩺", layout="wide")
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
ui.topnav("Health")
if not auth.can("can_view_dashboard"):
    st.error("Health is for RQS and admins.")
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

st.markdown("## 🩺 Health")
st.caption("Every part of the morning, as it last reported. Refreshes every 15 seconds.")


@st.fragment(run_every=15)
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
    agent_s, db_s, ssrs_s, sync_s, build_s, _ahead_s, arr_s, hot_s, files_s, app_s = states
    st.markdown(flow_svg({
        "email": arr_s, "flow": arr_s, "arr": files_s, "ssrs": ssrs_s, "staff": sync_s,
        "agent": agent_s, "build": build_s, "sheet": build_s, "push": "human",
        "hotsos": hot_s, "db": db_s, "app": app_s}), unsafe_allow_html=True)
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
