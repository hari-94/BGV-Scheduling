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

#: How long a session lasts without being used at all. It is renewed on every
#: visit (see ensure_cookie), so somebody who opens the app in a normal working
#: week is never signed out; this is the gap after which they are.
TTL_DAYS = 30


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
    """The token this browser is carrying, or None.

    Only a real, non-empty string counts. Streamlit's cookie jar is not always
    a cookie jar: under a test harness it is a mock whose .get() answers with
    another mock, which is perfectly truthy and would sail on into the hash as
    though somebody were signed in -- failing there instead, with an error
    about buffers that says nothing about sessions.
    """
    try:
        v = st.context.cookies.get(COOKIE)
    except Exception:
        return None
    return v if isinstance(v, str) and v.strip() else None


def _expiry() -> str:
    import datetime
    return (clock.now() + datetime.timedelta(days=TTL_DAYS)).isoformat(timespec="seconds")


def _expired(rec: dict) -> bool:
    """Whether a stored session has run out.

    Parsed rather than compared as text: the stored stamp carries a UTC offset,
    and Breckenridge changes offset twice a year, so two strings that look
    orderable are not. A stamp that will not parse is treated as still valid --
    a bad clock should not sign the floor out.
    """
    import datetime
    raw = (rec or {}).get("expires") or ""
    if not raw:
        return False
    try:
        return datetime.datetime.fromisoformat(raw) < clock.now()
    except ValueError:
        return False


def _extend(token: str) -> None:
    """Push a live session's expiry out again."""
    h = _hash(token)
    try:
        rec = db.load_session(h)
        if not rec:
            return
        rec["expires"] = _expiry()
        db.save_session(h, rec)
    except Exception as ex:
        print(f"[session] could not extend session: {ex}")


def remember(user: dict) -> None:
    """Start a session that survives a refresh."""
    token = secrets.token_urlsafe(32)
    try:
        db.save_session(_hash(token), {
            "username": user.get("username", ""),
            "expires": _expiry(),
        })
    except Exception as ex:
        print(f"[session] could not store session: {ex}")
        return
    st.session_state["_session_token"] = token
    _write_cookie(token)


def ensure_cookie() -> None:
    """Make sure the browser really has the token, on every page.

    Writing it once at sign-in was not enough: the login screen writes the
    cookie and then immediately switches page, and the page it came from is
    torn down before the browser ever runs the little script that would have
    stored it. So nothing was saved, and the next refresh went back to the
    login form.

    This runs on every page instead. st.context.cookies reports what the
    browser sent with the page load, so until a reload happens it will not
    show a cookie written a moment ago -- which means this rewrites it a few
    times over a few reruns. That is harmless: the write is the same each
    time, and it stops of its own accord once a load carries the cookie back.
    """
    token = st.session_state.get("_session_token")
    if not token:
        return
    if _cookie_token() != token:
        _write_cookie(token)       # not carrying it yet; keep offering it
        return
    # It is carrying it -- and that is exactly when the old version stopped,
    # which is why people were signed out anyway. A cookie written from a page
    # has a life the browser decides: Safari on iOS caps a script-set cookie at
    # seven days and will drop it whether or not the app is being used. Since
    # nothing ever reset that clock, everybody was signed out a week after
    # signing in, phones first.
    #
    # So renew it once per browser session: rewrite the cookie to restart its
    # clock and push the record's expiry out to match. Somebody who opens the
    # app in a normal week is then never signed out. Once per session, not per
    # rerun -- each write is an iframe.
    if not st.session_state.get("_session_renewed"):
        st.session_state["_session_renewed"] = True
        _write_cookie(token)
        _extend(token)


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
    if _expired(rec):
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
    # Coming back on a cookie is itself a visit, so start its clock again.
    _extend(token)
    _write_cookie(token)
    st.session_state["_session_renewed"] = True
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
    st.session_state.pop("_session_renewed", None)
    _clear_cookie()
