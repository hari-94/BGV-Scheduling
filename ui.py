"""
ui.py — shared page chrome.

One horizontal navigation bar for every page, so moving between them never
changes where the menu lives. The Cleaning Schedule page keeps its sidebar,
but only for the attendance controls — its navigation comes from here too.
"""
import streamlit as st
import auth
import i18n

# Wrap Streamlit's text calls once, at import, so every page is translated
# whether or not it remembers to ask. ui is imported by all of them.
i18n.install()

#: Every destination, with the permission that reveals it. Order is the order
#: they appear across the bar.
#: (path, label, icon, permission, translation key). Icons are Material
#: Symbols (":material/name:", built into Streamlit): one line-drawn set that
#: takes the text colour and reads the same on every phone, where emoji were
#: drawn differently by each device. The label doubles as the
#: `active` marker, so it stays English in the code and is translated only on
#: the way to the screen.
NAV_ITEMS = [
    ("pages/4_My_Home.py",       "My Home",       ":material/home:", None, "nav.my_home"),
    ("pages/5_My_Rooms.py",      "My Rooms",      ":material/bed:", "_my_rooms", "nav.my_rooms"),
    ("cleaning_scheduler.py",    "Schedule",      ":material/cleaning_services:", "can_generate", "nav.schedule"),
    ("pages/1_Dashboard.py",     "Dashboard",     ":material/dashboard:", "can_view_dashboard", "nav.dashboard"),
    ("pages/3_Roster_Import.py", "Roster Import", ":material/upload_file:", "can_generate", "nav.roster_import"),
    ("pages/6_Property.py",      "Property",      ":material/apartment:", "can_view_insp_tab", "nav.property"),
    ("pages/9_Forecast.py",      "Forecast",      ":material/trending_up:", "can_view_dashboard", "nav.forecast"),
    ("pages/10_Stats.py",        "Stats",         ":material/monitoring:",    "can_manage_users", "nav.health"),
    ("pages/11_Report.py",       "Report",        ":material/summarize:",     "can_manage_users", "nav.report"),
    ("pages/12_Questions.py",    "Questions",     ":material/quiz:",          "can_manage_users", "nav.questions"),
    ("pages/8_HotSOS.py",        "HotSOS",        ":material/sync_alt:", "can_manage_users", "nav.hotsos"),
    ("pages/7_Profile.py",       "Profile",       ":material/account_circle:", None, "nav.profile"),
    ("pages/2_Admin.py",         "Admin",         ":material/admin_panel_settings:", "can_manage_users", "nav.admin"),
]

