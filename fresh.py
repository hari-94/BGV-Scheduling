"""
fresh.py — the app's shared modules as they are on disk now, not as the
running process first loaded them.

Streamlit re-reads a page on every run, but an imported module stays as it
was first loaded, and a deploy that lands while nobody has the app open
leaves every later session on the old copy until somebody reboots the app
(CLAUDE.md, "A deploy does not reload an imported module"). The top menu
lived like that for days in October: no Report link, and a phone layout
fixed on disk but not on anyone's screen.

Each page calls `latest("i18n", "ui")` before drawing the menu. A module is
reloaded the first time this process sees it here and again whenever its
file changes; otherwise the cost is one stat per module. Names go in the
order they depend on each other -- i18n before the ui that uses it.
"""
import importlib
import os
import sys
import threading

_LOCK = threading.Lock()
_SEEN = {}        # module name -> mtime of the file it was last (re)loaded from


def latest(*names):
    for name in names:
        mod = sys.modules.get(name)
        path = getattr(mod, "__file__", None)
        if not path:
            continue
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            continue
        if _SEEN.get(name) == stamp:
            continue
        with _LOCK:
            if _SEEN.get(name) == stamp:
                continue
            try:
                importlib.reload(mod)
            except Exception as ex:         # the old copy is better than no page
                print(f"[fresh] could not reload {name}: {ex}")
            _SEEN[name] = stamp
