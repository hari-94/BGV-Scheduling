"""
warm.py — fill the server's shared caches as soon as the app starts (25 Nov).

After a restart (every deploy, and whenever Streamlit Cloud recycles the
app) the first person to open a page waited for what every page needs: the
staff weeks (~2 s, 95 weeks), today's floor (~0.7 s), the name directory.
Dashboard took ~6 s, My Home ~5 s, the Report ~8 s on a first open; under a
second after. `start()` -- called from auth.require_login, so from the very
first page anybody opens -- reads them once on a thread of its own, once per
process. A page that gets there first just reads them itself, as before.

No Streamlit here.
"""
import sys
import threading
import time

_FLAG = "_bgv_warm_started"      # on sys: survives fresh.latest reloading this module


def _run():
    t0 = time.time()
    done = []
    for name, fn in (("staff weeks", lambda: __import__("db").load_staff_weeks()),
                     ("overrides", lambda: __import__("db").load_staff_overrides()),
                     ("floor", lambda: __import__("floor").today()),
                     ("names", lambda: (__import__("staff_names").aliases(),
                                        __import__("staff_names").attendants()))):
        try:
            fn()
            done.append(name)
        except Exception as ex:
            print(f"[warm] {name}: {type(ex).__name__}: {ex}")
    print(f"[warm] {', '.join(done)} ready in {time.time() - t0:.1f}s")


def start():
    if getattr(sys, _FLAG, False):
        return
    setattr(sys, _FLAG, True)
    threading.Thread(target=_run, daemon=True, name="bgv-warm").start()
