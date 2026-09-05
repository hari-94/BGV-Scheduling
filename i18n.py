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
    "rooms.subtitle_team": ("The rooms you are inspecting today",
                            "Los cuartos que inspeccionas hoy"),
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
    "rooms.team_note":    ("housekeepers you are inspecting today — you can mark a room for any of them",
                           "camaristas que inspeccionas hoy — puedes marcar un cuarto por cualquiera de ellas"),
    "rooms.mark_rest":    ("Mark the rest done", "Marcar el resto como terminado"),
    "rooms.notes_new":    ("{n} new note(s) from your team",
                           "{n} nota(s) nueva(s) de tu equipo"),
    "rooms.notes_read":   ("Mark the notes as read", "Marcar las notas como leídas"),
    "rooms.more":         ("Details", "Detalles"),
    "rooms.yourday":      ("YOUR DAY", "TU DÍA"),
    "rooms.startwith":    ("Start with", "Empieza con"),
    "rooms.by":           ("by", "para las"),
    "nav.property":       ("Property", "Propiedad"),
    "nav.profile":        ("Profile", "Mi perfil"),
    "profile.hello":      ("Signed in as", "Sesión iniciada como"),
    "profile.change_pw":  ("Change your password", "Cambia tu contraseña"),
    "profile.rule":       ("At least {n} characters. Only you can change it — "
                           "nobody else needs to know the new one.",
                           "Al menos {n} caracteres. Solo tú puedes cambiarla; "
                           "nadie más necesita saber la nueva."),
    "profile.current":    ("Current password", "Contraseña actual"),
    "profile.new":        ("New password", "Contraseña nueva"),
    "profile.confirm":    ("New password again", "Repite la contraseña nueva"),
    "profile.signout_others": ("Sign out my other phones and computers",
                               "Cerrar sesión en mis otros teléfonos y computadoras"),
    "profile.save":       ("Change my password", "Cambiar mi contraseña"),
    "profile.done":       ("Done — your password is changed. You are still signed in here.",
                           "Listo: tu contraseña cambió. Aquí sigues con la sesión abierta."),
    "profile.ended_others": ("Signed out of {n} other device(s).",
                             "Se cerró la sesión en {n} dispositivo(s) más."),
    "profile.err_blank":  ("Fill in all three boxes.", "Llena las tres casillas."),
    "profile.err_current": ("That is not your current password.",
                            "Esa no es tu contraseña actual."),
    "profile.err_match":  ("The two new passwords are not the same.",
                           "Las dos contraseñas nuevas no son iguales."),
    "profile.err_short":  ("Too short — use at least {n} characters.",
                           "Muy corta: usa al menos {n} caracteres."),
    "profile.err_same":   ("That is the password you already have.",
                           "Esa es la contraseña que ya tienes."),
    "profile.err_save":   ("Could not save it. Try again in a moment.",
                           "No se pudo guardar. Inténtalo de nuevo en un momento."),
    "profile.help":       ("Forgotten your password? A manager can set a new one for you.",
                           "¿Olvidaste tu contraseña? Un gerente puede ponerte una nueva."),
    "prop.no_access":     ("This page is for managers and RQS.",
                           "Esta página es para gerentes y RQS."),
    "prop.no_rooms":      ("No schedule has been saved yet, so there are no rooms to place.",
                           "Aún no se ha guardado ningún horario, así que no hay cuartos que ubicar."),
    "prop.colour":        ("Colour by", "Color por"),
    "prop.by_status":     ("Cleaning status", "Estado de limpieza"),
    "prop.by_service":    ("Service", "Servicio"),
    "prop.by_building":   ("Building", "Edificio"),
    "prop.off_today":     ("Not on a chart today", "Sin hoja hoy"),
    "prop.show_amenities": ("Amenities", "Amenidades"),
    "prop.flat":          ("2D plan", "Plano 2D"),
    "prop.size_note":     ("Box depth is the room's cleaning time — a 140 is deeper "
                           "than a 120, and a 70 deeper than a Dust n Vac. The room "
                           "number and its service are printed on the top of each box.",
                           "La profundidad de cada caja es el tiempo de limpieza: un 140 "
                           "es más profundo que un 120, y un 70 más que un Dust n Vac. "
                           "El número del cuarto y su servicio van impresos arriba."),
    "prop.refresh":       ("Refresh status", "Actualizar estado"),
    "prop.getting_around": ("Getting around the property", "Moverse por la propiedad"),
    "prop.bridges_title": ("Where the bridges are", "Dónde están los puentes"),
    "prop.costs_title":   ("What a walk costs", "Cuánto cuesta caminar"),
    "prop.caveat":        ("Every room sits at its true building, level and place along "
                           "the corridor, and each bridge is drawn at the level it crosses. "
                           "The plans carry no measurements, so the proportions are taken "
                           "off the drawings rather than surveyed.",
                           "Cada cuarto está en su edificio, nivel y lugar real del pasillo, "
                           "y cada puente se dibuja en el nivel que cruza. Los planos no "
                           "traen medidas, así que las proporciones se tomaron de los dibujos, "
                           "no de un levantamiento."),
    "rooms.arrival":      ("Arrival", "Llegada"),
    "rooms.the_room":     ("The room", "El cuarto"),
    "rooms.guest_now":    ("Guest now", "Huésped actual"),
    "rooms.guest_next":   ("Arriving", "Va a llegar"),
    "rooms.res_type":     ("Booking", "Tipo de reserva"),
    "rooms.occupancy":    ("Occupancy", "Ocupación"),
    "rooms.late_out":     ("Late checkout", "Salida tardía"),
    "rooms.building_l":   ("Building", "Edificio"),
    "rooms.floor_l":      ("Floor", "Piso"),
    "rooms.service_l":    ("Service", "Servicio"),
    "rooms.minutes_l":    ("Time", "Tiempo"),
    "rooms.chart_l":      ("Chart", "Hoja"),
    "rooms.cleaner_l":    ("Housekeeper", "Camarista"),
    "rooms.rqs_l":        ("RQS", "RQS"),
    "rooms.progress_l":   ("Progress", "Avance"),
    "rooms.marked_l":     ("Marked", "Marcado"),
    "rooms.by_l":         ("Last touched by", "Último cambio por"),
    "rooms.t_started":    ("started", "empezó"),
    "rooms.t_ready":      ("ready", "listo"),
    "rooms.t_inspected":  ("inspected", "inspeccionado"),
    "rooms.notes_all_read": ("{n} note(s) from your team, all read",
                             "{n} nota(s) de tu equipo, todas leídas"),
    "rooms.awaiting_rqs": ("waiting for the RQS to inspect",
                           "esperando la inspección del RQS"),
    "rooms.the_round":    ("The round", "El recorrido"),
    "rooms.other_ways":   ("Something else", "Otra cosa"),
    "rooms.close":        ("Close", "Cerrar"),
    "rooms.done_here":    ("nothing left to do on this one",
                           "ya no queda nada por hacer aquí"),

    # ── statuses ─────────────────────────────────────────────────────────
    "st.not_started":     ("Waiting to clean", "Esperando limpieza"),
    "st.in_progress":     ("Cleaning", "Limpiando"),
    "st.cleaned":         ("Ready for RQS", "Listo para RQS"),
    "st.inspected":       ("Inspected", "Inspeccionado"),
    "st.already_clean":   ("Already clean", "Ya está limpio"),
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


