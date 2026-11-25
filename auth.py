"""
auth.py — Session auth helpers and role-based access control.

Roles:
  admin       → full access: generate, manage users, view all
  rqs         → generate schedules, view all groups/HKs/inspectors
  housekeeper → view-only: sees ONLY their own group assignments
  houseperson → the same phone-only access as a housekeeper; My Rooms shows
                their carpet and stripping rooms (duties.py). Its own role so
                the Admin page and the menu say what they are (HP, 21 Oct)
  frontdesk   → the Front Desk page only: today's rooms, late checkouts,
                departures and notes (Hari, 21 Nov)
"""
import streamlit as st

ROLE_PERMISSIONS = {
    "admin": {
        "can_generate":      True,
        "can_paste_input":   True,
        "can_edit_roster":   True,
        "can_view_groups":   True,
        "can_view_hk_tab":   True,
        "can_view_insp_tab": True,
        "can_manage_users":  True,
        "can_view_dashboard":True,
        "can_delete_data":   True,
    },
    "rqs": {
        "can_generate":      True,
        "can_paste_input":   True,
        "can_edit_roster":   False,
        "can_view_groups":   True,
        "can_view_hk_tab":   True,
        "can_view_insp_tab": True,
        "can_manage_users":  False,
        "can_view_dashboard":True,
        "can_delete_data":   False,
    },
    "housekeeper": {
        "can_generate":      False,
        "can_paste_input":   False,
        "can_edit_roster":   False,
        "can_view_groups":   True,   # filtered to own groups only
        "can_view_hk_tab":   True,
        "can_view_insp_tab": False,
        "can_manage_users":  False,
        "can_view_dashboard":False,
        "can_delete_data":   False,
    },
}
# A houseperson sees what a housekeeper sees: their own day, nothing to edit.
ROLE_PERMISSIONS["houseperson"] = dict(ROLE_PERMISSIONS["housekeeper"])
# The front desk (Hari, 21 Nov): one shared account whose menu is the Front
# Desk page alone -- today's rooms, and their late checkouts, departures and
# notes. Managers (admin) have the page too; RQS and the floor don't.
ROLE_PERMISSIONS["frontdesk"] = {p: False for p in ROLE_PERMISSIONS["admin"]}
for _r in ROLE_PERMISSIONS:
    ROLE_PERMISSIONS[_r]["can_view_frontdesk"] = _r in ("admin", "frontdesk")

#: Where each role lands after signing in.
HOME = {"frontdesk": "pages/14_Front_Desk.py"}


def home_page(role=None) -> str:
    return HOME.get(role if role is not None else st.session_state.get("role", ""),
                    "pages/4_My_Home.py")


def is_frontdesk() -> bool:
    return st.session_state.get("role", "") == "frontdesk"

ROLE_COLORS = {
    "admin":        ("#7C3AED", "#F5F3FF"),
    "rqs":          ("#0D9488", "#ECFDF5"),
    "housekeeper":  ("#2563EB", "#EFF6FF"),
    "houseperson":  ("#B45309", "#FFFBEB"),
    "frontdesk":    ("#BE185D", "#FDF2F8"),
}

# Positive welcome messages per role
WELCOME_MESSAGES = {
    "admin": [
        "Ready to make today's operations seamless! 🚀",
        "You've got this — let's make today exceptional! ✨",
        "Leading with excellence today! 💫",
    ],
    "rqs": [
        "Your inspections keep standards high — let's go! 🔍",
        "Every room you inspect shines a little brighter! ✨",
        "Quality starts with you — have a great shift! 💪",
    ],
    "housekeeper": [
        "Your hard work makes every guest's day better! 🌟",
        "You're the heart of BGV Peak 8 — thank you! 💚",
        "Every room you touch is a gift to our guests! ✨",
        "You make BGV Peak 8 shine — have a great day! 🌞",
        "Your dedication makes the difference — we see you! 🙌",
    ],
    "houseperson": [
        "Fresh carpets and ready rooms start with you! 🌟",
        "You keep the whole floor moving — thank you! 💪",
        "Every room you prepare makes the day easier for everyone! ✨",
    ],
}

