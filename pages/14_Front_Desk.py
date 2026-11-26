"""
Front Desk — today's rooms for the desk (Hari, 21 Nov).

Every room on today's charts: HotSOS's status, who is cleaning it and who
inspects it, when it was started, cleaned and inspected, the current and the
arriving guest. A search box at the top filters by room, housekeeper, RQS or
guest as you type; the tiles filter by status; Clear filter puts it all back.
The Arrival Report's late checkouts are on it by themselves; rooms the team
adds to the day's tab after the build (an early departure) appear, tagged.

On a room the desk marks a late checkout with the time the guest leaves,
guest departed, or a note to housekeeping (frontdesk.py). They reach the
housekeeper's phone and route at once. (Into the GC8 Inspections tab's Notes
as well is agreed, not built yet -- see frontdesk.py.)

Everything comes off the shared floor (floor.py), the one snapshot every page
reads. For the front desk's shared account (role "frontdesk", whose menu is
this page alone) and managers. The board is a component
(components/frontdesk_board): search, light/dark and the motion run in the
browser, so they cost the app nothing.
"""
import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth
import ui
import fresh

st.set_page_config(page_title="Front Desk", page_icon="GC8", layout="wide")
st.markdown("<style>[data-testid='stSidebarNav']{display:none!important;}</style>",
            unsafe_allow_html=True)
auth.require_login()
fresh.latest("i18n", "ui", "prereg", "frontdesk", "floor", "frontdesk_board", "frontdesk_view")    # as they are on disk, not as first loaded
ui.topnav("Front Desk")

if not auth.can("can_view_frontdesk"):
    st.error("The Front Desk page is for the front desk and managers.")
    st.stop()

# The page around the board. Dark when the board's switch says so: the board
# sets data-fd-theme on this page's <html>, and only this page styles it --
# these rules leave with the page.
_D = 'html[data-fd-theme="dark"]'
_NAV = ":is(.st-key-bgvnav,#bgvnav)"
_NAVM = ":is(.st-key-bgvnavm,#bgvnavm)"
_NAVB = ":is(.st-key-bgvnavb,#bgvnavb)"
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
.stApp{{background:#f6f7f9!important;background-image:none!important;transition:background-color .35s ease;}}
html,body,[class*="css"]{{font-family:'DM Sans',-apple-system,sans-serif!important;}}
.block-container{{max-width:min(1560px,100%);padding:1.1rem 1.25rem .5rem!important;}}
iframe[title="frontdesk_board.frontdesk_board"]{{border:0;display:block;}}
{_D} .stApp{{background:#0b1119!important;}}
{_D} {_NAV} [data-testid="stHorizontalBlock"]{{background:linear-gradient(180deg,#151e2b 0%,#111925 100%)!important;
  border-color:#223044!important;box-shadow:0 1px 2px rgba(0,0,0,.3),0 10px 26px rgba(0,0,0,.35)!important;}}
{_D} {_NAV} [data-testid="stPageLink"] a,{_D} {_NAV} [data-testid="stPageLink"] a p,
{_D} {_NAV} [data-testid="stPageLink"] a span{{color:#c3cdd9!important;}}
{_D} {_NAV} [data-testid="stPageLink"] a:hover{{background:#1c2a3c!important;}}
{_D} {_NAV} [data-testid="stPageLink"] a:hover p,{_D} {_NAV} [data-testid="stPageLink"] a:hover span{{color:#fff!important;}}
{_D} {_NAV} [data-testid="stColumn"]:has(.navactive) [data-testid="stPageLink"] a,
{_D} {_NAV} [data-testid="stColumn"]:has(.navactive) [data-testid="stPageLink"] a p,
{_D} {_NAV} [data-testid="stColumn"]:has(.navactive) [data-testid="stPageLink"] a span{{color:#fff!important;}}
{_D} {_NAV} .stButton button,{_D} {_NAV} .stButton button:focus,{_D} {_NAV} .stButton button:active{{
  background:#151e2b!important;color:#c3cdd9!important;border-color:#2a3648!important;}}
{_D} {_NAV} .stButton button p,{_D} {_NAV} .stButton button span{{color:inherit!important;}}
{_D} {_NAV} .stButton button:hover{{background:#3a1d22!important;color:#ffb4b4!important;border-color:#5a2a31!important;}}
{_D} {_NAVM} .stButton>button,{_D} {_NAVM} [data-testid="stPopover"] button{{background:transparent!important;
  color:#c3cdd9!important;}}
{_D} {_NAVB} [data-testid="stPageLink"] a,{_D} {_NAVB} [data-testid="stPageLink"] a p{{color:#c3cdd9!important;}}
{_D} .navwho{{color:#8d9aab!important;}}
{_D} .navwho b{{color:#e6edf5!important;}}
{_D} .navwho .role{{background:#1a2738!important;color:#8fb6e3!important;}}
{_D} {_NAVB}{{background:#121a26!important;box-shadow:0 -1px 0 #223044!important;}}
{_D} .navm-title{{color:#e6edf5!important;}}
{_D} [data-testid="stAlert"]{{background:#1a2330!important;color:#e6edf5!important;}}
</style>""", unsafe_allow_html=True)

# The board itself -- the save, the staleness check, the 30 s refresh -- is
# frontdesk_view.py, shared with the Schedule page's Front Desk tab.
import frontdesk_view                               # noqa: E402
frontdesk_view.show(key="fdb")
