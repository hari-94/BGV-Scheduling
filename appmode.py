"""
The Android app's view of the site: three pages, no menu, sized for a phone.

The app (BGVSchedulingApp, a WebView) draws its own bottom tabs for My Home,
My Rooms and Profile, so in here the top menu goes, every other page says it
lives on the website, and the page loses the margins a browser tab needs and a
phone screen cannot spare. Nothing changes for anybody in a browser.

How a visit is recognised: the app adds "BGVSchedulingApp/<version>" to its
user agent, which Streamlit hands us in st.context.headers. `?app=1` does the
same from a desktop browser, which is how to look at app mode without a phone.
Either one latches for the session, because Streamlit's page links drop the
query string.
"""
import re

import streamlit as st

#: The pages the app has a tab for, by the label each page passes to
#: ui.topnav. The app's tabs click the hidden links `links()` draws, so a tab
#: switch is Streamlit's own page change and keeps the session.
PAGES = [
    ("pages/4_My_Home.py",  "My Home",  "nav.my_home"),
    ("pages/5_My_Rooms.py", "My Rooms", "nav.my_rooms"),
    ("pages/7_Profile.py",  "Profile",  "nav.profile"),
]
ALLOWED = {label for _p, label, _k in PAGES}
LINKS_KEY = "bgvapplinks"
UA_MARK = "BGVSchedulingApp"
MIN_VERSION = (1, 1)        # the first build with tabs

# Phone-sized chrome. `!important` throughout because every page sets its own
# .block-container width and padding, and this has to win on all of them.
APP_CSS = """
<style>
header[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],
[data-testid="stStatusWidget"],footer{display:none !important;}
section[data-testid="stSidebar"],[data-testid="stSidebarNav"],
[data-testid="stExpandSidebarButton"]{display:none !important;}
.block-container,[data-testid="stMainBlockContainer"]{
  max-width:100% !important;
  padding:12px 12px 24px 12px !important;
}
/* Phone type: inputs at 16px so Android does not zoom on focus. */
.stTextInput input,.stNumberInput input,.stTextArea textarea,
[data-baseweb="select"] div{font-size:16px !important;}
.stButton>button,.stFormSubmitButton>button{min-height:44px;}
h1{font-size:1.45rem !important;} h2{font-size:1.25rem !important;}
h3{font-size:1.1rem !important;}
/* A page's stylesheets are markdown blocks holding nothing but <style>: zero
   tall, but each wrapper still takes the column's 15px gap -- five of them,
   plus the hidden tab links, put ~90px above the first card. Out of the flow
   they cost nothing, and a <style> under display:none still applies. The
   links still answer a script's click() while hidden. */
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] > div >
  [data-testid="stMarkdownContainer"] > style:only-child),
[data-testid="stLayoutWrapper"]:has(> .st-key-""" + LINKS_KEY + """),
.st-key-""" + LINKS_KEY + """{display:none !important;}
</style>
"""


def _has_tabs(ua: str) -> bool:
    """The app from 1.1 on. 1.0 marked its user agent too but had no tabs, so
    hiding the menu from it would leave somebody on one page with no way off
    it; it keeps the website view until it is updated."""
    m = re.search(UA_MARK + r"/(\d+)\.(\d+)", ua)
    return bool(m) and (int(m.group(1)), int(m.group(2))) >= MIN_VERSION


def active() -> bool:
    """True when this session is the Android app (or ?app=1 asked for it)."""
    if st.session_state.get("_app_mode"):
        return True
    on = False
    try:
        ua = st.context.headers.get("User-Agent", "") or ""
        on = _has_tabs(ua)
    except Exception:
        pass
    try:
        if str(st.query_params.get("app", "")).lower() in ("1", "true", "yes"):
            on = True
    except Exception:
        pass
    if on:
        st.session_state["_app_mode"] = True
    return on


def chrome() -> None:
    """The phone stylesheet. Safe to call on any page, signed in or not."""
    st.markdown(APP_CSS, unsafe_allow_html=True)


def links() -> None:
    """Hidden page links for the app's tabs to click, plus the language marker
    the app reads to label its tabs in Spanish or English."""
    import i18n
    box = st.container(key=LINKS_KEY)
    with box:
        for path, label, _k in PAGES:
            st.page_link(path, label=label)
        st.markdown(f'<span data-bgvlang="{i18n.lang()}"></span>', unsafe_allow_html=True)


def guard(label: str) -> None:
    """Stop any page the app has no tab for, with a way back."""
    if label in ALLOWED:
        return
    import i18n
    st.info(i18n.t("app.website_only"))
    st.page_link("pages/4_My_Home.py", label=i18n.t("nav.my_home"), icon=":material/home:")
    st.stop()


def account_buttons() -> None:
    """Language and sign out, which live in the top menu on the website. The
    app has no menu, so its Profile tab carries them."""
    import auth, i18n
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        code, lab = i18n.other()
        if st.button(lab, key="app_lang", icon=":material/translate:",
                     use_container_width=True, help="English / Español"):
            i18n.set_lang(code)
            st.rerun()
    with c2:
        if st.button(i18n.t("nav.sign_out"), key="app_signout", icon=":material/logout:",
                     use_container_width=True):
            auth.logout()
            st.switch_page("cleaning_scheduler.py")
