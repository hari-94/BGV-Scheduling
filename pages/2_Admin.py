"""
Admin panel — user management (admin only).
"""
import streamlit as st
import sys, os
import html as _html
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

# ── Theme (shared with main app via session_state) ─────────────────────────────
_THEME = "light"   # locked to formal office theme

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500;600&display=swap');
:root{
  --bg:#080810; --bg2:#13131f; --border:rgba(99,102,241,.18); --border-hi:rgba(99,102,241,.45);
  --indigo:#6366f1; --cyan:#22d3ee; --rose:#f43f5e;
  --txt:#e2e8f0; --txt2:#94a3b8; --txt3:#475569;
  --radius:14px; --radius-sm:8px;
}
*{box-sizing:border-box;}
html,body,[class*="css"]{font-family:'DM Sans',sans-serif!important;color:var(--txt)!important;}
.stApp{
  background:var(--bg)!important;
  background-image:
    radial-gradient(ellipse 80% 50% at 20% -10%,rgba(124,58,237,.14) 0%,transparent 60%),
    radial-gradient(ellipse 60% 40% at 80% 100%,rgba(34,211,238,.06) 0%,transparent 55%)!important;
}
.block-container{padding-top:1.4rem!important;max-width:1100px;background:transparent!important;}
::-webkit-scrollbar{width:4px;height:4px;}
::-webkit-scrollbar-thumb{background:var(--indigo);border-radius:99px;}

