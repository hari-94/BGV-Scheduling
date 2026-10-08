"""
HotSOS — push the day's final assignments into HotSOS.

This page never talks to HotSOS or SSRS itself. Both are inside the company,
so the work is done by hotsos_agent.py on the office PC; the page leaves it a
request in app_settings and shows what comes back. That is also why the page
says, first of all, whether the PC is listening -- a button that silently
does nothing is worse than no button.

Nothing reaches HotSOS until an RQS presses Push. Preview is the same run
without the last step, and is what to look at first.
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

st.set_page_config(page_title="HotSOS", page_icon="🛰️", layout="wide")
st.markdown("<style>.block-container{max-width:min(1200px,97%);}"
            "[data-testid='stSidebarNav']{display:none!important;}</style>",
            unsafe_allow_html=True)
auth.require_login()
ui.topnav("HotSOS")
if not auth.can("can_generate"):
    st.error("Only RQS and admins can push to HotSOS.")
    st.stop()

me = st.session_state.get("display_name") or auth.current_user().get("username", "")
ONLINE_SECONDS = 180


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


st.markdown("## 🛰️ HotSOS")

# ── is the office PC listening? ─────────────────────────────────────────────
beat = db._load_key(hs.HEARTBEAT_KEY) or {}
beat_age = _age(beat.get("at"))
online = beat_age is not None and beat_age < ONLINE_SECONDS
if online:
    st.success(f"Office PC **{beat.get('host', '')}** is connected "
               f"(last seen {_ago(beat_age)}).")
else:
    st.warning(f"The office PC isn't connected (last seen {_ago(beat_age)}). "
               "Requests will wait until it's back on.")

# ── push ─────────────────────────────────────────────────────────────────────
st.markdown("### Assign rooms in HotSOS")
st.caption("Reads the day's tab of **GC8 Inspections 2026** in SharePoint as it is "
           "when you press the button, so make call-off changes there first. "
           "Preview shows what would change; Push sends it.")

c1, c2, c3, c4 = st.columns([1.3, 1, 1, 2.2])
day = c1.date_input("Day", value=clock.today(), key="hs_day")
final = c4.checkbox("The sheet is final", key="hs_final",
                    help="Push is unlocked once you've confirmed the sheet is done.")


def _request(mode):
    db._upsert_key(hs.REQUEST_KEY, {"id": uuid.uuid4().hex, "date": str(day),
                                    "mode": mode, "by": me, "at": clock.stamp()})


if c2.button("Preview", use_container_width=True):
    _request("preview")
if c3.button("Push to HotSOS", type="primary", use_container_width=True,
             disabled=not final):
    _request("push")


ACTION_LABEL = {hs.ASSIGN: "✅ assign", hs.MOVE: "🔁 move", hs.ALREADY: "✔ already set",
                hs.NO_ROOM: "⚠ room not in HotSOS", hs.NO_PERSON: "⚠ name not matched",
                hs.NO_HSKP: "— nobody on sheet"}


@st.fragment(run_every=5)
def result_panel():
    req = db._load_key(hs.REQUEST_KEY) or {}
    res = db._load_key(hs.RESULT_KEY) or {}
    if req.get("id") and req["id"] != res.get("id"):
        st.info(f"⏳ {req.get('mode', '').title()} for {req.get('date')} requested by "
                f"{req.get('by')} — waiting for the office PC to pick it up…")
        return
    if not res:
        st.caption("No preview or push yet.")
        return
    if res.get("status") == "running":
        st.info(f"⏳ {res['mode'].title()} for {res['date']} is running…")
        return

    head = (f"**{res['mode'].title()}** for **{res['date']}** (tab “{res.get('tab', '?')}”) "
            f"by {res.get('by', '')}, finished {_ago(_age(res.get('finished_at')))}")
    if res.get("status") == "error":
        st.error(f"{head}\n\n{res.get('error')}")
        return
    counts = res.get("counts", {})
    if res["mode"] == "push":
        (st.success if res["status"] == "done" else st.warning)(
            f"{head} — **{res.get('sent', 0)} rooms sent to HotSOS**.")
    else:
        st.info(f"{head} — preview only, nothing was sent.")
    for e in res.get("errors", []):
        st.error(e)

    m = st.columns(5)
    m[0].metric("To assign", counts.get(hs.ASSIGN, 0))
    m[1].metric("To move", counts.get(hs.MOVE, 0))
    m[2].metric("Already set", counts.get(hs.ALREADY, 0))
    m[3].metric("Name not matched", counts.get(hs.NO_PERSON, 0))
    m[4].metric("Room not in HotSOS", counts.get(hs.NO_ROOM, 0))
    if res.get("unmatched_names"):
        st.warning("These names on the sheet aren't matched to a HotSOS attendant yet: "
                   f"**{', '.join(res['unmatched_names'])}**. Match them below, then "
                   "Preview again.")

    plan = res.get("plan") or []
    if plan:
        df = pd.DataFrame([{
            "Room": l["room"], "Service": l["service"], "Sheet": l["who"],
            "HotSOS attendant": l["hotsos_name"], "Now in HotSOS": l["current"],
            "Action": ACTION_LABEL.get(l["action"], l["action"]),
            "Result": l.get("outcome", ""),
        } for l in plan])
        svc = st.multiselect("Service", sorted(df["Service"].unique()),
                             key="hs_svc_filter", placeholder="All services")
        if svc:
            df = df[df["Service"].isin(svc)]
        st.dataframe(df, hide_index=True, use_container_width=True,
                     height=min(38 + 35 * len(df), 600))


result_panel()

# ── names ────────────────────────────────────────────────────────────────────
st.markdown("### Match sheet names to HotSOS")
st.caption("The sheet says “Amalia”; HotSOS knows a full name. Clear matches are "
           "made automatically; anything ambiguous is set here once and remembered.")
res = db._load_key(hs.RESULT_KEY) or {}
saved = db._load_key(hs.NAMES_KEY) or {}
options = res.get("attendants") or sorted(set(saved.values()))
rows = [{"Sheet name": k, "HotSOS attendant": v} for k, v in sorted(saved.items())]
rows += [{"Sheet name": n, "HotSOS attendant": None}
         for n in res.get("unmatched_names", []) if n not in saved]
if not options:
    st.caption("Run a Preview first — it brings back the list of HotSOS attendants.")
else:
    edited = st.data_editor(
        pd.DataFrame(rows or [{"Sheet name": "", "HotSOS attendant": None}]),
        num_rows="dynamic", hide_index=True, use_container_width=True,
        key=f"hs_names_{res.get('id', '')}",
        column_config={"HotSOS attendant": st.column_config.SelectboxColumn(
            options=options)})
    if st.button("Save names"):
        # An unpicked dropdown comes back as NaN, which is truthy -- test for
        # a real value, or "nobody chosen yet" is saved as a name.
        new = {str(r["Sheet name"]).strip(): r["HotSOS attendant"]
               for _, r in edited.iterrows()
               if pd.notna(r["Sheet name"]) and str(r["Sheet name"]).strip()
               and pd.notna(r["HotSOS attendant"]) and r["HotSOS attendant"]}
        db._upsert_key(hs.NAMES_KEY, new)
        st.success(f"Saved {len(new)} names. Press Preview to check them.")


st.caption("Staffing needs from SSRS are on the **Forecast** page.")
