"""
appsecrets.py -- the app's secrets by name, wherever this process runs.

Looked up in this order, first non-empty wins:
  1. an environment variable of the same name (GitHub Actions, any shell);
  2. .streamlit/secrets.toml beside the code, in the working directory, or in
     the home directory (the office PC, the backup PC, local development);
  3. Streamlit's st.secrets (Streamlit Cloud).

Never calls a Streamlit command before the last step, so it is safe to use
before set_page_config. Extracted from db._get_credentials (26 Nov) so the
Supabase keys and the D1 token are found the same way.
"""
import functools
import os
import pathlib
import tomllib

_TOML_PLACES = (
    pathlib.Path(__file__).parent / ".streamlit" / "secrets.toml",
    pathlib.Path.cwd() / ".streamlit" / "secrets.toml",
    pathlib.Path.home() / ".streamlit" / "secrets.toml",
)


@functools.cache
def _toml_files() -> tuple[dict, ...]:
    """Each secrets.toml that exists, read once per process (db.py asks on every call)."""
    found = []
    for path in _TOML_PLACES:
        try:
            found.append(tomllib.loads(path.read_text(encoding="utf-8")))
        except (OSError, tomllib.TOMLDecodeError):
            continue
    return tuple(found)


def get(name: str) -> str:
    """The secret called `name`, or "" if it isn't set anywhere."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    for data in _toml_files():
        value = str(data.get(name, "") or "").strip()
        if value:
            return value
    try:
        import streamlit as st
        return str(st.secrets.get(name, "") or "").strip()
    except Exception:  # no Streamlit, or no secrets file: nothing more to try
        return ""
