"""
My Rooms — the day's rooms for one housekeeper, and what they have done.

This is the only page most of the team ever opens, usually on a phone midway
down a corridor. It reads today's published schedule straight from the
database on every run, so a swap or a room move an RQS makes upstairs shows up
here without anyone reloading anything.
"""
import streamlit as st
import sys, os, datetime, hashlib
import html as _html
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, db, clock, i18n
import assignments
import roomstatus as _rst
import ui

st.set_page_config(page_title="My Rooms", page_icon="🛎️", layout="wide")
auth.require_login()
ui.topnav("My Rooms")

T = i18n.t


def e(s):
    return _html.escape(str(s) if s is not None else "")


# ── statuses ─────────────────────────────────────────────────────────────────
# The words come from roomstatus so that a room marked here is the same room
# the supervisor sees moving on the Live board. They used to be two private
# vocabularies writing into one column, and neither could read the other.
NOT_STARTED = _rst.PENDING
IN_PROGRESS = _rst.STARTED
CLEANED = _rst.DONE
INSPECTED = _rst.INSPECTED
DND = _rst.DND
HELP = _rst.HELP
ALREADY = _rst.ALREADY_CLEAN

# (background, ink, accent) — the accent is the stripe down the card's edge.
# Taken from roomstatus so the board and the handset colour a room the same.
STATUS_STYLE = {k: (v[3], v[4], v[2]) for k, v in _rst.META.items()}
STATUS_KEY = {NOT_STARTED: "st.not_started", IN_PROGRESS: "st.in_progress",
              ALREADY: "st.already_clean",
              CLEANED: "st.cleaned", INSPECTED: "st.inspected",
              DND: "st.dnd", HELP: "st.help"}
STATUS_ICON = {NOT_STARTED: "○", IN_PROGRESS: "◐", CLEANED: "✓",
               ALREADY: "✓",
               INSPECTED: "★", DND: "⏸", HELP: "!"}

