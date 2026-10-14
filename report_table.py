"""
report_table.py — the Report page's sortable tables: a static Streamlit
component (components/report_table/index.html) that shows a table drawn in
Python and sorts it when a column name is clicked.

Declared here, in an ordinary module, and never in the page.
declare_component names a component after the module that calls it, and a
page Streamlit runs from pages/ is not a module it can find: on 14 Oct the
page itself declared it, passed every local test (they ran the page as a
script), and on the live app raised "module is None. This should never
happen." for everyone who opened the Report.
"""
import os

import streamlit.components.v1 as components

_component = components.declare_component(
    "report_table",
    path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "components", "report_table"))


def table(html: str, css: str, key: str):
    """Draw one table. Sorting happens in the browser; nothing comes back."""
    return _component(html=html, css=css, key=key, default=None)
