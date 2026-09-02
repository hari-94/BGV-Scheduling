"""
i18n_es.py — the Spanish the app is read in.

Keys are the exact English the code passes to Streamlit, so a label that is
edited in the code simply falls back to English here rather than showing a
wrong translation. Anything a manager typed -- names, room numbers, sheet
names, notes -- is never in this table and never touched.
"""

ES = {
    # ── page chrome, tabs, section headings ──────────────────────────────
    "Schedule": "Horario",
    "Reassign": "Reasignar",
    "Live": "En vivo",
    "Week view": "Vista semanal",
    "Month view": "Vista mensual",
    "Plan a week": "Planear la semana",
    "Attendance": "Asistencia",
    "Apply to roster": "Aplicar a la lista",
    "What changed": "Qué cambió",
    "Upload & sync": "Subir y sincronizar",
    "Activity": "Actividad",
    "Daily Log": "Registro diario",
    "Manage": "Administrar",
    "Team": "Equipo",
    "Status": "Estado",
    "Generate": "Generar",

    # ── the sidebar ──────────────────────────────────────────────────────
    "Daily Attendance": "Asistencia del día",
    "↻ Reload today from schedule": "↻ Recargar hoy desde el horario",
    "Add or remove a housekeeper": "Agregar o quitar una camarista",
    "Add or remove an inspector": "Agregar o quitar un inspector",
    "Housekeepers": "Camaristas",
    "Inspectors": "Inspectores",
    "**Housekeepers**": "**Camaristas**",
    "**Inspectors**": "**Inspectores**",
    "Tick who is in. Buildings come from the staff sheet.":
        "Marca quién viene hoy. Los edificios vienen de la hoja de personal.",
    "All in": "Todos",
    "All out": "Ninguno",
    "Building": "Edificio",
    "Bldg": "Edif.",
    "Name": "Nombre",
    "Add HK": "Agregar camarista",
    "Add Inspector": "Agregar inspector",
    "Add": "Agregar",
    "Remove": "Quitar",
    "Paste names (one per line or comma-separated)":
        "Pega los nombres (uno por línea o separados por comas)",
    "RQS tools": "Herramientas de RQS",
    "Shuffle RQS order": "Revolver el orden de RQS",
    "RQS order shuffled": "Se revolvió el orden de RQS",
    "Pairs the RQS with different housekeepers next time the schedule is built.":
        "Empareja a los RQS con otras camaristas la próxima vez que se arme el horario.",
    "### RQS Roles Today": "### Roles de RQS hoy",
    "RQS 1 (Dust & Vac)": "RQS 1 (Sacudir y aspirar)",
    "RQS 2 (Daily Service)": "RQS 2 (Servicio diario)",
    "### Daily Service Team": "### Equipo de servicio diario",
    "Daily Service Team": "Equipo de servicio diario",
    "Daily Service team": "Equipo de servicio diario",
    "On Daily Service": "En servicio diario",
    "HKs dedicated to Daily Service today. Only they get DS charts — and they "
    "are held back from Full Clean / Dust n Vac.":
        "Camaristas dedicadas hoy al servicio diario. Sólo ellas reciben hojas "
        "de servicio diario, y quedan fuera de limpieza completa y de sacudir "
        "y aspirar.",
    "None selected — Daily Service is assigned from the full roster as usual.":
        "Nadie seleccionado — el servicio diario se asigna de toda la lista, "
        "como siempre.",
    "### Priority HKs": "### Camaristas prioritarias",
    "Priority HKs": "Camaristas prioritarias",
    "Select HKs who need a full 380-min group (productivity recovery).":
        "Elige camaristas que necesiten un grupo completo de 380 minutos "
        "(recuperación de productividad).",
    "They clean rooms the rest of the day — the number never means unavailable.":
        "Limpian cuartos el resto del día; el número nunca significa que no "
        "estén disponibles.",
    "No housekeepers marked as present.": "No hay camaristas marcadas como presentes.",

    # ── the board and reassigning ────────────────────────────────────────
    "Sort housekeepers by": "Ordenar camaristas por",
    "Find a housekeeper": "Buscar una camarista",
    "Service": "Servicio",
    "Show": "Mostrar",
    "Show DV": "Mostrar sacudir y aspirar",
    "Group by": "Agrupar por",
    "Inspectors shown": "Inspectores mostrados",
    "Hide empty housekeepers": "Ocultar camaristas sin cuartos",
    "Move to housekeeper": "Pasar a la camarista",
    "Apply these moves": "Aplicar estos cambios",
    "Apply room moves": "Aplicar los cambios de cuartos",
    "No moves pending.": "No hay cambios pendientes.",
    "No room moves pending.": "No hay cambios de cuartos pendientes.",
    "Nothing matches those filters.": "Nada coincide con esos filtros.",
    "No housekeepers under the inspectors you picked.":
        "No hay camaristas con los inspectores que elegiste.",
    "Every chart has a housekeeper and an RQS.":
        "Cada hoja tiene camarista y RQS.",
    "All staff are assigned and at or above their thresholds.":
        "Todo el personal está asignado y en o por encima de su mínimo.",
    "Assign": "Asignar",
    "One column per inspector, always in the same order. Sorting reorders the "
    "cards inside each column, not the columns. Filters only change what you "
    "can see. Dragging a card takes all of that housekeeper's charts, and "
    "nothing is saved until you press Apply.":
        "Una columna por inspector, siempre en el mismo orden. El ordenamiento "
        "acomoda las tarjetas dentro de cada columna, no las columnas. Los "
        "filtros sólo cambian lo que ves. Al arrastrar una tarjeta se mueven "
        "todas las hojas de esa camarista, y nada se guarda hasta que "
        "presiones Aplicar.",
    "Drag a room to any housekeeper on the board, including one under a "
    "different RQS. Times, buildings and floors are recalculated for both "
    "charts. Nothing is saved until you press Apply.":
        "Arrastra un cuarto a cualquier camarista del tablero, incluso con "
        "otro RQS. Los tiempos, edificios y pisos se recalculan en ambas "
        "hojas. Nada se guarda hasta que presiones Aplicar.",

    # ── the live board ───────────────────────────────────────────────────
    "Rooms": "Cuartos",
    "rooms": "cuartos",
    "Person": "Persona",
    "People": "Personas",
    "Housekeeper": "Camarista",
    "Inspector (RQS)": "Inspector (RQS)",
    "RQS": "RQS",
    "Start": "Empezar",
    "Done": "Terminado",
    "Clean": "Limpio",
    "Undo": "Deshacer",
    "Reset": "Reiniciar",
    "No rooms on today's schedule yet.":
        "Todavía no hay cuartos en el horario de hoy.",
    "Pick one room or several, then say what happened. Housekeepers marking "
    "their own rooms show up here too.":
        "Elige uno o varios cuartos y di qué pasó. Lo que marcan las camaristas "
        "en sus propios cuartos también aparece aquí.",

    # ── planning a week ──────────────────────────────────────────────────
    "Week": "Semana",
    "Week to plan": "Semana a planear",
    "Start from": "Empezar desde",
    "Month": "Mes",
    "Date": "Fecha",
    "Period": "Periodo",
    "Which": "Cuál",
    "Most recent": "Más reciente",
    "Already stored": "Ya guardada",
    "New weeks": "Semanas nuevas",
    "New weeks added": "Semanas nuevas agregadas",
    "Weeks changed": "Semanas modificadas",
    "Cells changed": "Celdas modificadas",
    "Cells filled": "Celdas llenas",
    "Working days": "Días trabajados",
    "Days worked": "Días trabajados",
    "Days off": "Días libres",
    "Days in period": "Días del periodo",
    "Avg days / person": "Promedio de días por persona",
    "Need a look": "Revisar",
    "Sections to edit": "Secciones a editar",
    "Sections you do not open are saved exactly as drafted above.":
        "Las secciones que no abras se guardan tal como quedaron arriba.",
    "Store at least one week first — a plan is built from what came before.":
        "Guarda al menos una semana primero: el plan se arma con lo anterior.",
    "Planning a new week is an admin task. You can review it here once saved.":
        "Planear una semana nueva es tarea de administración. Aquí puedes "
        "revisarla una vez guardada.",
    "Uses the sheet it was built from, with the dates rewritten to this week "
    "and last week's absences cleared.":
        "Usa la hoja de la que se armó, con las fechas cambiadas a esta semana "
        "y las ausencias de la semana pasada borradas.",
    "What the patterns actually say": "Lo que de verdad dicen los patrones",
    "Nobody has changed building recently.":
        "Nadie ha cambiado de edificio recientemente.",

    # ── staffing numbers ─────────────────────────────────────────────────
    "How many people this week needs": "Cuánta gente necesita esta semana",
    "Seeded from the same weekday last week — type over any of it. Labour "
    "minutes and checkouts are the two numbers the sheet hides; daily "
    "services is the row it leaves blank, and filling it in is what makes "
    "the inspector count right.":
        "Tomado del mismo día de la semana pasada; puedes escribir encima. Los "
        "minutos de trabajo y las salidas son los dos números que la hoja "
        "esconde; el servicio diario es la fila que deja vacía, y llenarla es "
        "lo que hace correcto el número de inspectores.",
    "Why these numbers differ from the sheet's":
        "Por qué estos números no son los de la hoja",

    # ── daily service rotation ───────────────────────────────────────────
    "Daily service — whose turn": "Servicio diario — a quién le toca",
    "Put these in the plan": "Ponerlos en el plan",
    "Take them back out": "Quitarlos del plan",
    "In the plan — edit any of them in the grids below like any other cell.":
        "Ya están en el plan; puedes cambiarlos abajo como cualquier otra celda.",
    "Each name shows their turns against days worked in the last four weeks, "
    "and how long since the last one. Only housekeepers the plan already has "
    "working that day are eligible.":
        "Cada nombre muestra sus turnos contra los días trabajados en las "
        "últimas cuatro semanas, y cuánto hace del último. Sólo entran las "
        "camaristas que el plan ya tiene trabajando ese día.",
    "How the turn is decided, and whether it is fairer":
        "Cómo se decide el turno, y si es más justo",

    # ── the month view ───────────────────────────────────────────────────
    "Upload the workbook first — a month is built from the weeks in it.":
        "Sube primero el archivo: el mes se arma con las semanas que trae.",
    "No stored days in that month.": "No hay días guardados en ese mes.",
    "The name and the two tallies stay put while the days slide past. **In** "
    "is days worked, **DS** days on daily service — the pair to compare "
    "people on. Codes: a building number, **DS** daily service, **H1** "
    "houseperson zone, **VTO** paid time off, **NC** no call, blank for off.":
        "El nombre y los dos totales se quedan fijos mientras los días pasan de "
        "lado. **In** son días trabajados y **DS** días de servicio diario: con "
        "esos dos se compara a la gente. Claves: número de edificio, **DS** "
        "servicio diario, **H1** zona de houseperson, **VTO** tiempo libre "
        "pagado, **NC** no llamó, vacío si descansó.",

    # ── upload and sync ──────────────────────────────────────────────────
    "Upload Housekeeping Dashboard (.xlsx)":
        "Subir el archivo de ama de llaves (.xlsx)",
    "Upload the workbook to compare it against what is stored. Nothing is "
    "written until you press **Save**.":
        "Sube el archivo para compararlo con lo guardado. No se escribe nada "
        "hasta que presiones **Guardar**.",
    "Save to app": "Guardar en la app",
    "Save edits": "Guardar cambios",
    "No changes to save.": "No hay cambios que guardar.",
    "Nothing new — the stored copy already matches this workbook.":
        "Nada nuevo: la copia guardada ya coincide con este archivo.",
    "The last upload matched what was already stored.":
        "La última subida coincidió con lo que ya estaba guardado.",
    "No dated sheets found — is this the weekly schedule workbook?":
        "No se encontraron hojas con fechas. ¿Es el archivo del horario semanal?",
    "No weeks stored yet. Upload the workbook on the **Upload & sync** tab.":
        "Todavía no hay semanas guardadas. Sube el archivo en la pestaña "
        "**Subir y sincronizar**.",
    "No workbook stored yet — upload it on the **Upload & sync** tab.":
        "Todavía no hay archivo guardado; súbelo en la pestaña **Subir y "
        "sincronizar**.",
    "The stored workbook could not be read.":
        "No se pudo leer el archivo guardado.",
    "Nothing loaded yet.": "Todavía no se ha cargado nada.",
    "Keep people not on this sheet (mark absent instead of removing)":
        "Conservar a quien no esté en esta hoja (marcar ausente en vez de quitar)",
    "Build updated workbook": "Armar el archivo actualizado",
    "Build Excel file": "Armar el archivo de Excel",
    "Download updated Schedule.xlsx": "Descargar Schedule.xlsx actualizado",
    "Download this week as Excel": "Descargar esta semana en Excel",
    "Download this plan as Excel": "Descargar este plan en Excel",
    "Download Excel": "Descargar Excel",
    "Download CSV": "Descargar CSV",
    "No in-app edits to write back yet.":
        "Todavía no hay cambios de la app para escribir de vuelta.",
    "Same layout as the source workbook — section headers, formulas and the "
    "red no-call marks all intact.":
        "El mismo formato del archivo original: encabezados, fórmulas y las "
        "marcas rojas de no llamó, intactas.",

    # ── the week grid ────────────────────────────────────────────────────
    "Every cell is a dropdown, with the choices that fit that role. Pick and "
    "press Save.":
        "Cada celda es una lista con las opciones que corresponden a ese "
        "puesto. Elige y presiona Guardar.",
    "New choice": "Opción nueva",
    "Type a value first.": "Escribe un valor primero.",
    "Type anything the dropdown does not offer. It is added to this role's "
    "list and stays available from then on.":
        "Escribe lo que la lista no ofrezca. Se agrega a las opciones de ese "
        "puesto y queda disponible desde entonces.",
    "No call / no show": "No llamó / no vino",
    "VTO — paid": "VTO — pagado",
    "What the numbers mean (from the workbook's own legend)":
        "Qué significan los números (según la leyenda del archivo)",
    "Sorted by days worked. Use it to see who is due time off and who is "
    "carrying the week.":
        "Ordenado por días trabajados. Sirve para ver a quién le toca descansar "
        "y quién está cargando la semana.",
    "Nothing recorded for that period.": "No hay nada registrado en ese periodo.",
    "Nothing selected to apply.": "No hay nada seleccionado para aplicar.",
    "Late checkouts, room moves, notes auto-matched.":
        "Salidas tardías, cambios de cuarto y notas emparejados automáticamente.",
    "Email parsed — no late checkouts found.":
        "Correo leído: no se encontraron salidas tardías.",
    "Paste room data first.": "Pega primero los datos de los cuartos.",
    "No valid rows — check tab-separated data with a header row.":
        "No hay filas válidas: revisa que estén separadas por tabulaciones y "
        "con fila de encabezado.",
    "Upload the .xlsx above, or copy-paste from Excel (include header row).":
        "Sube el .xlsx arriba, o copia y pega desde Excel (incluye el encabezado).",

    # ── signing in and accounts ──────────────────────────────────────────
    "Sign In": "Entrar",
    "Username": "Usuario",
    "Password": "Contraseña",
    "Keep me signed in on this device": "Mantener la sesión en este dispositivo",
    "Please enter both username and password.":
        "Escribe el usuario y la contraseña.",
    "Invalid username or password.": "Usuario o contraseña incorrectos.",
    "Cannot connect to database.": "No se puede conectar a la base de datos.",
    "Admin access required.": "Se requiere acceso de administrador.",
    "Only admins can delete data.": "Sólo administración puede borrar datos.",
    "Dashboard requires RQS or Admin role.":
        "El panel requiere ser RQS o administrador.",
    "This page is for admins and RQS. Your own schedule is on **My Home**.":
        "Esta página es para administración y RQS. Tu horario está en **Mi Inicio**.",
    "Create User": "Crear usuario",
    "Delete User": "Borrar usuario",
    "All Users": "Todos los usuarios",
    "No users found.": "No se encontraron usuarios.",
    "No other users to edit.": "No hay otros usuarios que editar.",
    "User": "Usuario",
    "Role": "Puesto",
    "New Role": "Puesto nuevo",
    "Save Role": "Guardar puesto",
    "Current Password": "Contraseña actual",
    "New Password": "Contraseña nueva",
    "Confirm New Password": "Confirmar la contraseña nueva",
    "Confirm Password": "Confirmar la contraseña",
    "Confirm": "Confirmar",
    "Update My Password": "Cambiar mi contraseña",
    "Reset Password": "Restablecer la contraseña",
    "User to reset": "Usuario a restablecer",
    "Current password incorrect.": "La contraseña actual es incorrecta.",
    "New passwords don't match.": "Las contraseñas nuevas no coinciden.",
    "Passwords don't match.": "Las contraseñas no coinciden.",
    "Minimum 6 characters.": "Mínimo 6 caracteres.",
    "Password must be at least 6 characters.":
        "La contraseña debe tener al menos 6 caracteres.",
    "Delete": "Borrar",
    "email": "correo",
    "People signed in": "Personas que entraron",
    "Total sign-ins": "Entradas en total",
    "Who has signed in, how often, and when they were last active.":
        "Quién ha entrado, cuántas veces y cuándo estuvo activo por última vez.",
    "No sign-ins recorded yet. Activity will appear here as people log in.":
        "Todavía no hay entradas registradas. La actividad aparecerá aquí "
        "conforme la gente entre.",
    "Refresh Status": "Actualizar el estado",

    # ── odds and ends ────────────────────────────────────────────────────
    "Housekeepers present": "Camaristas presentes",
    "Inspectors present": "Inspectores presentes",
    "Housekeepers + buildings": "Camaristas y edificios",
    "Inspectors + RQS 1/2": "Inspectores y RQS 1/2",
    "RQS 1 / RQS 2": "RQS 1 / RQS 2",
    "In-app edits live": "Los cambios de la app se mantienen",
    "No data yet. Generate a schedule on the main page first.":
        "Todavía no hay datos. Genera un horario en la página principal.",
    "ℹ No room data yet. Generate a schedule and revisit.":
        "ℹ Todavía no hay cuartos. Genera un horario y vuelve.",
    "ℹ Inspector room counts are 0. Re-generate the schedule and revisit.":
        "ℹ Los cuartos por inspector están en 0. Vuelve a generar el horario.",
    "Once a manager imports the weekly schedule, your days will show up here.":
        "En cuanto un gerente importe el horario semanal, tus días aparecerán aquí.",
    "None.": "Ninguno.",
    "Show the SQL": "Ver el SQL",
    "Schedule date": "Fecha del horario",
    "Schedule.xlsx": "Schedule.xlsx",
    "⋯": "⋯",
}