# ── Translating the whole app, without rewriting every call ─────────────────
# The pages hold roughly five hundred labels between them. Wrapping each one by
# hand would be five hundred chances to break an f-string, so the Streamlit
# calls that carry text are wrapped once, here, and the text is looked up on
# its way to the screen. A string that is not in the table goes through
# untouched, which is what makes this safe: the worst case is English.
import re as _re

try:
    from i18n_es import ES as _ES
except Exception:                       # never let a missing table break a page
    _ES = {}

#: Longest first, so "Daily Service Team" wins over "Daily Service".
_PHRASES = sorted((k for k in _ES if len(k) >= 6), key=len, reverse=True)

#: Only whole words are replaced inside a longer sentence, or "Add" would
#: rewrite the middle of somebody's name.
_WORD = {k: _re.compile(r"(?<![A-Za-z])" + _re.escape(k) + r"(?![A-Za-z])")
         for k in _PHRASES}

_TEXT_NODE = _re.compile(r">([^<>]{2,})<")


def _phrases(s: str) -> str:
    """Translate the known phrases inside a string built at runtime."""
    for k in _PHRASES:
        if k in s:
            s = _WORD[k].sub(_ES[k], s)
    return s


#: Everything inside these carries code, not prose. A phrase that happened to
#: appear in a stylesheet would be rewritten into nonsense CSS, so they are
#: lifted out, left alone, and put back.
_CODE_BLOCK = _re.compile(r"<(style|script).*?</>", _re.S | _re.I)


