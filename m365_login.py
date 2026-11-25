"""
m365_login.py — sign an agent PC's browser in to Microsoft 365 as a given
account, with no one at the PC (Hari, 25 Nov: "a master user id and password
that will resume all the operation" if his work account goes).

Everything the office PC reads from or writes to SharePoint and Outlook goes
through one Chrome profile that somebody signed in to by hand
(sharepoint.PROFILE). If that account is switched off, all of it stops. The
Admin page's hand-over (credentials.py, service "m365") sends a manager's
e-mail and password, sealed to each PC; the PC signs a *new* profile in with
them here, proves it can read what the app needs (`verify`), and only then
switches to it (agent.json "m365_profile"). A wrong password, a refused
approval or a missing permission leaves the old profile in use.

GPLRINC signs in through its own ADFS page (fs.grandtimber.com) after
Microsoft's, and may ask for a phone approval. The approval can't be given
from here: the number Microsoft shows is reported (`report`), the Admin page
shows it, and the manager approves on the phone. "Stay signed in?" is
answered Yes, so the profile stays signed in like the hand-made one.

The password is used for the sign-in and kept only in this PC's Credential
Manager (KEYRING), so the agent can sign in again when the session lapses
(`keep_signed_in`) -- never in the database, never in a log.

No Streamlit here.
"""
import os
import re
import time

KEYRING = "BGV M365"
WAIT_SECONDS = 240           # the whole sign-in, approval included
RETRY_SECONDS = 2 * 3600     # keep_signed_in: at most this often


def profile_for(email) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(email).lower()).strip("-")[:60]
    return os.path.join(os.path.expanduser("~"), ".bgv-agent", f"pa-browser-{slug}")


def _visible(page, sel):
    try:
        el = page.query_selector(sel)
        return el if el and el.is_visible() else None
    except Exception:
        return None


def _text(page, sel):
    el = _visible(page, sel)
    try:
        return (el.inner_text() or "").strip() if el else ""
    except Exception:
        return ""


def _drive(page, email, password, report, deadline, done):
    """Answer each sign-in screen until `done(page)` or a refusal. Returns
    (ok, message)."""
    told = None
    pw_sent = 0
    while time.time() < deadline:
        if done(page):
            return True, "signed in"
        # Refusals, in Microsoft's words or ADFS's.
        for sel in ("#usernameError", "#passwordError", "#errorText", "#idTD_Error",
                    "#service_exception_message"):
            t = _text(page, sel)
            if t:
                return False, t[:200]
        # Microsoft: which account.
        el = _visible(page, "input[name=loginfmt]")
        if el and not (el.input_value() or "").strip():
            el.fill(email)
            page.click("#idSIButton9")
            page.wait_for_timeout(2500)
            continue
        # ADFS (fs.grandtimber.com): its own user + password form.
        el = _visible(page, "#passwordInput")
        if el:
            if pw_sent >= 2:
                return False, "the password page came back -- the password was not accepted"
            u = _visible(page, "#userNameInput")
            if u and not (u.input_value() or "").strip():
                u.fill(email)
            el.fill(password)
            pw_sent += 1
            page.click("#submitButton")
            page.wait_for_timeout(3000)
            continue
        # Microsoft's own password page (an account that isn't federated).
        el = _visible(page, "input[name=passwd]")
        if el and not (el.input_value() or "").strip():
            if pw_sent >= 2:
                return False, "the password page came back -- the password was not accepted"
            el.fill(password)
            pw_sent += 1
            page.click("#idSIButton9")
            page.wait_for_timeout(3000)
            continue
        # A phone approval: show the number to whoever approves it.
        num = _text(page, "#idRichContext_DisplaySign")
        msg = None
        if num:
            msg = f"approve the sign-in on the phone -- number {num}"
        elif _visible(page, "#idDiv_SAOTCAS_Description") or _visible(page, "#idDiv_SAOTCAS_Title"):
            msg = "approve the sign-in request on the phone"
        elif _visible(page, "#idTxtBx_SAOTCC_OTC"):
            return False, ("Microsoft asks for a code from the phone, which this PC can't type: "
                           "press Open sign-in and finish it at the PC")
        if msg:
            if msg != told:
                report(msg)
                told = msg
            page.wait_for_timeout(2000)
            continue
        # "Stay signed in?" -- yes, so the profile keeps the sign-in.
        if _visible(page, "#KmsiCheckboxField") or _visible(page, "#KmsiDescription"):
            page.click("#idSIButton9")
            page.wait_for_timeout(2500)
            continue
        page.wait_for_timeout(1500)
    return False, "no answer in time" + (" (the phone approval wasn't given)" if told else "")


