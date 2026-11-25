"""
credentials.py — changing a service password from the Admin page, without the
password ever sitting in the database readable.

The passwords the agents use live on the agent PCs themselves (the office PC,
and the backup PC that stands in for it), in Windows Credential Manager. When
one changes, somebody used to have to sit at each PC and run `setup`. Now the
Admin page does it:

  * each agent PC keeps its own key pair; the private half never leaves that
    PC's Credential Manager, the public half is published here
    (agent_pubkey_<host>) when the agent starts;
  * the page encrypts the new password once per PC with that PC's public key
    (P-256 ECDH + AES-GCM) and leaves it as a request (cred_req_<host>_<svc>);
  * the agent picks it up within two minutes (five, on a backup PC standing
    by), decrypts it, *signs in with it
    first*, and only saves it if the service accepted it -- a typo on the page
    must not lock the PC out of HotSOS. Then it deletes the request and writes
    what happened (cred_status_<host>_<svc>), which the page shows.

Microsoft 365: SharePoint and Outlook are read through a Chrome profile
signed in to an account. Somebody signed the first one in by hand; since 25
Nov the page can also *hand over* to another account (a manager's, if the
one in use is switched off): the e-mail and password go sealed like a
HotSOS password, the PC signs a new profile in with them (m365_login.py),
shows the phone-approval number on the page while it waits, checks it can
read everything the app reads, and only then switches to it. It can still
*test* the sign-in, or open the sign-in window for whoever is at the PC.

No Streamlit here, so the agent imports it too.
"""
import base64
import json
import os
import socket
import uuid

import clock
import db

PUBKEY_PREFIX = "agent_pubkey_"     # {host, role, pub, at}
REQ_PREFIX = "cred_req_"            # {id, service, action, username?, sealed?, by, at}
STATUS_PREFIX = "cred_status_"      # {id, service, action, ok, msg, username?, by, at}
KEYRING_KEY = ("BGV agent key", "private")

#: The services an agent PC signs in to. "password": the page sends a new one;
#: "signin": a browser sign-in, which the page can only test or reopen.
SERVICES = {
    "hotsos": {"label": "HotSOS", "kind": "password",
               "used_for": "Preview / Push to HotSOS, and the room-status mirror"},
    "m365": {"label": "Microsoft 365 (SharePoint + Outlook)", "kind": "account",
             "used_for": "GC8 Inspections, Schedule, the front desk's Pre-Reg, the ENG sheet "
                         "outbox, App Alerts and the Arrival Report e-mail"},
}

#: Shown on the page so nobody hunts for these in the wrong place.
NOT_HERE = [
    ("SSRS reports", "the office PC's own Windows sign-in -- change it on that PC; "
                     "nothing is stored by the app"),
    ("Supabase key", "Streamlit Cloud > the app > Settings > Secrets, and "
                     ".streamlit/secrets.toml on each agent PC"),
    ("Windows sign-in on the office PC", "the agent and OneDrive run in that sign-in. A new "
     "account signs in to the PC, lets OneDrive sync the GC8 Inspections and Schedules "
     "folders, and runs run_agent.bat once; then hand over Microsoft 365 and HotSOS here"),
    ("Power Automate flows", "Save Arrival Report to SharePoint, ENG sheet update, App Alerts "
     "e-mails, BGV Teams notes. They belong to whoever made them: add a manager as co-owner "
     "now (flow > Share), or they stop with that account"),
    ("ENG sheet Office Script", "'ENG sheet update.osts' sits in its owner's OneDrive; a "
     "co-owner of the flow should save a copy to a shared library"),
    ("E-mails the app depends on", "the Arrival Report e-mail and the 5 AM SSRS Housekeeping "
     "Dashboard go to one mailbox; add a second recipient (front desk list, SSRS "
     "subscription)"),
]


def _b64(b):
    return base64.b64encode(b).decode()


def _aad(host, service):
    # Bound into the ciphertext: a request copied to another PC's or another
    # service's key fails to open rather than being applied there.
    return f"{host}|{service}".encode()