def _html(s: str) -> str:
    """Translate the words between the tags, never the markup itself."""
    kept = []

    def stash(m):
        kept.append(m.group(0))
        return "@@I18N%d@@" % (len(kept) - 1)

    s = _CODE_BLOCK.sub(stash, s)

    def one(m):
        inner = m.group(1)
        stripped = inner.strip()
        hit = _ES.get(stripped)
        if hit:
            return ">" + inner.replace(stripped, hit) + "<"
        return ">" + _phrases(inner) + "<"
    s = _TEXT_NODE.sub(one, s)
    return _re.sub(r"@@I18N(\d+)@@", lambda m: kept[int(m.group(1))], s)


def tr(text):
    """English in, whatever this reader wants out."""
    if not isinstance(text, str) or lang() != "es" or not text.strip():
        return text
    hit = _ES.get(text.strip())
    if hit is not None:
        return text.replace(text.strip(), hit)
    if "<" in text and ">" in text:
        return _html(text)
    return _phrases(text)


#: Streamlit calls whose first argument is read by a person. Dropdown OPTIONS
#: are deliberately not translated -- the code compares against them, so
#: translating the options would change what the app does, not how it reads.
_FIRST_ARG = (
    "button", "caption", "checkbox", "download_button", "error", "expander",
    "form_submit_button", "header", "info", "link_button", "markdown",
    "metric", "multiselect", "number_input", "popover", "radio", "selectbox",
    "slider", "subheader", "success", "text_area", "text_input", "title",
    "toast", "toggle", "warning", "write", "date_input", "time_input",
    "file_uploader", "select_slider", "color_picker",
)


def _wrap_first(fn):
    def inner(*a, **kw):
        if a:
            a = (tr(a[0]),) + a[1:]
        elif "label" in kw:
            kw["label"] = tr(kw["label"])
        elif "body" in kw:
            kw["body"] = tr(kw["body"])
        for k in ("help", "placeholder"):
            if isinstance(kw.get(k), str):
                kw[k] = tr(kw[k])
        return fn(*a, **kw)
    inner.__name__ = getattr(fn, "__name__", "wrapped")
    return inner


def _wrap_list(fn):
    """st.tabs: the labels are shown, and nothing is compared against them."""
    def inner(*a, **kw):
        if a and isinstance(a[0], (list, tuple)):
            a = ([tr(x) for x in a[0]],) + a[1:]
        return fn(*a, **kw)
    inner.__name__ = getattr(fn, "__name__", "wrapped")
    return inner


def install() -> None:
    """Wrap Streamlit once per process.

    Both the module-level functions and the DeltaGenerator methods are
    wrapped: `st.button(...)` goes through the first, `col.button(...)`
    through the second, and this app uses both.
    """
    if getattr(st, "_i18n_installed", False):
        return
    try:
        from streamlit.delta_generator import DeltaGenerator as _DG
    except Exception:
        _DG = None
    for name in _FIRST_ARG:
        fn = getattr(st, name, None)
        if callable(fn):
            setattr(st, name, _wrap_first(fn))
        if _DG is not None:
            m = getattr(_DG, name, None)
            if callable(m):
                setattr(_DG, name, _wrap_first(m))
    for name in ("tabs",):
        fn = getattr(st, name, None)
        if callable(fn):
            setattr(st, name, _wrap_list(fn))
        if _DG is not None:
            m = getattr(_DG, name, None)
            if callable(m):
                setattr(_DG, name, _wrap_list(m))
    # Column headers in a table are labels too.
    try:
        import streamlit.column_config as _cc
        for name in ("TextColumn", "NumberColumn", "SelectboxColumn",
                     "CheckboxColumn", "DateColumn", "Column"):
            f = getattr(_cc, name, None)
            if callable(f):
                setattr(_cc, name, _wrap_first(f))
    except Exception:
        pass
    st._i18n_installed = True
