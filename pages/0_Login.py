"""
Login page — handles sign-in and first-time setup.
"""
import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import db, auth

st.set_page_config(page_title="Login · Cleaning Schedule",
                   page_icon="🔑", layout="centered")

auth.init_auth()

# Already logged in
if st.session_state.get("logged_in"):
    st.success(f"✅ Already signed in as **{st.session_state.get('username','')}**. Go to the main page.")
    st.stop()

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
*,*::before,*::after{box-sizing:border-box;}
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.block-container{padding-top:3rem!important;max-width:420px!important;}
.login-card{
  background:#fff;border:1px solid #e2e8f0;border-radius:20px;
  padding:36px 36px 28px;
  box-shadow:0 4px 24px rgba(0,0,0,.08),0 1px 4px rgba(0,0,0,.04);
}
.login-title{
  font-size:1.5rem;font-weight:800;letter-spacing:-.5px;
  background:linear-gradient(135deg,#1e293b,#5B4FE9);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text;margin:0 0 4px;text-align:center;
}
.login-sub{font-size:.82rem;color:#64748b;text-align:center;margin:0 0 24px}
.stButton>button{
  width:100%!important;border-radius:10px!important;
  font-weight:700!important;font-size:.85rem!important;
  background:linear-gradient(135deg,#5B4FE9,#7C6FF5)!important;
  border:none!important;color:#fff!important;padding:10px!important;
  box-shadow:0 2px 8px rgba(91,79,233,.3)!important;
  transition:all .15s!important;
}
.stButton>button:hover{box-shadow:0 4px 16px rgba(91,79,233,.45)!important;transform:translateY(-1px)}
.stTextInput input{border-radius:10px!important;border:1.5px solid #e2e8f0!important;padding:10px 12px!important;}
.stTextInput input:focus{border-color:#5B4FE9!important;box-shadow:0 0 0 3px rgba(91,79,233,.12)!important;}
</style>
""", unsafe_allow_html=True)

# ── Try Supabase connection + ensure admin ─────────────────────────────────────
try:
    db.ensure_admin_exists()
    _db_ok = True
except Exception as _db_err:
    _db_ok = False
    _db_err_msg = str(_db_err)

# ── Login form ─────────────────────────────────────────────────────────────────
st.markdown('<div class="login-card">', unsafe_allow_html=True)
st.markdown('<p class="login-title">🧹 Cleaning Schedule</p>', unsafe_allow_html=True)
st.markdown('<p class="login-sub">Sign in to continue</p>', unsafe_allow_html=True)

if not _db_ok:
    st.error(f"⚠️ Database not connected. Check your Supabase credentials.\n\n`{_db_err_msg}`")
    st.markdown("""
**Quick fix:**
1. Create a `.streamlit/secrets.toml` file with:
```toml
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_KEY = "your-anon-key"
```
2. Or set environment variables `SUPABASE_URL` and `SUPABASE_KEY`
""")
    st.stop()

username = st.text_input("Username", placeholder="Enter your username", key="li_user")
password = st.text_input("Password", placeholder="Enter your password",
                          type="password", key="li_pass")

if st.button("Sign In", type="primary"):
    if not username or not password:
        st.error("Please enter both username and password.")
    else:
        user = db.authenticate(username.strip(), password)
        if user:
            auth.login(user)
            st.success(f"Welcome back, **{user['username']}**!")
            st.rerun()
        else:
            st.error("Invalid username or password.")

st.markdown("</div>", unsafe_allow_html=True)

# ── Helpful hint ───────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;margin-top:16px;font-size:.75rem;color:#94a3b8">
  First time? Default admin credentials:<br>
  <strong>Username:</strong> admin &nbsp;·&nbsp; <strong>Password:</strong> admin1234<br>
  <em>Change your password after first login.</em>
</div>
""", unsafe_allow_html=True)