def _seal(pub_pem, secret, host, service):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    pub = serialization.load_pem_public_key(pub_pem.encode())
    eph = ec.generate_private_key(ec.SECP256R1())
    key = HKDF(hashes.SHA256(), 32, None, b"bgv-cred").derive(eph.exchange(ec.ECDH(), pub))
    nonce = os.urandom(12)
    return {"eph": _b64(eph.public_key().public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)),
            "nonce": _b64(nonce),
            "ct": _b64(AESGCM(key).encrypt(nonce, secret.encode(), _aad(host, service)))}


def _open(priv, sealed, host, service):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    eph = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), base64.b64decode(sealed["eph"]))
    key = HKDF(hashes.SHA256(), 32, None, b"bgv-cred").derive(priv.exchange(ec.ECDH(), eph))
    return AESGCM(key).decrypt(base64.b64decode(sealed["nonce"]),
                               base64.b64decode(sealed["ct"]), _aad(host, service)).decode()


def _payload(row):
    p = row.get("payload")
    return json.loads(p) if isinstance(p, str) else (p or {})


# ── the page's side ──────────────────────────────────────────────────────────
def agents():
    """Every agent PC that has registered, newest first."""
    out = [_payload(r) for r in db._like_keys(PUBKEY_PREFIX, with_payload=True)]
    return sorted((a for a in out if a.get("host")), key=lambda a: a.get("at", ""), reverse=True)


def statuses():
    """{(host, service): the last thing that PC reported doing}."""
    out = {}
    for r in db._like_keys(STATUS_PREFIX, with_payload=True):
        p = _payload(r)
        if p.get("host") and p.get("service"):
            out[(p["host"], p["service"])] = p
    return out


def pending():
    """{(host, service): request} still waiting for that PC to pick them up."""
    out = {}
    for r in db._like_keys(REQ_PREFIX, with_payload=True):
        p = _payload(r)
        if p.get("host") and p.get("service"):
            out[(p["host"], p["service"])] = {k: v for k, v in p.items() if k != "sealed"}
    return out


def request_password(service, username, password, by, hosts=None):
    """Leave the new password for every agent PC (or just `hosts`), sealed to
    each one's own key. Returns the hosts it was left for."""
    sent = []
    for a in agents():
        if hosts and a["host"] not in hosts:
            continue
        db._upsert_key(f"{REQ_PREFIX}{a['host']}_{service}", {
            "id": uuid.uuid4().hex, "host": a["host"], "service": service, "action": "set",
            "username": username, "sealed": _seal(a["pub"], password, a["host"], service),
            "by": by, "at": clock.stamp()})
        sent.append(a["host"])
    return sent


def request_action(host, service, action, by):
    """'test' a stored sign-in, or (Microsoft 365) 'signin': open the window."""
    db._upsert_key(f"{REQ_PREFIX}{host}_{service}", {
        "id": uuid.uuid4().hex, "host": host, "service": service, "action": action,
        "by": by, "at": clock.stamp()})


def forget_agent(host):
    """A PC that is gone for good: no more requests are sealed for it."""
    db._delete_key(f"{PUBKEY_PREFIX}{host}")
    for svc in SERVICES:
        db._delete_key(f"{REQ_PREFIX}{host}_{svc}")


# ── the agent's side ─────────────────────────────────────────────────────────
def _private_key():
    """This PC's key, made on first use and kept in Credential Manager (a P-256
    key is short enough to fit; an RSA one is not)."""
    import keyring
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    pem = keyring.get_password(*KEYRING_KEY)
    if pem:
        return serialization.load_pem_private_key(pem.encode(), None)
    key = ec.generate_private_key(ec.SECP256R1())
    keyring.set_password(*KEYRING_KEY, key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode())
    return key


def register(role):
    """Publish this PC's public key, so the page can seal passwords to it."""
    from cryptography.hazmat.primitives import serialization
    host = socket.gethostname()
    pub = _private_key().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    db._upsert_key(f"{PUBKEY_PREFIX}{host}", {"host": host, "role": role, "pub": pub,
                                               "at": clock.stamp()})


def _hotsos_try(username, password):
    from hotsos_client import HotSOS
    h = HotSOS(username, password)
    h.close()


