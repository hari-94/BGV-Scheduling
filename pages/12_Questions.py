"""
Questions — the few decisions the 5 AM run has to guess today, put to the
managers (manager_questions). Managers only, like Report and Stats.

Each manager's answers are one app_settings row (mq_<username>), written when
they press Save. The second tab lays everyone's answers side by side for
whoever turns them into rules.
"""
import html
import io
import json
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, clock, db, ui            # noqa: E402
import fresh                          # noqa: E402
import manager_questions as mq        # noqa: E402

st.set_page_config(page_title="Questions", page_icon="❓", layout="wide")
st.markdown("""<style>
.block-container{max-width:min(860px,97%);}
[data-testid='stSidebarNav']{display:none!important;}
.mq-h1{font-size:1.55rem;font-weight:800;color:#16202e;margin:0;line-height:1.2}
.mq-sub{font-size:.95rem;color:#4b5667;margin:4px 0 8px;line-height:1.45}
.mq-part{font-size:.76rem;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:#2a6fd6;
         margin:16px 0 4px}
.mq-q{font-size:1.02rem;font-weight:700;color:#16202e;line-height:1.35;margin:0 0 3px}
.mq-n{color:#2a6fd6;margin-right:6px}
.mq-now{font-size:.86rem;color:#5b6675;margin:0 0 6px;line-height:1.4}
.mq-now b{color:#3b4656}
.mq-lbl{font-size:.875rem;color:#31333f;margin:2px 0 0}
.mq-who{font-size:.9rem;color:#1f2733;margin:3px 0;line-height:1.45}
.mq-who b{color:#16202e}
.mq-none{color:#9aa3af}
.stTabs [data-baseweb='tab']{padding:4px 12px}
</style>""", unsafe_allow_html=True)

auth.require_login()
fresh.latest("i18n", "ui", "manager_questions")   # the menu and questions as they are on disk
ui.topnav("Questions")
# Managers only -- the same permission Report and Stats use; auth is an
# imported module and a running app keeps its old copy, so no new permission.
if not auth.can("can_manage_users"):
    st.error("These questions are for managers.")
    st.stop()

e = html.escape
user = auth.current_user().get("username", "")
me = st.session_state.get("display_name") or user
KEY = mq.KEY_PREFIX + user


def _payload(p):
    return json.loads(p) if isinstance(p, str) else (p or {})


def _load_mine():
    try:
        return db._load_key(KEY) or {}
    except Exception as ex:
        st.error(f"Couldn't load your saved answers: {ex}")
        return {}


def _when(stamp):
    """'Oct 15, 2:05 PM' from a stored ISO stamp."""
    import datetime as _dt
    try:
        t = _dt.datetime.fromisoformat(str(stamp))
        return t.strftime("%b %d, %I:%M %p").replace(" 0", " ")
    except ValueError:
        return str(stamp)[:16].replace("T", " ")


def _wkey(q, fkey):
    return f"mq_{q['key']}_{fkey}"


def _collect():
    """The form's values, keyed the way manager_questions stores them."""
    out = {}
    for q in mq.QUESTIONS:
        a = {}
        for kind, fkey, label, *rest in q["fields"]:
            k = _wkey(q, fkey)
            if kind == "all":
                a[fkey] = [o for i, o in enumerate(rest[0]) if st.session_state.get(f"{k}_{i}")]
            elif kind == "rank":
                a[fkey] = list(st.session_state.get(k) or [])
            elif kind == "num":
                v = st.session_state.get(k)
                a[fkey] = int(v) if v is not None else None
            else:
                a[fkey] = st.session_state.get(k) or ("" if kind != "one" else None)
        a["notes"] = (st.session_state.get(_wkey(q, "notes")) or "").strip()
        out[q["key"]] = a
    return out


saved = _load_mine()
answers = saved.get("answers") or {}
n_q = len(mq.QUESTIONS)
done = sum(mq.answered(q, answers.get(q["key"])) for q in mq.QUESTIONS)

st.markdown('<div class="mq-h1">Manager questions</div>'
            f'<div class="mq-sub">{n_q} quick questions about days that don\'t go to plan. '
            "Your answers teach the 5 AM run to do what you would do.</div>", unsafe_allow_html=True)

tab_me, tab_all = st.tabs(["My answers", "Everyone's answers"])

