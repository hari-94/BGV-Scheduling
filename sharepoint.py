"""
sharepoint.py — read a workbook straight from SharePoint, as it is right now.

Preview and Push used to read the OneDrive-synced copy on the office PC,
which trails an Excel Online edit by ten seconds to a minute. An RQS who
fixes a call-off and presses Push straight away deserves the sheet they just
saw. So the file is fetched from SharePoint at the moment of the press,
through the Chrome window on the office PC that is already signed in to
Microsoft 365 (started with --remote-debugging-port=9333). The request is
made inside a SharePoint page, so it carries that window's own sign-in; no
password or token is handled here.

If that window is open its sign-in is used directly; if not, a hidden Chrome
is started on the same profile for the length of the download. If the
sign-in has lapsed, `fetch` returns why and the caller falls back to the
synced copy -- and says so.

Site and folder: the ENG & RQS site (GC8HSKP), Documents › Office › GC8
Inspections, which is what the office PC syncs as
"ENG & RQS - GC8 Inspections".
"""
import base64
import os
import threading

CDP = "http://127.0.0.1:9333"
# The browser profile that was signed in to Microsoft 365 for Power Automate.
# Its cookies keep the sign-in, so a hidden Chrome on the same profile is
# signed in too -- no window has to stay open on the desk.
PROFILE = os.path.join(os.path.expanduser("~"), ".bgv-agent", "pa-browser")
SITE = "https://grandtimber.sharepoint.com/sites/GC8HSKP"
FOLDER = "/sites/GC8HSKP/Shared Documents/Office/GC8 Inspections"

_JS = """async (url) => {
  const meta = await fetch(url + "?$select=TimeLastModified,Length&$expand=ModifiedBy",
                           {headers: {Accept: "application/json;odata=nometadata"},
                            credentials: "include", cache: "no-store"});
  if (!meta.ok) return {error: "SharePoint answered " + meta.status};
  const m = await meta.json();
  const res = await fetch(url + "/$value", {credentials: "include", cache: "no-store"});
  if (!res.ok) return {error: "download answered " + res.status};
  const buf = new Uint8Array(await res.arrayBuffer());
  let bin = ""; const step = 0x8000;
  for (let i = 0; i < buf.length; i += step) bin += String.fromCharCode.apply(null, buf.subarray(i, i + step));
  return {b64: btoa(bin), modified: m.TimeLastModified,
          by: (m.ModifiedBy && m.ModifiedBy.Title) || ""};
}"""


#: One read at a time. The Report sync reads on its own thread, and two hidden
#: Chromes can't share the profile -- the second would fail and a Push would
#: fall back to the synced copy for nothing. A Push waits its turn instead.
_ONE_AT_A_TIME = threading.Lock()


def fetch(file_name, timeout_ms=60000):
    """(bytes, info) for `file_name` in the GC8 Inspections folder, where
    info = {"modified", "by"}; or (None, {"error": why})."""
    if not _ONE_AT_A_TIME.acquire(timeout=150):
        return None, {"error": "another SharePoint read is still running"}
    try:
        return _fetch(file_name, timeout_ms)
    finally:
        _ONE_AT_A_TIME.release()


_LIST_JS = """async (url) => {
  const r = await fetch(url, {headers: {Accept: "application/json;odata=nometadata"},
                              credentials: "include", cache: "no-store"});
  if (!r.ok) return {error: "SharePoint answered " + r.status};
  return await r.json();
}"""


def list_folder(sub, top=20):
    """[(name, modified ISO)] newest first, in a folder under GC8 Inspections
    (e.g. "Arrival Reports") -- for a PC that has no synced copy of it."""
    if not _ONE_AT_A_TIME.acquire(timeout=150):
        return []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            hidden = None
            try:
                browser = p.chromium.connect_over_cdp(CDP, timeout=3000)
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            except Exception:
                hidden = ctx = p.chromium.launch_persistent_context(
                    PROFILE, channel="chrome", headless=True)
            page = ctx.new_page()
            try:
                page.goto(SITE, timeout=60000)
                path = f"{FOLDER}/{sub}".replace("'", "''")
                out = page.evaluate(_LIST_JS, f"{SITE}/_api/web/GetFolderByServerRelativeUrl"
                                    f"('{path}')/Files?$select=Name,TimeLastModified"
                                    f"&$orderby=TimeLastModified desc&$top={int(top)}")
            finally:
                page.close()
                if hidden is not None:
                    hidden.close()
    except Exception:
        return []
    finally:
        _ONE_AT_A_TIME.release()
    return [(f["Name"], f["TimeLastModified"]) for f in (out or {}).get("value", [])]


