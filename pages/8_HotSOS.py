"""
HotSOS — push the day's final assignments into HotSOS, and keep one name per
person.

This page never talks to HotSOS or SSRS itself. Both are inside the company,
so the work is done by hotsos_agent.py on the office PC; the page leaves it a
request in app_settings and shows what comes back. That is also why the page
says, first of all, whether the PC is listening -- a button that silently
does nothing is worse than no button.

The result reads the way an RQS checks it: per housekeeper, changes first,
problems on top. Names come from the staff directory (staff_names.py), whose
full names are HotSOS's own; a name it doesn't know gets a small box to match
it once, and the app is renamed to follow.

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
import hotsos_sync as hs            # noqa: E402
import staff_names as sn            # noqa: E402

st.set_page_config(page_title="HotSOS", page_icon="🛰️", layout="wide")
st.markdown("""<style>
.block-container{max-width:min(1200px,97%);}
[data-testid='stSidebarNav']{display:none!important;}
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
.attn{background:#fff8eb;border:1px solid #f6d58e;border-radius:12px;padding:10px 14px;margin:6px 0 12px;
      font-size:.85rem;color:#5c3d00}
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


def _request(mode, day=None):
    db._upsert_key(hs.REQUEST_KEY, {"id": uuid.uuid4().hex,
                                    "date": str(day or clock.today()),
                                    "mode": mode, "by": me, "at": clock.stamp()})


SVC = {"full clean": "FC", "daily service": "DS", "dust n vac": "DV"}


def _svc(s):
    return SVC.get(str(s).strip().lower(), str(s)[:2].upper())


st.markdown("## 🛰️ HotSOS")
beat = db._load_key(hs.HEARTBEAT_KEY) or {}
beat_age = _age(beat.get("at"))
if beat_age is not None and beat_age < ONLINE_SECONDS:
    st.caption(f"🟢 Office PC **{beat.get('host', '')}** connected · last seen {_ago(beat_age)}")
else:
    st.warning(f"The office PC isn't connected (last seen {_ago(beat_age)}). "
               "Requests will wait until it's back on.")

# ── today's sheet: built at 5 AM, edited by the team, pushed when final ───
import daily_build  # noqa: E402
_b = db._load_key(daily_build.BUILD_KEY) or {}
_bc1, _bc2 = st.columns([4, 1.3])
if _b.get("date") == clock.today_iso() and _b.get("status") == "done":
    _arr = "✓ Arrival Report" if _b.get("arrival") else "⚠️ no Arrival Report found"
    _bc1.markdown(
        f"📄 **Today's sheet** — tab **{_b.get('tab')}** in **{_b.get('workbook')}** "
        f"(SharePoint › Office › GC8 Inspections) · built "
        f"{_ago(_age(_b.get('finished_at')))} by {_b.get('by')} · {_b.get('rooms')} rooms, "
        f"{_b.get('charts')} charts · {_arr}"
        + (" · *kept: someone has edited it*" if "edited" in str(_b.get("outcome")) else ""))
    if _b.get("dv_unassigned"):
        st.warning(f"No RQS 2 on today's staff schedule, so {_b['dv_unassigned']} Dust n Vac "
                   "rooms have no one in HSKP. Put today's RQS 2 on them in the sheet before "
                   "pushing — or mark RQS 2 in Schedule.xlsx and the 5 AM draft fills them in.")
elif _b.get("status") == "running":
    _bc1.info("⏳ Building today's sheet…")
elif _b.get("status") == "error" and _b.get("date") == clock.today_iso():
    _bc1.error(f"Today's sheet wasn't built: {_b.get('error')}")
else:
    _bc1.caption("📄 Today's sheet hasn't been built yet — it's built at 5 AM.")
if _bc2.button("Build today's sheet", use_container_width=True,
               help="Builds the schedule like pressing Generate, and writes today's tab. "
                    "A tab someone has already edited is never overwritten."):
    _request("build", clock.today())
    st.toast("Asked the office PC to build today's sheet.")

st.caption("Edit the day's tab in SharePoint (call-offs, swaps), then **Preview** to see "
           "what would change and **Push** when it's final — that updates HotSOS and the "
           "app's charts.")
c1, c2, c3, c4 = st.columns([1.3, 1, 1, 2.2])
day = c1.date_input("Day", value=clock.today(), key="hs_day")
final = c4.checkbox("The sheet is final", key="hs_final",
                    help="Push is unlocked once you've confirmed the sheet is done.")
if c2.button("Preview", use_container_width=True):
    _request("preview", day)
if c3.button("Push to HotSOS", type="primary", use_container_width=True,
             disabled=not final):
    _request("push", day)

@st.fragment(run_every=5)
def result_panel():
    req = db._load_key(hs.REQUEST_KEY) or {}
    cur = db._load_key(hs.RESULT_KEY) or {}
    # What's happening now goes in a banner; below it stays the last run that
    # finished, until a newer one replaces it -- a press never blanks the page.
    if req.get("id") and req["id"] != cur.get("id"):
        st.info(f"⏳ {req.get('mode', '').title()} for {req.get('date')} asked by "
                f"{req.get('by')} — waiting for the office PC… (last result below)")
    elif cur.get("status") == "running":
        st.info(f"⏳ {cur['mode'].title()} for {cur['date']} is running — about a minute… "
                "(last result below)")
    elif cur.get("status") == "error":
        st.error(f"{cur.get('mode', '').title()} for {cur.get('date')} · "
                 f"{_ago(_age(cur.get('finished_at')))}: {cur.get('error')}")
    res = db._load_key(hs.LAST_KEY) or (cur if cur.get("plan") is not None else {})
    if not res:
        st.caption("No preview yet — press **Preview** to see what would change.")
        return

    head = (f"**{res['mode'].title()}** for **{res['date']}** · tab “{res.get('tab', '?')}” · "
            f"{res.get('by', '')} · {_ago(_age(res.get('finished_at')))}")
    if res.get("sheet_saved_at"):
        _sv = _dt.datetime.fromisoformat(res["sheet_saved_at"]).astimezone(clock.MTN)
        head += (f"  \n📄 Read the sheet as saved at **{_sv:%I:%M:%S %p}**".replace(" 0", " ")
                 + " — if your last edit is newer, wait a few seconds and Preview again.")
    if res["mode"] == "push":
        (st.success if res["status"] == "done" else st.warning)(
            f"{head} — **{res.get('sent', 0)} rooms sent to HotSOS**"
            + (f" · app charts updated ({res['app']['renamed']} charts changed hands, "
               f"{res['app']['moved']} rooms moved)" if (res.get("app") or {}).get("changed")
               else ""))
    else:
        st.info(f"{head} — preview only, nothing was sent")
    if res.get("warning"):
        st.warning(res["warning"])
    for err in res.get("errors", []):
        st.error(err)

    plan = res.get("plan") or []
    n = {a: sum(1 for l in plan if l["action"] == a) for a in
         (hs.ASSIGN, hs.MOVE, hs.ALREADY, hs.NO_PERSON, hs.NO_ROOM, hs.NO_HSKP)}
    m = st.columns(4)
    m[0].metric("Will change", n[hs.ASSIGN] + n[hs.MOVE],
                help=f"{n[hs.ASSIGN]} new, {n[hs.MOVE]} moved from someone else")
    m[1].metric("Already right", n[hs.ALREADY])
    m[2].metric("Need attention", n[hs.NO_PERSON] + n[hs.NO_ROOM])
    m[3].metric("No housekeeper", n[hs.NO_HSKP], help="Left as they are in HotSOS")

    # Problems first, in words someone can act on.
    attn = []
    if res.get("unmatched_names"):
        attn.append("Names not matched to anyone in HotSOS: <b>"
                    + e(", ".join(res["unmatched_names"]))
                    + "</b> — match them in the box below.")
    miss = [l["room"] for l in plan if l["action"] == hs.NO_ROOM]
    if miss:
        attn.append(f"Rooms HotSOS doesn't have today: <b>{e(', '.join(miss))}</b>")
    if attn:
        st.markdown('<div class="attn">⚠️ ' + "<br>⚠️ ".join(attn) + "</div>",
                    unsafe_allow_html=True)

    only_changes = st.toggle("Show only rooms that will change", value=True,
                             key="hs_only_changes")
    by_person = {}
    for l in plan:
        if l.get("hotsos_name"):
            by_person.setdefault(l["hotsos_name"], []).append(l)
    cards = []
    for person, lines in sorted(by_person.items(),
                                key=lambda kv: (-sum(l["action"] in (hs.ASSIGN, hs.MOVE)
                                                     for l in kv[1]), kv[0])):
        shown = [l for l in lines if not only_changes
                 or l["action"] in (hs.ASSIGN, hs.MOVE)]
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
                     f'<div class="hk-meta">{len(lines)} rooms ({e(svcs)}) · '
                     f'{chg} to change</div>{"".join(chips)}</div>')
    if cards:
        cols = st.columns(3)
        for i, c in enumerate(cards):
            cols[i % 3].markdown(c, unsafe_allow_html=True)
        st.caption("🔵 new · 🟠 moved from someone else (hover for who) · ⚪ already "
                   "right · green outline = sent")
    elif only_changes:
        st.success("Nothing to change — HotSOS already matches the sheet.")

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
