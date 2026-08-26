"""
ui.py — shared page chrome.

A horizontal navigation bar and the styling that goes with it, so every page
outside the scheduler looks and behaves the same. The Cleaning Schedule page
deliberately does NOT use this: its sidebar carries the attendance controls,
not navigation, so it keeps what it has.
"""
import streamlit as st
import auth

#: Every destination, with the permission that reveals it. Order is the order
#: they appear across the bar.
NAV_ITEMS = [
    ("pages/4_My_Home.py",       "My Home",       "🏠", None),
    ("cleaning_scheduler.py",    "Schedule",      "🧹", "can_generate"),
    ("pages/1_Dashboard.py",     "Dashboard",     "📊", "can_view_dashboard"),
    ("pages/3_Roster_Import.py", "Roster Import", "📥", "can_generate"),
    ("pages/2_Admin.py",         "Admin",         "⚙️", "can_manage_users"),
]

CHROME_CSS = """
<style>
/* Navigation lives across the top now, so the sidebar has nothing to hold. */
section[data-testid="stSidebar"]{display:none !important;}
[data-testid="collapsedControl"]{display:none !important;}
[data-testid="stSidebarNav"]{display:none !important;}

.navwrap{
  display:flex;align-items:center;justify-content:space-between;gap:14px;
  background:linear-gradient(180deg,#ffffff 0%,#fbfcfe 100%);
  border:1px solid #e4e8ee;border-radius:14px;padding:7px 10px;
  margin:0 0 16px;box-shadow:0 1px 2px rgba(22,32,46,.04),0 6px 18px rgba(22,32,46,.05);
}
.navwrap .who{
  font-size:.74rem;color:#5b6675;white-space:nowrap;padding-right:6px;
}
.navwrap .who b{color:#16202e}

/* st.page_link renders an anchor; dress it as a pill. */
[data-testid="stPageLink"] a{
  border-radius:10px !important;padding:7px 14px !important;
  font-size:.82rem !important;font-weight:600 !important;
  color:#5b6675 !important;text-decoration:none !important;
  border:1px solid transparent !important;
  transition:background .15s ease,color .15s ease,transform .12s ease,
             box-shadow .15s ease !important;
}
[data-testid="stPageLink"] a:hover{
  background:#eef4fb !important;color:#1c4a78 !important;
  transform:translateY(-1px);
  box-shadow:0 4px 10px rgba(37,99,168,.10) !important;
}
[data-testid="stPageLink"] a p{font-weight:600 !important;margin:0 !important;}
/* The page you are on. */
.navactive [data-testid="stPageLink"] a{
  background:linear-gradient(135deg,#1e4f86 0%,#2f74b8 55%,#4a90cc 100%) !important;
  color:#fff !important;
  box-shadow:0 3px 10px rgba(30,79,134,.28),inset 0 1px 0 rgba(255,255,255,.18) !important;
}
.navactive [data-testid="stPageLink"] a:hover{
  color:#fff !important;transform:translateY(-1px);
}
.navactive [data-testid="stPageLink"] a p{color:#fff !important;}

/* Tabs: a soft raised pill rather than a flat block.
   The radius is repeated on the selected state and on the inner wrapper —
   the highlight is painted on a child, so setting it only on the tab button
   leaves square corners poking out from under the rounded parent. */
.stTabs [data-baseweb="tab-list"]{
  gap:6px !important;background:#f2f5f9 !important;
  border:1px solid #e4e8ee !important;border-radius:14px !important;
  padding:5px !important;overflow:visible !important;
}
.stTabs [data-baseweb="tab"]{
  border-radius:11px !important;padding:8px 17px !important;
  font-size:.79rem !important;font-weight:600 !important;
  color:#5b6675 !important;border:none !important;background:transparent !important;
  overflow:hidden !important;
  transition:background .16s ease,color .16s ease,box-shadow .16s ease,
             transform .12s ease !important;
}
.stTabs [data-baseweb="tab"] > *{border-radius:11px !important;}
.stTabs [data-baseweb="tab"]:hover{
  background:rgba(255,255,255,.8) !important;color:#1c4a78 !important;
}
.stTabs [aria-selected="true"]{
  border-radius:11px !important;
  background:linear-gradient(135deg,#1e4f86 0%,#2f74b8 55%,#4a90cc 100%) !important;
  color:#fff !important;
  box-shadow:0 3px 10px rgba(30,79,134,.26),inset 0 1px 0 rgba(255,255,255,.20) !important;
}
.stTabs [aria-selected="true"]:hover{transform:translateY(-1px);}
.stTabs [aria-selected="true"] p,
.stTabs [aria-selected="true"] div{color:#fff !important;}
/* Streamlit's own sliding underline would sit square under the pill. */
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"]{display:none !important;background:transparent !important;}

/* Buttons pick up the same family. */
.stButton>button[kind="primary"]{
  background:linear-gradient(135deg,#1e4f86 0%,#2f74b8 60%,#4a90cc 100%) !important;
  border:none !important;color:#fff !important;
  box-shadow:0 3px 10px rgba(30,79,134,.24) !important;
}
.stButton>button[kind="primary"]:hover{filter:brightness(1.06);transform:translateY(-1px);}

@media (max-width:820px){
  .navwrap{flex-direction:column;align-items:stretch;gap:6px}
  .navwrap .who{text-align:right;padding:0 4px 2px}
  .stTabs [data-baseweb="tab"]{padding:6px 11px !important;font-size:.72rem !important;}
}
</style>
"""

def topnav(active: str = ""):
    """Draw the horizontal navigation bar.

    `active` is the label of the current page, so it can be highlighted.
    Only destinations the signed-in role may reach are shown.
    """
    st.markdown(CHROME_CSS, unsafe_allow_html=True)
    items = [it for it in NAV_ITEMS if it[3] is None or auth.can(it[3])]

    who = st.session_state.get("display_name") or st.session_state.get("username", "")
    role = str(st.session_state.get("role", "")).title()

    st.markdown('<div class="navwrap">', unsafe_allow_html=True)
    cols = st.columns(len(items) + 2, vertical_alignment="center")
    for col, (path, label, icon, _perm) in zip(cols, items):
        with col:
            if label == active:
                st.markdown('<div class="navactive">', unsafe_allow_html=True)
                st.page_link(path, label=label, icon=icon)
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.page_link(path, label=label, icon=icon)
    with cols[-2]:
        st.markdown(f'<div class="who">Signed in as <b>{who}</b><br>{role}</div>',
                    unsafe_allow_html=True)
    with cols[-1]:
        if st.button("Sign out", key=f"nav_signout_{active or 'x'}",
                     use_container_width=True):
            auth.logout()
            st.switch_page("cleaning_scheduler.py")
    st.markdown("</div>", unsafe_allow_html=True)