_PUT_JS = """async ([site, folder, name, b64, expect]) => {
  const q = s => s.replace(/'/g, "''");
  const file = site + "/_api/web/GetFileByServerRelativeUrl('" + q(folder + "/" + name) + "')";
  if (expect) {
    const m = await fetch(file + "?$select=TimeLastModified",
                          {headers: {Accept: "application/json;odata=nometadata"},
                           credentials: "include", cache: "no-store"});
    if (m.ok) {
      const t = (await m.json()).TimeLastModified;
      if (t !== expect) return {error: "changed on SharePoint since it was read (" + t + ")"};
    }
  }
  const ctx = await fetch(site + "/_api/contextinfo", {method: "POST", credentials: "include",
                          headers: {Accept: "application/json;odata=nometadata"}});
  if (!ctx.ok) return {error: "contextinfo answered " + ctx.status};
  const digest = (await ctx.json()).FormDigestValue;
  const bin = atob(b64); const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  const r = await fetch(site + "/_api/web/GetFolderByServerRelativeUrl('" + q(folder) +
                        "')/Files/add(url='" + q(name) + "',overwrite=true)",
                        {method: "POST", credentials: "include", body: buf,
                         headers: {Accept: "application/json;odata=nometadata",
                                   "X-RequestDigest": digest}});
  if (!r.ok) return {error: "upload answered " + r.status + " " + (await r.text()).slice(0, 200)};
  const j = await r.json();
  return {modified: j.TimeLastModified};
}"""


def upload(file_name, data: bytes, expect_modified=None, timeout_ms=120000):
    """Save `data` as `file_name` under the GC8 Inspections folder (a sub-path
    such as "App Outbox/x.txt" works) -- for the backup PC, which has no
    synced folder to write into. With `expect_modified` (the `modified` that
    `fetch` returned), nothing is saved if anybody saved the file since, so a
    stale copy never overwrites the team's typing. (info, None) or (None, why)."""
    # Its own thread: a Push calls this with HotSOS's Playwright still open
    # on the caller's thread, and a second sync Playwright there refuses to
    # start ("Sync API inside the asyncio loop").
    box = {}
    t = threading.Thread(target=lambda: box.update(r=_upload(file_name, data, expect_modified,
                                                             timeout_ms)), daemon=True)
    t.start()
    t.join(timeout_ms / 1000 + 200)
    return box.get("r") or (None, "the upload did not finish")


def _upload(file_name, data, expect_modified, timeout_ms):
    if not _ONE_AT_A_TIME.acquire(timeout=150):
        return None, "another SharePoint call is still running"
    try:
        from playwright.sync_api import sync_playwright
        sub, _, name = f"/{file_name}".rpartition("/")
        with sync_playwright() as p:
            hidden = None
            try:
                browser = p.chromium.connect_over_cdp(CDP, timeout=3000)
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            except Exception:
                hidden = ctx = p.chromium.launch_persistent_context(
                    PROFILE, channel="chrome", headless=True)
            page = ctx.new_page()
            try:
                page.goto(SITE, timeout=timeout_ms)
                if not page.url.startswith(SITE):
                    return None, "this PC's Chrome isn't signed in to SharePoint"
                out = page.evaluate(_PUT_JS, [SITE, FOLDER + sub, name,
                                              base64.b64encode(data).decode(), expect_modified])
            finally:
                page.close()
                if hidden is not None:
                    hidden.close()
    except Exception as ex:
        return None, str(ex).splitlines()[0][:160]
    finally:
        _ONE_AT_A_TIME.release()
    if not out or out.get("error"):
        return None, (out or {}).get("error", "no answer")
    return out, None