with tab_me:
    if st.session_state.pop("mq_just_saved", False):
        st.success("Saved. Thank you!")
    st.progress(done / n_q, text=f"{done} of {n_q} answered"
                + (f" · last saved {_when(saved.get('saved_at'))}" if saved.get("saved_at") else ""))
    st.caption("Answer what you can and press **Save my answers** at the bottom. "
               "“Today” shows what the app does now. You can change your answers any time.")

    with st.form("mq_form", border=False):
        for part, qs in mq.PARTS:
            st.markdown(f'<div class="mq-part">{e(part)}</div>', unsafe_allow_html=True)
            for q in qs:
                a = answers.get(q["key"]) or {}
                with st.container(border=True):
                    st.markdown(f'<div class="mq-q"><span class="mq-n">{mq.NUMBER[q["key"]]}.</span>{e(q["q"])}</div>'
                                + (f'<div class="mq-now"><b>Today:</b> {e(q["now"])}</div>' if q["now"] else ""),
                                unsafe_allow_html=True)
                    for kind, fkey, label, *rest in q["fields"]:
                        k, v = _wkey(q, fkey), a.get(fkey)
                        if kind == "one":
                            opts = rest[0]
                            st.radio(label, opts, index=opts.index(v) if v in opts else None, key=k)
                        elif kind == "all":
                            st.markdown(f'<div class="mq-lbl">{e(label)}</div>', unsafe_allow_html=True)
                            for i, o in enumerate(rest[0]):
                                st.checkbox(o, value=o in (v or []), key=f"{k}_{i}")
                        elif kind == "rank":
                            opts = rest[0]
                            st.multiselect(label, opts, default=[x for x in (v or []) if x in opts], key=k,
                                           placeholder="Pick the first one…")
                        elif kind == "num":
                            st.number_input(label, min_value=0, step=1, key=k,
                                            value=int(v) if isinstance(v, (int, float)) else None)
                        elif kind == "long":
                            st.text_area(label, value=v or "", key=k)
                        else:
                            st.text_input(label, value=v or "", key=k)
                    st.text_input("Anything to add? (optional)", value=a.get("notes", ""), key=_wkey(q, "notes"))
        go = st.form_submit_button("Save my answers", type="primary", use_container_width=True)

    if go:
        try:
            db._upsert_key(KEY, {"username": user, "name": me, "saved_at": clock.stamp(), "answers": _collect()})
            st.session_state["mq_just_saved"] = True
            st.rerun()
        except Exception as ex:
            st.error(f"Couldn't save your answers: {ex}")

with tab_all:
    try:
        rows = db._like_keys(mq.KEY_PREFIX, with_payload=True)
    except Exception as ex:
        rows = []
        st.error(f"Couldn't load the answers: {ex}")
    people = sorted((p for p in (_payload(r.get("payload")) for r in rows) if p.get("answers") is not None),
                    key=lambda p: str(p.get("name") or p.get("username") or "").lower())
    if not people:
        st.info("Nobody has saved answers yet.")
    else:
        st.caption(" · ".join(f"**{e(str(p.get('name') or p.get('username')))}** saved "
                              f"{_when(p.get('saved_at'))}" for p in people))
        for part, qs in mq.PARTS:
            st.markdown(f'<div class="mq-part">{e(part)}</div>', unsafe_allow_html=True)
            for q in qs:
                with st.container(border=True):
                    lines = []
                    for p in people:
                        s = mq.summary(q, (p.get("answers") or {}).get(q["key"]))
                        lines.append(f'<div class="mq-who"><b>{e(str(p.get("name") or p.get("username")))}:</b> '
                                     + (e(s) if s else '<span class="mq-none">no answer</span>') + "</div>")
                    st.markdown(f'<div class="mq-q"><span class="mq-n">{mq.NUMBER[q["key"]]}.</span>{e(q["q"])}</div>'
                                + "".join(lines), unsafe_allow_html=True)
        # One row per question, one column per manager, for keeping or printing.
        import pandas as pd
        table = pd.DataFrame(
            {"No.": [mq.NUMBER[q["key"]] for q in mq.QUESTIONS],
             "Question": [q["q"] for q in mq.QUESTIONS],
             **{str(p.get("name") or p.get("username")):
                [mq.summary(q, (p.get("answers") or {}).get(q["key"])) for q in mq.QUESTIONS] for p in people}})
        buf = io.BytesIO()
        table.to_excel(buf, index=False, sheet_name="Answers")
        st.download_button("Download everyone's answers (Excel)", buf.getvalue(),
                           file_name=f"Manager answers {clock.today_iso()}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
