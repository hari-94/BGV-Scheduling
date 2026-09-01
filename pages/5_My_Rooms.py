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
import ui

st.set_page_config(page_title="My Rooms", page_icon="🛎️", layout="wide")
auth.require_login()
ui.topnav("My Rooms")

T = i18n.t


def e(s):
    return _html.escape(str(s) if s is not None else "")


# ── statuses ─────────────────────────────────────────────────────────────────
NOT_STARTED, IN_PROGRESS, CLEANED = "not_started", "in_progress", "cleaned"
INSPECTED, DND, HELP = "inspected", "dnd", "help"

# (background, ink, accent) — the accent is the stripe down the card's edge.
STATUS_STYLE = {
    NOT_STARTED: ("#f4f7fb", "#4a5768", "#c3cedd"),
    IN_PROGRESS: ("#fff5d9", "#7a5200", "#f0b429"),
    CLEANED:     ("#dcfbe7", "#0a5c32", "#22b365"),
    INSPECTED:   ("#dbeafe", "#12447e", "#2f80ed"),
    DND:         ("#ede9fe", "#4c1d95", "#8b5cf6"),
    HELP:        ("#ffe1e1", "#8a1c1c", "#e5484d"),
}
STATUS_KEY = {NOT_STARTED: "st.not_started", IN_PROGRESS: "st.in_progress",
              CLEANED: "st.cleaned", INSPECTED: "st.inspected",
              DND: "st.dnd", HELP: "st.help"}