st.markdown("""<style>
.mrhero{background:linear-gradient(135deg,#12395f 0%,#1f5fa0 55%,#3f8ed0 100%);
  color:#fff;border-radius:20px;padding:20px 24px;margin:2px 0 16px;
  box-shadow:0 10px 30px rgba(18,57,95,.24);animation:mrfade .5s ease both}
.mrhero h1{margin:0;font-size:1.65rem;font-weight:800;letter-spacing:-.02em}
.mrhero p{margin:3px 0 0;opacity:.92;font-size:.92rem}
.mrbar{height:10px;border-radius:99px;background:rgba(255,255,255,.24);
  margin-top:14px;overflow:hidden}
.mrbar i{display:block;height:100%;border-radius:99px;
  background:linear-gradient(90deg,#8ff0b6,#25d366);
  transition:width .7s cubic-bezier(.2,.8,.25,1)}
.mrcount{font-size:.82rem;font-weight:700;margin-top:7px;opacity:.95}

.mrcard{border-radius:16px;padding:13px 15px 11px;margin:0 0 10px;
  border:1px solid #e2e8f1;border-left-width:7px;background:#fff;
  box-shadow:0 1px 3px rgba(16,26,42,.06);
  animation:mrrise .38s cubic-bezier(.2,.8,.25,1) both}
.mrcard.just{animation:mrpop .55s cubic-bezier(.2,1.3,.35,1) both}
.mrcard.working{position:relative;overflow:hidden}
.mrcard.working:after{content:"";position:absolute;inset:0;
  background:linear-gradient(100deg,transparent 30%,rgba(255,255,255,.65) 50%,
  transparent 70%);animation:mrsweep 2.4s linear infinite}
.mrroom{font-size:1.22rem;font-weight:800;letter-spacing:-.01em;color:#16202e}
.mrmeta{font-size:.76rem;color:#5a6a7b;margin-top:2px}
.mrpill{display:inline-block;border-radius:99px;padding:3px 11px;
  font-size:.72rem;font-weight:800;letter-spacing:.01em}
.mrtag{display:inline-block;border-radius:7px;padding:2px 8px;margin:6px 6px 0 0;
  font-size:.7rem;font-weight:700;background:#eef2f7;color:#42536a}
.mrtag.pet{background:#fff0e0;color:#8a4b00}
.mrtag.late{background:#fde8ef;color:#9b1c48}
.mrnote{font-size:.75rem;color:#5a6a7b;margin-top:7px;
  border-left:3px solid #dbe3ec;padding-left:8px}
.mrdone{background:linear-gradient(135deg,#0f8f4a,#28c76f);color:#fff;
  border-radius:16px;padding:16px 20px;font-weight:800;text-align:center;
  font-size:1.05rem;box-shadow:0 8px 22px rgba(15,143,74,.28);
  animation:mrbounce .7s cubic-bezier(.2,1.4,.4,1) both;margin-bottom:14px}
.mrlive{font-size:.72rem;color:#6b7a8c;margin:2px 0 10px}
.mrlive b{color:#25a35a}

@keyframes mrfade{from{opacity:0;transform:translateY(-6px)}to{opacity:1}}
@keyframes mrrise{from{opacity:0;transform:translateY(9px) scale(.985)}
  to{opacity:1;transform:none}}
@keyframes mrpop{0%{transform:scale(1)}35%{transform:scale(1.035)}
  100%{transform:scale(1)}}
@keyframes mrsweep{from{transform:translateX(-120%)}to{transform:translateX(120%)}}
@keyframes mrbounce{0%{opacity:0;transform:scale(.9)}
  60%{transform:scale(1.03)}100%{opacity:1;transform:scale(1)}}

div[data-testid="stButton"] button{border-radius:11px;font-weight:700;
  font-size:.8rem;padding:.42rem .2rem;transition:transform .12s ease,
  box-shadow .16s ease,filter .16s ease}
div[data-testid="stButton"] button:hover{transform:translateY(-1px);
  box-shadow:0 5px 14px rgba(16,26,42,.14)}
div[data-testid="stButton"] button:active{transform:scale(.97)}


/* ── One room, one card ──
   Modelled on the handheld the team already uses: the room and the guest
   carry the line, what changes the approach sits underneath as chips, and the
   one thing you press is a circle on the right, big enough for a thumb in a
   corridor. */
.tk{display:flex;align-items:center;gap:11px;min-height:66px;
  border:1px solid #e2e8f1;border-left-width:6px;border-radius:13px;
  padding:9px 13px;background:#fff;
  box-shadow:0 1px 2px rgba(16,26,42,.05);
  transition:background .35s ease,border-color .35s ease,opacity .3s ease;
  animation:tkin .32s cubic-bezier(.2,.8,.25,1) both}
.tkico{font-size:1.5rem;flex:0 0 auto;opacity:.75;line-height:1}
.tkmain{flex:1 1 auto;min-width:0}
.tkline1{display:flex;align-items:baseline;gap:9px}
.tkroom{font-weight:800;font-size:1.06rem;color:#16202e;
  font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.tkmins{font-size:.74rem;color:#5b6b7e;white-space:nowrap}
.tknote{font-size:.75rem}
.tkguest{font-size:.86rem;color:#42536a;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}
.tkarr{font-size:.72rem;color:#7b8798;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}
.tkfoot{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-top:4px}
.tkrqs{margin-left:auto;font-size:.72rem;color:#5b6b7e;white-space:nowrap}
.tkdot{width:11px;height:11px;border-radius:50%;flex:0 0 auto;
  transition:background .35s ease,transform .3s ease}
.tkchip{font-size:.6rem;font-weight:800;letter-spacing:.05em;
  border-radius:6px;padding:2px 6px;background:#eef2f7;color:#42536a}
.tkchip.owner{background:#fff3cd;color:#7a5200}
.tkchip.vip{background:#ffe0ef;color:#9b1c48}
.tkchip.early{background:#dbeafe;color:#12447e}
.tkchip.pet{background:#fff0e0;color:#8a4b00}
.tkchip.late{background:#fde8ef;color:#9b1c48}
/* Finished rooms recede rather than vanish -- still countable, no longer
   competing with what is left. */
.tk.gone{background:#fafcfa}
.tk.gone .tkroom,.tk.gone .tkguest{opacity:.5}
.tk.gone .tkroom{text-decoration:line-through;text-decoration-thickness:1px}
.tk.just{animation:tkpop .55s cubic-bezier(.2,1.2,.3,1) both}
.tk.just .tkdot{animation:tkdot .6s ease both}
.tk.working{position:relative;overflow:hidden}
.tk.working:after{content:"";position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(100deg,transparent 35%,rgba(255,255,255,.5) 50%,
  transparent 65%);animation:mrsweep 2.6s linear infinite}

/* The circle. Streamlit gives a keyed widget a st-key- class, which is the
   only handle there is on one particular button. */
[class*="st-key-"][class*="_go_"] button{
  border-radius:50% !important;width:54px !important;height:54px !important;
  min-height:54px !important;padding:0 !important;
  font-size:1.35rem !important;line-height:1 !important;
  border:3px solid #cfd9e5 !important;background:#fff !important;
  transition:transform .15s ease,border-color .2s ease,box-shadow .2s ease}
[class*="st-key-"][class*="_go_"] button:hover{
  border-color:#2f9169 !important;transform:scale(1.06);
  box-shadow:0 6px 16px rgba(47,145,105,.22) !important}
[class*="st-key-"][class*="_go_"] button:active{transform:scale(.94)}

.dlghead{font-size:1.02rem;margin:0 0 10px;display:flex;align-items:center;
  gap:9px;flex-wrap:wrap}
.dlgnow{margin-left:auto;border-radius:99px;padding:3px 11px;font-size:.7rem;
  font-weight:800;letter-spacing:.03em}
.dlgdot{width:14px;height:14px;border-radius:50%;margin:0 auto}
/* A housekeeper's rooms sit under their name, indented, always open. */
.tmhead{display:flex;align-items:center;gap:10px;margin:16px 0 6px}
.tmname{font-weight:800;font-size:.92rem;color:#16202e}
.tmcount{font-size:.76rem;color:#5b6b7e;font-variant-numeric:tabular-nums}
.tmbar{flex:1;height:6px;border-radius:99px;background:#e6ebf2;overflow:hidden}
.tmbar i{display:block;height:100%;border-radius:99px;
  background:linear-gradient(90deg,#2f9169,#46b184);transition:width .6s ease}
.mrbar.sm{height:6px;margin:0 0 8px}
.mrteam{margin:18px 0 8px;font-size:.8rem;color:#42536a;
  border-top:1px solid #e6ebf2;padding-top:12px}
@keyframes tkin{from{opacity:0;transform:translateY(6px)}to{opacity:1}}
@keyframes tkpop{0%{transform:scale(1)}30%{transform:scale(1.012)}
  100%{transform:scale(1)}}
@keyframes tkdot{0%{transform:scale(1)}35%{transform:scale(2.2)}
  100%{transform:scale(1)}}
@media (max-width:640px){
  .tkarr{display:none}
  .tkico{font-size:1.25rem}
  .tkroom{font-size:1rem}
}

/* Most of the team is on a phone in a corridor, so the two columns become
   one rather than squeezing to half a screen wide. */
@media (max-width:700px){
  [data-testid="stHorizontalBlock"]{flex-wrap:wrap}
  [data-testid="stColumn"]{min-width:100% !important;flex:1 1 100% !important}
  .mrhero h1{font-size:1.35rem}
}
</style>""", unsafe_allow_html=True)

