"""
ui.py — shared page chrome.

One horizontal navigation bar for every page, so moving between them never
changes where the menu lives. The Cleaning Schedule page keeps its sidebar,
but only for the attendance controls — its navigation comes from here too.
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
[data-testid="stSidebarNav"]{display:none !important;}

/* The bar itself. A wrapper <div> cannot contain Streamlit columns — the
   markdown closes before they render — so the row that HOLDS the page links
   is styled directly instead. */
[data-testid="stHorizontalBlock"]:has([data-testid="stPageLink"]){
  background:linear-gradient(180deg,#ffffff 0%,#f7f9fc 100%);
  border:1px solid #e3e8ef;border-radius:16px;
  padding:8px 12px !important;margin:0 0 18px !important;
  align-items:center !important;gap:2px !important;
  box-shadow:0 1px 2px rgba(16,26,42,.04),0 10px 26px rgba(16,26,42,.06);
}
[data-testid="stHorizontalBlock"]:has([data-testid="stPageLink"])
  [data-testid="stVerticalBlock"]{gap:0 !important;}

.navwho{
  font-size:.72rem;line-height:1.35;color:#64707f;text-align:right;
  white-space:nowrap;padding-right:4px;
}
.navwho b{color:#16202e;font-weight:700}
.navwho .role{
  display:inline-block;margin-top:2px;padding:1px 8px;border-radius:20px;
  background:#eef3fa;color:#3c6ea5;font-size:.6rem;font-weight:700;
  letter-spacing:.07em;text-transform:uppercase;
}

/* st.page_link renders an anchor; dress it as a pill. */
[data-testid="stPageLink"]{margin:0 !important;}
[data-testid="stPageLink"] a{
  border-radius:11px !important;padding:9px 10px !important;
  font-size:.82rem !important;font-weight:600 !important;
  color:#5a6675 !important;text-decoration:none !important;
  justify-content:center !important;
  transition:background .16s ease,color .16s ease,transform .14s ease,
             box-shadow .16s ease !important;
}
[data-testid="stPageLink"] a:hover{
  background:#eef4fb !important;color:#1c4a78 !important;
  transform:translateY(-1px);
  box-shadow:0 5px 14px rgba(37,99,168,.13) !important;
}
[data-testid="stPageLink"] a p{font-weight:600 !important;margin:0 !important;}

/* The page you are on. */
.navactive + div [data-testid="stPageLink"] a,
.navactive ~ div [data-testid="stPageLink"] a{
  background:linear-gradient(135deg,#1b4a80 0%,#2d72b8 52%,#4b93d1 100%) !important;
  color:#fff !important;
  box-shadow:0 4px 14px rgba(27,74,128,.32),
             inset 0 1px 0 rgba(255,255,255,.22) !important;
}
.navactive ~ div [data-testid="stPageLink"] a p{color:#fff !important;}
.navactive ~ div [data-testid="stPageLink"] a:hover{
  color:#fff !important;transform:translateY(-1px);filter:brightness(1.05);
}

/* Sign out sits quietly until you reach for it. */
[data-testid="stHorizontalBlock"]:has([data-testid="stPageLink"]) .stButton>button{
  border-radius:11px !important;font-size:.78rem !important;font-weight:600 !important;
  background:#fff !important;color:#5a6675 !important;
  border:1px solid #dfe5ee !important;padding:8px 10px !important;
}
[data-testid="stHorizontalBlock"]:has([data-testid="stPageLink"]) .stButton>button:hover{
  background:#fff1f1 !important;color:#b42323 !important;
  border-color:#f4c9c9 !important;
}

/* Tabs: a soft raised pill on a light track.
   The radius is repeated on the selected state and the inner wrapper —
   Streamlit paints the highlight on a child, so a radius set only on the
   parent leaves square corners poking out underneath. */
.stTabs [data-baseweb="tab-list"]{
  gap:6px !important;background:#eef2f7 !important;
  border:1px solid #e3e8ef !important;border-radius:14px !important;
  padding:5px !important;
}
.stTabs [data-baseweb="tab"]{
  border-radius:11px !important;padding:8px 18px !important;
  font-size:.79rem !important;font-weight:600 !important;
  color:#5a6675 !important;border:none !important;background:transparent !important;
  overflow:hidden !important;
  transition:background .16s ease,color .16s ease,box-shadow .16s ease,
             transform .14s ease !important;
}
.stTabs [data-baseweb="tab"] > *{border-radius:11px !important;}
.stTabs [data-baseweb="tab"]:hover{background:#fff !important;color:#1c4a78 !important;}
.stTabs [aria-selected="true"]{
  border-radius:11px !important;
  background:linear-gradient(135deg,#1b4a80 0%,#2d72b8 52%,#4b93d1 100%) !important;
  color:#fff !important;
  box-shadow:0 4px 14px rgba(27,74,128,.30),
             inset 0 1px 0 rgba(255,255,255,.22) !important;
}
.stTabs [aria-selected="true"]:hover{transform:translateY(-1px);filter:brightness(1.05);}
.stTabs [aria-selected="true"] p,
.stTabs [aria-selected="true"] div{color:#fff !important;}
/* Streamlit's sliding underline would sit square beneath the pill. */
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"]{display:none !important;background:transparent !important;}

.stButton>button[kind="primary"]{
  background:linear-gradient(135deg,#1b4a80 0%,#2d72b8 55%,#4b93d1 100%) !important;
  border:none !important;color:#fff !important;
  box-shadow:0 4px 12px rgba(27,74,128,.26) !important;
}
.stButton>button[kind="primary"]:hover{filter:brightness(1.07);transform:translateY(-1px);}

@media (max-width:900px){
  [data-testid="stHorizontalBlock"]:has([data-testid="stPageLink"]){
    padding:6px !important;border-radius:13px;
  }
  [data-testid="stPageLink"] a{padding:8px 6px !important;font-size:.74rem !important;}
  .navwho{font-size:.64rem}
  .stTabs [data-baseweb="tab"]{padding:6px 11px !important;font-size:.72rem !important;}
}
</style>
"""