def sign_in(email, password, report=lambda m: None, profile=None, headless=True):
    """Sign `profile` (a new one for `email` by default) in as `email`.
    Returns (ok, message, profile)."""
    import sharepoint
    from playwright.sync_api import sync_playwright
    profile = profile or profile_for(email)
    os.makedirs(profile, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(profile, channel="chrome", headless=headless)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(sharepoint.SITE, timeout=90000)
            ok, msg = _drive(page, email, password, report, time.time() + WAIT_SECONDS,
                             lambda pg: pg.url.startswith(sharepoint.SITE))
            if not ok:
                return False, msg, profile
            ok, msg = verify(ctx)
            return ok, msg, profile
        finally:
            ctx.close()


def verify(ctx) -> tuple:
    """Can this sign-in do what the app needs? Each place it reads, by its own
    request. Returns (ok, message)."""
    import prereg
    import sharepoint
    page = ctx.new_page()
    got, bad = [], []
    try:
        checks = [
            ("GC8 Inspections", sharepoint.SITE,
             f"{sharepoint.SITE}/_api/web/GetFolderByServerRelativeUrl('{sharepoint.FOLDER}')"),
            ("Daily Tasks (front desk)", prereg.TEAM_SITE,
             f"{prereg.TEAM_SITE}/_api/web/GetFileById('{prereg.FILE_ID}')"),
        ]
        for name, site, url in checks:
            try:
                page.goto(site, timeout=60000)
                out = page.evaluate(sharepoint._LIST_JS, url + "?$select=Name")
                (bad if (out or {}).get("error") else got).append(name)
            except Exception:
                bad.append(name)
        try:
            page.goto(sharepoint.OWA, timeout=90000)
            page.wait_for_timeout(4000)
            (got if page.url.startswith("https://outlook.") else bad).append("Outlook")
        except Exception:
            bad.append("Outlook")
    finally:
        page.close()
    if bad:
        return False, (f"signed in, but can't open: {', '.join(bad)} -- give this account access "
                       "and hand over again (the old sign-in stays in use)")
    return True, "signed in; reads " + ", ".join(got)


def save_password(email, password):
    import keyring
    keyring.set_password(KEYRING, email, password)


def stored_password(email):
    try:
        import keyring
        return keyring.get_password(KEYRING, email)
    except Exception:
        return None


_LAST_TRY = [0.0]


def keep_signed_in(cfg, report, log, now=None):
    """Called by the agent when SharePoint says the profile isn't signed in:
    sign the handed-over account in again with its saved password, at most
    every RETRY_SECONDS. Returns (ok, message) or None when there is nothing
    it can do (no hand-over yet, no saved password, or too soon)."""
    import sharepoint
    email = cfg.get("m365_user")
    if not email or sharepoint.PROFILE == sharepoint.DEFAULT_PROFILE:
        return None
    now = now or time.time()
    if now - _LAST_TRY[0] < RETRY_SECONDS:
        return None
    _LAST_TRY[0] = now
    pw = stored_password(email)
    if not pw:
        return None
    if not sharepoint._ONE_AT_A_TIME.acquire(timeout=150):
        return None
    try:
        ok, msg, _ = sign_in(email, pw, report=report, profile=sharepoint.PROFILE)
    finally:
        sharepoint._ONE_AT_A_TIME.release()
    log(f"m365: signed in again as {email}: {msg}")
    return ok, msg