# ── text that lives inside the HTML cards and headings ───────────────────
ES.update({
    # the schedule page
    "Grand Timber GC8": "Grand Timber GC8",
    "Housekeeping · Scheduling · Live Tracking":
        "Ama de llaves · Horarios · Seguimiento en vivo",
    "Sign in with your Grand Timber email":
        "Entra con tu correo de Grand Timber",
    "Welcome back": "Bienvenido de nuevo",
    "Today": "Hoy",
    "Rooms today": "Cuartos de hoy",
    "On duty": "En turno",
    "RQS on duty": "RQS en turno",
    "HKs present": "Camaristas presentes",
    "Board — drag a housekeeper to another RQS":
        "Tablero — arrastra una camarista a otro RQS",
    "Move single rooms": "Mover cuartos uno por uno",
    "Charts still needing someone": "Hojas que siguen sin nadie",
    "Mark rooms": "Marcar cuartos",
    "Latest": "Lo más reciente",
    "Not started": "Sin empezar",
    "Cleaning": "Limpiando",
    "Ready for RQS": "Listo para RQS",
    "Inspected": "Inspeccionado",
    "Need help": "Necesita ayuda",
    "Active": "Activo",
    "Inspector": "Inspector",
    "inspector": "inspector",
    "Floor": "Piso",
    "Your Rooms Today": "Tus cuartos de hoy",
    "No rooms assigned yet for today.": "Todavía no hay cuartos asignados hoy.",
    "Check back once the schedule is generated.":
        "Vuelve cuando el horario esté generado.",
    "Building your schedule": "Armando tu horario",
    "Packing rooms into the fewest, tidiest charts…":
        "Acomodando los cuartos en las hojas más ordenadas…",
    "Parsing": "Leyendo",
    "Grouping": "Agrupando",
    "Assigning": "Asignando",
    "Last run was short": "La última corrida quedó corta",
    "Staff schedule loaded": "Horario de personal cargado",
    "Today loaded automatically": "Hoy se cargó automáticamente",
    "Roster Import": "Importar lista",

    # my home
    "Hello": "Hola",
    "Your schedule, straight from the staff sheet.":
        "Tu horario, directo de la hoja de personal.",
    "Your day": "Tu día",
    "Roles and shifts": "Puestos y turnos",
    "Next working day": "Próximo día de trabajo",
    "No further working days in the stored weeks.":
        "No hay más días de trabajo en las semanas guardadas.",
    "No staff schedule has been loaded yet.":
        "Todavía no se ha cargado ningún horario de personal.",
    "Days you work in this period": "Días que trabajas en este periodo",
    "Worked": "Trabajados",
    "Break it down": "Ver por periodo",

    # the dashboard
    "Performance Dashboard": "Panel de desempeño",
    "Daily · weekly · monthly metrics": "Métricas diarias, semanales y mensuales",
    "Rooms Cleaned by Service Type": "Cuartos limpiados por tipo de servicio",
    "Average Working Time per Day": "Tiempo promedio de trabajo por día",
    "Rooms Inspected": "Cuartos inspeccionados",
    "Groups Inspected": "Grupos inspeccionados",
    "Avg Rooms/Insp/Day": "Prom. cuartos por inspector al día",
    "Avg Time/Day": "Tiempo promedio por día",
    "Active HK": "Camaristas activas",
    "Active Inspectors": "Inspectores activos",
    "Total Rooms": "Cuartos en total",
    "Full Clean": "Limpieza completa",
    "Daily Service": "Servicio diario",
    "Dust &amp; Vac": "Sacudir y aspirar",
    "Detail Table": "Tabla de detalle",
    "Schedule History": "Historial de horarios",
    "Data Management": "Manejo de datos",

    # roster import
    "The weekly staff schedule — stored, compared week to week, and editable here.":
        "El horario semanal del personal: guardado, comparado semana con semana "
        "y editable aquí.",
    "Schedule last loaded": "Horario cargado por última vez",
    "Never — upload the workbook below": "Nunca — sube el archivo abajo",
    "Upload the weekly workbook": "Sube el archivo semanal",
    "Draft — change anything before saving":
        "Borrador: cambia lo que quieras antes de guardar",
    "Edit this week": "Editar esta semana",
    "Export back to Excel": "Exportar de vuelta a Excel",
    "One person in detail": "Una persona a detalle",
    "Who has worked how much": "Quién ha trabajado cuánto",
    "From sheet": "De la hoja",
    "Sheet": "Hoja",
    "Detail": "Detalle",
    "Apply": "Aplicar",
    "Changed cells": "Celdas cambiadas",
    "In-app edits": "Cambios hechos en la app",
    "Moved": "Movidos",
    "New:": "Nuevo:",
    "Stored but not in this file:": "Guardado pero no está en este archivo:",
    "POSSIBLE DUPLICATE NAMES": "POSIBLES NOMBRES DUPLICADOS",
    "RECENTLY TRANSFERRED": "TRANSFERIDOS RECIENTEMENTE",
    "DAYS OF THE WEEK USUALLY WORKED": "DÍAS DE LA SEMANA QUE SUELE TRABAJAR",
    "HOUSEKEEPERS — BUILDINGS BARELY MOVE":
        "CAMARISTAS — CASI NO CAMBIAN DE EDIFICIO",
    "HOUSEPERSONS — ZONES PERSIST, THEN SHIFT":
        "HOUSEPERSONS — LAS ZONAS SE MANTIENEN Y LUEGO CAMBIAN",
    "HOUSEKEEPER — 8AM TO 10AM EXTRA TASK":
        "CAMARISTA — TAREA EXTRA DE 8 A 10 AM",
    "ROLES &amp; SHIFTS": "PUESTOS Y TURNOS",
    "How many people this week needs": "Cuánta gente necesita esta semana",
    "Daily service — whose turn": "Servicio diario — a quién le toca",

    # admin
    "Admin Panel": "Panel de administración",
    "User management &amp; system settings":
        "Manejo de usuarios y ajustes del sistema",
    "User Roster": "Lista de usuarios",
    "Create New User": "Crear un usuario nuevo",
    "Edit User": "Editar usuario",
    "Reset User Password": "Restablecer la contraseña de un usuario",
    "Change My Password": "Cambiar mi contraseña",
    "App Usage": "Uso de la app",
    "Recent Sign-ins": "Entradas recientes",
    "By Person": "Por persona",
    "Role permissions:": "Permisos por puesto:",
    "— Full access: generate schedules, manage users, edit everything":
        "— Acceso total: generar horarios, manejar usuarios, editar todo",
    "— Paste room data, generate schedules, view all tabs and dashboard":
        "— Pegar datos de cuartos, generar horarios, ver todas las pestañas y el panel",
    "— View-only: see their groups and the schedule":
        "— Sólo lectura: ver sus grupos y el horario",
})
