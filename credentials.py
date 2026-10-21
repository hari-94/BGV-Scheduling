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

Microsoft 365 is not a stored password: SharePoint is read through a Chrome
profile that somebody signed in to by hand (with a phone approval, usually).
So for it the page can only ask a PC to *test* that sign-in, or to open the
sign-in window so whoever is at that PC can redo it.

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
    "m365": {"label": "Microsoft 365 (SharePoint)", "kind": "signin",
             "used_for": "reading GC8 Inspections and the daily sheet live"},
}

#: Shown on the page so nobody hunts for these in the wrong place.
NOT_HERE = [
    ("SSRS reports", "the office PC's own Windows sign-in -- change it on that PC; "
                     "nothing is stored by the app"),
    ("Supabase key", "Streamlit Cloud > the app > Settings > Secrets, and "
                     ".streamlit/secrets.toml on each agent PC"),
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
        if action == "test":
            data, info = sharepoint.fetch("GC8 Daily Schedule.xlsx")
            if data is None:
                return False, f"SharePoint not readable: {info.get('error', '')}", None
            return True, "SharePoint read OK", None
        if action == "signin":
            import subprocess
            chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            subprocess.Popen([chrome, f"--user-data-dir={sharepoint.PROFILE}",
                              "--new-window", sharepoint.SITE])
            return True, ("sign-in window opened -- whoever is at this PC signs in, "
                          "closes the window, then press Test"), None
    return False, f"unknown request {svc}/{action}", None


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
