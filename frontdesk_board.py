"""
frontdesk_board.py — the Front Desk page's board, a static Streamlit
component (components/frontdesk_board/index.html).

Declared here, in an ordinary module, and never in the page: declare_component
names a component after the module that calls it, and a page run from pages/
is not a module it can find (report_table.py has the story).
"""
import os

import streamlit.components.v1 as components

_component = components.declare_component(
    "frontdesk_board",
    path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "components", "frontdesk_board"))


def board(rows, times, stamp: str, can_edit: bool, key: str, day: str = "",
          stale: bool = False, ack: str = None, ack_err: str = None, prereg: dict = None):
    """Draw the board. Returns the last thing the desk did --
    {id, action, room, value} -- or None. `ack` is the id of the last one the
    page saved (with `ack_err` if it failed): the board's toast waits for it.
    `prereg` = {"at", "carried", "error"}: when the Pre-Reg list was read."""
    return _component(rows=rows, times=times, stamp=stamp, can_edit=can_edit, day=day,
                      stale=stale, ack=ack, ack_err=ack_err, prereg=prereg or {}, key=key, default=None)
