"""
xlsx_compat.py — let openpyxl open workbooks the newest Excel saves.

On 5 Nov 2026, while IT was updating internal apps, GC8 Inspections 2026.xlsx
was saved with one font Excel now writes -- Aptos, `<family val="18"/>` -- and
openpyxl 3.1.5 caps a font's family at 14, so it refused the whole workbook
("could not read stylesheet"). Every reader of that file stopped at once: the
sheet -> app sync, the Teams notes' HK/RQS lookup, the Report, and the 5 AM
build, which writes the day's tab into it. Excel itself is fine with 18.

Importing this module raises the cap. It is idempotent and does nothing else;
every module that calls openpyxl.load_workbook (directly or through pandas)
imports it first.
"""
try:
    from openpyxl.styles.fonts import Font as _Font
    # The descriptor on the class, not a font's value.
    _Font.__dict__["family"].max = 255
except Exception as _ex:                      # an openpyxl that moved it: say so
    print(f"[xlsx_compat] could not relax the font family limit: {_ex}")
