"""
auth.py — Session auth helpers and role-based access control.

Roles:
  admin       → full access: all tabs, user management, edit everything
  rqs         → can paste data, generate schedules, view everything
  housekeeper → view-only: can see Groups tab + their own assignments
"""
import streamlit as st

ROLE_PERMISSIONS = {
    "admin": {
        "can_generate":      True,
        "can_paste_input":   True,
        "can_edit_roster":   True,   # add/remove HKs and inspectors
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
        "can_view_groups":   True,
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

def init_auth():
    """Initialise auth session state keys."""
    for k, v in [("logged_in", False), ("username", ""), ("role", ""), ("user_id", None)]:
        if k not in st.session_state:
            st.session_state[k] = v

def login(user: dict):
    """Set session state after successful authentication."""
    st.session_state["logged_in"] = True
    st.session_state["username"]  = user["username"]
    st.session_state["role"]      = user["role"]
    st.session_state["user_id"]   = user.get("id")

def logout():
    for k in ("logged_in","username","role","user_id"):
        st.session_state[k] = False if k=="logged_in" else ""

def current_user() -> dict:
    return {
        "logged_in": st.session_state.get("logged_in", False),
        "username":  st.session_state.get("username", ""),
        "role":      st.session_state.get("role", ""),
    }

def can(permission: str) -> bool:
    """Check if current user has a specific permission."""
    role = st.session_state.get("role", "")
    return ROLE_PERMISSIONS.get(role, {}).get(permission, False)

def require_login():
    """Stop page if not authenticated."""
    init_auth()
    if not st.session_state.get("logged_in"):
        st.warning("🔒 Please sign in from the main page first.")
        st.stop()

def role_badge(role: str) -> str:
    """Return an HTML badge for the given role."""
    import html as _html
    ac, bg = ROLE_COLORS.get(role, ("#64748b","#f1f5f9"))
    labels = {"admin":"👑 Admin","rqs":"🔍 RQS","housekeeper":"🧑‍🔧 Housekeeper"}
    lbl = labels.get(role, role.title())
    return (f'<span style="background:{bg};color:{ac};border-radius:6px;'
            f'padding:2px 10px;font-size:.72rem;font-weight:700">{_html.escape(lbl)}</span>')