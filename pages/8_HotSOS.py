"""
HotSOS — push the day's final assignments into HotSOS, and keep one name per
person.

This page never talks to HotSOS or SSRS itself. Both are inside the company,
so the work is done by hotsos_agent.py on the office PC; the page leaves it a
request in app_settings and shows what comes back. That is also why the page
says, first of all, whether the PC is listening -- a button that silently
does nothing is worse than no button.

Laid out as the three things an RQS does, in order -- 1 the day's sheet,
2 Preview, 3 Push -- then one result card: what was read, four counts, and
every problem in a single "needs attention" box, so warnings never stack up
as separate banners. The housekeeper cards and the full table follow.

Names come from the staff directory (staff_names.py), whose full names are
HotSOS's own; a name it doesn't know gets a small box to match it once.

Nothing reaches HotSOS until an RQS presses Push.
"""
import datetime as _dt
import html
import os
import sys
import uuid

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, clock, db, ui          # noqa: E402
import daily_build                  # noqa: E402
import hotsos_sync as hs            # noqa: E402
import staff_names as sn            # noqa: E402

st.set_page_config(page_title="HotSOS", page_icon="🛰️", layout="wide")
st.markdown("""<style>
.block-container{max-width:min(1200px,97%);}
[data-testid='stSidebarNav']{display:none!important;}
.hs-top{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:4px}
.hs-title{font-family:'Syne',sans-serif;font-size:1.6rem;font-weight:700;color:#16202e}
.pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:4px 11px;
      font-size:.78rem;font-weight:600;border:1px solid #e6e9ee;background:#fff;color:#1f2733;margin-left:6px}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.step{background:#fff;border:1px solid #e6e9ee;border-radius:14px;padding:12px 14px 4px;height:100%}
.step-n{font-size:.72rem;font-weight:700;color:#2563a8;letter-spacing:.05em;text-transform:uppercase}
.step-t{font-weight:700;color:#16202e;font-size:.98rem;margin:2px 0 4px}
.step-s{font-size:.8rem;color:#5b6675;line-height:1.45;height:4.4em;overflow:hidden}
.res{background:#fff;border:1px solid #e6e9ee;border-radius:14px;padding:14px 16px;margin-top:14px}
.res-h{display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;align-items:baseline}
.res-t{font-weight:700;color:#16202e;font-size:1rem}
.res-when{font-size:.78rem;color:#5b6675}
.res-src{font-size:.8rem;color:#5b6675;margin-top:3px}
.verdict{margin-top:10px;font-size:.9rem;font-weight:600;padding:9px 12px;border-radius:10px}
.v-ok{background:#ecf7ee;color:#05603a}.v-info{background:#eef4fd;color:#184f95}
.v-warn{background:#fff8eb;color:#7a4a00}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:12px}
.kpi{border:1px solid #eef0f3;border-radius:10px;padding:8px 12px}
.kpi b{display:block;font-family:'Syne',sans-serif;font-size:1.5rem;color:#16202e;line-height:1.1}
.kpi span{font-size:.74rem;color:#5b6675}
.kpi.hot b{color:#2563a8}.kpi.bad b{color:#b42318}
@media (max-width:640px){.kpis{grid-template-columns:repeat(2,1fr)}}
.attn{background:#fff8eb;border:1px solid #f6d58e;border-radius:12px;padding:10px 14px;margin-top:12px;
      font-size:.84rem;color:#5c3d00;line-height:1.6}
.attn-h{font-weight:700;margin-bottom:2px}
.live{font-size:.82rem;color:#184f95;background:#eef4fd;border-radius:10px;padding:8px 12px;margin-top:10px}
.hk-card{background:#fff;border:1px solid #e6e9ee;border-radius:14px;padding:12px 14px;margin-bottom:12px}
.hk-name{font-weight:700;color:#16202e;font-size:.95rem}
.hk-meta{font-size:.75rem;color:#5b6675;margin:2px 0 8px}
.chip{display:inline-block;border-radius:8px;padding:3px 8px;margin:0 5px 5px 0;font-size:.78rem;
      font-family:'DM Mono',monospace;border:1px solid transparent;line-height:1.35}
.chip small{font-family:'DM Sans',sans-serif;opacity:.8}
.c-assign{background:#e8f1fc;color:#184f95;border-color:#b7d3f6}
.c-move{background:#fff4e5;color:#8a4b00;border-color:#fad7a0}
.c-already{background:#f2f3f5;color:#5b6675}
.c-sent{box-shadow:inset 0 0 0 1px #0ca30c}
.c-fail{background:#fdecec;color:#9b1c1c;border-color:#f5b5b5}
.legend{font-size:.75rem;color:#5b6675;margin:-4px 0 6px}
</style>""", unsafe_allow_html=True)
auth.require_login()
ui.topnav("HotSOS")
if not auth.can("can_generate"):
    st.error("Only RQS and admins can push to HotSOS.")
    st.stop()

