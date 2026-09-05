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
import property_map as pmap
import daystart as _day
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
/* Same width family as the rest of the app. Without a cap this page took
   Streamlit's wide default and stretched right across a big monitor. */
.block-container{max-width:min(1100px,97%);}
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
.tkroom{font-weight:800;font-size:1.06rem;color:var(--ink,#16202e);
  font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.tkmins{font-size:.74rem;color:var(--ink,#5b6b7e);opacity:.85;white-space:nowrap}
.tknote{font-size:.75rem}
.tkguest{font-size:.86rem;color:var(--ink,#42536a);white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}
.tkarr{font-size:.72rem;color:var(--ink,#7b8798);opacity:.8;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}
.tkfoot{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-top:4px}
.tkrqs{margin-left:auto;font-size:.72rem;color:var(--ink,#5b6b7e);opacity:.9;white-space:nowrap}
.tkdot{width:11px;height:11px;border-radius:50%;flex:0 0 auto;
  transition:background .35s ease,transform .3s ease}
.tkchip{font-size:.6rem;font-weight:800;letter-spacing:.05em;
  border-radius:6px;padding:2px 6px;background:#eef2f7;color:#42536a;
  white-space:nowrap}
.tkchip.owner{background:#fff3cd;color:#7a5200}
.tkchip.vip{background:#ffe0ef;color:#9b1c48}
.tkchip.early{background:#dbeafe;color:#12447e}
.tkchip.pet{background:#fff0e0;color:#8a4b00}
.tkchip.late{background:#fde8ef;color:#9b1c48}
.tkwhen{font-size:.72rem;font-weight:800;color:#12447e;background:#e8effa;
  border-radius:6px;padding:1px 6px;white-space:nowrap;font-variant-numeric:tabular-nums}
/* The day, as a shape. One strip from the first cart out to the last room
   finished, so the crunch is visible before it arrives rather than at 3pm. */
.dayw{background:#fff;border:1px solid #e3e8ef;border-radius:14px;
  padding:12px 14px 10px;margin:2px 0 12px}
.dayh{display:flex;align-items:baseline;gap:8px;margin-bottom:9px;flex-wrap:wrap}
.dayh b{font-size:.82rem;font-weight:800;letter-spacing:.04em;color:#42536a}
.dayh .fin{margin-left:auto;font-size:.8rem;font-weight:800;
  font-variant-numeric:tabular-nums;color:#166534}
.dayh .fin.over{color:#9b1c48}
.daytrack{position:relative;height:30px;border-radius:7px;background:#f1f4f8;
  overflow:hidden;display:flex}
.daytrack i{display:block;height:100%;overflow:hidden;
  display:flex;align-items:center;justify-content:center}
/* The room number lives in its own block on the bar. A segment too narrow to
   hold it clips to nothing rather than spilling over its neighbour, so a Dust
   n Vac round of forty short rooms stays a bar instead of a smear of text. */
.daytrack i b{font-size:.63rem;font-weight:800;color:#fff;letter-spacing:.01em;
  white-space:nowrap;font-variant-numeric:tabular-nums;
  text-shadow:0 1px 2px rgba(16,32,52,.4)}
.daytrack i.job.u0 b,.daytrack i.job.late b{color:#1c2b3d;text-shadow:none}
.daytrack i.go{background:repeating-linear-gradient(135deg,#cbd5e1 0 3px,#dbe2ea 3px 6px)}
.daytrack i.wait{background:repeating-linear-gradient(135deg,#fbcfe8 0 4px,#fde8ef 4px 8px)}
/* Four segment colours, each paired with the text colour that actually reads
   on it at 4.5:1 or better. u2 used to be #5b8cd6, which failed both ways --
   3.4:1 against white and 4.2:1 against dark -- so it is darker now. */
.daytrack i.job{background:#93b4e6}
.daytrack i.job.u2{background:#3d72c0}
.daytrack i.job.u3{background:#2f6fc4}
.daytrack i.job.late{background:#e59ab8}
.daymark{position:absolute;top:0;bottom:0;width:2px;background:#9b1c48;opacity:.75}
.daymark.soft{background:#94a3b8;opacity:.6}
.dayax{display:flex;justify-content:space-between;margin-top:4px;
  font-size:.64rem;color:#8a94a4;font-variant-numeric:tabular-nums}
.daysum{margin-top:7px;font-size:.72rem;color:#6b7789}
.daysum b{color:#42536a}
/* Finished rooms recede rather than vanish -- still countable, no longer
   competing with what is left. */
/* A finished room goes darker rather than crossed out. A line through a room
   number makes it harder to read at the moment it most needs checking -- when
   somebody asks which rooms are done. */
.tk.gone{filter:saturate(1.25) brightness(.965)}
.tk.gone{filter:none}
/* The whole card lights up in the colour it has just become, then settles.
   A dot changing colour on a phone held at arm's length is easy to miss; a
   card that flushes is not, and it says which room took the change when six
   of them are on screen. */
.tk.just{animation:tkflash .95s cubic-bezier(.2,.8,.25,1) both}
.tk.just .tkdot{animation:tkdot .6s ease both}
@keyframes tkflash{
  0%{background:var(--tint);box-shadow:0 0 0 4px var(--acc),
     0 10px 26px rgba(16,26,42,.18);transform:scale(1.012)}
  45%{background:var(--tint);box-shadow:0 0 0 2px var(--acc),
     0 6px 16px rgba(16,26,42,.12)}
  100%{background:#fff;box-shadow:0 1px 2px rgba(16,26,42,.05);transform:none}
}
/* At rest the card keeps a wash of its status, so the state reads without
   hunting for the dot. */
.tk{background:var(--tint,#fff)}
.tk.working{position:relative;overflow:hidden}
.tk.working:after{content:"";position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(100deg,transparent 35%,rgba(255,255,255,.5) 50%,
  transparent 65%);animation:mrsweep 2.6s linear infinite}

/* ── The menu the circle opens ──
   Modelled on the handheld: a short column of choices, the words on the left
   and a coloured icon on the right, each row tall enough to hit without
   looking. Streamlit gives a keyed widget a st-key- class, which is the only
   handle there is on one particular widget. */
[data-testid="stPopoverBody"]{padding:6px}
/* The menu floats from the circle. Nudged back over the card so it does not
   hang off the right edge of a phone. */
#stFloatingOverlayPortal [data-testid="stPopoverBody"]{max-width:250px}
[data-testid="stPopoverBody"] .stButton>button{
  justify-content:space-between !important;text-align:left !important;
  font-size:.92rem !important;font-weight:600 !important;
  padding:11px 14px !important;min-height:46px !important;
  border:none !important;background:transparent !important;
  border-radius:9px !important}
[data-testid="stPopoverBody"] .stButton>button:hover{
  background:#f2f6fb !important}
[data-testid="stPopoverBody"] .stButton>button:disabled{
  opacity:.45 !important}
/* The step the room would naturally take next is the one that is filled in. */
[data-testid="stPopoverBody"] .stButton>button[kind="primary"]{background:#eaf4ff !important;
  color:#12447e !important}

/* The circle itself. */
[class*="st-key-pop_"]>div>button,
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
/* One bar per housekeeper, under the one that counts everybody. Tight enough
   that a floor of six fits above the rooms rather than pushing them down. */
/* A note from the floor. Loud enough to be seen on the way past, quiet
   enough not to be the page. */
.ntbox{border:1px solid #f0c86a;background:#fffaf0;border-radius:12px;
  padding:11px 13px;margin:0 0 10px}
.nthead{font-weight:800;font-size:.84rem;color:#7a5200;margin-bottom:6px}
.ntrow{border-top:1px solid #f2e3c4;padding:6px 0 2px}
.ntrow:first-of-type{border-top:none}
.ntrow b{font-size:.86rem;color:#16202e}
.ntwho{font-size:.72rem;color:#8a6d3b;margin-left:8px}
.nttext{font-size:.82rem;color:#42536a;margin-top:2px}
/* And on the card itself, so it is still there after the alert is cleared. */
.tkmsg{font-size:.74rem;color:#7a5200;background:#fff8e8;border-radius:7px;
  padding:3px 7px;margin-top:4px;white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis}
/* The strip that opens a card, and what it opens. */
[class*="st-key-"][class*="_more_"] button{
  border:none !important;background:transparent !important;
  color:#5b6b7e !important;font-size:.7rem !important;font-weight:700 !important;
  letter-spacing:.06em;text-transform:uppercase;min-height:26px !important;
  padding:2px !important}
[class*="st-key-"][class*="_more_"] button:hover{
  background:#eef2f7 !important;color:#12447e !important}
.dtwrap{border:1px solid #e2e8f1;border-radius:11px;background:#fbfcfe;
  padding:10px 13px;margin:0 0 10px;
  animation:tkin .25s cubic-bezier(.2,.8,.25,1) both}
.dthead{font-family:'DM Mono',monospace;font-size:.6rem;font-weight:700;
  text-transform:uppercase;letter-spacing:.12em;color:#8a95a4;
  margin:8px 0 3px;border-bottom:1px solid #eef2f7;padding-bottom:3px}
.dthead:first-child{margin-top:0}
.dtrow{display:flex;gap:10px;font-size:.79rem;padding:2px 0}
.dtk{color:#7b8798;min-width:104px;flex:0 0 auto}
.dtv{color:#16202e;font-weight:600;min-width:0;overflow-wrap:anywhere}
.dtnote{font-size:.8rem;color:#7a5200;background:#fff8e8;border-radius:7px;
  padding:6px 9px;margin-top:3px}
.pgwrap{border:1px solid #e6ebf2;border-radius:12px;padding:9px 12px;
  background:#fbfcfe;margin:0 0 12px}
.pgrow{display:flex;align-items:center;gap:10px;padding:3px 0}
.pgname{font-size:.8rem;font-weight:700;color:#16202e;min-width:112px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pgbar{flex:1;height:7px;border-radius:99px;background:#e6ebf2;overflow:hidden}
.pgbar i{display:block;height:100%;border-radius:99px;
  background:linear-gradient(90deg,#2f9169,#46b184);transition:width .6s ease}
.pgnum{font-size:.74rem;color:#5b6b7e;font-variant-numeric:tabular-nums;
  min-width:44px;text-align:right}
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
@st.cache_data(ttl=5, show_spinner=False)
def _fresh(_tick=0):
    """Today's charts and statuses, held for a few seconds.

    Every tap reruns the page, and reading the schedule and the whole status
    table again each time is what made marking a room feel like waiting. Five
    seconds is short enough that a change made upstairs still arrives on the
    next poll, and the cache is dropped outright the moment this page writes
    anything, so your own marks never lag.
    """
    return assignments.todays_charts()


charts, statuses = _fresh()

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

# Who this page is answering for. An RQS is here for their team, so the team
# has to be worked out before the header, not after it: the header counts what
# is on the page, and for an inspector with no rooms of their own that used to
# be nothing at all -- "0 of 0 done" sitting above a housekeeper reading 4/4.
_team_of = my_insp or mine
_my_team = sorted({g.get("housekeeper", "") for g in charts
                   if _team_of and g.get("inspector") == _team_of
                   and g.get("housekeeper")
                   and not str(g.get("housekeeper", "")).startswith("Need")
                   and g.get("housekeeper") != mine})
_team_rooms = [(g, r) for g in charts
               if g.get("housekeeper") in _my_team
               for r in (g.get("rooms") or [])]
#: Every room this person can act on, theirs and their team's.
shown_rooms = my_rooms + _team_rooms

greet = str(mine or my_insp or "").split()[0].title()
done_n = sum(1 for _g, r in shown_rooms
             if _rst.is_clean(
                 (statuses.get(str(r.get("room", ""))) or {}).get("status")))
total_n = len(shown_rooms)
mins = sum(g.get("time", 0) for g in my_charts) or sum(
    r.get("time", 0) for _g, r in shown_rooms)
pct = int(round(100 * done_n / total_n)) if total_n else 0

st.markdown(
    f'<div class="mrhero"><h1>{e(T("rooms.hello", name=greet))}</h1>'
    f'<p>{e(T("rooms.subtitle") if my_rooms else T("rooms.subtitle_team"))}'
    f' · {e(today.strftime("%A, %d %B %Y"))}'
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
        repr(sorted((k, _rst.normalise((v or {}).get("status")),
                     str((v or {}).get("notes") or ""))
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
        chs, sts = assignments.todays_charts()
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
        # A new generation shuts every open menu, and the cache is dropped so
        # the change is on screen in the same breath rather than up to five
        # seconds later.
        st.session_state["mr_gen"] = st.session_state.get("mr_gen", 0) + 1
        _fresh.clear()
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
        # The time is the whole point of the flag -- "LATE OUT" on its own
        # tells somebody to skip the room, not when to come back for it.
        at = _day.late_out_at(r)
        out.append(("late", f"LATE OUT {at}" if at else "LATE OUT"))
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


#: Label, and the icon that carries it. The icon is what the eye finds on a
#: list read at arm's length; the words are for the first week.
_OPTIONS = [
    (NOT_STARTED, "⏳"), (IN_PROGRESS, "🧹"), (CLEANED, "🔍"), (INSPECTED, "✅"),
    (ALREADY, "✨"), (DND, "🚪"), (HELP, "❗"),
]


def _menu(code, g, owner, key_prefix, cur):
    """The options for one room, opened from its circle.

    A popover rather than a dialog: a dialog has to ask the server before it
    can even open, which on a phone at the end of a corridor is a wait before
    every single mark. This opens in the browser the moment it is touched.

    Its key carries a counter that moves on after every change, so the next
    render is a different widget and the menu is shut. That is what closes
    it -- the old one had to be dismissed by hand and often was not, so the
    following tap landed on whatever was underneath.
    """
    gen = st.session_state.get("mr_gen", 0)
    # Not use_container_width: that stretched the menu to the width of the row
    # and it came out as a slab under the card. A fixed, narrow menu floats
    # beside the circle that opened it, the way the handheld does it.
    with st.popover(_GLYPH.get(cur, "○"), use_container_width=True,
                    width=248, key=f"pop_{key_prefix}_{code}_{gen}"):
        for target, icon in _OPTIONS:
            if target in _rst.RQS_ONLY and not can_inspect:
                continue
            here = target == cur
            st.button(f"{T(STATUS_KEY[target])}\u2003{icon}",
                      key=f"m{gen}_{key_prefix}_{target}_{code}",
                      use_container_width=True, disabled=here,
                      type="primary" if target == _rst.NEXT.get(cur)
                      else "secondary",
                      on_click=_mark, args=(code, g, target, owner))
        with st.popover(f'{T("act.note")} 📝', use_container_width=True):
            _nkey = f"n{gen}_{key_prefix}_{code}"
            st.text_area(T("act.note_ph"),
                         value=(statuses.get(code) or {}).get("notes") or "",
                         key=_nkey, height=80, label_visibility="collapsed",
                         placeholder=T("act.note_ph"))
            # The KEY goes to the callback, not the text. Arguments are bound
            # when the button is drawn, so passing the text handed the callback
            # whatever the box held on the previous run -- which, for somebody
            # who types and then presses Save, is nothing. Every note written
            # on the floor was being saved as an empty string.
            st.button(T("act.save"), key=f"nb{gen}_{key_prefix}_{code}",
                      type="primary", use_container_width=True,
                      on_click=_save_note, args=(code, g, owner, _nkey))


def _save_note(code, g, owner, note_key):
    """Store a note. The text is read from the widget at the moment the
    button is pressed, which is the only way to get what was just typed."""
    txt = str(st.session_state.get(note_key, "") or "").strip()
    try:
        # Only columns room_status actually has. Inventing note_at and note_by
        # made PostgREST reject the whole write, so every note typed on the
        # floor was thrown away with an error the housekeeper could do nothing
        # about. The table already stamps updated_at and carries updated_by.
        db.upsert_room_status(code, {
            "notes": txt, "housekeeper": owner,
            "group_label": g.get("label", ""),
            "updated_by": me_display or me_user})
        st.session_state["mr_flash"] = code
        st.session_state["mr_gen"] = st.session_state.get("mr_gen", 0) + 1
        _fresh.clear()
    except Exception as ex:
        print(f"[my_rooms] note failed for {code}: {ex}")
        st.session_state["mr_error"] = code


def _toggle_more(code):
    st.session_state["mr_more"] = (
        None if st.session_state.get("mr_more") == code else code)


def _detail_html(g, r, rec, owner):
    """Everything else known about a room, once somebody asks for it.

    The arrival is the part people go looking for -- who is coming, what kind
    of booking it is, and whether the room is still occupied -- because that
    is what decides whether it can be done now or has to wait.
    """
    def _row(label, value):
        if value in (None, "", "—"):
            return ""
        return (f'<div class="dtrow"><span class="dtk">{e(label)}</span>'
                f'<span class="dtv">{e(value)}</span></div>')

    res = str(r.get("res_type", "") or "").strip()
    occ = str(r.get("status", "") or "").strip()
    arr = str(r.get("arriving", "") or "").strip()
    note = str(rec.get("notes") or "").strip()

    times = []
    for key, lbl in (("started_at", T("rooms.t_started")),
                     ("cleaned_at", T("rooms.t_ready")),
                     ("inspected_at", T("rooms.t_inspected"))):
        if rec.get(key):
            times.append(f"{lbl} {_local_hhmm(rec.get(key))}")

    return (
        '<div class="dtwrap">'
        + f'<div class="dthead">{e(T("rooms.arrival"))}</div>'
        + _row(T("rooms.guest_now"), str(r.get("guest", "") or "").strip())
        + _row(T("rooms.guest_next"), arr)
        + _row(T("rooms.res_type"), res)
        + _row(T("rooms.occupancy"), occ)
        # Under Arrival, because it is the other half of the same question:
        # can this room be done now, or does it have to wait?
        + _row(T("rooms.late_out"), str(r.get("late_checkout") or "").strip())
        + f'<div class="dthead">{e(T("rooms.the_room"))}</div>'
        + _row(T("rooms.building_l"), r.get("bld"))
        + _row(T("rooms.floor_l"), r.get("floor"))
        + _row(T("rooms.service_l"), i18n.service(g.get("service_type", "")))
        + _row(T("rooms.minutes_l"), f'{r.get("time", 0)} min')
        + _row(T("rooms.chart_l"), g.get("label"))
        + _row(T("rooms.cleaner_l"), owner)
        + _row(T("rooms.rqs_l"), g.get("inspector"))
        + (f'<div class="dthead">{e(T("rooms.progress_l"))}</div>'
           + _row(T("rooms.marked_l"), " · ".join(times)) if times else "")
        + _row(T("rooms.by_l"), rec.get("updated_by"))
        + (f'<div class="dthead">{e(T("act.note"))}</div>'
           f'<div class="dtnote">{e(note)}</div>' if note else "")
        + '</div>')


def _room_row(g, r, key_prefix, owner, editable=True, show_owner=False, when=None):
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
    nxt, why_not = _step(cur)

    chips = "".join(
        f'<span class="tkchip {kind}">{lbl}</span>' for kind, lbl in _flags_for(r))

    c_txt, c_btn = st.columns([6.4, 1.15], vertical_alignment="center")
    with c_txt:
        st.markdown(
            f'<div class="tk{" just" if code == flash else ""}'
            f'{" working" if cur == IN_PROGRESS else ""}'
            f'{" gone" if cur in (CLEANED, INSPECTED, ALREADY) else ""}" '
            f'style="border-left-color:{accent};--acc:{accent};--tint:{bg};'
            f'--ink:{ink}">'
            f'<div class="tkico">{icon}</div>'
            f'<div class="tkmain">'
            f'<div class="tkline1"><span class="tkroom">{e(code)}</span>'
            + (f'<span class="tkwhen">{e(when)}</span>' if when else "")
            + f'<span class="tkmins">⚑ {r.get("time", 0)}m</span>'
            f'{"<span class=tknote>📝</span>" if note else ""}</div>'
            f'<div class="tkguest">{e(guest) or "—"}</div>'
            + (f'<div class="tkarr">→ {e(arriving)}</div>' if arriving else "")
            + (f'<div class="tkmsg">📝 {e(note)}</div>' if note else "")
            + f'<div class="tkfoot">{chips}'
            f'<span class="tkrqs">{"🧹 " + e(owner) if show_owner else "👤 " + (e(insp) or "—")}</span></div>'
            f'</div>'
            f'<div class="tkdot" style="background:{accent}"></div>'
            f'</div>', unsafe_allow_html=True)
        # A card that opens. The line is what you work from; the rest of what
        # is known about the room is a tap away rather than crowding it.
        _open = st.session_state.get("mr_more") == code
        st.button(("▲ " if _open else "▼ ") + T("rooms.more"),
                  key=f"{key_prefix}_more_{code}", use_container_width=True,
                  on_click=_toggle_more, args=(code,))
        if _open:
            st.markdown(_detail_html(g, r, rec, owner), unsafe_allow_html=True)
    with c_btn:
        if editable:
            _menu(code, g, owner, key_prefix, cur)


# ── an RQS sees their whole team, and can mark for them ──────────────────────
def _local_hhmm(iso):
    """The row's timestamp, at the property. Supabase stamps in UTC."""
    try:
        import datetime as _dt
        t = _dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=_dt.timezone.utc)
        return t.astimezone(clock.MTN).strftime("%H:%M")
    except Exception:
        return ""


# ── notes from the floor ─────────────────────────────────────────────────────
if _my_team:
    _notes = []
    for _g, _r in _team_rooms:
        _rec = statuses.get(str(_r.get("room", ""))) or {}
        if str(_rec.get("notes") or "").strip():
            _at = str(_rec.get("updated_at") or "")
            _notes.append({
                "room": str(_r.get("room", "")),
                "hk": _g.get("housekeeper", ""),
                "text": str(_rec.get("notes")).strip(),
                "at": _at,
                "by": str(_rec.get("updated_by") or ""),
            })
    # A note is new when it does not say what it said last time this person
    # read it. Comparing the words rather than a timestamp means no new column
    # in a table somebody would have to migrate, and it survives a room being
    # touched for some other reason -- a status change does not resurrect a
    # note that has already been read.
    _seen = st.session_state.get("mr_note_seen")
    if _seen is None:
        try:
            _seen = db.load_note_seen(me_user or me_display) or {}
        except Exception:
            _seen = {}
        st.session_state["mr_note_seen"] = _seen
    _new = [n for n in _notes if _seen.get(n["room"]) != n["text"]]
    if _new:
        # Somebody wrote this while their hands were full. It should not have
        # to be found by opening rooms one at a time.
        st.markdown(
            f'<div class="ntbox"><div class="nthead">📝 '
            f'{T("rooms.notes_new", n=len(_new))}</div>'
            + "".join(
                f'<div class="ntrow"><b>{e(n["room"])}</b>'
                f'<span class="ntwho">{e(n["hk"])}'
                f'{" · " + e(_local_hhmm(n["at"])) if n["at"] else ""}</span>'
                f'<div class="nttext">{e(n["text"])}</div></div>'
                for n in sorted(_new, key=lambda x: x["at"], reverse=True))
            + '</div>', unsafe_allow_html=True)
        if st.button(T("rooms.notes_read"), key="btn_notes_read",
                     use_container_width=True):
            _now_seen = dict(_seen)
            _now_seen.update({n["room"]: n["text"] for n in _notes})
            st.session_state["mr_note_seen"] = _now_seen
            try:
                db.save_note_seen(me_user or me_display, _now_seen)
            except Exception as ex:
                print(f"[my_rooms] could not store the read marker: {ex}")
            st.rerun()
    elif _notes:
        st.caption(T("rooms.notes_all_read", n=len(_notes)))

if _my_team:
    # A bar for each of them, merged under the one that counts everybody, so
    # the whole floor is legible in a glance: how far along in total, and who
    # is behind. The rooms then run as one list -- grouping them under names
    # meant scrolling past a finished person to reach an unfinished one.
    st.markdown(f'<div class="mrteam">{len(_my_team)} '
                f'{T("rooms.team_note")}</div>', unsafe_allow_html=True)
    _bars = ""
    for _hk in _my_team:
        _rs = [r for g in charts if g.get("housekeeper") == _hk
               for r in (g.get("rooms") or [])]
        _dn = sum(1 for r in _rs
                  if _rst.is_clean((statuses.get(str(r.get("room", "")))
                                    or {}).get("status")))
        _pc = int(round(100 * _dn / max(len(_rs), 1)))
        _bars += (f'<div class="pgrow"><span class="pgname">{e(_hk)}</span>'
                  f'<span class="pgbar"><i style="width:{_pc}%"></i></span>'
                  f'<span class="pgnum">{_dn}/{len(_rs)}</span></div>')
    st.markdown(f'<div class="pgwrap">{_bars}</div>', unsafe_allow_html=True)

# One list per person, in the order the day should actually be worked: an
# early check-in first even if it is in the wrong building, a late checkout
# only once the guest has gone, and everything between walked as little as
# possible. Room-code order looks tidy but sends somebody past the same
# service elevator three times and knocks on a door at ten past ten that is
# not empty until noon.
_plan, _seatmap = {}, {}
for _g, _r in shown_rooms:
    _plan.setdefault(str(_g.get("housekeeper", "")), []).append(_r)
for _hk in list(_plan):
    try:
        _blocks = _day.plan_day(_plan[_hk])
    except Exception:
        _blocks = []          # an unmappable room must never blank the page
    _plan[_hk] = _blocks
    _seatmap[_hk] = {b["room"]: (i, b) for i, b in enumerate(_blocks)}


def _seat(item):
    g, r = item
    hk = str(g.get("housekeeper", ""))
    code = str(r.get("room", "")).strip().upper()
    return (hk, _seatmap.get(hk, {}).get(code, (999, None))[0], code)


def _day_strip(blocks):
    """The whole day as one proportional bar, with the deadlines drawn on it."""
    if not blocks:
        return ""
    s = _day.summary(blocks)
    begin = _day._mins(_day.DAY_START)
    finish = s["finish"]
    span = max(finish, _day._mins(_day.CHECKIN)) - begin
    if span <= 0:
        return ""

    def pct(m):
        return 100.0 * m / span

    segs, cur = "", begin
    for b in blocks:
        if b["travel"] > 0:
            segs += f'<i class="go" style="width:{pct(b["travel"]):.3f}%"></i>'
        if b["wait"] > 0:
            segs += f'<i class="wait" style="width:{pct(b["wait"]):.3f}%"></i>'
        # The lightest segment carries dark text; the three darker ones carry
        # white. Room numbers on a bar are only worth putting there if they can
        # be read at arm's length in a corridor.
        if b["release"] is not None:
            klass = "job late"
        elif b["urgency"] >= 100:
            klass = "job u3"
        elif b["urgency"] >= 50:
            klass = "job u2"
        else:
            klass = "job u0"
        segs += (f'<i class="{klass}" style="width:{pct(b["minutes"]):.3f}%" '
                 f'title="{e(b["room"])} · {b["minutes"]:.0f}m · done by '
                 f'{_day.hhmm(b["end"])}"><b>{e(b["room"])}</b></i>')
        cur = b["end"]

    tgt = pct(_day._mins(_day.TARGET_END) - begin)
    chk = pct(_day._mins(_day.CHECKIN) - begin)
    # Pacing lands most charts exactly on the target, where the overrun is a
    # rounding sliver. Half a minute is not late; showing "0m over" is.
    over = s["over"] > 0.5
    fin_txt = _day.hhmm(finish) + (" · %.0fm over" % s["over"] if over else " ✓")
    return (
        f'<div class="dayw">'
        f'<div class="dayh"><b>{e(T("rooms.yourday"))}</b>'
        f'<span class="fin{" over" if over else ""}">{e(fin_txt)}</span></div>'
        f'<div class="daytrack">{segs}'
        f'<span class="daymark soft" style="left:{tgt:.2f}%"></span>'
        f'<span class="daymark" style="left:{chk:.2f}%"></span>'
        f'</div>'
        f'<div class="dayax"><span>{_day.hhmm(begin)}</span>'
        f'<span>3:30 ▏ 4:00</span></div>'
        f'<div class="daysum">'
        f'<b>{s["rooms"]}</b> rooms · <b>{s["clean"]:.0f}m</b> cleaning · '
        f'<b>{s["travel"]:.0f}m</b> walking'
        # The sheet's minutes are standards the floor beats. Say by how much
        # rather than silently quoting times nobody can trace back.
        + (f' · paced <b>{(1 - s["pace"]) * 100:.0f}%</b> under the sheet'
           if s["pace"] < 0.995 else "")
        + (f' · <b>{s["wait"]:.0f}m</b> waiting on a guest' if s["wait"] > 0 else "")
        + (f' · <b>{s["late_rooms"]}</b> late checkout'
           + ("s" if s["late_rooms"] != 1 else "") if s["late_rooms"] else "")
        # Never present a guess as a plan: if the sheet carried no minutes for
        # some rooms, the finish time is an estimate and has to say so.
        + (f' · <b>{s["untimed"]}</b> with no time on the sheet, estimated'
           if s["untimed"] else "")
        + f'</div></div>')


_flat = sorted(shown_rooms, key=_seat)
_mixed = len({g.get("housekeeper") for g, _ in _flat}) > 1

# The day's shape goes above the rooms it describes. An RQS looking at a whole
# team gets one strip per person, so a chart that cannot finish is visible from
# the top of the page instead of at three in the afternoon.
_drawn = set()
for _g, _r in _flat:
    _hk = str(_g.get("housekeeper", ""))
    if _hk not in _drawn:
        _drawn.add(_hk)
        _strip = _day_strip(_plan.get(_hk) or [])
        if _strip:
            if _mixed and _hk:
                st.markdown(f'<div class="pgname" style="margin:14px 0 2px;'
                            f'font-weight:800">🧹 {e(_hk)}</div>',
                            unsafe_allow_html=True)
            st.markdown(_strip, unsafe_allow_html=True)
    _blk = _seatmap.get(_hk, {}).get(str(_r.get("room", "")).strip().upper(),
                                     (999, None))[1]
    # The done-by time, not the start time. "Be finished here by 11:45" is
    # something a person can pace against mid-room; "start at 10:07" stops
    # being useful the moment the day slips by ten minutes.
    _room_row(_g, _r, "mr", _g.get("housekeeper") or mine,
              show_owner=_mixed,
              when=(T("rooms.by") + " " + _day.hhmm(_blk["end"])) if _blk else None)