CHROME_CSS = """
<style>
[data-testid="stSidebarNav"]{display:none !important;}

/* ── The top menu ──
   Every page has a stylesheet of its own, and several restyle rows and
   columns wholesale on a phone: Dashboard, Admin and Roster Import stack every
   row, My Rooms widens every column, and the Schedule page keeps any row of
   buttons on one line -- which, the menu holding the language and sign-out
   buttons, ran it out past its border. The menu therefore sits in its own
   container (st.container(key="bgvnav")) and every rule for it is scoped
   with :is(.st-key-bgvnav,#bgvnav). The id never matches anything; it lends
   the selector an id's weight, which no page's class-and-attribute rule can
   outrank. One menu, the same on every tab. */
%NAV% [data-testid="stHorizontalBlock"]{
  background:linear-gradient(180deg,#ffffff 0%,#f7f9fc 100%) !important;
  border:1px solid #e3e8ef !important;border-radius:16px !important;
  padding:8px 12px !important;margin:0 0 18px !important;
  display:flex !important;flex-direction:row !important;flex-wrap:wrap !important;
  align-items:center !important;gap:4px 2px !important;
  max-width:100% !important;box-sizing:border-box !important;
  box-shadow:0 1px 2px rgba(16,26,42,.04),0 10px 26px rgba(16,26,42,.06) !important;
}
%NAV% [data-testid="stVerticalBlock"]{gap:0 !important;}
/* Content-sized columns: each link takes the width it needs and one spacer
   soaks up the rest, so the labels are never cropped mid-word. */
%NAV% [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]{
  flex:0 0 auto !important;width:auto !important;min-width:0 !important;max-width:none !important;
}
%NAV% [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has(.navspacer){
  flex:1 1 auto !important;}
/* The marker that says which page you are on takes no room of its own. */
%NAV% [data-testid="stElementContainer"]:has(.navactive),
%NAV% [data-testid="stElementContainer"]:has(.navspacer){display:none !important;}

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
%NAV% [data-testid="stPageLink"]{margin:0 !important;min-width:max-content !important;}
%NAV% [data-testid="stPageLink"] a{
  min-width:max-content !important;overflow:visible !important;
  border-radius:11px !important;padding:9px 10px !important;margin:0 !important;
  font-size:.82rem !important;font-weight:600 !important;line-height:1.2 !important;
  color:#5a6675 !important;text-decoration:none !important;background:transparent !important;
  justify-content:center !important;
  transition:background .16s ease,color .16s ease,transform .14s ease,
             box-shadow .16s ease !important;
}
%NAV% [data-testid="stPageLink"] a:hover{
  background:#eef4fb !important;color:#1c4a78 !important;
  transform:translateY(-1px);
  box-shadow:0 5px 14px rgba(37,99,168,.13) !important;
}
%NAV% [data-testid="stPageLink"] a p{
  font-weight:600 !important;margin:0 !important;font-size:inherit !important;
  white-space:nowrap !important;overflow:visible !important;text-overflow:clip !important;
}

/* The page you are on. */
%NAV% [data-testid="stColumn"]:has(.navactive) [data-testid="stPageLink"] a{
  background:linear-gradient(135deg,#1b4a80 0%,#2d72b8 52%,#4b93d1 100%) !important;
  color:#fff !important;
  box-shadow:0 4px 14px rgba(27,74,128,.32),
             inset 0 1px 0 rgba(255,255,255,.22) !important;
}
%NAV% [data-testid="stColumn"]:has(.navactive) [data-testid="stPageLink"] a p,
%NAV% [data-testid="stColumn"]:has(.navactive) [data-testid="stPageLink"] a span{
  color:#fff !important;}
%NAV% [data-testid="stColumn"]:has(.navactive) [data-testid="stPageLink"] a:hover{
  color:#fff !important;transform:translateY(-1px);filter:brightness(1.05);
}

/* Language and sign out sit quietly until you reach for them. */
%NAV% .stButton>button{
  border-radius:11px !important;font-size:.78rem !important;font-weight:600 !important;
  background:#fff !important;color:#5a6675 !important;white-space:nowrap !important;
  border:1px solid #dfe5ee !important;padding:8px 10px !important;
  min-height:0 !important;height:auto !important;line-height:1.2 !important;
  box-shadow:none !important;transform:none !important;
}
%NAV% .stButton>button:hover{
  background:#fff1f1 !important;color:#b42323 !important;
  border-color:#f4c9c9 !important;
}

/* On a phone: a grid of equal buttons -- three across at 390px, more on a
   wider screen -- all inside the border, the same on every tab. The name
   and role are left out; the language and sign-out buttons take a cell each. */
@media (max-width:820px){
  %NAV% [data-testid="stHorizontalBlock"]{
    display:grid !important;grid-template-columns:repeat(auto-fill,minmax(104px,1fr)) !important;
    gap:4px !important;padding:6px !important;border-radius:14px !important;
    margin:0 0 12px !important;
  }
  %NAV% [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]{
    width:auto !important;min-width:0 !important;flex:none !important;}
  %NAV% [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has(.navspacer),
  %NAV% [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has(.navwho){
    display:none !important;}
  %NAV% [data-testid="stPageLink"],
  %NAV% [data-testid="stPageLink"] a{min-width:0 !important;width:100% !important;}
  /* Streamlit pulls each item of a centred row in by a few pixels top and
     bottom; in a grid that stacks the rows on top of one another. */
  %NAV% [data-testid="stElementContainer"]{margin:0 !important;}
  %NAV% [data-testid="stPageLink"] a{
    justify-content:flex-start !important;gap:4px !important;padding:7px 6px !important;
    font-size:.74rem !important;}
  %NAV% [data-testid="stPageLink"] a [data-testid="stIconMaterial"]{font-size:1.05rem !important;}
  %NAV% [data-testid="stPageLink"] a > span:first-child{margin-right:0 !important;}
  /* A long label ("Roster Import", "Importar horario") takes a second line
     rather than losing its end. */
  %NAV% [data-testid="stPageLink"] a p{white-space:normal !important;line-height:1.15 !important;
    overflow-wrap:break-word !important;text-align:left !important;}
  %NAV% .stButton>button{width:100% !important;min-height:36px !important;
    padding:7px 8px !important;font-size:.76rem !important;}
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

@media (max-width:900px) and (min-width:821px){
  %NAV% [data-testid="stHorizontalBlock"]{padding:6px !important;border-radius:13px !important;}
  %NAV% [data-testid="stPageLink"] a{padding:8px 6px !important;font-size:.74rem !important;}
  .navwho{font-size:.64rem}
}
@media (max-width:900px){
  .stTabs [data-baseweb="tab"]{padding:6px 11px !important;font-size:.72rem !important;}
}

/* A flex child defaults to min-width:auto, which means it refuses to go
   narrower than its contents: one wide thing inside a column pushes the row,
   and then the page, off the side of the window instead of being contained by
   it. Columns are proportional here, so nothing wants that default. */
[data-testid="stColumn"]{min-width:0 !important;}

/* ── Getting the sidebar back ──
   The button that reopens a collapsed sidebar is rendered INSIDE
   [data-testid="stToolbar"], which this app was hiding wholesale. A hidden
   parent cannot be overridden from the child, which is why forcing the button
   visible did nothing at all: it was inside a display:none box the whole time.
   So the toolbar stays displayed and is emptied of the things we do not want
   -- the menu, the deploy button, the status widget -- rather than being
   switched off with the one control we need still inside it. The bar itself
   takes no clicks; the button takes its own back. */
[data-testid="stToolbar"]{
  display:flex !important;background:transparent !important;
  pointer-events:none !important;padding:0 !important;}
[data-testid="stMainMenu"],[data-testid="stMainMenuButton"],
[data-testid="stAppDeployButton"],[data-testid="stStatusWidget"],
[data-testid="stToolbarActions"],#MainMenu{display:none !important;}
[data-testid="stExpandSidebarButton"]{
  display:flex !important;visibility:visible !important;opacity:1 !important;
  pointer-events:auto !important;
  position:fixed !important;top:10px;left:10px;z-index:1000;
  background:#ffffff !important;border:1px solid #dbe3ec !important;
  border-radius:11px !important;box-shadow:0 3px 10px rgba(16,26,42,.13) !important;
  width:36px;height:36px;align-items:center;justify-content:center;}
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
}
</style>
"""
#: The menu's own container, and the weight its rules carry (see the CSS).
NAV_KEY = "bgvnav"
CHROME_CSS = CHROME_CSS.replace("%NAV%", f":is(.st-key-{NAV_KEY},#{NAV_KEY})")

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
    # Free plan watch: this process's memory (and caches dropped if it's high),
    # and the read meter flushed every 10 minutes. Never lets a page fail.
    try:
        import freetier
        freetier.tick("app")
    except Exception as _ex:
        print(f"[ui] free-plan tick: {_ex}")
    if hide_sidebar:
        # On a computer the menu is one width on every page, whatever width the
        # page itself chose (Profile is 760px wide, Dashboard 1200): centred on
        # the page, 1050px or the window less a margin. Not on the Schedule
        # page, whose sidebar takes part of the window.
        st.markdown('<style>section[data-testid="stSidebar"]{display:none !important;}'
                    '[data-testid="stExpandSidebarButton"]{display:none !important;}'
                    '@media (min-width:821px){'
                    f':is(.st-key-{NAV_KEY},#{NAV_KEY}){{width:min(1050px,calc(100vw - 48px)) !important;'
                    'max-width:none !important;position:relative !important;left:50% !important;'
                    'transform:translateX(-50%) !important;}}}</style>',
                    unsafe_allow_html=True)

    i18n.load_lang_for_user()
    # The sign-in page writes the cookie and then switches page, so the write
    # can be lost before the browser runs it. Every page tries again until the
    # browser is actually carrying it.
    if st.session_state.get("logged_in"):
        try:
            import session
            session.ensure_cookie()
        except Exception as ex:
            print(f"[ui] could not refresh the session cookie: {ex}")
    # The Android app draws its own tabs: no menu, phone margins, and only the
    # pages it has a tab for (appmode.py).
    import appmode
    if appmode.active():
        appmode.chrome()
        appmode.links()
        appmode.guard(active)
        return

    items = [it for it in NAV_ITEMS if _visible(it[3])]
    who = st.session_state.get("display_name") or st.session_state.get("username", "")
    role_key = f'role.{st.session_state.get("role", "")}'
    role = i18n.t(role_key) if role_key in i18n.STRINGS else \
        str(st.session_state.get("role", "")).title()

    # Its own container, so its rules reach it and no page's rules do.
    box = st.container(key=NAV_KEY)
    cols = box.columns(_weights(len(items)), vertical_alignment="center")
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
        if st.button(label, key=f"nav_lang_{active or 'x'}", icon=":material/translate:",
                     use_container_width=True, help="English / Español"):
            i18n.set_lang(code)
            st.rerun()
    with cols[len(items) + 3]:
        if st.button(i18n.t("nav.sign_out"), key=f"nav_signout_{active or 'x'}",
                     icon=":material/logout:",
                     use_container_width=True):
            auth.logout()
            st.switch_page("cleaning_scheduler.py")