cu = auth.current_user()
me_display = cu.get("display_name") or ""
me_user = cu.get("username", "")
today = clock.today()


# ── today's published schedule ───────────────────────────────────────────────
_load = assignments.todays_charts

charts, statuses = _load()

if not charts:
    st.markdown(f'<div class="mrhero"><h1>{e(T("rooms.no_schedule"))}</h1>'
                f'<p>{e(T("rooms.no_schedule_body"))}</p></div>',
                unsafe_allow_html=True)
    st.stop()

hk_names = assignments.housekeepers(charts)

# Sign-in names rarely match the schedule exactly, so try the display name and
# then the username.
mine = assignments.match_name(hk_names, me_display, me_user)

# Only a manager looks after everyone, so only a manager may browse. An RQS is
# here for their own rooms if they are carrying any, and for nothing else --
# the boards on the Schedule page are where they look after the team.
can_browse = auth.can("can_manage_users")
role = st.session_state.get("role", "")

# An RQS comes here for their team, not for rooms of their own. Matching them
# against the inspectors on today's charts is what decides that -- the role on
# the account is not enough, because an RQS who is not on duty today has no
# team to show.
_insp_names = sorted({g.get("inspector", "") for g in charts
                      if g.get("inspector")})
my_insp = assignments.match_name(_insp_names, me_display, me_user)

