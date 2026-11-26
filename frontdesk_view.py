"""
frontdesk_view.py — the Front Desk board as one drawable piece: the Front Desk
page draws it, and so does the Schedule page's Front Desk tab (Hari, 26 Nov:
"remove the Live tab ... plug in the front desk view, the live tab is
redundant"). One copy of the save, the staleness check and the refresh, so the
two can't drift.

Marks (late checkout, departed, notes) are saved only for someone with
can_view_frontdesk (the desk and managers); anyone else sees the board.
"""
import datetime

import streamlit as st

import auth
import clock

#: The mirror reads HotSOS every two minutes; older than this and the live
#: dot turns amber.
STALE_MINUTES = 6


def _do(action, me):
    """Save one thing the desk did on the board. Returns an error or None."""
    import frontdesk as fd
    day, room, v = clock.today_iso(), action.get("room"), action.get("value")
    try:
        kind = action.get("action")
        if kind == "late":
            fd.set_late_out(day, room, v or None, me)
        elif kind == "departed":
            fd.set_departed(day, room, bool(v), me)
        elif kind == "note":
            fd.add_note(day, room, v, me)
        elif kind == "note_remove":
            fd.remove_note(day, room, v, me)
        else:
            return f"Unknown action {kind!r}"
    except Exception as ex:
        return f"{room}: not saved -- {ex}"
    return None


def _stale(sync) -> bool:
    if sync.get("error"):
        return True
    try:
        at = datetime.datetime.fromisoformat(str(sync.get("at")))
        return (clock.now() - at).total_seconds() > STALE_MINUTES * 60
    except (TypeError, ValueError):
        return True


def show(key: str = "fdb"):
    """Draw the board, refreshed every 30 s. `key` keeps two copies apart
    (the page "fdb", the Schedule tab "fdb_sched")."""
    import frontdesk as fd
    import frontdesk_board
    me = auth.current_user().get("display_name") or fd.SOURCE
    can_edit = auth.can("can_view_frontdesk")
    times = [[t, fd.hhmm12(t)] for t in fd.LATE_TIMES]
    done_k, err_k = f"_{key}_done", f"_{key}_err"

    @st.fragment(run_every="30s")
    def _board():
        import floor
        act = st.session_state.get(key)
        if act and act.get("id") != st.session_state.get(done_k):
            st.session_state[done_k] = act.get("id")
            err = _do(act, me) if can_edit else "Only the front desk and managers can mark rooms."
            st.session_state[err_k] = err
            if err:
                st.error(err)
        try:
            # The shared floor (floor.py): the same rooms, people and statuses as
            # every other tab, the desk's marks and the sheet's added rooms with them.
            f = floor.today()
            rows = f.board()
        except Exception as ex:
            st.error(f"Couldn't read today's rooms: {ex}")
            return
        hs_at = fd.local_hhmm(f.sync.get("at"))
        stamp = "Live" + (f" · HotSOS read {hs_at}" if hs_at else "") + f" · updated {fd.local_hhmm(clock.stamp())}"
        today = clock.today()
        pr = getattr(f, "prereg", None) or {}
        pre = {"at": fd.local_hhmm(pr.get("at")) if pr.get("date") == clock.today_iso() else "",
               "carried": bool(pr.get("carried")) and pr.get("date") == clock.today_iso(),
               "error": pr.get("error") or ""}
        frontdesk_board.board(rows, times, stamp, can_edit, key=key,
                              day=f"{today:%A, %B} {today.day}", stale=_stale(f.sync),
                              ack=st.session_state.get(done_k), ack_err=st.session_state.get(err_k),
                              prereg=pre)

    _board()
