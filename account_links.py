"""
account_links.py — which row of the staff sheet an app account is.

My Home and My Rooms used to find a person only by guessing from the sign-in:
the display name, then the username ("rmejia@..." is Rosibel Mejia). That
cannot work for a new hire the sheet knows by first name alone ("Janelly",
"Carolina", 11 Nov), nor for somebody whose sign-in is a nickname's surname
(krafael@... is the sheet's "Enrique", HotSOS's "Kike Rafael"). An admin now
picks the sheet name when the account is made, or later on Edit User, and
that link is tried before any guess.

    LINKS_KEY  {"links": {username: name as on the sheet},
                "by": {username: who linked it}, "at": {username: when}}

Kept in app_settings rather than a column of app_users, so it needed no
change to the table. A name renamed later by the name directory
(staff_names) still finds its person: pages compare `staff_names.full` of
the link too.

No Streamlit here.
"""
import datetime

import clock
import db
import roster_import as ri

LINKS_KEY = "account_links"
SUFFIX = " · "     # roster_import's "Federico Lopez · Houseperson PM"


def _record() -> dict:
    return db._load_key(LINKS_KEY) or {}


def links() -> dict:
    """{username: sheet name}."""
    return _record().get("links") or {}


def link_for(username: str) -> str:
    return links().get(str(username or "").strip().lower(), "")


def set_link(username: str, name: str, by: str = "") -> None:
    """Link `username` to the sheet's `name`; an empty name removes the link."""
    uname = str(username or "").strip().lower()
    rec = _record()
    lk, who, at = (dict(rec.get(k) or {}) for k in ("links", "by", "at"))
    name = str(name or "").partition(SUFFIX)[0].strip()
    if name:
        lk[uname], who[uname], at[uname] = name, by, clock.stamp()
    else:
        for d in (lk, who, at):
            d.pop(uname, None)
    db._upsert_key(LINKS_KEY, {"links": lk, "by": who, "at": at})


def set_display_name(username: str, display: str) -> None:
    """The name the app greets them by. db.create_user does not take one."""
    db._client().table("app_users").update(
        {"display_name": display.strip()}).eq(
        "username", username.strip().lower()).execute()


def sheet_people(weeks=None, since_days=7) -> dict:
    """{name: section} for everyone on the sheet from last week onward,
    the latest week's section winning. Second-section rows ("· Houseperson
    PM") are folded into the person; the account is the person, not the row."""
    weeks = db.load_staff_weeks() if weeks is None else weeks
    cutoff = (clock.today() - datetime.timedelta(days=since_days)).isoformat()
    out = {}
    for wk in sorted(weeks):
        w = weeks[wk]
        if max(w.get("dates") or [""]) < cutoff:
            continue
        for n, p in (w.get("people") or {}).items():
            base, sep, _ = n.partition(SUFFIX)
            if base not in out or not sep:
                out[base] = p.get("section") or p.get("group") or ""
    return dict(sorted(out.items(), key=lambda kv: kv[0].lower()))


def find_pid(index: dict, name: str, aliases=None):
    """The pid in roster_import's people_index for a linked name, preferring
    the person's main row over a second section's."""
    if not name:
        return None
    want = {ri.norm_name(name)}
    full = (aliases or {}).get(name)
    if full:
        want.add(ri.norm_name(full))
    hits = [p for p, i in index.items()
            if ri.norm_name(str(i["label"]).partition(SUFFIX)[0]) in want]
    hits.sort(key=lambda p: SUFFIX in str(index[p]["label"]))
    return hits[0] if hits else None


def unaccounted(users, people=None, aliases=None) -> list:
    """[(name, section)] on the sheet that no account is linked to or would be
    matched to by My Home's guess -- most likely a new hire with no sign-in
    yet. Managers, sales and the like are on the sheet too; the page says so."""
    people = sheet_people() if people is None else people
    lk = links()
    linked = {ri.norm_name(v) for v in lk.values()}
    index = {n: {"label": n} for n in people}
    al = aliases or {}
    low = {k.lower(): v for k, v in al.items()}
    matched = set()
    for u in users:
        if u["username"] in lk:
            continue
        disp = u.get("display_name") or ""
        cands = [n for n in (low.get(disp.strip().lower(), ""), disp) if n]
        try:
            hit = ri.match_person(index, *cands, u["username"], aliases=al)
        except TypeError:
            hit = ri.match_person(index, *cands, u["username"])
        if hit:
            matched.add(hit)
    return [(n, s) for n, s in people.items()
            if n not in matched and ri.norm_name(n) not in linked]