if can_browse:
    mine = st.selectbox(
        T("rooms.whose"), hk_names,
        index=hk_names.index(mine) if mine in hk_names else 0, key="mr_person")
elif mine is None and role == "housekeeper":
    # Her name is on the schedule in some other spelling; let her find it
    # rather than telling her she has no work.
    mine = st.selectbox(T("rooms.not_matched"), hk_names, key="mr_person")
elif mine is None and not my_insp:
    st.markdown(f'<div class="mrcard"><div class="mrroom">'
                f'{e(T("rooms.none_today"))}</div>'
                f'<div class="mrmeta">{e(T("rooms.none_body"))}</div></div>',
                unsafe_allow_html=True)
    st.stop()

my_charts = [g for g in charts if mine and g.get("housekeeper") == mine]
my_rooms = [(g, r) for g in my_charts for r in (g.get("rooms") or [])]

greet = str(mine or my_insp or "").split()[0].title()
done_n = sum(1 for _g, r in my_rooms
             if _rst.is_clean(
                 (statuses.get(str(r.get("room", ""))) or {}).get("status")))
total_n = len(my_rooms)
mins = sum(g.get("time", 0) for g in my_charts)
pct = int(round(100 * done_n / total_n)) if total_n else 0

st.markdown(
    f'<div class="mrhero"><h1>{e(T("rooms.hello", name=greet))}</h1>'
    f'<p>{e(T("rooms.subtitle"))} · {e(today.strftime("%A, %d %B %Y"))}'
    f'{" · " + e(T("rooms.total_time", mins=mins)) if mins else ""}</p>'
    f'<div class="mrbar"><i style="width:{pct}%"></i></div>'
    f'<div class="mrcount">{e(T("rooms.progress", done=done_n, total=total_n))}'
    f'</div></div>', unsafe_allow_html=True)

if not my_rooms and not my_insp:
    st.markdown(f'<div class="mrcard"><div class="mrroom">'
                f'{e(T("rooms.none_today"))}</div>'
                f'<div class="mrmeta">{e(T("rooms.none_body"))}</div></div>',
                unsafe_allow_html=True)
    st.stop()


# ── live: notice what a supervisor changed, without a reload ─────────────────
def _fingerprint(chs, sts, who):
    sig = repr([(g.get("label"), g.get("housekeeper"), g.get("inspector"),
                 g.get("service_type"), g.get("time"),
                 [str(r.get("room")) for r in (g.get("rooms") or [])])
                for g in chs if g.get("housekeeper") == who]) + \
        repr(sorted((k, _rst.normalise((v or {}).get("status")))
                    for k, v in sts.items()))
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()


fp_now = _fingerprint(charts, statuses, mine or my_insp)
st.session_state["mr_fp"] = fp_now


@st.fragment(run_every=20)
def _watch():
    """Poll for changes upstairs and reload the page when there are any.

    The fingerprint covers only this person's charts and the statuses, so an
    unrelated edit elsewhere does not yank the page out from under someone
    halfway through marking a room.
    """
    try:
        chs, sts = _load()
    except Exception:
        return
    if _fingerprint(chs, sts, mine) != st.session_state.get("mr_fp"):
        st.session_state["mr_changed"] = True
        st.rerun()
    st.markdown(
        f'<div class="mrlive"><b>●</b> {e(T("rooms.live"))} · '
        f'{e(T("rooms.last_check", time=clock.clock_str()))}'
        f'</div>', unsafe_allow_html=True)


_watch()

if st.session_state.pop("mr_changed", False):
    st.toast(T("rooms.updated"), icon="🔄")

if done_n and done_n == total_n:
    st.markdown(f'<div class="mrdone">🎉 {e(T("rooms.all_done"))}</div>',
                unsafe_allow_html=True)