me = st.session_state.get("display_name") or auth.current_user().get("username", "")
ONLINE_SECONDS = 180
e = html.escape


def _age(stamp):
    try:
        return (clock.now() - _dt.datetime.fromisoformat(stamp)).total_seconds()
    except Exception:
        return None


def _ago(sec):
    if sec is None:
        return "never"
    if sec < 90:
        return f"{int(sec)} s ago"
    if sec < 5400:
        return f"{int(sec // 60)} min ago"
    return f"{sec / 3600:.1f} h ago"


def _clock(stamp):
    try:
        t = _dt.datetime.fromisoformat(stamp).astimezone(clock.MTN)
        return f"{t:%I:%M %p}".lstrip("0")
    except Exception:
        return "—"


def _request(mode, day=None):
    db._upsert_key(hs.REQUEST_KEY, {"id": uuid.uuid4().hex,
                                    "date": str(day or clock.today()),
                                    "mode": mode, "by": me, "at": clock.stamp()})


SVC = {"full clean": "FC", "daily service": "DS", "dust n vac": "DV"}


def _svc(s):
    return SVC.get(str(s).strip().lower(), str(s)[:2].upper())


# ── header: what this is, and whether the office PC is listening ───────────
beat = db._load_key(hs.HEARTBEAT_KEY) or {}
beat_age = _age(beat.get("at"))
online = beat_age is not None and beat_age < ONLINE_SECONDS
pc = (f'<span class="pill"><span class="dot" style="background:#0ca30c"></span>'
      f'Office PC online</span>' if online else
      f'<span class="pill" style="border-color:#f5b5b5;color:#9b1c1c"><span class="dot" '
      f'style="background:#d03b3b"></span>Office PC offline · {_ago(beat_age)}</span>')
st.markdown(f'<div class="hs-top"><span class="hs-title">🛰️ HotSOS</span><span>{pc}</span></div>',
            unsafe_allow_html=True)
if not online:
    st.caption("Nothing below can run until the office PC is back on; presses wait for it.")

# ── the three steps ─────────────────────────────────────────────────────────
_b = db._load_key(daily_build.BUILD_KEY) or {}
today = clock.today_iso()
if _b.get("date") == today and _b.get("status") == "done":
    sheet_line = (f"Tab <b>{e(str(_b.get('tab')))}</b> · {_b.get('rooms')} rooms, "
                  f"{_b.get('charts')} charts · built {_clock(_b.get('finished_at'))}"
                  + (" · Arrival Report ✓" if _b.get("arrival") else " · no Arrival Report"))
elif _b.get("status") == "running":
    sheet_line = "Building now…"
elif _b.get("date") == today and _b.get("status") == "error":
    sheet_line = f"<span style='color:#b42318'>Build failed: {e(str(_b.get('error'))[:90])}</span>"
else:
    sheet_line = "Not built yet today — it's built at 5 AM."

s1, s2, s3 = st.columns(3)
with s1:
    st.markdown(f'<div class="step"><div class="step-n">Step 1</div>'
                f'<div class="step-t">Today\'s sheet</div><div class="step-s" title="GC8 Daily '
                f'Schedule.xlsx · SharePoint › Office › GC8 Inspections">{sheet_line}</div></div>',
                unsafe_allow_html=True)
    if st.button("Build today's sheet", use_container_width=True,
                 help="Builds the schedule like pressing Generate, and writes today's tab. "
                      "A tab someone has already edited is never overwritten."):
        _request("build", clock.today())
        st.toast("Asked the office PC to build today's sheet.")
with s2:
    st.markdown('<div class="step"><div class="step-n">Step 2</div>'
                '<div class="step-t">Preview</div><div class="step-s">Edit the tab for call-offs '
                'and swaps, then check what would change. Reads the sheet live.</div></div>',
                unsafe_allow_html=True)
    day = st.date_input("Day", value=clock.today(), key="hs_day", label_visibility="collapsed")
    if st.button("Preview", use_container_width=True):
        _request("preview", day)
with s3:
    st.markdown('<div class="step"><div class="step-n">Step 3</div>'
                '<div class="step-t">Push</div><div class="step-s">Sends the final sheet to '
                'HotSOS and updates the app\'s charts.</div></div>', unsafe_allow_html=True)
    final = st.checkbox("The sheet is final", key="hs_final")
    if st.button("Push to HotSOS", type="primary", use_container_width=True, disabled=not final):
        _request("push", day)


