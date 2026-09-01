"""
auth.py — Session auth helpers and role-based access control.

Roles:
  admin       → full access: generate, manage users, view all
  rqs         → generate schedules, view all groups/HKs/inspectors
  housekeeper → view-only: sees ONLY their own group assignments
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

ROLE_COLORS = {
    "admin":        ("#7C3AED", "#F5F3FF"),
    "rqs":          ("#0D9488", "#ECFDF5"),
    "housekeeper":  ("#2563EB", "#EFF6FF"),
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
        "You're the heart of Grand Timber — thank you! 💚",
        "Every room you touch is a gift to our guests! ✨",
        "You make Grand Timber shine — have a great day! 🌞",
        "Your dedication makes the difference — we see you! 🙌",
    ],
}

import random
def get_welcome_msg(role: str) -> str:
    msgs = WELCOME_MESSAGES.get(role, ["Have a great day! ✨"])
    # Use hour as seed so it stays consistent within a session but rotates daily
    from datetime import datetime
    seed = datetime.now().hour + datetime.now().day
    return msgs[seed % len(msgs)]


def init_auth():
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
    init_auth()
    if not st.session_state.get("logged_in"):
        st.warning("🔒 Please sign in from the main page first.")
        st.stop()

def is_housekeeper() -> bool:
    return st.session_state.get("role","") == "housekeeper"

def my_display_name() -> str:
    return st.session_state.get("display_name","") or st.session_state.get("username","")

def role_badge(role: str) -> str:
    import html as _html
    ac, bg = ROLE_COLORS.get(role, ("#64748b","#f1f5f9"))
    labels = {"admin":"👑 Admin","rqs":"🔍 RQS","housekeeper":"🧑‍🔧 Housekeeper"}
    lbl = labels.get(role, role.title())
    return (f'<span style="background:{bg};color:{ac};border-radius:6px;'
            f'padding:2px 10px;font-size:.72rem;font-weight:700">{_html.escape(lbl)}</span>')