# ── marking a room ───────────────────────────────────────────────────────────
ALREADY_CLEAN_K = ALREADY

def _mark(room, chart, new_status, who=None):
    """Record where a room has got to.

    `who` is whose room it is, which is not always the person pressing the
    button: an RQS marks on behalf of a housekeeper who has her hands full.
    The row keeps the housekeeper's name and records who actually pressed it.
    """
    now = clock.stamp()
    fields = {"status": new_status, "housekeeper": who or mine,
              "group_label": chart.get("label", ""),
              "inspector": chart.get("inspector", "") or "",
              "updated_by": me_user or me_display}
    if new_status == IN_PROGRESS:
        fields["started_at"] = now
        fields["cleaned_at"] = None
    elif new_status == CLEANED:
        fields["cleaned_at"] = now
    elif new_status == INSPECTED:
        fields["inspected_at"] = now
    elif new_status == NOT_STARTED:
        fields["started_at"] = None
        fields["cleaned_at"] = None
    try:
        db.upsert_room_status(room, fields)
        st.session_state["mr_flash"] = room
    except Exception as ex:
        print(f"[my_rooms] save failed for {room}: {ex}")
        st.session_state["mr_error"] = room
    # No st.rerun() here: this runs as a button callback, and Streamlit already
    # reruns after one. Calling it again threw the run away mid-flight.


if st.session_state.pop("mr_error", None):
    st.error(T("act.offline"))

flash = st.session_state.pop("mr_flash", None)


def _flags_for(r):
    """The things about a room that change how it is approached.

    Drawn from what the sheet actually carries rather than a wish list: an
    owner's unit is the VIP case at a timeshare, an arriving guest means the
    room has a deadline, and the notes are scanned for the words people
    actually type when a room needs special handling.
    """
    out = []
    res = str(r.get("res_type", "") or "")
    if "owner" in res.lower():
        out.append(("owner", "OWNER"))
    note = " ".join(str(r.get(k, "") or "") for k in ("notes", "service"))
    low = note.lower()
    if "vip" in low:
        out.append(("vip", "VIP"))
    if "priority" in low or "rush" in low:
        out.append(("vip", "PRIORITY"))
    if "early" in low:
        out.append(("early", "EARLY IN"))
    if str(r.get("arriving", "") or "").strip() and not any(
            k == "early" for k, _ in out):
        out.append(("early", "ARRIVING"))
    if str(r.get("pet", "") or "").strip():
        out.append(("pet", "PET"))
    if r.get("late_checkout"):
        out.append(("late", "LATE OUT"))
    return out


#: What the room is, at a glance, before reading anything.
_SVC_ICON = {"Full Clean": "🧳", "Full Clean (IH)": "🧳",
             "Daily Service": "🛏", "Dust n Vac": "🧹"}

#: The glyph is where the room is now; tapping moves it one step on.
_GLYPH = {NOT_STARTED: "○", IN_PROGRESS: "◐", CLEANED: "✓", INSPECTED: "★",
          ALREADY: "✓", DND: "⏸", HELP: "!"}

#: Who may close a room. A housekeeper hands it over; the RQS signs it off.
can_inspect = auth.can("can_view_insp_tab")


def _step(cur):
    """The next step for this room, and why it might not be takeable."""
    nxt = _rst.NEXT.get(cur)
    if nxt is None:
        return None, T("rooms.done_here")
    if nxt in _rst.RQS_ONLY and not can_inspect:
        return None, T("rooms.awaiting_rqs")
    return nxt, ""


def _open_marker(code, owner):
    """Remember which room was tapped; the dialog opens on the next run."""
    st.session_state["mr_open"] = {"room": code, "owner": owner}


