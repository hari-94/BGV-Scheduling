"""
Admin panel — user management (admin only).
"""
import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db, auth

st.set_page_config(page_title="Admin · Cleaning Schedule", page_icon="👑", layout="wide")

st.markdown("""<style>
[data-testid="stSidebarNav"]{display:none !important;}
</style>""", unsafe_allow_html=True)

# Guard: init defaults
for _k, _v in [("logged_in",False),("username",""),("role","")]:
    if _k not in st.session_state: st.session_state[_k] = _v

auth.init_auth()
if not st.session_state.get("logged_in"):
    st.markdown("""
<div style="text-align:center;padding:60px 20px;font-family:Inter,sans-serif">
  <div style="font-size:3rem;margin-bottom:16px">🔒</div>
  <div style="font-size:1.2rem;font-weight:700;color:#1e293b;margin-bottom:8px">Not signed in</div>
  <div style="color:#64748b;margin-bottom:20px">Please sign in from the main page.</div>
</div>""", unsafe_allow_html=True)
    # (navigation via sidebar)
    st.stop()
if not auth.can("can_manage_users"):
    st.error("⛔ Admin access required.")
    # (navigation via sidebar)
    st.stop()

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
*{box-sizing:border-box;} html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.block-container{padding-top:1.4rem!important;max-width:1100px;}