#: Widths: one narrow slot per link, a spacer that soaks up the middle, then
#: the person and the way out. Without the spacer the links spread across the
#: whole width and stop reading as a group.
def _weights(n):
    return [1.0] * n + [1.4, 1.5, 1.0]

def topnav(active: str = "", hide_sidebar: bool = True):
    """Draw the horizontal navigation bar.

    `active` is the label of the current page so it can be highlighted.
    `hide_sidebar` is False on the scheduler, which still needs its sidebar for
    the attendance controls.
    """
    st.markdown(CHROME_CSS, unsafe_allow_html=True)
    if hide_sidebar:
        st.markdown('<style>section[data-testid="stSidebar"]{display:none !important;}'
                    '[data-testid="collapsedControl"]{display:none !important;}</style>',
                    unsafe_allow_html=True)

    items = [it for it in NAV_ITEMS if it[3] is None or auth.can(it[3])]
    who = st.session_state.get("display_name") or st.session_state.get("username", "")
    role = str(st.session_state.get("role", "")).title()

    cols = st.columns(_weights(len(items)), vertical_alignment="center")
    for col, (path, label, icon, _perm) in zip(cols, items):
        with col:
            if label == active:
                # Marker div; the CSS reaches the link beside it. Streamlit
                # gives no hook of its own for "this page link is current".
                st.markdown('<span class="navactive"></span>', unsafe_allow_html=True)
            st.page_link(path, label=label, icon=icon)
    with cols[len(items) + 1]:
        st.markdown(f'<div class="navwho">Signed in as <b>{who}</b><br>'
                    f'<span class="role">{role}</span></div>', unsafe_allow_html=True)
    with cols[len(items) + 2]:
        if st.button("Sign out", key=f"nav_signout_{active or 'x'}",
                     use_container_width=True):
            auth.logout()
            st.switch_page("cleaning_scheduler.py")