@st.dialog("Mark this room")
def _marker(code, g, r, owner):
    """Every option for one room, on one screen.

    A dialog rather than a dropdown: a dropdown had to be dismissed by hand
    and did not always go, so a second tap landed on whatever was underneath
    it. This closes itself the moment something is chosen.
    """
    rec = statuses.get(code) or {}
    cur = _rst.normalise(rec.get("status"))
    guest = str(r.get("guest", "") or "").strip()
    st.markdown(f'<div class="dlghead"><b>{e(code)}</b>'
                f'{" · " + e(guest) if guest else ""}'
                f'<span class="dlgnow" style="background:{_rst.META[cur][3]};'
                f'color:{_rst.META[cur][4]}">{e(T(STATUS_KEY[cur]))}</span></div>',
                unsafe_allow_html=True)

    def _pick(target):
        _mark(code, g, target, owner)
        st.session_state.pop("mr_open", None)
        st.rerun()

    # The road first, in order, so the next step is where the eye lands.
    st.caption(T("rooms.the_round"))
    for target in (NOT_STARTED, IN_PROGRESS, CLEANED, INSPECTED):
        if target in _rst.RQS_ONLY and not can_inspect:
            continue
        dot = _rst.META[target][2]
        here = target == cur
        c1, c2 = st.columns([0.5, 6], vertical_alignment="center")
        with c1:
            st.markdown(f'<div class="dlgdot" style="background:{dot}"></div>',
                        unsafe_allow_html=True)
        with c2:
            st.button(T(STATUS_KEY[target]) + ("  ✓" if here else ""),
                      key=f"dlg_{target}_{code}", use_container_width=True,
                      disabled=here,
                      type="primary" if target == _rst.NEXT.get(cur) else "secondary",
                      on_click=_pick, args=(target,))

    # Then the ways off it.
    st.caption(T("rooms.other_ways"))
    d1, d2, d3 = st.columns(3)
    for col, (lbl, target) in zip((d1, d2, d3),
                                  (("st.already_clean", ALREADY),
                                   ("act.dnd", DND), ("act.help", HELP))):
        with col:
            st.button(T(lbl), key=f"dlg_{target}_{code}",
                      use_container_width=True, disabled=target == cur,
                      on_click=_pick, args=(target,))

    st.caption(T("act.note"))
    txt = st.text_area(T("act.note_ph"), value=rec.get("notes") or "",
                       key=f"dlg_note_{code}", height=90,
                       label_visibility="collapsed",
                       placeholder=T("act.note_ph"))
    n1, n2 = st.columns([1, 1])
    with n1:
        if st.button(T("act.save"), key=f"dlg_nb_{code}", type="primary",
                     use_container_width=True):
            try:
                db.upsert_room_status(code, {
                    "notes": txt, "housekeeper": owner,
                    "group_label": g.get("label", ""),
                    "updated_by": me_user or me_display})
                st.session_state["mr_flash"] = code
            except Exception as ex:
                print(f"[my_rooms] note failed for {code}: {ex}")
                st.session_state["mr_error"] = code
            st.session_state.pop("mr_open", None)
            st.rerun()
    with n2:
        if st.button(T("rooms.close"), key=f"dlg_x_{code}",
                     use_container_width=True):
            st.session_state.pop("mr_open", None)
            st.rerun()


def _room_row(g, r, key_prefix, owner, editable=True):
    """One room, as a line you can act on without reading twice."""
    code = str(r.get("room", ""))
    rec = statuses.get(code) or {}
    cur = _rst.normalise(rec.get("status"))
    bg, ink, accent = STATUS_STYLE.get(cur, STATUS_STYLE[NOT_STARTED])
    guest = str(r.get("guest", "") or "").strip()
    if guest.lower() in ("unallocated", "---", "room, walk", "deposit, deposit"):
        guest = ""
    arriving = str(r.get("arriving", "") or "").strip()
    insp = g.get("inspector", "") or ""
    note = rec.get("notes") or ""
    icon = _SVC_ICON.get(g.get("service_type", ""), "🧳")
    glyph = _GLYPH.get(cur, "○")
    nxt, why_not = _step(cur)

    chips = "".join(
        f'<span class="tkchip {kind}">{lbl}</span>' for kind, lbl in _flags_for(r))

    c_txt, c_btn = st.columns([6.4, 1.15], vertical_alignment="center")
    with c_txt:
        st.markdown(
            f'<div class="tk{" just" if code == flash else ""}'
            f'{" working" if cur == IN_PROGRESS else ""}'
            f'{" gone" if cur in (CLEANED, INSPECTED, ALREADY) else ""}" '
            f'style="border-left-color:{accent}">'
            f'<div class="tkico">{icon}</div>'
            f'<div class="tkmain">'
            f'<div class="tkline1"><span class="tkroom">{e(code)}</span>'
            f'<span class="tkmins">⚑ {r.get("time", 0)}m</span>'
            f'{"<span class=tknote>📝</span>" if note else ""}</div>'
            f'<div class="tkguest">{e(guest) or "—"}</div>'
            + (f'<div class="tkarr">→ {e(arriving)}</div>' if arriving else "")
            + f'<div class="tkfoot">{chips}'
            f'<span class="tkrqs">👤 {e(insp) or "—"}</span></div>'
            f'</div>'
            f'<div class="tkdot" style="background:{accent}"></div>'
            f'</div>', unsafe_allow_html=True)
    with c_btn:
        if editable:
            # One control, not two. The circle shows where the room is and
            # opens the full list of what it could be -- a menu beside it was
            # a second thing to learn and a second thing to miss.
            st.button(glyph, key=f"{key_prefix}_go_{code}",
                      help=T(STATUS_KEY.get(cur, "st.not_started")),
                      use_container_width=True,
                      on_click=_open_marker, args=(code, owner))


