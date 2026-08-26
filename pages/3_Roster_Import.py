"""
Roster Import — the weekly staff Schedule.xlsx, stored, diffed and editable.

Upload the workbook weekly; the page stores each week, shows what changed since
last time, renders any week as an Excel-style grid, lets you correct cells in
the app, and exports a workbook with those corrections written back in.
"""
import streamlit as st
import sys, os, io, json, datetime
import html as _html
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, db, roster_import as ri

st.set_page_config(page_title="Roster Import · Cleaning Schedule",
                   page_icon="GC8", layout="wide")

st.markdown("""<style>
[data-testid="stSidebarNav"]{display:none !important;}
</style>""", unsafe_allow_html=True)

for _k, _v in [("logged_in", False), ("username", ""), ("role", "")]:
    if _k not in st.session_state: st.session_state[_k] = _v

auth.init_auth()
if not st.session_state.get("logged_in"):
    st.markdown('<div style="text-align:center;padding:60px 20px">'
                '<div style="font-size:1.2rem;font-weight:700;color:#1e293b">Not signed in</div>'
                '<div style="color:#64748b">Please sign in from the main page.</div></div>',
                unsafe_allow_html=True)
    st.stop()
if not auth.can("can_edit_roster"):
    st.error("Admin access required to import or edit the staff schedule.")
    st.stop()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500;600&display=swap');
