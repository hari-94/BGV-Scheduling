"""
session.py — staying signed in across a refresh.

Streamlit's session state dies with the browser tab, so a refresh dropped
everyone back to the login form. A signed-in browser now carries a random
token in a cookie; the token itself is meaningless, and the record that says
whose it is lives in the database.

Only the hash of the token is stored, so a look at the settings table does not
hand anyone a live session. Signing out deletes the record, which ends the
session everywhere rather than only in the tab that clicked it.
"""
import hashlib
import secrets

import streamlit as st
import streamlit.components.v1 as components

import clock
import db

COOKIE = "bgv_session"
TTL_DAYS = 7


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _write_cookie(token: str, days: int = TTL_DAYS) -> None:
    """Ask the browser to keep the token.

    Streamlit cannot set a response header, so the cookie is written from the
    page. SameSite=Lax keeps it off other people's sites; it is not marked
    Secure because the app is also served over plain http on the property.
    """
    age = int(days * 24 * 3600)
    components.html(
        f"<script>try{{parent.document.cookie="
        f"'{COOKIE}={token}; path=/; max-age={age}; SameSite=Lax';}}"
        f"catch(e){{}}</script>", height=0, width=0)


def _clear_cookie() -> None:
    components.html(
        f"<script>try{{parent.document.cookie="
        f"'{COOKIE}=; path=/; max-age=0; SameSite=Lax';}}"
        f"catch(e){{}}</script>", height=0, width=0)


def _cookie_token():
    try:
        return st.context.cookies.get(COOKIE)
    except Exception:
        return None


def remember(user: dict) -> None:
    """Start a session that survives a refresh."""
    token = secrets.token_urlsafe(32)
    expires = clock.now() + __import__("datetime").timedelta(days=TTL_DAYS)
    try:
        db.save_session(_hash(token), {
            "username": user.get("username", ""),
            "expires": expires.isoformat(timespec="seconds"),
        })
    except Exception as ex:
        print(f"[session] could not store session: {ex}")
        return
    st.session_state["_session_token"] = token
    _write_cookie(token)


def restore() -> bool:
    """Bring back a signed-in session from the browser's cookie.

    Returns True if somebody was signed back in. Any failure -- no cookie, an
    unknown token, an expired one, a user since deleted -- simply means the
    login form, never an error.
    """
    token = _cookie_token()
    if not token:
        return False
    try:
        rec = db.load_session(_hash(token))
    except Exception as ex:
        print(f"[session] lookup failed: {ex}")
        return False
    if not rec:
        return False
    exp = rec.get("expires") or ""
    if exp and exp < clock.now().isoformat(timespec="seconds"):
        try:
            db.delete_session(_hash(token))
        except Exception:
            pass
        return False
    try:
        user = db.get_user(rec.get("username", ""))
    except Exception as ex:
        print(f"[session] user lookup failed: {ex}")
        return False
    if not user:
        return False
    import auth
    auth.login(user)
    st.session_state["_session_token"] = token
    return True


def forget() -> None:
    """End the session on the server as well as in this tab."""
    token = st.session_state.get("_session_token") or _cookie_token()
    if token:
        try:
            db.delete_session(_hash(token))
        except Exception as ex:
            print(f"[session] could not delete session: {ex}")
    st.session_state.pop("_session_token", None)
    _clear_cookie()