def get_welcome_msg(role: str) -> str:
    msgs = WELCOME_MESSAGES.get(role, ["Have a great day! ✨"])
    # Use hour as seed so it stays consistent within a session but rotates daily
    from datetime import datetime
    seed = datetime.now().hour + datetime.now().day
    return msgs[seed % len(msgs)]


def init_auth():
    # The first visit to a freshly started app also fills the shared caches,
    # in the background (warm.py) -- once per process.
    try:
        import warm
        warm.start()
    except Exception:
        pass
    fresh = "logged_in" not in st.session_state
    for k, v in [("logged_in",False),("username",""),("display_name",""),("role",""),("user_id",None)]:
        if k not in st.session_state:
            st.session_state[k] = v
    # A refresh starts a brand new session state, which is what used to throw
    # everyone back to the login form. If the browser still carries a valid
    # token, sign them straight back in.
    if fresh and not st.session_state["logged_in"]:
        try:
            import session
            # A deploy doesn't reload an imported module (fresh.py): the live
            # app ran the cookie-only session.py for a day after the URL-token
            # fix was pushed, and phones kept being signed out (7 Nov).
            import fresh as _fresh
            _fresh.latest("session")
            session.restore()
        except Exception as ex:
            print(f"[auth] session restore failed: {ex}")

def login(user: dict):
    st.session_state["logged_in"]    = True
    st.session_state["username"]     = user["username"]
    st.session_state["display_name"] = user.get("display_name") or user["username"]
    st.session_state["role"]         = user["role"]
    st.session_state["user_id"]      = user.get("id")

def logout():
    try:
        import session
        session.forget()
    except Exception as ex:
        print(f"[auth] session cleanup failed: {ex}")
    for k in ("logged_in","username","display_name","role","user_id"):
        st.session_state[k] = False if k=="logged_in" else ""

def current_user() -> dict:
    return {
        "logged_in":    st.session_state.get("logged_in", False),
        "username":     st.session_state.get("username", ""),
        "display_name": st.session_state.get("display_name", ""),
        "role":         st.session_state.get("role", ""),
    }

def can(permission: str) -> bool:
    role = st.session_state.get("role", "")
    return ROLE_PERMISSIONS.get(role, {}).get(permission, False)

def require_login():
    """Send anyone who is not signed in to the sign-in screen.

    It used to stop the page with a note telling them to go to the main page
    themselves, which on a refreshed inner page is a dead end with no link out
    of it.
    """
    init_auth()
    # Restored on an inner page: they stay there. Only the entry page sends a
    # restored sign-in home, and this must not bounce a later visit to it.
    st.session_state.pop("_restored_now", None)
    if st.session_state.get("logged_in"):
        return
    try:
        st.switch_page("cleaning_scheduler.py")
    except Exception:
        # Older Streamlit, or a context where switching is not allowed.
        st.warning("Please sign in from the main page first.")
        st.stop()

def is_housekeeper() -> bool:
    """The phone-only view: housekeepers, and housepersons, who see the same."""
    return st.session_state.get("role","") in ("housekeeper", "houseperson")


def my_display_name() -> str:
    return st.session_state.get("display_name","") or st.session_state.get("username","")

def role_badge(role: str) -> str:
    import html as _html
    ac, bg = ROLE_COLORS.get(role, ("#64748b","#f1f5f9"))
    labels = {"admin":"👑 Admin","rqs":"🔍 RQS","housekeeper":"🧑‍🔧 Housekeeper"}
    lbl = labels.get(role, role.title())
    return (f'<span style="background:{bg};color:{ac};border-radius:6px;'
            f'padding:2px 10px;font-size:.72rem;font-weight:700">{_html.escape(lbl)}</span>')
