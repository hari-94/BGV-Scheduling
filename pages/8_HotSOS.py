"""
HotSOS — push the day's final assignments into HotSOS, and keep one name per
person.

This page never talks to HotSOS or SSRS itself. Both are inside the company,
so the work is done by hotsos_agent.py on the office PC; the page leaves it a
request in app_settings and shows what comes back. That is also why the page
says, first of all, whether the PC is listening -- a button that silently
does nothing is worse than no button.

Two tabs:
  Push         Preview / Push, and the result read the way an RQS checks
               it: per housekeeper, changes first, problems on top.
  Staff names  The directory (staff_names.py): every name the team types,
               against the full name HotSOS knows. Approve it once, then
               rename the app to full names.

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

tab_push, tab_names = st.tabs(["📤 Push to HotSOS", "👥 Staff names"])

# ══════════════════════════════════════════════════════════════════════════════
#  PUSH
# ══════════════════════════════════════════════════════════════════════════════
with tab_push:
    st.caption("Reads the day's tab of **GC8 Inspections 2026** in SharePoint as it is when "
               "you press the button, so make call-off changes there first. **Preview** "
               "shows what would change; **Push** sends it.")
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
        res = db._load_key(hs.RESULT_KEY) or {}
        if req.get("id") and req["id"] != res.get("id"):
            st.info(f"⏳ {req.get('mode', '').title()} for {req.get('date')} asked by "
                    f"{req.get('by')} — waiting for the office PC…")
            return
        if not res or res.get("mode") == "staff":
            st.caption("No preview yet — press **Preview** to see what would change.")
            return
        if res.get("status") == "running":
            st.info(f"⏳ {res['mode'].title()} for {res['date']} is running — about a minute…")
            return

        head = (f"**{res['mode'].title()}** for **{res['date']}** · tab “{res.get('tab', '?')}” · "
                f"{res.get('by', '')} · {_ago(_age(res.get('finished_at')))}")
        if res.get("status") == "error":
            st.error(f"{head}\n\n{res.get('error')}")
            return
        if res["mode"] == "push":
            (st.success if res["status"] == "done" else st.warning)(
                f"{head} — **{res.get('sent', 0)} rooms sent to HotSOS**")
        else:
            st.info(f"{head} — preview only, nothing was sent")
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
                        + "</b> — set them on the <b>Staff names</b> tab, then Preview again.")
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

# ══════════════════════════════════════════════════════════════════════════════
#  STAFF NAMES
# ══════════════════════════════════════════════════════════════════════════════
with tab_names:
    st.caption("One name per person: the full name HotSOS knows. Approve the table once; "
               "after that, every Schedule.xlsx import and every push uses it, whatever "
               "spelling the sheet has that day.")
    att_rec = db._load_key(sn.ATTENDANTS_KEY) or {}
    attendants = att_rec.get("attendants") or []
    a1, a2 = st.columns([4, 1.3])
    a1.caption(f"HotSOS staff list: **{len(attendants)}** attendants · pulled "
               f"{_ago(_age(att_rec.get('pulled_at')))}")
    if a2.button("Refresh from HotSOS", use_container_width=True):
        _request("staff")
        st.toast("Asked the office PC to read HotSOS's staff list.")

    if not attendants:
        st.info("No HotSOS staff list yet — press **Refresh from HotSOS**.")
    else:
        approved = sn.aliases()
        rows = sn.suggest(sn.names_in_use(), attendants, approved)
        need = sum(r["how"] == "no match" for r in rows)
        st.markdown(f"**{len(rows)}** names on the recent schedule and roster · "
                    f"**{need}** need you to pick")
        only_need = st.toggle("Show only names that need a pick", value=need > 0,
                              key="sn_only_need")
        HOW = {"approved": "✅ approved", "already full": "✅ already full",
               "suggested": "💡 suggested", "no match": "❓ pick one"}
        shown = [r for r in rows if not only_need or r["how"] == "no match"]
        labels = sorted(a["label"] for a in attendants)
        edited = st.data_editor(
            pd.DataFrame([{"Name as typed": r["name"], "HotSOS full name": r["full"] or None,
                           "Status": HOW[r["how"]]} for r in shown]),
            hide_index=True, use_container_width=True, disabled=["Name as typed", "Status"],
            key=f"sn_editor_{only_need}_{len(approved)}",
            column_config={"HotSOS full name": st.column_config.SelectboxColumn(
                options=labels, help="Leave empty for someone who isn't in HotSOS")},
            height=min(38 + 35 * len(shown), 520))
        if st.button("Approve these names", type="primary"):
            table = dict(approved)
            # Rows hidden by the toggle keep their suggestion: approving the
            # short list must not throw away the long one.
            for r in rows:
                if r["full"] and r["full"] != r["name"]:
                    table[r["name"]] = r["full"]
            for _, r in edited.iterrows():
                v = r["HotSOS full name"]
                if pd.notna(v) and v and v != r["Name as typed"]:
                    table[r["Name as typed"]] = v
                else:
                    table.pop(r["Name as typed"], None)
            db._upsert_key(sn.DIRECTORY_KEY, {"aliases": table, "approved_by": me,
                                              "approved_at": clock.stamp()})
            st.success(f"Approved {len(table)} names.")
            st.rerun()

        if approved:
            st.markdown("#### Use full names in the app")
            plan = sn.plan_rename(approved)
            todo = len(plan["weeks"]) + len(plan["overrides"]) + len(plan["roster"]) + plan["charts"]
            if not todo:
                st.success("The app already uses the full names.")
            else:
                st.markdown(
                    f"Renames **{len(plan['roster'])}** people on the standing roster, "
                    f"**{len(plan['weeks'])}** stored weeks of the staff schedule, "
                    f"**{len(plan['overrides'])}** in-app roster edits and "
                    f"**{plan['charts']}** of today's charts. Past schedules keep the names "
                    "they were written with. New Schedule.xlsx imports are renamed on the way in.")
                ok = st.checkbox("I've checked the names above", key="sn_ok")
                if st.button("Rename to full names", disabled=not ok):
                    with st.spinner("Renaming…"):
                        out = sn.apply_rename(approved)
                    if out["failed"]:
                        st.error("Some renames failed:\n\n" + "\n\n".join(out["failed"]))
                    else:
                        st.success("Done: " + ", ".join(out["done"]))