for _g, _r in sorted(my_rooms, key=lambda x: str(x[1].get("room", ""))):
    _room_row(_g, _r, "mr", mine)


_pending = st.session_state.get("mr_open")
if _pending:
    _hit = next(((g, r) for g in charts for r in (g.get("rooms") or [])
                 if str(r.get("room", "")) == _pending["room"]), None)
    if _hit:
        _marker(_pending["room"], _hit[0], _hit[1], _pending["owner"])
    else:
        st.session_state.pop("mr_open", None)


# ── an RQS sees their whole team, and can mark for them ──────────────────────
_team_of = my_insp or mine
_my_team = sorted({g.get("housekeeper", "") for g in charts
                   if _team_of and g.get("inspector") == _team_of
                   and g.get("housekeeper")
                   and not str(g.get("housekeeper", "")).startswith("Need")
                   and g.get("housekeeper") != mine})
if _my_team:
    st.markdown(f'<div class="mrteam"><b>{len(_my_team)}</b> '
                f'{T("rooms.team_note")}</div>', unsafe_allow_html=True)
    for _hk in _my_team:
        _hk_charts = [g for g in charts if g.get("housekeeper") == _hk]
        _hk_rooms = [(g, r) for g in _hk_charts for r in (g.get("rooms") or [])]
        _hk_done = sum(1 for _g, r in _hk_rooms
                       if _rst.is_clean((statuses.get(str(r.get("room", "")))
                                         or {}).get("status")))
        _pct = int(round(100 * _hk_done / max(len(_hk_rooms), 1)))
        # Always open. A supervisor walking the floor wants the rooms in front
        # of them, not a row of closed drawers to remember to open.
        st.markdown(
            f'<div class="tmhead"><span class="tmname">{e(_hk)}</span>'
            f'<span class="tmcount">{_hk_done}/{len(_hk_rooms)}</span>'
            f'<span class="tmbar"><i style="width:{_pct}%"></i></span></div>',
            unsafe_allow_html=True)
        with st.container():
            _left = [(g, r) for g, r in _hk_rooms
                     if not _rst.is_clean((statuses.get(str(r.get("room", "")))
                                           or {}).get("status"))]
            if _left and st.button(T("rooms.mark_rest"), key=f"allrest_{_hk}",
                                   use_container_width=True):
                _snap = None
                for g, r in _left:
                    try:
                        db.upsert_room_status(str(r.get("room", "")), {
                            "status": CLEANED, "housekeeper": _hk,
                            "group_label": g.get("label", ""),
                            "inspector": g.get("inspector", "") or "",
                            "cleaned_at": clock.stamp(),
                            "updated_by": me_user or me_display})
                    except Exception as ex:
                        print(f"[my_rooms] bulk mark failed: {ex}")
                st.rerun()
            for _g2, _r2 in sorted(_hk_rooms,
                                   key=lambda x: str(x[1].get("room", ""))):
                _room_row(_g2, _r2, f"t{_hk}", _hk)