:root{--bg:#f4f5f7;--bg2:#fff;--border:#e2e5ea;--border-hi:#c3c9d4;
  --indigo:#2563a8;--txt:#1f2733;--txt2:#5b6675;--txt3:#8a93a1;--radius:14px;--radius-sm:8px;}
*{box-sizing:border-box;}
html,body,[class*="css"]{font-family:'DM Sans',sans-serif!important;color:var(--txt)!important;}
.stApp{background:#f4f5f7!important;}
.block-container{padding-top:1.2rem!important;max-width:1400px;}
.pg-title{font-family:'Syne',sans-serif!important;font-size:1.6rem;font-weight:700;
  letter-spacing:-.03em;color:#16202e;margin:0 0 2px}
.pg-sub{font-size:.82rem;color:var(--txt2);margin:0 0 .8rem}
.sec{font-family:'DM Mono',monospace!important;font-size:.6rem;font-weight:500;
  text-transform:uppercase;letter-spacing:.16em;color:var(--txt2);
  padding-bottom:6px;border-bottom:1px solid var(--border);margin:1.2rem 0 .6rem}
.stamp{display:flex;flex-wrap:wrap;align-items:center;gap:10px 22px;background:#fff;
  border:1px solid var(--border);border-left:3px solid var(--indigo);border-radius:10px;
  padding:11px 16px;margin-bottom:14px}
.stamp .k{font-family:'DM Mono',monospace;font-size:.58rem;text-transform:uppercase;
  letter-spacing:.12em;color:var(--txt3);display:block;margin-bottom:2px}
.stamp .v{font-size:.85rem;font-weight:600;color:#16202e}
.pill{display:inline-block;border-radius:6px;padding:1px 8px;font-size:.68rem;font-weight:700}
.mono{font-family:'DM Mono',monospace;font-size:.72rem;color:var(--txt3)}
.gridwrap{overflow-x:auto;border:1px solid var(--border);border-radius:10px;background:#fff}
table.wk{border-collapse:collapse;width:100%;font-size:.76rem}
table.wk th{position:sticky;top:0;background:#f8fafc;padding:7px 9px;text-align:left;
  font-family:'DM Mono',monospace;font-size:.6rem;text-transform:uppercase;letter-spacing:.09em;
  color:var(--txt2);border-bottom:1px solid var(--border);white-space:nowrap}
table.wk td{padding:5px 9px;border-bottom:1px solid #eef1f5;vertical-align:top}
table.wk td.nm{font-weight:600;color:#16202e;white-space:nowrap;position:sticky;left:0;background:#fff}
table.wk tr.grp td{background:#eef2f7;font-family:'DM Mono',monospace;font-size:.6rem;
  text-transform:uppercase;letter-spacing:.11em;color:var(--txt2);font-weight:600}
.cell{display:block;border-radius:5px;padding:2px 6px;font-size:.72rem;line-height:1.3}
.chg{outline:2px solid #f59e0b;outline-offset:1px}
.ovr{box-shadow:inset 3px 0 0 #7c3aed}
footer{visibility:hidden!important;}#MainMenu{visibility:hidden!important;}
header[data-testid="stHeader"]{background:transparent!important;height:0!important;}
section[data-testid="stSidebar"]{background:#fff!important;border-right:1px solid var(--border)!important;}
.stButton>button{border-radius:var(--radius-sm)!important;font-weight:600!important;background:#fff!important;
  color:var(--txt)!important;border:1px solid var(--border-hi)!important;}
.stButton>button:hover{background:#2563a8!important;color:#fff!important;border-color:#2563a8!important;}
.stButton>button[kind="primary"]{background:#2563a8!important;border:none!important;color:#fff!important;}
@media (max-width:768px){
  .block-container{padding-left:.4rem!important;padding-right:.4rem!important;}
  .pg-title{font-size:1.3rem!important;}
  [data-testid="stHorizontalBlock"]{flex-direction:column!important;}
  [data-testid="stHorizontalBlock"] > [data-testid="column"]{width:100%!important;min-width:100%!important;}
}
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Navigate")
    st.page_link("cleaning_scheduler.py", label="Cleaning Schedule")
    st.page_link("pages/1_Dashboard.py", label="Dashboard")
    st.page_link("pages/3_Roster_Import.py", label="Roster Import")
    if auth.can("can_manage_users"):
        st.page_link("pages/2_Admin.py", label="Admin")

def e(s): return _html.escape(str(s) if s is not None else "")

KIND_STYLE = {
    ri.KIND_DAILY:   ("#ccfbf1", "#115e59"),
    ri.KIND_WORKING: ("#dcfce7", "#15803d"),
    ri.KIND_OFF:     ("#f8fafc", "#94a3b8"),
    ri.KIND_OTHER:   ("#fef3c7", "#92400e"),
    ri.KIND_UNKNOWN: ("#fee2e2", "#991b1b"),
}
KIND_LABEL = {ri.KIND_DAILY: "Daily Service", ri.KIND_WORKING: "Working",
              ri.KIND_OFF: "Off", ri.KIND_OTHER: "Other duty",
              ri.KIND_UNKNOWN: "Unrecognised"}
#: Must match the Schedule page's RQS selectbox "nobody" option exactly.
RQS_NONE = "— none —"

def human_ago(iso):
    try:
        then = datetime.datetime.fromisoformat(str(iso))
    except Exception:
        return str(iso or "—")
    now = datetime.datetime.now(then.tzinfo) if then.tzinfo else datetime.datetime.now()
    secs = (now - then).total_seconds()
    if secs < 90:            return "just now"
    if secs < 5400:          return f"{int(secs//60)} min ago"
    if secs < 172800:        return f"{int(secs//3600)} hours ago"
    return f"{int(secs//86400)} days ago"

# ══════════════════════════════════════════════════════════════════════════════
#  HEADER — last-loaded stamp
# ══════════════════════════════════════════════════════════════════════════════
meta = db.load_staff_meta() or {}
overrides = db.load_staff_overrides()
week_keys = db.staff_week_keys()

st.markdown('<p class="pg-title">Roster Import</p>', unsafe_allow_html=True)
st.markdown('<p class="pg-sub">The weekly staff schedule — stored, compared week to week, '
            'and editable here.</p>', unsafe_allow_html=True)

if meta.get("uploaded_at"):
    when = str(meta["uploaded_at"])[:16].replace("T", " ")
    fields = [
        ("Schedule last loaded", f'{when} <span style="color:#8a93a1;font-weight:400">'
                                 f'({human_ago(meta["uploaded_at"])})</span>'),
        ("By", e(meta.get("uploaded_by", "—"))),
        ("File", e(meta.get("file_name", "—"))),
        ("Weeks stored", f'{len(week_keys)}'),
        ("Covering", f'{e(meta.get("date_min","—"))} → {e(meta.get("date_max","—"))}'),
    ]
    if overrides:
        fields.append(("In-app edits", f'<span style="color:#7c3aed">{len(overrides)}</span>'))
    _fi = db.staff_file_info()
    fields.append(("Workbook stored",
                   f'<span style="color:#15803d">yes · {_fi["size"]/1024/1024:.1f} MB</span>'
                   if _fi.get("size") else '<span style="color:#b45309">no</span>'))
    _aa = db.load_autoapply() or {}
    fields.append(("Today auto-loaded",
                   f'<span style="color:#15803d">{e(_aa.get("date",""))}</span>'
                   if _aa.get("date") else '<span style="color:#8a93a1">not yet</span>'))
    st.markdown('<div class="stamp">' + "".join(
        f'<div><span class="k">{k}</span><span class="v">{v}</span></div>' for k, v in fields
    ) + '</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="stamp" style="border-left-color:#f59e0b">'
                '<div><span class="k">Schedule last loaded</span>'
                '<span class="v">Never — upload the workbook below</span></div></div>',
                unsafe_allow_html=True)

tab_week, tab_changes, tab_sync, tab_apply = st.tabs(
    ["Week view", "What changed", "Upload & sync", "Apply to roster"])

# ══════════════════════════════════════════════════════════════════════════════
#  UPLOAD & SYNC
# ══════════════════════════════════════════════════════════════════════════════
with tab_sync:
    st.markdown('<p class="sec">Upload the weekly workbook</p>', unsafe_allow_html=True)
    up = st.file_uploader("Schedule.xlsx", type=["xlsx", "xlsm"], key="ri_xlsx",
                          help="One sheet per week, Sunday–Saturday in columns B–H.")
    if up is not None:
        st.session_state["ri_raw_bytes"] = up.getvalue()
        st.session_state["ri_file_name"] = up.name

    raw = st.session_state.get("ri_raw_bytes")
    if not raw:
        st.info("Upload the workbook to compare it against what is stored. "
                "Nothing is written until you press **Save**.")
    else:
        @st.cache_data(show_spinner="Reading workbook…", max_entries=2)
        def _parse(raw_bytes: bytes):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True)
            return ri.parse_all_weeks(wb), len(wb.worksheets)

        try:
            incoming, n_sheets = _parse(raw)
        except Exception as ex:
            st.error(f"Could not read that workbook: {ex}")
            st.stop()
        if not incoming:
            st.error("No dated sheets found — is this the weekly schedule workbook?")
            st.stop()

        stored = db.load_staff_weeks()
        d = ri.diff_all(stored, incoming)
        st.success(f"Read **{n_sheets}** sheets · **{len(incoming)}** dated weeks "
                   f"from `{e(st.session_state.get('ri_file_name',''))}`")

        c = st.columns(4)
        c[0].metric("New weeks", len(d["new_weeks"]))
        c[1].metric("Weeks changed", len(d["changed_weeks"]))
        c[2].metric("Cells changed", d["n_changed_cells"])
        c[3].metric("Already stored", len(stored))

        if d["new_weeks"]:
            st.markdown(f'<div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;'
                        f'padding:9px 13px;font-size:.79rem;color:#065f46">'
                        f'<b>New week(s):</b> {e(", ".join(d["new_weeks"]))}</div>',
                        unsafe_allow_html=True)
        if d["gone_weeks"]:
            st.markdown(f'<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;'
                        f'padding:9px 13px;font-size:.79rem;color:#991b1b;margin-top:6px">'
                        f'<b>Stored but not in this file:</b> {e(", ".join(d["gone_weeks"]))} — '
                        f'these are kept, not deleted.</div>', unsafe_allow_html=True)

        if d["changed_weeks"]:
            st.markdown('<p class="sec">Changed cells</p>', unsafe_allow_html=True)
            rows = []
            for wk, dd in sorted(d["changed_weeks"].items()):
                for ch in dd["changed"]:
                    rows.append({"Week": wk, "Person": ch["name"], "Date": ch["date"],
                                 "Was": ch["old"] or "—", "Now": ch["new"] or "—"})
                for n in dd["added_people"]:
                    rows.append({"Week": wk, "Person": n, "Date": "—",
                                 "Was": "not on sheet", "Now": "added"})
                for n in dd["removed_people"]:
                    rows.append({"Week": wk, "Person": n, "Date": "—",
                                 "Was": "on sheet", "Now": "removed"})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                         height=min(60 + 35 * len(rows), 420))

        clash = [k for k in overrides
                 if k.split("|", 2)[0] in d["changed_weeks"] and any(
                     ch["name"] == k.split("|", 2)[1] and ch["date"] == k.split("|", 2)[2]
                     for ch in d["changed_weeks"][k.split("|", 2)[0]]["changed"])]
        if clash:
            st.warning(f"**{len(clash)}** of your in-app edits sit on cells that also changed "
                       f"in this file. Your edits win and are kept — the Week view shows the "
                       f"Excel value underneath each one so you can revert if you'd rather.")

        if not d["new_weeks"] and not d["changed_weeks"]:
            st.info("Nothing new — the stored copy already matches this workbook.")

        if st.button("Save to app", type="primary", key="ri_save"):
            touched = set(d["new_weeks"]) | set(d["changed_weeks"])
            with st.spinner(f"Saving {len(touched) or len(incoming)} week(s)…"):
                to_write = touched if stored else set(incoming)
                ok, failed = 0, []
                for wk in sorted(to_write):
                    try:
                        db.save_staff_week(wk, incoming[wk]); ok += 1
                    except Exception as ex:
                        failed.append(f"{wk}: {ex}")
                all_dates = sorted(x for w in incoming.values() for x in w["dates"])
                try:
                    db.save_staff_meta({
                        "uploaded_at": datetime.datetime.now().isoformat(timespec="seconds"),
                        "uploaded_by": st.session_state.get("username", "unknown"),
                        "file_name":   st.session_state.get("ri_file_name", ""),
                        "n_sheets":    n_sheets,
                        "n_weeks":     len(incoming),
                        "date_min":    all_dates[0] if all_dates else "",
                        "date_max":    all_dates[-1] if all_dates else "",
                        "last_diff": {
                            "new_weeks": d["new_weeks"],
                            "n_changed_cells": d["n_changed_cells"],
                            # Bounded so the meta row stays small.
                            "changed": [
                                {"week": wk, **ch}
                                for wk, dd in sorted(d["changed_weeks"].items())
                                for ch in dd["changed"]][:500],
                        },
                    })
                except Exception as ex:
                    failed.append(f"meta: {ex}")
                # Keep the workbook itself so the Excel export works any day,
                # not only in a session where someone happened to upload it.
                try:
                    db.save_staff_file(raw, st.session_state.get("ri_file_name", ""))
                except Exception as ex:
                    failed.append(f"workbook: {ex}")
                # A fresh upload supersedes today's auto-apply, so let it re-run.
                try:
                    db.save_autoapply({})
                except Exception:
                    pass
            if failed:
                st.error("Some writes failed:\n\n" + "\n\n".join(f"- {f}" for f in failed))
            else:
                st.success(f"Saved {ok} week(s). Timestamp updated.")
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
#  WEEK VIEW — Excel-style grid + editing
# ══════════════════════════════════════════════════════════════════════════════
with tab_week:
    if not week_keys:
        st.info("No weeks stored yet. Upload the workbook on the **Upload & sync** tab.")
    else:
        today_iso = datetime.date.today().isoformat()
        default_wk = max([w for w in week_keys if w <= today_iso], default=week_keys[-1])
        cc = st.columns([2, 2, 3])
        with cc[0]:
            sel_wk = st.selectbox("Week", week_keys,
                                  index=week_keys.index(default_wk), key="ri_wk",
                                  format_func=lambda w: f"Week of {w}")
        week = db.load_staff_week(sel_wk)
        if not week:
            st.error(f"Could not load week {sel_wk}.")
            st.stop()
        eff, applied = ri.apply_overrides(week, overrides, sel_wk)
        last_diff = (meta.get("last_diff") or {})
        changed_set = {(ch["name"], ch["date"]) for ch in last_diff.get("changed", [])
                       if ch.get("week") == sel_wk}
        with cc[1]:
            groups = ["All", "Housekeepers", "RQS", "Other teams"]
            sel_grp = st.selectbox("Show", groups, key="ri_grp")
        with cc[2]:
            st.markdown(
                f'<div style="padding-top:26px;font-size:.76rem;color:#5b6675">'
                f'Sheet <b>{e(week["sheet"])}</b> &nbsp;·&nbsp; {len(eff["people"])} people'
                f'{" &nbsp;·&nbsp; <span style=\"color:#7c3aed\">" + str(len(applied)) + " edited here</span>" if applied else ""}'
                f'{" &nbsp;·&nbsp; <span style=\"color:#b45309\">" + str(len(changed_set)) + " changed at last sync</span>" if changed_set else ""}'
                f'</div>', unsafe_allow_html=True)

        def wanted(rec):
            if sel_grp == "All": return True
            if sel_grp == "Housekeepers": return rec["group"] == "hk"
            if sel_grp == "RQS": return rec["group"] == "rqs"
            return rec["group"] == "other"

        st.markdown(
            '<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:.7rem;color:#5b6675;margin:.5rem 0">'
            + "".join(f'<span><span class="pill" style="background:{b};color:{f}">&nbsp;&nbsp;</span> {KIND_LABEL[k]}</span>'
                      for k, (b, f) in KIND_STYLE.items())
            + '<span><span class="pill" style="background:#fff;color:#f59e0b;outline:2px solid #f59e0b">&nbsp;&nbsp;</span> changed at last sync</span>'
              '<span><span class="pill" style="background:#fff;box-shadow:inset 3px 0 0 #7c3aed">&nbsp;&nbsp;</span> edited in app</span>'
            + '</div>', unsafe_allow_html=True)

        # ── grid ──────────────────────────────────────────────────────────────
        dates = eff["dates"]
        head = "".join(
            f'<th>{datetime.date.fromisoformat(dt).strftime("%a")}<br>'
            f'<span style="font-weight:400;color:#8a93a1">{dt[5:]}</span></th>' for dt in dates)
        body, current = [], None
        for name, rec in eff["people"].items():
            if not wanted(rec): continue
            if rec["section"] != current:
                current = rec["section"]
                body.append(f'<tr class="grp"><td colspan="{len(dates)+1}">{e(current)}</td></tr>')
            tds = []
            for dt in dates:
                raw = rec["cells"].get(dt, "")
                kind = ri.classify(raw)
                bg, fg = KIND_STYLE[kind]
                cls = "cell"
                if (name, dt) in changed_set: cls += " chg"
                tip = ""
                if (name, dt) in applied:
                    cls += " ovr"
                    was = applied[(name, dt)]["excel"] or "(blank)"
                    tip = f' title="Edited in app · Excel says: {e(was)}"'
                tds.append(f'<td><span class="{cls}" style="background:{bg};color:{fg}"{tip}>'
                           f'{e(raw) or "&nbsp;"}</span></td>')
            body.append(f'<tr><td class="nm">{e(name)}</td>{"".join(tds)}</tr>')
        st.markdown(f'<div class="gridwrap"><table class="wk"><thead><tr><th>Name</th>{head}</tr>'
                    f'</thead><tbody>{"".join(body)}</tbody></table></div>',
                    unsafe_allow_html=True)

        # ── editing ───────────────────────────────────────────────────────────
        st.markdown('<p class="sec">Edit this week</p>', unsafe_allow_html=True)
        st.caption("Change any cell and press Save. Edits are kept as overrides — they "
                   "survive re-uploading the workbook, and the grid marks them in purple. "
                   "Clear a cell to mark that person off.")
        cols_lbl = [f'{datetime.date.fromisoformat(dt).strftime("%a")} {dt[5:]}' for dt in dates]
        rows = [{"Name": n, **{cols_lbl[i]: rec["cells"].get(dt, "")
                               for i, dt in enumerate(dates)}}
                for n, rec in eff["people"].items() if wanted(rec)]
        base = pd.DataFrame(rows, columns=["Name"] + cols_lbl)
        edited = st.data_editor(
            base, hide_index=True, use_container_width=True, key=f"ri_ed_{sel_wk}_{sel_grp}",
            height=min(120 + 35 * len(base), 520), num_rows="fixed",
            column_config={"Name": st.column_config.TextColumn("Name", disabled=True, width="medium")},
        )
        b1, b2, _ = st.columns([1, 1, 3])
        with b1:
            if st.button("Save edits", type="primary", key="ri_save_ed"):
                new_ov = dict(overrides)
                added = removed = 0
                for _, row in edited.iterrows():
                    name = row["Name"]
                    src = week["people"].get(name, {}).get("cells", {})
                    for i, dt in enumerate(dates):
                        val = str(row[cols_lbl[i]] or "").strip()
                        excel_val = str(src.get(dt, "") or "")
                        key = ri.override_key(sel_wk, name, dt)
                        if val == excel_val:
                            # Back to what the workbook says — drop the override
                            # instead of storing a no-op.
                            if key in new_ov: del new_ov[key]; removed += 1
                        elif new_ov.get(key, {}).get("value", None) != val:
                            new_ov[key] = {
                                "value": val,
                                "by": st.session_state.get("username", "unknown"),
                                "at": datetime.datetime.now().isoformat(timespec="seconds")}
                            added += 1
                if not added and not removed:
                    st.info("No changes to save.")
                else:
                    try:
                        db.save_staff_overrides(new_ov)
                        st.success(f"Saved — {added} edit(s) recorded, {removed} reverted.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Could not save edits: {ex}")
        with b2:
            wk_ov = [k for k in overrides if k.split("|", 2)[0] == sel_wk]
            if wk_ov and st.button(f"Revert all ({len(wk_ov)})", key="ri_revert"):
                try:
                    db.save_staff_overrides({k: v for k, v in overrides.items() if k not in wk_ov})
                    st.success(f"Reverted {len(wk_ov)} edit(s) for this week.")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Could not revert: {ex}")

# ══════════════════════════════════════════════════════════════════════════════
#  WHAT CHANGED
# ══════════════════════════════════════════════════════════════════════════════
with tab_changes:
    last_diff = (meta.get("last_diff") or {})
    if not meta.get("uploaded_at"):
        st.info("Nothing loaded yet.")
    else:
        st.markdown(f'<p class="sec">At the last sync — {str(meta["uploaded_at"])[:16].replace("T"," ")}'
                    f' by {e(meta.get("uploaded_by","—"))}</p>', unsafe_allow_html=True)
        c = st.columns(3)
        c[0].metric("New weeks added", len(last_diff.get("new_weeks", [])))
        c[1].metric("Cells changed", last_diff.get("n_changed_cells", 0))
        c[2].metric("In-app edits live", len(overrides))
        if last_diff.get("new_weeks"):
            st.markdown(f'<div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;'
                        f'padding:9px 13px;font-size:.79rem;color:#065f46">'
                        f'<b>New:</b> {e(", ".join(last_diff["new_weeks"]))}</div>',
                        unsafe_allow_html=True)
        ch = last_diff.get("changed", [])
        if ch:
            st.markdown('<p class="sec">Cell changes</p>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame([{"Week": x.get("week", ""), "Person": x.get("name", ""),
                                        "Date": x.get("date", ""), "Was": x.get("old") or "—",
                                        "Now": x.get("new") or "—"} for x in ch]),
                         use_container_width=True, hide_index=True,
                         height=min(60 + 35 * len(ch), 460))
            if last_diff.get("n_changed_cells", 0) > len(ch):
                st.caption(f"Showing the first {len(ch)} of "
                           f"{last_diff['n_changed_cells']} changes.")
        elif not last_diff.get("new_weeks"):
            st.info("The last upload matched what was already stored.")

        if overrides:
            st.markdown('<p class="sec">In-app edits</p>', unsafe_allow_html=True)
            orows = []
            for k, v in sorted(overrides.items()):
                try: wk, name, dt = k.split("|", 2)
                except ValueError: continue
                orows.append({"Week": wk, "Person": name, "Date": dt,
                              "Set to": v.get("value") or "(cleared)",
                              "By": v.get("by", ""), "When": str(v.get("at", ""))[:16].replace("T", " ")})
            st.dataframe(pd.DataFrame(orows), use_container_width=True, hide_index=True,
                         height=min(60 + 35 * len(orows), 320))

        # ── export ────────────────────────────────────────────────────────────
        st.markdown('<p class="sec">Export back to Excel</p>', unsafe_allow_html=True)
        file_info = db.staff_file_info()
        if not overrides:
            st.caption("No in-app edits to write back yet.")
        elif not (st.session_state.get("ri_raw_bytes") or file_info.get("size")):
            st.info("No workbook stored yet — upload it on the **Upload & sync** tab.")
        else:
            src = ("this session's upload" if st.session_state.get("ri_raw_bytes")
                   else f'the stored copy ({e(file_info.get("file_name","")) or "workbook"}, '
                        f'saved {str(file_info.get("saved_at",""))[:16].replace("T"," ")})')
            st.caption(f"Writes every in-app edit into a copy of {src}. Formulas and cell "
                       f"comments are preserved. Download it and put it back on OneDrive "
                       f"to bring Excel in line with the app.")
            if st.button("Build updated workbook", key="ri_export"):
                try:
                    raw = st.session_state.get("ri_raw_bytes")
                    if not raw:
                        with st.spinner("Fetching the stored workbook…"):
                            raw, _fi = db.load_staff_file()
                    if not raw:
                        st.error("The stored workbook could not be read.")
                        st.stop()
                    stored_weeks = db.load_staff_weeks()
                    out, n, skipped = ri.write_overrides_to_workbook(raw, stored_weeks, overrides)
                    st.session_state["ri_export_bytes"] = out
                    st.session_state["ri_export_note"] = (n, len(skipped))
                except Exception as ex:
                    st.error(f"Export failed: {ex}")
            if st.session_state.get("ri_export_bytes"):
                n, n_skip = st.session_state.get("ri_export_note", (0, 0))
                if n_skip:
                    st.warning(f"{n_skip} edit(s) could not be placed — their sheet or row "
                               f"is no longer in the stored workbook.")
                st.success(f"{n} edit(s) written.")
                st.download_button(
                    "Download updated Schedule.xlsx",
                    data=st.session_state["ri_export_bytes"],
                    file_name=f"Schedule_updated_{datetime.date.today():%Y%m%d}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="ri_dl")

# ══════════════════════════════════════════════════════════════════════════════
#  APPLY TO ROSTER
# ══════════════════════════════════════════════════════════════════════════════
with tab_apply:
    if not week_keys:
        st.info("No weeks stored yet. Upload the workbook on the **Upload & sync** tab.")
    else:
        all_days = []
        for wk in week_keys:
            base = datetime.date.fromisoformat(wk)
            all_days += [base + datetime.timedelta(days=i) for i in range(7)]
        all_days = sorted(set(all_days))
        today = datetime.date.today()
        default = today if today in all_days else min(all_days, key=lambda d: abs((d - today).days))
        c1, c2 = st.columns([1, 2])
        with c1:
            picked = st.date_input("Schedule date", value=default,
                                   min_value=all_days[0], max_value=all_days[-1], key="ri_day")
        wk_for = max([w for w in week_keys if w <= picked.isoformat()], default=None)
        week = db.load_staff_week(wk_for) if wk_for else None
        if not week or picked.isoformat() not in week["dates"]:
            st.warning(f"**{picked:%A, %B %d, %Y}** is not in any stored week.")
            st.stop()
        eff, _applied = ri.apply_overrides(week, overrides, wk_for)
        people = ri.week_to_people(eff, picked.isoformat())
        update = ri.build_roster_update(people, st.session_state.get("hk_roster", {}))
        with c2:
            st.markdown(f'<div style="padding-top:26px;font-size:.79rem;color:#5b6675">'
                        f'From sheet <b>{e(week["sheet"])}</b> · week of {e(wk_for)}</div>',
                        unsafe_allow_html=True)

        n_hk = sum(1 for v in update["hk_roster"].values() if v["present"])
        n_ins = sum(1 for v in update["insp_roster"].values() if v)
        m = st.columns(4)
        m[0].metric("Housekeepers present", n_hk)
        m[1].metric("On Daily Service", len(update["ds_team"]))
        m[2].metric("Inspectors present", n_ins)
        m[3].metric("RQS 1 / RQS 2", f'{update["rqs1"] or "—"} / {update["rqs2"] or "—"}')

        if update["building_changes"]:
            rows = "<br>".join(f'&nbsp;&nbsp;<b>{e(n)}</b>: Building {o} → Building {w}'
                               for n, o, w in update["building_changes"])
            st.markdown(f'<div style="background:#fffbeb;border:1px solid #fcd34d;border-radius:8px;'
                        f'padding:10px 13px;font-size:.78rem;color:#92400e;margin-top:8px">'
                        f'<b>{len(update["building_changes"])} building change(s)</b> — the sheet '
                        f'will overwrite the current roster:<br>{rows}</div>', unsafe_allow_html=True)
        if update["new_people"]:
            st.markdown(f'<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;'
                        f'padding:10px 13px;font-size:.78rem;color:#1e40af;margin-top:8px">'
                        f'<b>{len(update["new_people"])} new name(s)</b>: '
                        f'{e(", ".join(update["new_people"]))} — check these are not a '
                        f're-spelling of someone already on the roster.</div>', unsafe_allow_html=True)
        if update["unknown"]:
            st.markdown(f'<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;'
                        f'padding:10px 13px;font-size:.78rem;color:#991b1b;margin-top:8px">'
                        f'<b>{len(update["unknown"])} cell(s) not recognised</b>, treated as NOT '
                        f'available: {", ".join(f"<b>{e(n)}</b> ({e(v)})" for n, v in update["unknown"])}'
                        f'</div>', unsafe_allow_html=True)

        st.markdown('<p class="sec">Detail</p>', unsafe_allow_html=True)
        det = pd.DataFrame([{"Name": p["name"], "Section": p["section"],
                             "Status": KIND_LABEL[p["kind"]], "Cell": p["raw"] or "—"}
                            for p in people])
        st.dataframe(det, use_container_width=True, hide_index=True,
                     height=min(60 + 33 * len(det), 460))

        st.markdown('<p class="sec">Apply</p>', unsafe_allow_html=True)
        o = st.columns(3)
        do_hk = o[0].checkbox("Housekeepers + buildings", value=True, key="ri_do_hk")
        do_rqs = o[1].checkbox("Inspectors + RQS 1/2", value=True, key="ri_do_rqs")
        do_ds = o[2].checkbox("Daily Service team", value=True, key="ri_do_ds")
        keep = st.checkbox("Keep people not on this sheet (mark absent instead of removing)",
                           value=False, key="ri_keep")
        st.caption(f"Then open the Schedule page and press **Generate** to build "
                   f"{picked:%b %d}'s charts.")

        if st.button("Apply to roster", type="primary", key="ri_apply"):
            applied_msg = []
            if do_hk:
                new_roster = dict(update["hk_roster"])
                if keep:
                    for name, v in st.session_state.get("hk_roster", {}).items():
                        if name not in new_roster:
                            new_roster[name] = {"building": v.get("building", 1), "present": False}
                st.session_state["hk_roster"] = new_roster
                for k in [k for k in list(st.session_state) if k.startswith("att_")]:
                    del st.session_state[k]
                applied_msg.append(f"{sum(1 for v in new_roster.values() if v['present'])} "
                                   f"housekeepers present of {len(new_roster)}")
            if do_rqs:
                new_insp = dict(update["insp_roster"])
                if keep:
                    for name, v in st.session_state.get("insp_roster", {}).items():
                        new_insp.setdefault(name, False)
                st.session_state["insp_roster"] = new_insp
                for k in [k for k in list(st.session_state) if k.startswith("insp_att_")]:
                    del st.session_state[k]
                st.session_state["rqs1"] = update["rqs1"]
                st.session_state["rqs2"] = update["rqs2"]
                # Point the Schedule page's RQS selectboxes at these people.
                # Clearing their keys instead would reset them to "no one" and
                # overwrite rqs1/rqs2 the next time that page runs.
                for k, v in (("rqs1_sel", update["rqs1"]), ("rqs2_sel", update["rqs2"])):
                    st.session_state[k] = v if (v and new_insp.get(v)) else RQS_NONE
                applied_msg.append(f"{sum(1 for v in new_insp.values() if v)} inspectors present")
            if do_ds:
                roster_now = st.session_state.get("hk_roster", {})
                team = ([n for n in update["ds_team"] if roster_now.get(n, {}).get("present")]
                        if do_hk else list(update["ds_team"]))
                st.session_state["ds_team"] = team
                applied_msg.append(f"{len(team)} on the Daily Service team")
            if not applied_msg:
                st.warning("Nothing selected to apply.")
            else:
                if do_hk or do_rqs:
                    try:
                        db.save_roster(st.session_state.get("hk_roster", {}),
                                       st.session_state.get("insp_roster", {}))
                    except Exception as ex:
                        st.warning(f"Applied to this session, but saving to the database "
                                   f"failed — it will not survive a reload. ({ex})")
                st.session_state["roster_import_note"] = (
                    f"{picked:%b %d, %Y} from sheet '{week['sheet']}'")
                st.success("Applied — " + "; ".join(applied_msg) + ".")
