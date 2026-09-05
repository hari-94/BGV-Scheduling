"""
Profile — who you are signed in as, and changing your own password.

Everyone gets this, which is the point: the only place a password could be
changed was the Admin page, so a housekeeper who wanted to change hers had to
ask somebody with the keys to type a new one for her, and that person then knew
it. Most of the team reads this on a phone in Spanish, so it is short, the rules
are stated before they are broken, and every string is translated.
"""
import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, db, i18n
import session as _session
import ui

st.set_page_config(page_title="Profile", page_icon="👤", layout="wide")
st.markdown("<style>.block-container{max-width:min(760px,97%);}"
            "[data-testid='stSidebarNav']{display:none!important;}</style>",
            unsafe_allow_html=True)
auth.require_login()
ui.topnav("Profile")

T = i18n.t
MIN_LEN = 6          # the same floor the rest of the app uses

me = auth.current_user()
uname = me.get("username", "")

st.markdown(f"""<div style="background:#fff;border:1px solid #e6e9ee;border-radius:16px;
     padding:18px 22px;margin-bottom:16px">
  <div style="font-size:1.3rem;font-weight:700;color:#16202e">
    {i18n.t('profile.hello')} {st.session_state.get('display_name') or uname}</div>
  <div style="font-size:.85rem;color:#5b6675;margin-top:4px">
    {uname} · {auth.role_badge(me.get('role',''))}</div>
</div>""", unsafe_allow_html=True)

st.markdown(f"#### {T('profile.change_pw')}")
st.caption(T("profile.rule").format(n=MIN_LEN))

with st.form("profile_pw", clear_on_submit=False):
    cur = st.text_input(T("profile.current"), type="password",
                        autocomplete="current-password")
    new1 = st.text_input(T("profile.new"), type="password",
                         autocomplete="new-password")
    new2 = st.text_input(T("profile.confirm"), type="password",
                         autocomplete="new-password")
    others = st.checkbox(T("profile.signout_others"), value=True)
    go = st.form_submit_button(T("profile.save"), type="primary",
                               use_container_width=True)

if go:
    # Checked in the order a person would: are you who you say, then is the new
    # one usable, then is it actually new. Each failure says which one it was.
    if not cur or not new1 or not new2:
        st.error(T("profile.err_blank"))
    elif not db.verify_password(uname, cur):
        st.error(T("profile.err_current"))
    elif new1 != new2:
        st.error(T("profile.err_match"))
    elif len(new1) < MIN_LEN:
        st.error(T("profile.err_short").format(n=MIN_LEN))
    elif new1 == cur:
        st.error(T("profile.err_same"))
    else:
        ok, msg = db.update_password(uname, new1)
        if not ok:
            st.error(T("profile.err_save"))
            print(f"[profile] password update failed for {uname}: {msg}")
        else:
            ended = 0
            if others:
                # Keep this browser signed in -- being thrown back to the login
                # form is a poor reward for doing the right thing -- and end the
                # rest, which is the point of changing it.
                keep = ""
                tok = st.session_state.get("_session_token")
                if tok:
                    keep = _session._hash(tok)
                ended = db.delete_other_sessions(uname, keep)
            st.success(T("profile.done"))
            if ended:
                st.info(T("profile.ended_others").format(n=ended))
            st.balloons()

st.markdown("---")
st.caption(T("profile.help"))