# ── the result ──────────────────────────────────────────────────────────────
@st.fragment(run_every=5)
def result_panel():
    req = db._load_key(hs.REQUEST_KEY) or {}
    cur = db._load_key(hs.RESULT_KEY) or {}
    live = ""
    if req.get("id") and req["id"] != cur.get("id"):
        live = (f"⏳ {e(req.get('mode', '').title())} for {e(str(req.get('date')))} asked by "
                f"{e(str(req.get('by')))} — waiting for the office PC…")
    elif cur.get("status") == "running":
        live = f"⏳ {e(cur['mode'].title())} for {e(cur['date'])} is running — about a minute…"
    if live:
        st.markdown(f'<div class="live">{live} The last result stays below until it\'s done.</div>',
                    unsafe_allow_html=True)
    if cur.get("status") == "error":
        st.error(f"{cur.get('mode', '').title()} for {cur.get('date')} "
                 f"({_ago(_age(cur.get('finished_at')))}): {cur.get('error')}")

    res = db._load_key(hs.LAST_KEY) or (cur if cur.get("plan") is not None else {})
    if not res:
        st.markdown('<div class="res"><div class="res-t">No preview yet</div>'
                    '<div class="res-src">Press Preview to see what would change.</div></div>',
                    unsafe_allow_html=True)
        return

    plan = res.get("plan") or []
    n = {a: sum(1 for l in plan if l["action"] == a) for a in
         (hs.ASSIGN, hs.MOVE, hs.ALREADY, hs.NO_PERSON, hs.NO_ROOM, hs.NO_HSKP)}
    change = n[hs.ASSIGN] + n[hs.MOVE]

    # One verdict line, in words.
    if res["mode"] == "push":
        if res["status"] != "done":
            verdict = ("v-warn", f"Pushed with problems: {res.get('sent', 0)} rooms sent — "
                                 "see below.")
        elif not res.get("sent") and not change:
            verdict = ("v-ok", f"✓ HotSOS matches the sheet — all {len(plan)} rooms are with "
                               "the right person.")
        else:
            app = res.get("app") or {}
            verdict = ("v-ok", f"✓ {res.get('sent', 0)} rooms sent to HotSOS"
                       + (" · app charts updated" if app.get("changed") else ""))
    else:
        verdict = (("v-info", f"{change} room{'s' if change != 1 else ''} would change. "
                              "Nothing has been sent.") if change else
                   ("v-ok", "✓ Nothing to change — HotSOS already matches the sheet."))

    src = ""
    if res.get("sheet_saved_at"):
        who = f" by {e(res['sheet_by'])}" if res.get("sheet_by") else ""
        where = res.get("sheet_source") or "the synced copy on the office PC"
        src = (f"Read {e(where)} · sheet last saved {_clock(res['sheet_saved_at'])}{who}"
               + ("" if where.startswith("live") else
                  " — if your last edit is newer, wait a few seconds and Preview again"))

    # Every problem, in one place.
    attn = []
    for col, who_ in (("HSKP", "housekeeper"), ("RQS", "RQS")):
        for person, blds in ((res.get("rule23") or {}).get(col) or {}).items():
            attn.append(f"<b>Rule:</b> {e(person)} ({who_}) has Full Clean in buildings "
                        f"{' and '.join(blds)} — give one side to someone else.")
    if res.get("unmatched_names"):
        attn.append("<b>Names HotSOS doesn't know:</b> " + e(", ".join(res["unmatched_names"]))
                    + " — match them in the box at the bottom.")
    miss = [l["room"] for l in plan if l["action"] == hs.NO_ROOM]
    if miss:
        attn.append(f"<b>Not on HotSOS today:</b> {e(', '.join(miss))}")
    if _b.get("date") == res.get("date") and _b.get("dv_unassigned") and n[hs.NO_HSKP]:
        attn.append(f"<b>Dust n Vac:</b> no RQS 2 on the staff schedule — put a name on those "
                    "rows in the sheet.")
    if res.get("warning"):
        attn.append(f"<b>Two tabs:</b> {e(res['warning'])}")
    for err in res.get("errors", []):
        attn.append(f"<b>HotSOS:</b> {e(err)}")

    kpis = [("hot" if change else "", change, "will change"),
            ("", n[hs.ALREADY], "already right"),
            ("bad" if n[hs.NO_PERSON] + n[hs.NO_ROOM] else "", n[hs.NO_PERSON] + n[hs.NO_ROOM],
             "need attention"),
            ("", n[hs.NO_HSKP], "no housekeeper on the sheet")]
    st.markdown(
        f'<div class="res"><div class="res-h"><span class="res-t">{e(res["mode"].title())} · '
        f'{e(res["date"])} · {e(str(res.get("tab", "?")))}</span>'
        f'<span class="res-when">{e(str(res.get("by", "")))} · {_ago(_age(res.get("finished_at")))}'
        f'</span></div>'
        + (f'<div class="res-src">{src}</div>' if src else "")
        + f'<div class="verdict {verdict[0]}">{verdict[1]}</div>'
        + '<div class="kpis">' + "".join(f'<div class="kpi {c}"><b>{v}</b><span>{t}</span></div>'
                                         for c, v, t in kpis) + '</div>'
        + (f'<div class="attn"><div class="attn-h">⚠️ Needs attention</div>'
           + "<br>".join(attn) + '</div>' if attn else "")
        + '</div>', unsafe_allow_html=True)

    # Per housekeeper.
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    only_changes = st.toggle("Only rooms that will change", value=bool(change),
                             key="hs_only_changes")
    by_person = {}
    for l in plan:
        if l.get("hotsos_name"):
            by_person.setdefault(l["hotsos_name"], []).append(l)
    cards = []
    for person, lines in sorted(by_person.items(),
                                key=lambda kv: (-sum(l["action"] in (hs.ASSIGN, hs.MOVE)
                                                     for l in kv[1]), kv[0])):
        shown = [l for l in lines if not only_changes or l["action"] in (hs.ASSIGN, hs.MOVE)]
        if not shown:
            continue
        chg = sum(l["action"] in (hs.ASSIGN, hs.MOVE) for l in lines)
        svcs = " · ".join(f"{v} {k}" for k, v in sorted(
            {_svc(l["service"]): sum(_svc(x["service"]) == _svc(l["service"])
                                     for x in lines) for l in lines}.items()))
        chips = []
        for l in sorted(shown, key=lambda l: l["room"]):
            cls = {"assign": "c-assign", "move": "c-move"}.get(l["action"], "c-already")
            out = l.get("outcome", "")
            if out == "sent":
                cls += " c-sent"
            elif out:
                cls = "c-fail"
            tip = (f"from {l['current']}" if l["action"] == hs.MOVE else
                   "already set" if l["action"] == hs.ALREADY else "new")
            team = f" · team: {l['who']}" if "/" in l["who"] else ""
            chips.append(f'<span class="chip {cls}" title="{e(tip + team)}">{e(l["room"])} '
                         f'<small>{_svc(l["service"])}</small></span>')
        cards.append(f'<div class="hk-card"><div class="hk-name">{e(person)}</div>'
                     f'<div class="hk-meta">{len(lines)} rooms · {e(svcs)}'
                     + (f' · <b>{chg} to change</b>' if chg else "") + f'</div>{"".join(chips)}</div>')
    if cards:
        st.markdown('<div class="legend">Blue: new · amber: moved from someone else (hover for '
                    'who) · grey: already right · green outline: sent</div>',
                    unsafe_allow_html=True)
        cols = st.columns(3)
        for i, c in enumerate(cards):
            cols[i % 3].markdown(c, unsafe_allow_html=True)
    elif only_changes:
        st.caption("No rooms to change. Switch the toggle off to see everyone's rooms.")

    with st.expander("Every room, as a table"):
        st.dataframe(pd.DataFrame([{
            "Room": l["room"], "Service": l["service"], "Sheet": l["who"],
            "HotSOS attendant": l["hotsos_name"], "Now in HotSOS": l["current"],
            "Action": l["action"], "Result": l.get("outcome", ""),
        } for l in plan]), hide_index=True, use_container_width=True)