def _apply(req, cfg_path, keyring_service, log):
    """Do one request. Returns (ok, message, username-or-None)."""
    import keyring
    host = socket.gethostname()
    svc, action = req.get("service"), req.get("action")
    if svc == "hotsos":
        cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        if action == "set":
            user = (req.get("username") or cfg.get("hotsos_user") or "").strip()
            pw = _open(_private_key(), req["sealed"], host, svc)
            try:
                _hotsos_try(user, pw)
            except Exception as ex:
                return False, (f"HotSOS refused {user}: {str(ex).splitlines()[0][:160]} "
                               "-- the old password is kept"), user
            keyring.set_password(keyring_service, user, pw)
            cfg["hotsos_user"] = user
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(json.dumps(cfg, indent=2))
            return True, "saved, and HotSOS accepted it", user
        if action == "test":
            user = cfg.get("hotsos_user", "")
            pw = keyring.get_password(keyring_service, user) if user else None
            if not pw:
                return False, "no HotSOS password saved on this PC", user
            try:
                _hotsos_try(user, pw)
            except Exception as ex:
                return False, f"sign-in failed: {str(ex).splitlines()[0][:160]}", user
            return True, "signed in", user
    if svc == "m365":
        import sharepoint
        cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        who = cfg.get("m365_user") or None
        if action == "set":
            return _m365_handover(req, cfg, cfg_path, host, log)
        if action == "test":
            data, info = sharepoint.fetch("GC8 Daily Schedule.xlsx")
            if data is None:
                return False, f"SharePoint not readable: {info.get('error', '')}", who
            return True, "SharePoint read OK", who
        if action == "signin":
            import subprocess
            chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            subprocess.Popen([chrome, f"--user-data-dir={sharepoint.PROFILE}",
                              "--new-window", sharepoint.SITE])
            return True, ("sign-in window opened -- whoever is at this PC signs in, "
                          "closes the window, then press Test"), None
    return False, f"unknown request {svc}/{action}", None


def _m365_handover(req, cfg, cfg_path, host, log):
    """Sign a new profile in as the account the page sent; switch to it only
    once it reads everything (m365_login.py)."""
    import m365_login
    import sharepoint
    email = (req.get("username") or "").strip()
    if "@" not in email:
        return False, "an e-mail address is needed", email

    def report(msg):           # the phone-approval number, while the sign-in waits
        db._upsert_key(f"{STATUS_PREFIX}{host}_m365", {
            "id": req.get("id"), "host": host, "service": "m365", "action": "set",
            "ok": True, "waiting": True, "msg": msg, "username": email,
            "by": req.get("by"), "asked_at": req.get("at"), "at": clock.stamp()})

    pw = _open(_private_key(), req["sealed"], host, "m365")
    if not sharepoint._ONE_AT_A_TIME.acquire(timeout=150):
        return False, "the browser was busy -- send it again", email
    try:
        ok, msg, profile = m365_login.sign_in(email, pw, report=report)
    finally:
        sharepoint._ONE_AT_A_TIME.release()
    if not ok:
        return False, f"{msg} -- still using {cfg.get('m365_user') or 'the original sign-in'}", email
    m365_login.save_password(email, pw)
    cfg.update(m365_user=email, m365_profile=profile)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, indent=2))
    sharepoint.PROFILE = profile
    return True, f"{msg}. This PC now works as {email}", email


def agent_poll(cfg_path, keyring_service, log):
    """Called from the agent's loop: do whatever the page left for this PC."""
    host = socket.gethostname()
    for row in db._like_keys(f"{REQ_PREFIX}{host}_", with_payload=True):
        req = _payload(row)
        if req.get("host") != host:
            continue
        # Gone first: a request that crashes the agent must not run again on
        # every restart. Its sealed password goes with it.
        db._delete_key(row["key"])
        try:
            ok, msg, user = _apply(req, cfg_path, keyring_service, log)
        except Exception as ex:
            ok, msg, user = False, f"{type(ex).__name__}: {str(ex).splitlines()[0][:160]}", None
        label = SERVICES.get(req.get("service"), {}).get("label", req.get("service"))
        log(f"credentials: {label} {req.get('action')} by {req.get('by')}: {msg}")
        db._upsert_key(f"{STATUS_PREFIX}{host}_{req.get('service')}", {
            "id": req.get("id"), "host": host, "service": req.get("service"),
            "action": req.get("action"), "ok": ok, "msg": msg, "username": user,
            "by": req.get("by"), "asked_at": req.get("at"), "at": clock.stamp()})