.pg-title{font-family:'Syne',sans-serif!important;font-size:1.6rem;font-weight:800;letter-spacing:-.04em;
  background:linear-gradient(135deg,#fff 0%,#a78bfa 50%,var(--cyan) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin:0 0 4px}
.pg-sub{font-size:.82rem;color:var(--txt2);margin:0 0 1rem}
.sec{font-family:'DM Mono',monospace!important;font-size:.6rem;font-weight:500;text-transform:uppercase;
     letter-spacing:.16em;color:var(--indigo);padding-bottom:6px;border-bottom:1px solid var(--border);margin:1.2rem 0 .6rem}

.stTabs [data-baseweb="tab-list"]{gap:4px;background:rgba(255,255,255,.03)!important;border:1px solid var(--border)!important;border-radius:var(--radius-sm);padding:4px!important}
.stTabs [data-baseweb="tab"]{border-radius:6px!important;padding:7px 16px!important;font-size:.78rem!important;
  font-weight:600!important;color:var(--txt2)!important;border:none!important;background:transparent!important}
.stTabs [aria-selected="true"]{background:rgba(99,102,241,.2)!important;color:var(--cyan)!important;box-shadow:0 0 0 1px rgba(99,102,241,.4)!important}

section[data-testid="stSidebar"]{
  background:rgba(13,13,26,.88)!important;backdrop-filter:blur(20px)!important;
  border-right:1px solid var(--border)!important;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] *{color:var(--txt2)!important;}
.stButton>button{border-radius:var(--radius-sm)!important;font-weight:600!important;border:1px solid var(--border)!important;
  background:rgba(255,255,255,.04)!important;color:var(--txt)!important;}
.stButton>button:hover{border-color:var(--border-hi)!important;background:rgba(99,102,241,.1)!important;}
.stButton>button[kind="primary"]{background:linear-gradient(135deg,var(--indigo),#818cf8)!important;border:none!important;color:#fff!important;}
.stSelectbox [data-baseweb="select"]>div,.stMultiSelect [data-baseweb="select"]>div,
.stTextInput input,.stTextArea textarea{background:rgba(255,255,255,.03)!important;border:1px solid var(--border)!important;color:var(--txt)!important;}
[data-baseweb="popover"] [role="listbox"],[data-baseweb="menu"]{background:var(--bg2)!important;border:1px solid var(--border)!important;}
label{color:var(--txt2)!important;}
hr{border:none!important;height:1px!important;background:var(--border)!important;}
footer{visibility:hidden!important;}#MainMenu{visibility:hidden!important;}
header[data-testid="stHeader"]{background:transparent!important;height:0!important;}
[data-testid="stSidebarNav"]{display:none !important;}

/* MOBILE */
@media (max-width: 768px) {
  .block-container{padding-left:.5rem!important;padding-right:.5rem!important;max-width:100%!important;}
  .pg-title{font-size:1.3rem!important;}
  .stTabs [data-baseweb="tab-list"]{flex-wrap:wrap!important;}
  .stTabs [data-baseweb="tab"]{padding:5px 10px!important;font-size:.7rem!important;}
  section[data-testid="stSidebar"][aria-expanded="true"]{min-width:88vw!important;max-width:92vw!important;}
  section[data-testid="stSidebar"][aria-expanded="false"]{min-width:0!important;max-width:0!important;margin-left:-92vw!important;}
  [data-testid="stHorizontalBlock"]{flex-direction:column!important;}
  [data-testid="stHorizontalBlock"] > [data-testid="column"]{width:100%!important;flex:1 1 100%!important;min-width:100%!important;}
}
</style>
""", unsafe_allow_html=True)

# Light theme override
if _THEME == "light":
    st.markdown("""<style>
:root{--bg:#f4f5f7;--bg2:#ffffff;--border:#e2e5ea;--border-hi:#c3c9d4;
  --indigo:#2563a8;--cyan:#3b7fb8;
  --txt:#1f2733;--txt2:#5b6675;--txt3:#8a93a1;}
.stApp{background:#f4f5f7!important;background-image:none!important;}
.pg-title{color:#16202e!important;-webkit-text-fill-color:#16202e!important;background:none!important;font-weight:700!important;}
.sec{color:#5b6675!important;border-bottom:1px solid var(--border)!important;}
.stTabs [data-baseweb="tab-list"]{background:#ffffff!important;border:1px solid var(--border)!important;}
.stTabs [aria-selected="true"]{background:#2563a8!important;color:#ffffff!important;}
.stButton>button{background:#ffffff!important;color:var(--txt)!important;border:1px solid var(--border-hi)!important;}
.stButton>button:hover{background:#2563a8!important;color:#ffffff!important;border-color:#2563a8!important;}
section[data-testid="stSidebar"]{background:#ffffff!important;border-right:1px solid var(--border)!important;}
.stSelectbox [data-baseweb="select"]>div,.stTextInput input,.stTextArea textarea{background:#ffffff!important;color:var(--txt)!important;border:1px solid var(--border-hi)!important;}
[data-baseweb="popover"] [role="listbox"],[data-baseweb="menu"]{background:#ffffff!important;}
::-webkit-scrollbar-thumb{background:#c3c9d4!important;}
</style>""", unsafe_allow_html=True)
elif _THEME == "glass-light":
    st.markdown("""<style>
:root{--bg:#eef1f7;--bg2:rgba(255,255,255,.62);--border:rgba(255,255,255,.75);--border-hi:rgba(94,92,230,.45);
  --indigo:#5e5ce6;--cyan:#0a84c1;--txt:#1c1c1e;--txt2:#5b5b60;--txt3:#9a9aa2;}
.stApp{background:#eef1f7!important;background-image:
  radial-gradient(ellipse 90% 60% at 15% -10%,rgba(94,92,230,.14) 0%,transparent 60%),
  radial-gradient(ellipse 70% 50% at 90% 0%,rgba(10,132,193,.10) 0%,transparent 55%)!important;
  background-attachment:fixed!important;}
.kpi{background:rgba(255,255,255,.55)!important;backdrop-filter:blur(26px) saturate(180%)!important;
  -webkit-backdrop-filter:blur(26px) saturate(180%)!important;border:1px solid rgba(255,255,255,.78)!important;
  border-radius:18px!important;box-shadow:0 8px 28px rgba(31,38,135,.10), inset 0 1px 0 rgba(255,255,255,.95)!important;}
.kpi .val{color:#1c1c1e!important;text-shadow:none!important;}
.stTabs [data-baseweb="tab-list"]{background:rgba(255,255,255,.5)!important;border:1px solid rgba(255,255,255,.75)!important;
  backdrop-filter:blur(20px) saturate(170%)!important;-webkit-backdrop-filter:blur(20px) saturate(170%)!important;border-radius:14px!important;}
.stTabs [aria-selected="true"]{background:rgba(255,255,255,.92)!important;color:#5e5ce6!important;
  box-shadow:0 2px 10px rgba(31,38,135,.12)!important;border-radius:10px!important;}
.stButton>button{background:rgba(255,255,255,.6)!important;color:var(--txt)!important;border:1px solid rgba(255,255,255,.8)!important;
  border-radius:13px!important;backdrop-filter:blur(16px)!important;-webkit-backdrop-filter:blur(16px)!important;}
section[data-testid="stSidebar"]{background:rgba(255,255,255,.55)!important;backdrop-filter:blur(34px) saturate(180%)!important;
  -webkit-backdrop-filter:blur(34px) saturate(180%)!important;border-right:1px solid rgba(255,255,255,.7)!important;}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] *{color:var(--txt)!important;}
.stSelectbox [data-baseweb="select"]>div,.stDateInput input,.stTextInput input,.stTextArea textarea{
  background:rgba(255,255,255,.62)!important;color:var(--txt)!important;border:1px solid rgba(255,255,255,.85)!important;border-radius:13px!important;}
[data-baseweb="popover"] [role="listbox"],[data-baseweb="menu"]{background:rgba(255,255,255,.92)!important;backdrop-filter:blur(28px)!important;border-radius:14px!important;}
</style>""", unsafe_allow_html=True)

elif _THEME == "glass-dark":
    st.markdown("""<style>
:root{--bg:#0b0b0f;--bg2:rgba(38,38,48,.5);--border:rgba(255,255,255,.14);--border-hi:rgba(125,122,255,.5);
  --indigo:#7d7aff;--cyan:#64d2ff;--txt:#f2f2f7;--txt2:#aeaeb6;--txt3:#6c6c75;}
.stApp{background:#0b0b0f!important;background-image:
  radial-gradient(ellipse 90% 60% at 15% -10%,rgba(125,122,255,.16) 0%,transparent 60%),
  radial-gradient(ellipse 70% 50% at 90% 0%,rgba(100,210,255,.09) 0%,transparent 55%)!important;
  background-attachment:fixed!important;}
.kpi{background:rgba(36,36,46,.45)!important;backdrop-filter:blur(26px) saturate(160%)!important;
  -webkit-backdrop-filter:blur(26px) saturate(160%)!important;border:1px solid rgba(255,255,255,.14)!important;
  border-radius:18px!important;box-shadow:0 8px 28px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.10)!important;}
.kpi .val{color:#f2f2f7!important;text-shadow:0 0 20px rgba(125,122,255,.4)!important;}
.stTabs [data-baseweb="tab-list"]{background:rgba(36,36,46,.45)!important;border:1px solid rgba(255,255,255,.13)!important;
  backdrop-filter:blur(22px) saturate(150%)!important;-webkit-backdrop-filter:blur(22px) saturate(150%)!important;border-radius:14px!important;}
.stTabs [aria-selected="true"]{background:rgba(125,122,255,.25)!important;color:#cfcdff!important;
  box-shadow:0 0 0 1px rgba(125,122,255,.45)!important;border-radius:10px!important;}
.stButton>button{background:rgba(46,46,58,.5)!important;color:var(--txt)!important;border:1px solid rgba(255,255,255,.15)!important;
  border-radius:13px!important;backdrop-filter:blur(18px)!important;-webkit-backdrop-filter:blur(18px)!important;}
section[data-testid="stSidebar"]{background:rgba(22,22,30,.55)!important;backdrop-filter:blur(36px) saturate(160%)!important;
  -webkit-backdrop-filter:blur(36px) saturate(160%)!important;border-right:1px solid rgba(255,255,255,.12)!important;}
.stSelectbox [data-baseweb="select"]>div,.stDateInput input,.stTextInput input,.stTextArea textarea{
  background:rgba(36,36,46,.5)!important;color:var(--txt)!important;border:1px solid rgba(255,255,255,.15)!important;border-radius:13px!important;}
[data-baseweb="popover"] [role="listbox"],[data-baseweb="menu"]{background:rgba(30,30,40,.92)!important;backdrop-filter:blur(30px)!important;border-radius:14px!important;}
</style>""", unsafe_allow_html=True)

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

tab_users, tab_create, tab_pw, tab_activity = st.tabs(
    ["👥 All Users", "➕ Create User", "🔑 Reset Password", "📊 Activity"])

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
        # Theme-aware colors for the iframe table
        if _THEME.endswith("light"):
            _t_txt="#0f172a"; _t_txt2="#64748b"; _t_th_bg="#f8fafc"; _t_th_tx="#64748b"
            _t_card_bg="#ffffff"; _t_card_br="#e2e8f0"; _t_row_br="#f1f5f9"
            _t_sh="0 2px 12px rgba(0,0,0,.05)"
        else:
            _t_txt="#e2e8f0"; _t_txt2="#94a3b8"; _t_th_bg="rgba(99,102,241,.06)"; _t_th_tx="#475569"
            _t_card_bg="rgba(13,13,26,.9)"; _t_card_br="rgba(99,102,241,.18)"; _t_row_br="rgba(99,102,241,.08)"
            _t_sh="0 8px 32px rgba(0,0,0,.35)"
        ROLE_COL = {"admin":"#a78bfa","rqs":"#5eead4","housekeeper":"#93c5fd"} if not _THEME.endswith("light") else {"admin":"#7C3AED","rqs":"#0D9488","housekeeper":"#2563EB"}
        ROLE_BG  = {"admin":"rgba(167,139,250,.15)","rqs":"rgba(20,184,166,.15)","housekeeper":"rgba(37,99,235,.15)"} if not _THEME.endswith("light") else {"admin":"#F5F3FF","rqs":"#ECFDF5","housekeeper":"#EFF6FF"}
        rows_html = ""
        for u in users:
            role = u.get("role","")
            ac   = ROLE_COL.get(role,"#94a3b8")
            bg   = ROLE_BG.get(role,"rgba(148,163,184,.15)")
            badge= (f'<span style="background:{bg};color:{ac};border-radius:6px;'
                    f'padding:2px 10px;font-size:.71rem;font-weight:700">{role.title()}</span>')
            ll   = u.get("last_login","—") or "Never"
            if ll != "—" and ll != "Never":
                ll = ll[:16].replace("T"," ")
            rows_html += f"""<tr>
              <td style="padding:10px 14px;font-weight:600;color:{_t_txt};border-bottom:1px solid {_t_row_br}">{_html.escape(u.get("username",""))}</td>
              <td style="padding:10px 14px;border-bottom:1px solid {_t_row_br}">{badge}</td>
              <td style="padding:10px 14px;color:{_t_txt2};font-size:.78rem;border-bottom:1px solid {_t_row_br}">{_html.escape(str(u.get("created_at",""))[:10])}</td>
              <td style="padding:10px 14px;color:{_t_txt2};font-size:.78rem;border-bottom:1px solid {_t_row_br}">{_html.escape(ll)}</td>
            </tr>"""
        th_s = (f"padding:9px 14px;text-align:left;font-size:.6rem;font-weight:500;font-family:'DM Mono',monospace;"
                f"text-transform:uppercase;letter-spacing:.1em;color:{_t_th_tx};"
                f"background:{_t_th_bg};border-bottom:1px solid {_t_card_br}")
        tbl = f"""<!DOCTYPE html><html><head>
<style>@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600&display=swap');
*{{box-sizing:border-box;margin:0;padding:0;font-family:'DM Sans',sans-serif;}}</style>
</head><body>
<div style="border-radius:14px;overflow:hidden;border:1px solid {_t_card_br};background:{_t_card_bg};box-shadow:{_t_sh}">
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
# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVITY — who is using the app
# ═══════════════════════════════════════════════════════════════════════════════
with tab_activity:
    st.markdown('<p class="sec">App Usage</p>', unsafe_allow_html=True)
    st.caption("Who has signed in, how often, and when they were last active.")

    from datetime import datetime, timezone, timedelta
    _MTN = timezone(timedelta(hours=-7))   # Mountain Time (matches the schedule app)
    def _fmt_mtn(ts):
        if not ts: return "—"
        try:
            s = str(ts).replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(_MTN).strftime("%b %d, %Y · %I:%M %p")
        except Exception:
            return str(ts)
    def _ago(ts):
        try:
            s = str(ts).replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - dt
            secs = int(delta.total_seconds())
            if secs < 60:    return "just now"
            if secs < 3600:  return f"{secs//60}m ago"
            if secs < 86400: return f"{secs//3600}h ago"
            return f"{secs//86400}d ago"
        except Exception:
            return ""

    summary = db.login_summary()
    events  = db.load_login_events(100)

    if not summary:
        st.info("No sign-ins recorded yet. Activity will appear here as people log in.")
    else:
        # Top-line metrics
        c1, c2, c3 = st.columns(3)
        c1.metric("People signed in", len(summary))
        c2.metric("Total sign-ins", sum(r["count"] for r in summary))
        _last = summary[0]["last_ts"] if summary else ""
        c3.metric("Most recent", _ago(_last) or "—")

        ROLE_LBL = {"admin":"Admin","rqs":"RQS","housekeeper":"Housekeeper"}

        # Per-user rollup
        st.markdown('<p class="sec" style="margin-top:1.2rem">By Person</p>', unsafe_allow_html=True)
        for r in summary:
            role_lbl = ROLE_LBL.get(r["role"], r["role"] or "—")
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'background:#ffffff;border:1px solid #e2e5ea;border-radius:10px;'
                f'padding:10px 14px;margin-bottom:6px">'
                f'<div><span style="font-weight:600;color:#16202e">{_html.escape(r["display_name"])}</span>'
                f'<span style="color:#8a93a1;font-size:.78rem;margin-left:8px">{role_lbl}</span></div>'
                f'<div style="text-align:right">'
                f'<div style="color:#16202e;font-size:.82rem">{_fmt_mtn(r["last_ts"])}</div>'
                f'<div style="color:#8a93a1;font-size:.72rem">{r["count"]} sign-in(s) · {_ago(r["last_ts"])}</div>'
                f'</div></div>',
                unsafe_allow_html=True)

        # Recent sign-in feed
        st.markdown('<p class="sec" style="margin-top:1.2rem">Recent Sign-ins</p>', unsafe_allow_html=True)
        feed = ""
        for e in events[:40]:
            nm = _html.escape(e.get("display_name") or e.get("username","?"))
            role_lbl = ROLE_LBL.get(e.get("role",""), e.get("role","") or "")
            feed += (f'<div style="display:flex;justify-content:space-between;'
                     f'padding:6px 2px;border-bottom:1px solid #eef0f3;font-size:.8rem">'
                     f'<span style="color:#1f2733">{nm}'
                     f'<span style="color:#8a93a1;font-size:.72rem;margin-left:6px">{role_lbl}</span></span>'
                     f'<span style="color:#5b6675">{_fmt_mtn(e.get("ts",""))}</span></div>')
        st.markdown(f'<div style="background:#ffffff;border:1px solid #e2e5ea;'
                    f'border-radius:10px;padding:8px 14px">{feed}</div>', unsafe_allow_html=True)