/* MOBILE RESPONSIVE */
@media (max-width: 768px) {
  .block-container{padding-left:.6rem!important;padding-right:.6rem!important;max-width:100%!important;}
  [data-testid="stHorizontalBlock"]{flex-direction:column!important;}
  [data-testid="stHorizontalBlock"] > [data-testid="column"]{width:100%!important;flex:1 1 100%!important;min-width:100%!important;}
}
.pg-title{font-size:1.5rem;font-weight:800;letter-spacing:-.5px;
  background:linear-gradient(135deg,#1e293b,#7C3AED);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin:0 0 3px}
.pg-sub{font-size:.82rem;color:#64748b;margin:0 0 .8rem}
.sec{font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.12em;
     color:#94a3b8;padding-bottom:5px;border-bottom:1.5px solid #f1f5f9;margin:1rem 0 .6rem}
.stTabs [data-baseweb="tab-list"]{gap:4px;background:#f1f5f9;border-radius:10px;padding:3px;border:none!important}
.stTabs [data-baseweb="tab"]{border-radius:8px!important;padding:6px 16px!important;font-size:.78rem!important;
  font-weight:600!important;color:#64748b!important;border:none!important;background:transparent!important}
.stTabs [aria-selected="true"]{background:#fff!important;color:#1e293b!important;box-shadow:0 1px 4px rgba(0,0,0,.1)!important}
</style>
""", unsafe_allow_html=True)

cu = auth.current_user()

# ── Manual sidebar navigation (replaces hidden auto-nav) ─────────────────────
with st.sidebar:
    st.markdown("### 🧭 Navigate")
    st.page_link("cleaning_scheduler.py", label="🧹 Cleaning Schedule")
    st.page_link("pages/1_Dashboard.py", label="📊 Dashboard")
    st.page_link("pages/2_Admin.py", label="⚙️ Admin")
    st.markdown("---")
    _cu = st.session_state.get("display_name","") or st.session_state.get("username","")
    _role = st.session_state.get("role","")
    if _cu:
        st.caption(f"Signed in as **{_cu}** · {_role.title()}")

st.markdown('<p class="pg-title">👑 Admin Panel</p>', unsafe_allow_html=True)
st.markdown(f'<p class="pg-sub">Logged in as <strong>{cu["username"]}</strong> · User management & system settings</p>',
            unsafe_allow_html=True)

tab_users, tab_create, tab_pw = st.tabs(["👥 All Users", "➕ Create User", "🔑 Reset Password"])

# ═══════════════════════════════════════════════════════════════════════════════
# ALL USERS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_users:
    st.markdown('<p class="sec">User Roster</p>', unsafe_allow_html=True)

    users = db.load_users()
    if not users:
        st.info("No users found.")
    else:
        import html as _html
        ROLE_COL = {"admin":"#7C3AED","rqs":"#0D9488","housekeeper":"#2563EB"}
        ROLE_BG  = {"admin":"#F5F3FF","rqs":"#ECFDF5","housekeeper":"#EFF6FF"}
        rows_html = ""
        for u in users:
            role = u.get("role","")
            ac   = ROLE_COL.get(role,"#64748b")
            bg   = ROLE_BG.get(role,"#f1f5f9")
            badge= (f'<span style="background:{bg};color:{ac};border-radius:6px;'
                    f'padding:2px 10px;font-size:.71rem;font-weight:700">{role.title()}</span>')
            ll   = u.get("last_login","—") or "Never"
            if ll != "—" and ll != "Never":
                ll = ll[:16].replace("T"," ")
            rows_html += f"""<tr>
              <td style="padding:10px 14px;font-weight:600;color:#0f172a">{_html.escape(u.get("username",""))}</td>
              <td style="padding:10px 14px">{badge}</td>
              <td style="padding:10px 14px;color:#64748b;font-size:.78rem">{_html.escape(str(u.get("created_at",""))[:10])}</td>
              <td style="padding:10px 14px;color:#64748b;font-size:.78rem">{_html.escape(ll)}</td>
            </tr>"""
        th_s = ("padding:9px 14px;text-align:left;font-size:.67rem;font-weight:700;"
                "text-transform:uppercase;letter-spacing:.08em;color:#64748b;"
                "background:#f8fafc;border-bottom:1.5px solid #e2e8f0")
        tbl = f"""<!DOCTYPE html><html><head>
<style>*{{box-sizing:border-box;margin:0;padding:0;font-family:'Inter',sans-serif;}}</style>
</head><body>
<div style="border-radius:14px;overflow:hidden;border:1px solid #e2e8f0;box-shadow:0 2px 12px rgba(0,0,0,.05)">
<table style="width:100%;border-collapse:collapse;font-size:.82rem">
  <thead><tr>
    <th style="{th_s}">Username</th><th style="{th_s}">Role</th>
    <th style="{th_s}">Created</th><th style="{th_s}">Last Login</th>
  </tr></thead><tbody>{rows_html}</tbody>
</table></div></body></html>"""
        import streamlit.components.v1 as components
        components.html(tbl, height=max(80+len(users)*46,120), scrolling=False)

    # Edit role + delete
    st.markdown('<p class="sec" style="margin-top:1.2rem">Edit User</p>', unsafe_allow_html=True)
    usernames = [u["username"] for u in users if u["username"] != cu["username"]]
    if usernames:
        col_u, col_r = st.columns([2,2])
        with col_u:
            edit_user = st.selectbox("User", usernames, key="edit_user_sel")
        with col_r:
            current_role = next((u["role"] for u in users if u["username"]==edit_user), "housekeeper")
            new_role = st.selectbox("New Role", db.ROLES,
                                    index=db.ROLES.index(current_role) if current_role in db.ROLES else 0,
                                    key="edit_role_sel")

        btn_col1, btn_col2, _ = st.columns([1,1,3])
        with btn_col1:
            save_clicked = st.button("💾 Save Role", key="btn_save_role", use_container_width=True)
        with btn_col2:
            del_clicked  = st.button("🗑 Delete User", key="btn_del_user", use_container_width=True)

        if save_clicked:
            ok, msg = db.update_role(edit_user, new_role)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

        if del_clicked:
            ok, msg = db.delete_user(edit_user)
            if ok:
                st.success(msg)
            else:
                st.error(msg)
    else:
        st.info("No other users to edit.")

# ═══════════════════════════════════════════════════════════════════════════════
# CREATE USER
# ═══════════════════════════════════════════════════════════════════════════════
with tab_create:
    st.markdown('<p class="sec">Create New User</p>', unsafe_allow_html=True)
    with st.form("create_user_form"):
        c1, c2 = st.columns(2)
        with c1:
            new_uname = st.text_input("Username")
            new_role  = st.selectbox("Role", db.ROLES)
        with c2:
            new_pw    = st.text_input("Password", type="password")
            new_pw2   = st.text_input("Confirm Password", type="password")
        submitted = st.form_submit_button("➕ Create User", type="primary")
        if submitted:
            if new_pw != new_pw2:
                st.error("Passwords don't match.")
            elif len(new_pw) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                ok, msg = db.create_user(new_uname, new_pw, new_role)
                st.success(msg) if ok else st.error(msg)

    st.markdown("""
<div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:10px;
            padding:12px 16px;font-size:.8rem;color:#92400e;margin-top:12px">
  <strong>Role permissions:</strong><br>
  👑 <strong>Admin</strong> — Full access: generate schedules, manage users, edit everything<br>
  🔍 <strong>RQS</strong> — Paste room data, generate schedules, view all tabs and dashboard<br>
  🧑‍🔧 <strong>Housekeeper</strong> — View-only: see their groups and the schedule
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# RESET PASSWORD
# ═══════════════════════════════════════════════════════════════════════════════
with tab_pw:
    st.markdown('<p class="sec">Reset User Password</p>', unsafe_allow_html=True)
    all_users = db.load_users()
    unames_all = [u["username"] for u in all_users]
    if unames_all:
        with st.form("reset_pw_form"):
            target_user = st.selectbox("User to reset", unames_all)
            new_pw_r    = st.text_input("New Password", type="password")
            new_pw_r2   = st.text_input("Confirm New Password", type="password")
            if st.form_submit_button("🔑 Reset Password", type="primary"):
                if new_pw_r != new_pw_r2:
                    st.error("Passwords don't match.")
                elif len(new_pw_r) < 6:
                    st.error("Minimum 6 characters.")
                else:
                    ok, msg = db.update_password(target_user, new_pw_r)
                    st.success(msg) if ok else st.error(msg)

    # Change own password
    st.markdown('<p class="sec" style="margin-top:1.2rem">Change My Password</p>', unsafe_allow_html=True)
    with st.form("change_own_pw"):
        old_pw  = st.text_input("Current Password", type="password")
        new_pw_own = st.text_input("New Password", type="password")
        new_pw_own2= st.text_input("Confirm", type="password")
        if st.form_submit_button("Update My Password"):
            verified = db.authenticate(cu["username"], old_pw)
            if not verified:
                st.error("Current password incorrect.")
            elif new_pw_own != new_pw_own2:
                st.error("New passwords don't match.")
            elif len(new_pw_own) < 6:
                st.error("Minimum 6 characters.")
            else:
                ok, msg = db.update_password(cu["username"], new_pw_own)
                st.success(msg) if ok else st.error(msg)