"""
manager_questions.py — the few decisions the 5 AM run has to guess today,
asked of the managers in plain words. Only questions whose answer changes
what the app does on its own are here. No Streamlit: the page
(pages/12_Questions.py) draws it, and each manager's answers are one
app_settings row, KEY_PREFIX + username, so two managers saving at once can't
overwrite each other.

Every question says what the app does today ("now"), from the code, so most
answers are "keep it" or the one thing to change. A question's `key` is
stable -- answers are stored under it and turned into rules from it -- so
reword a question freely but never rename its key. An answer stores the
option's text, so once managers have answered, reword an option only with a
migration of the saved answers.

Field kinds:
  one   pick one (radio)            -> str
  all   tick all that apply         -> [str]
  rank  pick in order, first = 1st  -> [str] in the order picked
  num   a number                    -> int | None
  text  a short answer              -> str
  long  a longer answer             -> str
Every question also gets a free "notes" box.
"""

KEY_PREFIX = "mq_"
KEEP = "Keep it as it is"
RANK_HELP = "Pick in order: your first pick comes first. Leave out anything you'd never do."

PARTS = [
    ("Short of housekeepers", [
        dict(key="fc_short_order",
             q="Not enough housekeepers for the check-out rooms. Who should clean them first?",
             now="Every housekeeper is filled up to a full day. Then whoever is on Dust n Vac helps, "
                 "then housekeepers on projects.",
             fields=[("rank", "order", RANK_HELP,
                      ["Whoever is on Dust n Vac (housekeeper or RQS 2)", "Housekeepers on projects",
                       "Housepersons (HSP)", "Housekeepers on deep cleans", "Daily Service housekeepers",
                       "An inspector (RQS) cleaning rooms", "Overtime for housekeepers already working",
                       "A supervisor or manager cleaning rooms", "Leave rooms for tomorrow"])]),
        dict(key="fc_overtime",
             q="Can one housekeeper get more than a full day of check-out rooms?",
             now="No. A housekeeper's full day is 380 minutes and no housekeeper gets more.",
             fields=[("one", "choice", "Your answer",
                      ["No, keep 380 minutes as the most", "Yes, if the housekeeper agrees",
                       "Yes, if a manager says OK"]),
                     ("num", "max_minutes", "If yes, the most minutes for one housekeeper in one day")]),
        dict(key="fc_must_first",
             q="If some rooms can't be cleaned today, which rooms must the housekeepers do first?",
             now="No order. Rooms no housekeeper can take just say “No HK available”.",
             fields=[("all", "first", "Tick all that must be done first",
                      ["Early check-ins", "VIP rooms", "Owner stays", "Any room with a guest arriving today"])]),
    ]),
    ("Daily Service", [
        dict(key="ds_who",
             q="The schedule has no housekeeper on Daily Service. Which housekeeper should the app put on it?",
             now="A housekeeper working today who hasn't done Daily Service yet this week.",
             fields=[("one", "choice", "Your answer",
                      [KEEP, "Always the same housekeepers", "Housekeepers take turns, everyone equally",
                       "The most experienced housekeeper"]),
                     ("text", "names", "If always the same housekeepers, who?")]),
        dict(key="ds_full_day",
             q="How many minutes of Daily Service is a full day for one housekeeper?",
             now="460 minutes on weekdays, 510 on weekends (the minutes on the room list).",
             fields=[("num", "weekday", "Weekdays (leave empty to keep 460)"),
                     ("num", "weekend", "Weekends (leave empty to keep 510)")]),
        dict(key="ds_short_order",
             q="Not enough housekeepers for Daily Service. What should happen first?",
             now="The rooms say “Need Housekeeper”. No housekeeper is moved from check-out rooms until "
                 "every Daily Service list is full.",
             fields=[("rank", "order", RANK_HELP,
                      ["Move a housekeeper from check-out rooms", "Use whoever is on Dust n Vac (housekeeper or RQS 2)",
                       "Quick service in some rooms (towels and trash only)", "Skip some rooms until tomorrow",
                       "Overtime for Daily Service housekeepers"])]),
    ]),
    ("Inspectors (RQS)", [
        dict(key="rqs_rooms",
             q="How many check-out rooms can one inspector (RQS) check in a day?",
             now="12, and never more than 13.",
             fields=[("num", "rooms", "Rooms per inspector (leave empty to keep 12)")]),
        dict(key="rqs_short_order",
             q="Not enough inspectors (RQS). Who should inspect the extra rooms first?",
             now="Inspectors (RQS) on projects first. RQS 1 and RQS 2 only if no other inspector is free.",
             fields=[("rank", "order", RANK_HELP,
                      ["Inspectors (RQS) on projects", "RQS 2", "RQS 1", "A supervisor or manager",
                       "Leave some rooms not inspected"])]),
    ]),
    ("During the day", [
        dict(key="callout",
             q="A housekeeper calls out after the 5 AM lists are made. What should the app do?",
             now="Nothing. The inspector (RQS) moves that housekeeper's rooms by hand.",
             fields=[("one", "choice", "Your answer",
                      [KEEP, "Give only that housekeeper's rooms to other housekeepers nearby",
                       "Make all the lists again"])]),
        dict(key="short_shift",
             q="A housekeeper works a short shift (for example 10 to 2). How many rooms should the housekeeper get?",
             now="A full day, like every other housekeeper.",
             fields=[("one", "choice", "Your answer",
                      [KEEP, "Fewer rooms, based on the housekeeper's hours", "Give the housekeeper Daily Service"])]),
        dict(key="quiet_day",
             q="More housekeepers than rooms. What should the app do?",
             now="It gives full days to as few housekeepers as possible. The other housekeepers get no rooms.",
             fields=[("one", "choice", "Your answer",
                      [KEEP, "Give every housekeeper fewer rooms", "Offer early leave (VTO) to housekeepers",
                       "Send the extra housekeepers to projects"])]),
        # "auto_push" was question 12 until Hari settled it on 15 Oct: the lists
        # go to HotSOS every morning (hotsos_agent, {"daily": true}). Answers
        # already saved under that key are kept in their rows, just not shown.
    ]),
]

