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


def fetch(file_name, timeout_ms=60000):
    """(bytes, info) for `file_name` in the GC8 Inspections folder, where
    info = {"modified", "by"}; or (None, {"error": why})."""
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