STATUS_ICON = {NOT_STARTED: "○", IN_PROGRESS: "◐", CLEANED: "✓",
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

if can_browse:
    mine = st.selectbox(
        T("rooms.whose"), hk_names,
        index=hk_names.index(mine) if mine in hk_names else 0, key="mr_person")
elif mine is None and role == "housekeeper":
    # Her name is on the schedule in some other spelling; let her find it
    # rather than telling her she has no work.
    mine = st.selectbox(T("rooms.not_matched"), hk_names, key="mr_person")
elif mine is None:
    st.markdown(f'<div class="mrcard"><div class="mrroom">'
                f'{e(T("rooms.none_today"))}</div>'
                f'<div class="mrmeta">{e(T("rooms.none_body"))}</div></div>',
                unsafe_allow_html=True)
    st.stop()

my_charts = [g for g in charts if g.get("housekeeper") == mine]
my_rooms = [(g, r) for g in my_charts for r in (g.get("rooms") or [])]

greet = str(mine).split()[0].title() if mine else ""
done_n = sum(1 for _g, r in my_rooms
             if (statuses.get(str(r.get("room", ""))) or {}).get("status")
             in (CLEANED, INSPECTED))
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

if not my_rooms:
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
        repr(sorted((k, (v or {}).get("status")) for k, v in sts.items()))
    return hashlib.sha1(sig.encode("utf-8")).hexdigest()


fp_now = _fingerprint(charts, statuses, mine)
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
def _mark(room, chart, new_status):
    now = clock.stamp()
    fields = {"status": new_status, "housekeeper": mine,
              "group_label": chart.get("label", ""),
              "inspector": chart.get("inspector", "") or "",
              "updated_by": me_user or me_display}
    if new_status == IN_PROGRESS:
        fields["started_at"] = now
        fields["cleaned_at"] = None
    elif new_status == CLEANED:
        fields["cleaned_at"] = now
    elif new_status == NOT_STARTED:
        fields["started_at"] = None
        fields["cleaned_at"] = None
    try:
        db.upsert_room_status(room, fields)
        st.session_state["mr_flash"] = room
    except Exception as ex:
        print(f"[my_rooms] save failed for {room}: {ex}")
        st.session_state["mr_error"] = room
    st.rerun()


if st.session_state.pop("mr_error", None):
    st.error(T("act.offline"))

flash = st.session_state.pop("mr_flash", None)

# Two across on a laptop, one on a phone (see the media query above).
cols = st.columns(2, gap="small")
for i, (g, r) in enumerate(sorted(
        my_rooms, key=lambda x: str(x[1].get("room", "")))):
    code = str(r.get("room", ""))
    rec = statuses.get(code) or {}
    cur = rec.get("status") or NOT_STARTED
    bg, ink, accent = STATUS_STYLE.get(cur, STATUS_STYLE[NOT_STARTED])
    svc = i18n.service(g.get("service_type", ""))

    bits = []
    if r.get("bld"):
        bits.append(T("rooms.building", b=r["bld"]))
    if r.get("floor"):
        bits.append(T("rooms.floor", f=r["floor"]))
    bits.append(f'{r.get("time", 0)} min')

    tags = ""
    if str(r.get("pet", "")).strip():
        tags += f'<span class="mrtag pet">🐾 {e(T("rooms.pet"))}</span>'
    if r.get("late_checkout"):
        tags += f'<span class="mrtag late">🕔 {e(T("rooms.checkout"))}</span>'
    if g.get("label"):
        tags += f'<span class="mrtag">{e(g["label"])}</span>'

    note = rec.get("notes") or ""
    with cols[i % 2]:
        st.markdown(
            f'<div class="mrcard{" just" if code == flash else ""}'
            f'{" working" if cur == IN_PROGRESS else ""}" '
            f'style="border-left-color:{accent};background:{bg}">'
            f'<div class="mrroom">{e(code)}</div>'
            f'<div class="mrmeta">{e(svc)} · {e(" · ".join(bits))}</div>'
            f'<span class="mrpill" style="background:{accent};color:#fff">'
            f'{STATUS_ICON.get(cur, "")} {e(T(STATUS_KEY.get(cur, "st.not_started")))}'
            f'</span>{tags}'
            + (f'<div class="mrnote">📝 {e(note)}</div>' if note else "")
            + '</div>', unsafe_allow_html=True)

        # Two buttons, then everything else behind one menu -- this is read
        # at arm's length on a phone. Done never hides behind Start: someone
        # who cleaned a room without tapping Start still has to be able to
        # say so, and a missing start time is worth less than a missing room.
        if cur in (CLEANED, INSPECTED):
            primary = [("act.undo", IN_PROGRESS, "secondary")]
            more = [("act.help", HELP), ("act.dnd", DND)]
        elif cur == IN_PROGRESS:
            primary = [("act.done", CLEANED, "primary"),
                       ("act.undo", NOT_STARTED, "secondary")]
            more = [("act.help", HELP), ("act.dnd", DND)]
        else:
            primary = [("act.start", IN_PROGRESS, "secondary"),
                       ("act.done", CLEANED, "primary")]
            more = ([("act.dnd", DND), ("act.help", HELP)]
                    if cur == NOT_STARTED else
                    [("act.undo", NOT_STARTED), ("act.help", HELP)])

        bcols = st.columns(len(primary) + 1, gap="small")
        for (label_key, target, kind), bc in zip(primary, bcols):
            with bc:
                if st.button(T(label_key), key=f"mr_{target}_{code}",
                             type=kind, use_container_width=True):
                    _mark(code, g, target)
        with bcols[-1]:
            with st.popover("⋯", use_container_width=True):
                for label_key, target in more:
                    if st.button(T(label_key), key=f"mrx_{target}_{code}",
                                 use_container_width=True):
                        _mark(code, g, target)
                st.markdown(f'**{e(T("act.note"))}**')
                txt = st.text_area(T("act.note_ph"), value=note,
                                   key=f"mr_note_{code}", height=90,
                                   label_visibility="collapsed",
                                   placeholder=T("act.note_ph"))
                if st.button(T("act.save"), key=f"mr_notebtn_{code}",
                             type="primary", use_container_width=True):
                    try:
                        db.upsert_room_status(code, {
                            "notes": txt, "housekeeper": mine,
                            "group_label": g.get("label", ""),
                            "updated_by": me_user or me_display})
                        st.session_state["mr_flash"] = code
                    except Exception as ex:
                        print(f"[my_rooms] note failed for {code}: {ex}")
                        st.session_state["mr_error"] = code
                    st.rerun()