QUESTIONS = [q for _, qs in PARTS for q in qs]
NUMBER = {q["key"]: i + 1 for i, q in enumerate(QUESTIONS)}


def answered(q, a) -> bool:
    """Whether a question has any answer in it (notes count)."""
    a = a or {}
    return any(a.get(k) not in (None, "", []) for k in [f[1] for f in q["fields"]] + ["notes"])


def summary(q, a, tr=lambda s: s) -> str:
    """One line for the side-by-side table, in the reader's language (`tr`)."""
    a = a or {}
    bits = []
    for kind, fkey, label, *rest in q["fields"]:
        v = a.get(fkey)
        if v in (None, "", []):
            continue
        if kind == "rank":
            bits.append("  ".join(f"{i + 1}. {tr(x)}" for i, x in enumerate(v)))
        elif kind == "all":
            bits.append(", ".join(tr(x) for x in v))
        elif kind == "one":
            bits.append(tr(str(v)))
        else:
            bits.append(f"{tr(label).split(', ')[-1].split(' (')[0].strip('¿?')}: {v}")
    if a.get("notes"):
        bits.append(f"{tr('Note')}: {a['notes']}")
    return " · ".join(bits)


# ── Spanish ──────────────────────────────────────────────────────────────────
# The page follows the app's English / Español switch. Answers are stored in
# English whatever the reader's language (the radio and multiselect show these
# through format_func), so two managers' answers compare like for like and
# rules are built from one vocabulary. Same words as the rest of the app:
# camarista, servicio diario, inspector (RQS).
ES = {
    # parts
    "Short of housekeepers": "Faltan camaristas",
    "Daily Service": "Servicio diario",
    "Inspectors (RQS)": "Inspectores (RQS)",
    "During the day": "Durante el día",
    # shared
    KEEP: "Dejarlo como está",
    RANK_HELP: "Elige en orden: lo que elijas primero va primero. No elijas lo que nunca harías.",
    "Your answer": "Tu respuesta",
    # 1
    "Not enough housekeepers for the check-out rooms. Who should clean them first?":
        "No hay suficientes camaristas para los cuartos de salida. ¿Quién debe limpiarlos primero?",
    "Every housekeeper is filled up to a full day. Then whoever is on Dust n Vac helps, "
    "then housekeepers on projects.":
        "Primero a cada camarista se le llena el día completo. Luego ayuda quien esté en Sacudir y "
        "aspirar (Dust n Vac), y después las camaristas en proyectos.",
    "Whoever is on Dust n Vac (housekeeper or RQS 2)": "Quien esté en Sacudir y aspirar (camarista o RQS 2)",
    "Housekeepers on projects": "Camaristas en proyectos",
    "Housepersons (HSP)": "Housepersons (HSP)",
    "Housekeepers on deep cleans": "Camaristas en limpiezas profundas",
    "Daily Service housekeepers": "Camaristas de servicio diario",
    "An inspector (RQS) cleaning rooms": "Un inspector (RQS) limpiando cuartos",
    "Overtime for housekeepers already working": "Horas extra para las camaristas que ya están trabajando",
    "A supervisor or manager cleaning rooms": "Un supervisor o gerente limpiando cuartos",
    "Leave rooms for tomorrow": "Dejar cuartos para mañana",
    # 2
    "Can one housekeeper get more than a full day of check-out rooms?":
        "¿Puede una camarista recibir más de un día completo de cuartos de salida?",
    "No. A housekeeper's full day is 380 minutes and no housekeeper gets more.":
        "No. El día completo de una camarista es de 380 minutos y ninguna recibe más.",
    "No, keep 380 minutes as the most": "No, 380 minutos es lo máximo",
    "Yes, if the housekeeper agrees": "Sí, si la camarista está de acuerdo",
    "Yes, if a manager says OK": "Sí, si un gerente lo aprueba",
    "If yes, the most minutes for one housekeeper in one day":
        "Si es sí, ¿cuántos minutos como máximo para una camarista en un día?",
    # 3
    "If some rooms can't be cleaned today, which rooms must the housekeepers do first?":
        "Si hoy no se pueden limpiar todos los cuartos, ¿cuáles deben hacer primero las camaristas?",
    "No order. Rooms no housekeeper can take just say “No HK available”.":
        "No hay un orden. Los cuartos que ninguna camarista puede tomar solo dicen “No HK available”.",
    "Tick all that must be done first": "Marca todos los que se deben hacer primero",
    "Early check-ins": "Llegadas temprano (early check-in)",
    "VIP rooms": "Cuartos VIP",
    "Owner stays": "Cuartos de propietarios",
    "Any room with a guest arriving today": "Cualquier cuarto con un huésped que llega hoy",
    # 4
    "The schedule has no housekeeper on Daily Service. Which housekeeper should the app put on it?":
        "El horario no tiene ninguna camarista en servicio diario. ¿A qué camarista debe poner la app?",
    "A housekeeper working today who hasn't done Daily Service yet this week.":
        "A una camarista que trabaja hoy y que todavía no ha hecho servicio diario esta semana.",
    "Always the same housekeepers": "Siempre las mismas camaristas",
    "Housekeepers take turns, everyone equally": "Por turnos, todas las camaristas por igual",
    "The most experienced housekeeper": "La camarista con más experiencia",
    "If always the same housekeepers, who?": "Si siempre son las mismas camaristas, ¿quiénes?",
    # 5
    "How many minutes of Daily Service is a full day for one housekeeper?":
        "¿Cuántos minutos de servicio diario son un día completo para una camarista?",
    "460 minutes on weekdays, 510 on weekends (the minutes on the room list).":
        "460 minutos entre semana y 510 el fin de semana (los minutos de la lista de cuartos).",
    "Weekdays (leave empty to keep 460)": "Entre semana (déjalo vacío para mantener 460)",
    "Weekends (leave empty to keep 510)": "Fin de semana (déjalo vacío para mantener 510)",
    # 6
    "Not enough housekeepers for Daily Service. What should happen first?":
        "No hay suficientes camaristas para el servicio diario. ¿Qué debe pasar primero?",
    "The rooms say “Need Housekeeper”. No housekeeper is moved from check-out rooms until "
    "every Daily Service list is full.":
        "Los cuartos dicen “Need Housekeeper”. No se mueve a ninguna camarista de los cuartos de salida "
        "hasta que todas las listas de servicio diario estén llenas.",
    "Move a housekeeper from check-out rooms": "Mover a una camarista de los cuartos de salida",
    "Use whoever is on Dust n Vac (housekeeper or RQS 2)": "Usar a quien esté en Sacudir y aspirar (camarista o RQS 2)",
    "Quick service in some rooms (towels and trash only)": "Servicio rápido en algunos cuartos (solo toallas y basura)",
    "Skip some rooms until tomorrow": "Dejar algunos cuartos para mañana",
    "Overtime for Daily Service housekeepers": "Horas extra para las camaristas de servicio diario",
    # 7
    "How many check-out rooms can one inspector (RQS) check in a day?":
        "¿Cuántos cuartos de salida puede revisar un inspector (RQS) en un día?",
    "12, and never more than 13.": "12, y nunca más de 13.",
    "Rooms per inspector (leave empty to keep 12)": "Cuartos por inspector (déjalo vacío para mantener 12)",
    # 8
    "Not enough inspectors (RQS). Who should inspect the extra rooms first?":
        "No hay suficientes inspectores (RQS). ¿Quién debe revisar primero los cuartos que sobran?",
    "Inspectors (RQS) on projects first. RQS 1 and RQS 2 only if no other inspector is free.":
        "Primero los inspectores (RQS) que están en proyectos. RQS 1 y RQS 2 solo si no hay otro inspector libre.",
    "Inspectors (RQS) on projects": "Inspectores (RQS) en proyectos",
    "A supervisor or manager": "Un supervisor o gerente",
    "Leave some rooms not inspected": "Dejar algunos cuartos sin revisar",
    # 9
    "A housekeeper calls out after the 5 AM lists are made. What should the app do?":
        "Una camarista avisa que no viene después de que se hicieron las listas de las 5 AM. ¿Qué debe hacer la app?",
    "Nothing. The inspector (RQS) moves that housekeeper's rooms by hand.":
        "Nada. El inspector (RQS) mueve a mano los cuartos de esa camarista.",
    "Give only that housekeeper's rooms to other housekeepers nearby":
        "Repartir solo los cuartos de esa camarista entre otras camaristas cercanas",
    "Make all the lists again": "Hacer todas las listas otra vez",
    # 10
    "A housekeeper works a short shift (for example 10 to 2). How many rooms should the housekeeper get?":
        "Una camarista trabaja un turno corto (por ejemplo de 10 a 2). ¿Cuántos cuartos debe recibir?",
    "A full day, like every other housekeeper.": "Un día completo, igual que las demás camaristas.",
    "Fewer rooms, based on the housekeeper's hours": "Menos cuartos, según sus horas",
    "Give the housekeeper Daily Service": "Darle servicio diario",
    # 11
    "More housekeepers than rooms. What should the app do?": "Hay más camaristas que cuartos. ¿Qué debe hacer la app?",
    "It gives full days to as few housekeepers as possible. The other housekeepers get no rooms.":
        "Da días completos al menor número de camaristas posible. Las demás no reciben cuartos.",
    "Give every housekeeper fewer rooms": "Dar menos cuartos a cada camarista",
    "Offer early leave (VTO) to housekeepers": "Ofrecer salida temprano (VTO) a las camaristas",
    "Send the extra housekeepers to projects": "Mandar a proyectos a las camaristas que sobran",
    # the page
    "Manager questions": "Preguntas para gerentes",
    "{n} quick questions about days that don't go to plan. Your answers teach the 5 AM run to do what you would do.":
        "{n} preguntas rápidas sobre los días que no salen como se planeó. Tus respuestas le enseñan "
        "a la app de las 5 AM a hacer lo que tú harías.",
    "My answers": "Mis respuestas",
    "Everyone's answers": "Respuestas de todos",
    "Saved. Thank you!": "Guardado. ¡Gracias!",
    "{done} of {n} answered": "{done} de {n} contestadas",
    " · last saved {when}": " · guardado {when}",
    "Answer what you can and press **Save my answers** at the bottom. “Today” shows what the app does now. "
    "You can change your answers any time.":
        "Contesta lo que puedas y presiona **Guardar mis respuestas** abajo. “Hoy” muestra lo que hace "
        "la app ahora. Puedes cambiar tus respuestas cuando quieras.",
    "Today:": "Hoy:",
    "Anything to add? (optional)": "¿Algo más? (opcional)",
    "Pick the first one…": "Elige el primero…",
    "Save my answers": "Guardar mis respuestas",
    "These questions are for managers.": "Estas preguntas son para gerentes.",
    "Couldn't load your saved answers: {ex}": "No se pudieron cargar tus respuestas: {ex}",
    "Couldn't save your answers: {ex}": "No se pudieron guardar tus respuestas: {ex}",
    "Couldn't load the answers: {ex}": "No se pudieron cargar las respuestas: {ex}",
    "Nobody has saved answers yet.": "Nadie ha guardado respuestas todavía.",
    "{name} saved {when}": "{name} guardó {when}",
    "no answer": "sin respuesta",
    "Note": "Nota",
    "Question": "Pregunta",
    "Download everyone's answers (Excel)": "Descargar las respuestas de todos (Excel)",
    "Manager answers": "Respuestas de gerentes",
}
