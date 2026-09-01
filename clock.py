"""
clock.py — property-local time.

The lodge is in Breckenridge; the server it runs on may be anywhere, and on a
UTC host the calendar day rolls over at six in the evening Mountain time. Every
date this app shows or stores is the date it is *at the property*, so all of
them come from here rather than from the host's clock.
"""
import datetime as _dt
import zoneinfo as _zi

MTN = _zi.ZoneInfo("America/Denver")


def now() -> _dt.datetime:
    """The current moment at the property, timezone-aware."""
    return _dt.datetime.now(MTN)


def today() -> _dt.date:
    """Today's date at the property."""
    return now().date()


def today_iso() -> str:
    return today().isoformat()


def stamp() -> str:
    """A timestamp for storing, to the second, with its offset."""
    return now().isoformat(timespec="seconds")


def clock_str(fmt: str = "%H:%M:%S") -> str:
    return now().strftime(fmt)