def _fetch(file_name, timeout_ms):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as ex:
        return None, {"error": f"playwright missing: {ex}"}
    try:
        with sync_playwright() as p:
            hidden = None
            try:                                   # the visible window, if it's open
                browser = p.chromium.connect_over_cdp(CDP, timeout=3000)
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            except Exception:                      # otherwise its profile, hidden
                hidden = ctx = p.chromium.launch_persistent_context(
                    PROFILE, channel="chrome", headless=True)
            page = next((pg for pg in ctx.pages if pg.url.startswith(SITE)), None)
            opened = page is None
            if opened:
                page = ctx.new_page()
                page.goto(SITE, timeout=timeout_ms)
                if not page.url.startswith(SITE):
                    page.close()
                    return None, {"error": "the office PC's Chrome isn't signed in to SharePoint"}
            path = f"{FOLDER}/{file_name}".replace("'", "''")
            url = f"{SITE}/_api/web/GetFileByServerRelativeUrl('{path}')"
            out = page.evaluate(_JS, url)
            if opened:
                page.close()
            if hidden is not None:
                hidden.close()
    except Exception as ex:
        msg = str(ex).splitlines()[0][:160]
        if "user data directory is already in use" in msg.lower() or "ProcessSingleton" in msg:
            msg = "the sign-in browser profile is busy (another Chrome using it)"
        return None, {"error": msg}
    if not out or out.get("error"):
        return None, {"error": (out or {}).get("error", "no answer")}
    return base64.b64decode(out["b64"]), {"modified": out.get("modified"), "by": out.get("by", "")}


# ── the Housekeeping Dashboard email ─────────────────────────────────────────
# SSRS mails the day's Housekeeping Dashboard to Hari at 5:00 every morning
# ("Housekeeping Dashboard was executed at <date> 5:00 AM", from BGV NoReply),
# landing within the minute. The backup PC can't reach SSRS, but it can read
# that email: the same profile is signed in to Outlook on the web, which keeps
# a mail token in its page storage. Read only -- nothing is moved or marked.
OWA = "https://outlook.office.com/mail/"

_MAIL_JS = r"""async (since) => {
  let k = null;
  for (let i = 0; i < 30 && !k; i++) {
    k = Object.keys(localStorage).find(k => /accesstoken/i.test(k) &&
          (JSON.parse(localStorage[k]).target || "").includes("outlook.office.com/Mail.Read"));
    if (!k) await new Promise(r => setTimeout(r, 1000));
  }
  if (!k) return {error: "Outlook on the web isn't signed in"};
  const H = {headers: {Authorization: "Bearer " + JSON.parse(localStorage[k]).secret,
                       Accept: "application/json"}};
  const api = "https://outlook.office.com/api/v2.0/me/messages";
  const r = await fetch(api + "?$search=" + encodeURIComponent('"Housekeeping Dashboard was executed"')
                        + "&$top=5&$select=Subject,ReceivedDateTime,HasAttachments", H);
  if (!r.ok) return {error: "Outlook answered " + r.status};
  const m = (await r.json()).value.filter(x => x.HasAttachments && x.ReceivedDateTime >= since);
  m.sort((a, b) => a.ReceivedDateTime < b.ReceivedDateTime ? 1 : -1);
  if (!m.length) return {none: true};
  const a = await (await fetch(api + "/" + m[0].Id + "/attachments", H)).json();
  const x = (a.value || []).find(x => /\.xlsx$/i.test(x.Name || ""));
  if (!x) return {error: "the email has no .xlsx"};
  return {b64: x.ContentBytes, subject: m[0].Subject, at: m[0].ReceivedDateTime};
}"""


def dashboard_email(since_utc, timeout_ms=90000):
    """(bytes, info) for the newest Housekeeping Dashboard email received at or
    after `since_utc` ("2026-11-01T06:00:00Z"), info = {"subject", "at"};
    (None, {}) if none has come yet; (None, {"error": why})."""
    if not _ONE_AT_A_TIME.acquire(timeout=150):
        return None, {"error": "another SharePoint read is still running"}
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(PROFILE, channel="chrome", headless=True)
            try:
                page = ctx.new_page()
                page.goto(OWA, timeout=timeout_ms)
                out = page.evaluate(_MAIL_JS, since_utc)
            finally:
                ctx.close()
    except Exception as ex:
        msg = str(ex).splitlines()[0][:160]
        if "user data directory is already in use" in msg.lower() or "ProcessSingleton" in msg:
            msg = "the sign-in browser profile is busy (another Chrome using it)"
        return None, {"error": msg}
    finally:
        _ONE_AT_A_TIME.release()
    if not out or out.get("error"):
        return None, {"error": (out or {}).get("error", "no answer")}
    if out.get("none"):
        return None, {}
    return base64.b64decode(out["b64"]), {"subject": out.get("subject"), "at": out.get("at")}
