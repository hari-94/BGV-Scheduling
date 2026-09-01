"""
ui.py — shared page chrome.

One horizontal navigation bar for every page, so moving between them never
changes where the menu lives. The Cleaning Schedule page keeps its sidebar,
but only for the attendance controls — its navigation comes from here too.
"""
import streamlit as st
import auth
import i18n

#: Every destination, with the permission that reveals it. Order is the order
#: they appear across the bar.
#: (path, label, icon, permission, translation key). The label doubles as the
#: `active` marker, so it stays English in the code and is translated only on
#: the way to the screen.
NAV_ITEMS = [
    ("pages/4_My_Home.py",       "My Home",       "🏠", None, "nav.my_home"),
    ("pages/5_My_Rooms.py",      "My Rooms",      "🛎️", "_my_rooms", "nav.my_rooms"),
    ("cleaning_scheduler.py",    "Schedule",      "🧹", "can_generate", "nav.schedule"),
    ("pages/1_Dashboard.py",     "Dashboard",     "📊", "can_view_dashboard", "nav.dashboard"),
    ("pages/3_Roster_Import.py", "Roster Import", "📥", "can_generate", "nav.roster_import"),
    ("pages/2_Admin.py",         "Admin",         "⚙️", "can_manage_users", "nav.admin"),
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

/* Content-sized nav columns. Streamlit gives every column an equal flex
   basis, so adding a sixth link and the language switch squeezed the labels
   until they were cropped mid-word -- worse in Spanish, where the same words
   are longer. Each column takes the width it needs instead, and one marked
   spacer absorbs what is left over. */
[data-testid="stHorizontalBlock"]:has([data-testid="stPageLink"])
  > [data-testid="stColumn"]{
  flex:0 0 auto !important;width:auto !important;min-width:0 !important;
}
[data-testid="stHorizontalBlock"]:has([data-testid="stPageLink"])
  > [data-testid="stColumn"]:has(.navspacer){flex:1 1 auto !important;}
[data-testid="stPageLink"],
[data-testid="stPageLink"] a{min-width:max-content !important;
  overflow:visible !important;}
[data-testid="stPageLink"] a p{
  white-space:nowrap !important;overflow:visible !important;
  text-overflow:clip !important;
}
[data-testid="stHorizontalBlock"]:has([data-testid="stPageLink"])
  .stButton>button{white-space:nowrap !important;}

/* On a narrow screen the bar wraps onto a second line rather than shrinking
   the labels away. */
@media (max-width:1100px){
  [data-testid="stHorizontalBlock"]:has([data-testid="stPageLink"]){
    flex-wrap:wrap !important;row-gap:4px !important;
  }
}

/* ── Getting the sidebar back ──
   Every page flattens header[data-testid="stHeader"] to nothing, and in
   Streamlit 1.62 that header is where the button that reopens a collapsed
   sidebar lives -- so collapsing it hid the only way to bring it back. The
   button is lifted out of that header and pinned to the corner instead.
   (The old rules hid "collapsedControl", a name Streamlit stopped using
   several versions ago, so they were doing nothing at all.) */
[data-testid="stExpandSidebarButton"]{
  display:flex !important;visibility:visible !important;opacity:1 !important;
  position:fixed !important;top:10px;left:10px;z-index:1000;
  background:#ffffff !important;border:1px solid #dbe3ec !important;
  border-radius:11px !important;box-shadow:0 3px 10px rgba(16,26,42,.13) !important;
  width:36px;height:36px;align-items:center;justify-content:center;
}
[data-testid="stExpandSidebarButton"]:hover{
  border-color:#9fc0e0 !important;background:#f4f8fc !important;}
[data-testid="stExpandSidebarButton"] svg{color:#2d72b8 !important;}

/* ── On a phone ──
   The team opens this on a handset in a corridor, so the pages have to work
   at 390px without anyone asking for the desktop site. Streamlit's columns
   shrink rather than stack, which is what turns a three-column row into three
   unreadable slivers; below this width they wrap instead. */
@media (max-width:820px){
  .block-container{padding:0.7rem 0.75rem 2rem !important;max-width:100% !important;}
  [data-testid="stMain"] [data-testid="stHorizontalBlock"]{flex-wrap:wrap !important;}
  [data-testid="stMain"] [data-testid="stColumn"]{
    min-width:100% !important;flex:1 1 100% !important;}
  /* The sidebar is an overlay at this width and has the screen to itself, so
     its two-up lists stay two-up. */
  section[data-testid="stSidebar"] [data-testid="stColumn"]{
    min-width:0 !important;flex:1 1 0 !important;}
  section[data-testid="stSidebar"]{width:88vw !important;min-width:0 !important;}
  /* Tap targets, not mouse targets. */
  .stButton>button,.stDownloadButton>button{min-height:40px !important;}
  [data-testid="stExpandSidebarButton"]{width:40px;height:40px;}
  /* Anything that cannot be made narrower scrolls inside itself rather than
     pushing the whole page sideways. */
  [data-testid="stDataFrame"],[data-testid="stTable"],.stDataFrame{
    overflow-x:auto !important;}
  h1{font-size:1.5rem !important;}
  h2{font-size:1.15rem !important;}
  /* The nav bar keeps its own wrapping rule; just tighten it up here. */
  [data-testid="stHorizontalBlock"]:has([data-testid="stPageLink"]){
    padding:6px 7px !important;gap:1px !important;}
  [data-testid="stPageLink"] a{padding:7px 8px !important;font-size:.78rem !important;}
  .navwho{display:none !important;}
}
@media (max-width:430px){
  [data-testid="stPageLink"] a{font-size:.74rem !important;padding:6px !important;}
}
</style>
"""

#: Widths: one narrow slot per link, a spacer that soaks up the middle, then
#: the person and the way out. Without the spacer the links spread across the
#: whole width and stop reading as a group.
def _weights(n):
    return [1.0] * n + [0.6, 1.5, 0.9, 1.0]

def _visible(perm) -> bool:
    """Whether a nav entry belongs to this person.

    My Rooms is a special case rather than a permission. A housekeeper always
    has it, because an empty day is itself worth seeing. An admin always has
    it, because they look after everyone. An RQS is neither: they are on the
    page only on the days they are carrying rooms themselves, so the link
    appears only then.
    """
    if perm is None:
        return True
    if perm != "_my_rooms":
        return auth.can(perm)
    role = st.session_state.get("role", "")
    if role in ("housekeeper", "admin"):
        return True
    try:
        import assignments
        return assignments.has_rooms_today()
    except Exception as ex:            # never let a lookup cost the whole bar
        print(f"[ui] my-rooms visibility check failed: {ex}")
        return False


def topnav(active: str = "", hide_sidebar: bool = True):
    """Draw the horizontal navigation bar.

    `active` is the label of the current page so it can be highlighted.
    `hide_sidebar` is False on the scheduler, which still needs its sidebar for
    the attendance controls.
    """
    st.markdown(CHROME_CSS, unsafe_allow_html=True)
    if hide_sidebar:
        st.markdown('<style>section[data-testid="stSidebar"]{display:none !important;}'
                    '[data-testid="stExpandSidebarButton"]{display:none !important;}</style>',
                    unsafe_allow_html=True)

    i18n.load_lang_for_user()
    items = [it for it in NAV_ITEMS if _visible(it[3])]
    who = st.session_state.get("display_name") or st.session_state.get("username", "")
    role_key = f'role.{st.session_state.get("role", "")}'
    role = i18n.t(role_key) if role_key in i18n.STRINGS else \
        str(st.session_state.get("role", "")).title()

    cols = st.columns(_weights(len(items)), vertical_alignment="center")
    for col, (path, label, icon, _perm, tkey) in zip(cols, items):
        with col:
            if label == active:
                # Marker div; the CSS reaches the link beside it. Streamlit
                # gives no hook of its own for "this page link is current".
                st.markdown('<span class="navactive"></span>', unsafe_allow_html=True)
            st.page_link(path, label=i18n.t(tkey), icon=icon)
    with cols[len(items)]:
        st.markdown('<span class="navspacer"></span>', unsafe_allow_html=True)
    with cols[len(items) + 1]:
        st.markdown(f'<div class="navwho">{i18n.t("nav.signed_in_as")} <b>{who}</b><br>'
                    f'<span class="role">{role}</span></div>', unsafe_allow_html=True)
    with cols[len(items) + 2]:
        # The button shows the language you would be switching *to*, which is
        # the only way round that reads correctly in both.
        code, label = i18n.other()
        if st.button(f"🌐 {label}", key=f"nav_lang_{active or 'x'}",
                     use_container_width=True, help="English / Español"):
            i18n.set_lang(code)
            st.rerun()
    with cols[len(items) + 3]:
        if st.button(i18n.t("nav.sign_out"), key=f"nav_signout_{active or 'x'}",
                     use_container_width=True):
            auth.logout()
            st.switch_page("cleaning_scheduler.py")