result_panel()

# ── a name HotSOS doesn't know yet (a new hire, a new spelling) ────────────
# Outside the auto-refreshing panel on purpose: a table being edited must not
# redraw under someone's cursor every five seconds.
_res = db._load_key(hs.LAST_KEY) or db._load_key(hs.RESULT_KEY) or {}
_new = _res.get("unmatched_names") or []
_labels = sorted(a["label"] for a in sn.attendants())
if _new and _labels:
    with st.expander(f"👥 Match new names ({len(_new)})", expanded=True):
        st.caption("Pick the HotSOS person for each name the sheet used. It's remembered, "
                   "and the app is renamed to match. Leave a name empty if they aren't in "
                   "HotSOS.")
        _ed = st.data_editor(
            pd.DataFrame([{"Name on the sheet": n, "HotSOS full name": None} for n in _new]),
            hide_index=True, use_container_width=True, disabled=["Name on the sheet"],
            key=f"hs_newnames_{_res.get('id', '')}",
            column_config={"HotSOS full name": st.column_config.SelectboxColumn(
                options=_labels)})
        if st.button("Save names and Preview again", type="primary"):
            d = db._load_key(sn.DIRECTORY_KEY) or {}
            table = dict(d.get("aliases") or {})
            for _, r in _ed.iterrows():
                if pd.notna(r["HotSOS full name"]) and r["HotSOS full name"]:
                    table[r["Name on the sheet"]] = r["HotSOS full name"]
            db._upsert_key(sn.DIRECTORY_KEY, dict(d, aliases=table, approved_by=me,
                                                  approved_at=clock.stamp()))
            sn.apply_rename(table)
            _request("preview", st.session_state.get("hs_day"))
            st.rerun()
