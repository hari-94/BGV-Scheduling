"""
i18n.py — English / Spanish strings and the language switch.

Most of the housekeeping team speaks Spanish, so the pages they actually use
are written in both. The choice is remembered per sign-in, not per session:
someone who picks Spanish once should never have to pick it again.

Only the strings behind `t()` are translated. Anything a manager typed --
names, room numbers, notes -- is passed through untouched.
"""
import streamlit as st

LANGS = {"en": "English", "es": "Español"}
DEFAULT = "en"

STRINGS = {
    # ── navigation and chrome ────────────────────────────────────────────
    "nav.my_home":        ("My Home", "Mi Inicio"),
    "nav.my_rooms":       ("My Rooms", "Mis Cuartos"),
    "nav.schedule":       ("Schedule", "Horario"),
    "nav.dashboard":      ("Dashboard", "Panel"),
    "nav.roster_import":  ("Roster Import", "Importar Lista"),
    "nav.admin":          ("Admin", "Administración"),
    "nav.signed_in_as":   ("Signed in as", "Sesión de"),
    "nav.sign_out":       ("Sign out", "Cerrar sesión"),
    "role.admin":         ("Admin", "Administrador"),
    "role.rqs":           ("RQS", "RQS"),
    "role.housekeeper":   ("Housekeeper", "Camarista"),

    # ── My Rooms ─────────────────────────────────────────────────────────
    "rooms.title":        ("My Rooms", "Mis Cuartos"),
    "rooms.hello":        ("Hello, {name}", "Hola, {name}"),
    "rooms.subtitle":     ("Your rooms for today", "Tus cuartos de hoy"),
    "rooms.none_today":   ("No rooms for you today",
                           "No tienes cuartos hoy"),
    "rooms.none_body":    ("Nothing has been assigned to you yet. If you think "
                           "that is wrong, check with your supervisor.",
                           "Todavía no te han asignado nada. Si crees que hay un "
                           "error, avisa a tu supervisor."),
    "rooms.no_schedule":  ("Today's schedule is not ready yet",
                           "El horario de hoy aún no está listo"),
    "rooms.no_schedule_body": ("Your supervisor has not published today's rooms. "
                               "This page fills in as soon as they do.",
                               "Tu supervisor todavía no ha publicado los cuartos "
                               "de hoy. Esta página se llenará en cuanto lo haga."),
    "rooms.not_matched":  ("We could not match your sign-in to today's schedule "
                           "— pick your name",
                           "No pudimos encontrar tu nombre en el horario de hoy "
                           "— elige tu nombre"),
    "rooms.whose":        ("Whose rooms?", "¿Cuartos de quién?"),
    "rooms.progress":     ("{done} of {total} done", "{done} de {total} listos"),
    "rooms.all_done":     ("All done — great work!",
                           "¡Todo listo — excelente trabajo!"),
    "rooms.total_time":   ("{mins} min", "{mins} min"),
    "rooms.building":     ("Building {b}", "Edificio {b}"),
    "rooms.floor":        ("Floor {f}", "Piso {f}"),
    "rooms.pet":          ("Pet", "Mascota"),
    "rooms.checkout":     ("Late checkout", "Salida tarde"),
    "rooms.updated":      ("Your rooms were just updated by your supervisor",
                           "Tu supervisor acaba de cambiar tus cuartos"),
    "rooms.live":         ("Updating by itself", "Se actualiza solo"),
    "rooms.last_check":   ("Checked {time}", "Revisado {time}"),

    # ── statuses ─────────────────────────────────────────────────────────
    "st.not_started":     ("Not started", "Sin empezar"),
    "st.in_progress":     ("Cleaning", "Limpiando"),
    "st.cleaned":         ("Ready for RQS", "Listo para RQS"),
    "st.inspected":       ("Inspected", "Inspeccionado"),
    "st.dnd":             ("Do not disturb", "No molestar"),
    "st.help":            ("Need help", "Necesito ayuda"),

    # ── actions ──────────────────────────────────────────────────────────
    "act.start":          ("Start", "Empezar"),
    "act.done":           ("Done", "Terminado"),
    "act.undo":           ("Undo", "Deshacer"),
    "act.dnd":            ("Do not disturb", "No molestar"),
    "act.help":           ("Need help", "Necesito ayuda"),
    "act.note":           ("Note", "Nota"),
    "act.note_ph":        ("Anything your supervisor should know?",
                           "¿Algo que tu supervisor deba saber?"),
    "act.save":           ("Save", "Guardar"),
    "act.saved":          ("Saved", "Guardado"),
    "act.offline":        ("Could not save — try again in a moment",
                           "No se pudo guardar — inténtalo de nuevo"),

    # ── services ─────────────────────────────────────────────────────────
    "svc.Full Clean":       ("Full Clean", "Limpieza completa"),
    "svc.Full Clean (IH)":  ("Full Clean (IH)", "Limpieza completa (IH)"),
    "svc.Daily Service":    ("Daily Service", "Servicio diario"),
    "svc.Dust n Vac":       ("Dust n Vac", "Sacudir y aspirar"),
}


def lang() -> str:
    return st.session_state.get("lang") or DEFAULT


def set_lang(code: str) -> None:
    """Switch language and remember it for this sign-in."""
    if code not in LANGS:
        return
    st.session_state["lang"] = code
    user = st.session_state.get("username", "")
    if user:
        try:
            import db
            db.save_user_lang(user, code)
        except Exception as ex:      # a preference is never worth an error page
            print(f"[i18n] could not save language: {ex}")


def load_lang_for_user() -> None:
    """Pick up a remembered language once per session, after sign-in."""
    if st.session_state.get("lang"):
        return
    user = st.session_state.get("username", "")
    code = None
    if user:
        try:
            import db
            code = db.load_user_lang(user)
        except Exception:
            code = None
    st.session_state["lang"] = code if code in LANGS else DEFAULT


def t(key: str, **kw) -> str:
    """Translate `key`, filling in any {placeholders}.

    An unknown key returns itself rather than raising: a missing string should
    look wrong on the page, not take the page down.
    """
    pair = STRINGS.get(key)
    if pair is None:
        return key
    txt = pair[1] if lang() == "es" else pair[0]
    return txt.format(**kw) if kw else txt


def service(name: str) -> str:
    """Translate a service type, passing anything unrecognised through."""
    return t(f"svc.{name}") if f"svc.{name}" in STRINGS else name


def other() -> tuple:
    """The language this user is *not* in: (code, label)."""
    code = "en" if lang() == "es" else "es"
    return code, LANGS[code]
