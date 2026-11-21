"""Property — the building itself, in three dimensions, coloured by what is done.

For an RQS or a manager deciding who covers what. The floor plans say where a
room is; they do not say that buildings 2 and 3 never touch, or that a chart
holding rooms in both costs two bridge crossings. Seen as a solid, that is
obvious in a second, which is the whole reason this page exists.

The model is schematic. Every room sits at its true building, level, corridor
side and position along the corridor, and every bridge is drawn at the level it
actually crosses — the topology is exact. The dimensions are proportions taken
off the plans, which carry no measurements, so it is not a survey.
"""
import streamlit as st
import sys, os, json, collections, html
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, db, clock, i18n
import property_map as pmap
import roomstatus as _rst
import streamlit.components.v1 as components
import ui
import fresh
import avatars as av

st.set_page_config(page_title="Property", page_icon="🏔️", layout="wide")
# Same width family as the rest of the app, and unconditional: the plan
# view's stylesheet only renders in 2-D, so a cap in there would leave the
# 3-D view stretched across a big monitor.
st.markdown("<style>.block-container{max-width:min(1200px,97%);}</style>",
            unsafe_allow_html=True)
auth.require_login()
fresh.latest("i18n", "ui", "avatars")    # as they are on disk, not as first loaded
ui.topnav("Property")

T = i18n.t

if not auth.can("can_view_insp_tab"):
    st.warning(T("prop.no_access"))
    st.stop()


@st.cache_data(ttl=3600, show_spinner=False)
def _inventory():
    return db.all_known_rooms()


import floor  # noqa: E402


def _statuses(_gen):
    """Today's room statuses, off the shared floor (floor.py)."""
    return floor.today(fresh=bool(_gen) and st.session_state.get("_prop_seen") != _gen).statuses


@st.cache_data(ttl=600, show_spinner=False, max_entries=4)
def _today_from(_floor, stamp):
    """What each room is actually down for today: service, minutes, who has it.

    The inventory says the building exists; only the day's schedule says a room
    is a 140-minute Full Clean rather than a Dust n Vac touch-up, and that is
    what the boxes are sized and labelled by. Off the shared floor, worked out
    again only when it changed (`stamp`).
    """
    out = {}
    for g in (_floor.charts or []):
        for r in (g.get("rooms") or []):
            code = str(r.get("room", "")).strip().upper()
            if not code:
                continue
            try:
                mins = float(r.get("time") or 0)
            except (TypeError, ValueError):
                mins = 0.0
            out[code] = {"service": g.get("service_type", ""),
                         "minutes": mins,
                         "hk": g.get("housekeeper", "") or "",
                         "rqs": g.get("inspector", "") or "",
                         "label": g.get("label", "")}
    return out


@st.cache_data(ttl=300, show_spinner=False)
def _looks(_gen):
    """Who is drawn as a woman, a man or neutral -- set below, never guessed."""
    try:
        return db._load_key(av.SETTING_KEY) or {}
    except Exception:
        return {}


rooms = _inventory()
if not rooms:
    st.info(T("prop.no_rooms"))
    st.stop()

boxes = pmap.layout(rooms)
spans = pmap.bridge_spans()
gen = st.session_state.get("prop_gen", 0)
statuses = _statuses(gen)
st.session_state["_prop_seen"] = gen
_FLOOR = floor.today()
today = _today_from(_FLOOR, _FLOOR.fetched)

# ---------------------------------------------------------------- controls
c1, c2, c3 = st.columns([2.6, 1.2, 2.6])
with c1:
    colour_by = st.radio(T("prop.colour"),
                         [T("prop.by_status"), T("prop.by_service"),
                          T("prop.by_building")],
                         horizontal=True, key="prop_colour")
    av_choice = st.radio(T("prop.avatars"),
                         [T("prop.av_live"), T("prop.av_all"), T("prop.av_off")],
                         horizontal=True, key="prop_avatars")
with c2:
    flat = st.toggle(T("prop.flat"), value=False, key="prop_flat")
    show_extras = st.toggle(T("prop.show_amenities"), value=True, key="prop_extras")
    if st.button(T("prop.refresh"), use_container_width=True):
        st.session_state["prop_gen"] = st.session_state.get("prop_gen", 0) + 1
        st.rerun()
with c3:
    done = sum(1 for b in boxes
               if _rst.normalise((statuses.get(b["code"]) or {}).get("status"))
               in _rst.CLEANED)
    st.markdown(
        f'<div style="padding-top:6px;color:#5b6b7e;font-size:.86rem">'
        f'<b>{len(boxes)}</b> rooms · <b>{len(today)}</b> on a chart today · '
        f'<b>{done}</b> finished · <b>{len(spans)}</b> bridges</div>',
        unsafe_allow_html=True)

MODE = ("status" if colour_by == T("prop.by_status")
        else "service" if colour_by == T("prop.by_service") else "bld")
AV_MODE = ("live" if av_choice == T("prop.av_live")
           else "all" if av_choice == T("prop.av_all") else "off")
looks = _looks(st.session_state.get("prop_av_gen", 0))
ACT_LABEL = {a: T(f"prop.act_{a}") for a in av.ORDER}

# The signed-in person walks the property as themselves: their own look, in
# an RQS's navy unless they are housekeeping staff.
_me = auth.current_user()
_me_name = _me.get("display_name") or _me.get("username") or ""
PLAYER = {"look": av.look_of(looks, _me_name),
          "role": "hk" if _me.get("role") in ("housekeeper", "houseperson") else "rqs",
          "name": av.short_name(_me_name) or _me_name}
# The game's own words, so the game is bilingual like the rest of the page.
PLAY_TXT = {k: T(f"prop.play_{k}") for k in (
    "start", "stop", "help", "quests", "help_q", "ready_q", "xp", "visited",
    "level", "bld", "you", "since", "full", "map", "floors", "team", "office",
    "next", "hunt", "warm", "f_egg", "f_bunny", "f_golden", "f_pico", "f_duck",
    "f_all", "sound", "no_floor", "walk")}

# roomstatus owns the vocabulary and the colours; the model must not invent
# its own or the legend here stops matching the phone in somebody's hand.
STATUS_COLOUR = {k: v[2] for k, v in _rst.META.items()}
BLD_COLOUR = {1: "#5b8cd6", 2: "#c07a3e", 3: "#4e9e78"}
SVC_COLOUR = {"Full Clean": "#2563a8", "Full Clean (IH)": "#6d5bb5",
              "Daily Service": "#0f766e", "Dust n Vac": "#b45309"}
SVC_SHORT = {"Full Clean": "FC", "Full Clean (IH)": "IH",
             "Daily Service": "DS", "Dust n Vac": "DV"}
OFF_TODAY = "#c3ccd8"        # in the building, not on a chart today


def _depth(mins):
    """How deep a room is drawn. A 140 is not the same room as a 70.

    Depth rather than width, because the x positions are the real door
    positions along the corridor — widening a box would push it through its
    neighbour, while depth grows away from the hallway, which is also the way
    the bigger units genuinely run.
    """
    if not mins:
        return 0.62
    if mins <= 45:
        return 0.68
    if mins <= 80:
        return 0.92
    if mins <= 125:
        return 1.22
    return 1.46


for b in boxes:
    rec = statuses.get(b["code"]) or {}
    cur = _rst.normalise(rec.get("status"))
    day = today.get(b["code"]) or {}
    svc = day.get("service", "")
    b["status"] = cur
    b["svc"] = svc
    b["svc_short"] = SVC_SHORT.get(svc, "")
    b["mins"] = day.get("minutes", 0)
    b["depth"] = _depth(b["mins"])
    b["on_chart"] = bool(day)
    b["hk"] = rec.get("housekeeper") or day.get("hk", "")
    b["rqs"] = day.get("rqs", "")
    if not day:
        b["colour"] = OFF_TODAY
    elif MODE == "status":
        b["colour"] = STATUS_COLOUR.get(cur, "#94a3b8")
    elif MODE == "service":
        b["colour"] = SVC_COLOUR.get(svc, "#94a3b8")
    else:
        b["colour"] = BLD_COLOUR.get(b["bld"], "#94a3b8")
    b["av"] = 0          # how many people stand at this door

# Everybody once, at the room they marked last (avatars.place_people). The
# rooms keep their own colours; a person is drawn only where they last were.
people = []
if AV_MODE != "off":
    _now = clock.now()
    for i, p in enumerate(sorted(av.place_people(statuses, today, _now,
                                                 whole_team=AV_MODE == "all"),
                                 key=lambda p: p["name"].lower())):
        look = av.look_of(looks, p["name"])
        people.append({
            "code": p["code"], "key": av.key(look, p["act"]), "act": p["act"],
            "role": p["role"], "who": av.short_name(p["name"]), "name": p["name"],
            "col": av.ACT_COLOUR.get(p["act"], "#94a3b8"),
            "at": p["t"].astimezone(clock.MTN).strftime("%H:%M") if p["t"] else "",
        })
    _by_code = {b["code"]: b for b in boxes}
    _slots = collections.Counter()
    for p in people:       # two people at one door stand side by side
        p["slot"] = _slots[p["code"]]
        _slots[p["code"]] += 1
    for p in people:
        p["n"] = _slots[p["code"]]
        if p["code"] in _by_code:
            _by_code[p["code"]]["av"] = p["n"]

# Everything that is not a guest room. The service core is what a housekeeper's
# day is actually spent walking between, so it is drawn by default; the amenity
# volumes are what make the levels with no guest rooms stop being blank rows.
_levels = {(b["bld"], b["level"]) for b in boxes}
facils = pmap.facilities(_levels)
cores = pmap.service_cores(_levels)
if not show_extras:
    facils = [f for f in facils if f["kind"] != "amenity"]

AV_KEYS = sorted({p["key"] for p in people})
payload = json.dumps({"boxes": boxes, "spans": spans,
                      "facils": facils, "cores": cores,
                      "levels": pmap.LEVELS,
                      "doorW": pmap.DOOR_W, "levelH": pmap.LEVEL_H,
                      "hallD": pmap.HALL_D,
                      "people": people,
                      # one stepped strip per look and action actually on screen
                      "av": {k: av.strip_uri(*k.split("-", 1)) for k in AV_KEYS},
                      "acts": ACT_LABEL, "player": PLAYER, "txt": PLAY_TXT,
                      "day": clock.today_iso(),
                      "ready": list(_rst.READY), "help": _rst.HELP},
                     separators=(",", ":"))


def _game_bar():
    """The day as a score: how much of the floor is done, and what is live.

    Counted over the rooms on a chart today only -- a room nobody was ever
    going to clean is not a room left to do.
    """
    on = [b for b in boxes if b["on_chart"]]
    if not on:
        return ""
    n = collections.Counter(b["status"] for b in on)
    done = sum(v for k, v in n.items() if k in _rst.CLEANED)
    pct = round(100 * done / len(on))
    stars = "".join(
        f'<span style="opacity:{1 if pct >= q else .22}">★</span>' for q in (25, 50, 75, 100))

    def chip(action, count, colour):
        if not count:
            return ""
        return (f'<span class="gchip"><i class="av av-n-{action}" '
                f'style="background-color:transparent"></i>'
                f'<b style="color:{colour}">{count}</b> {ACT_LABEL[action]}</span>')

    chips = (chip("clean", n[_rst.STARTED], "#b45309")
             + chip("cheer", sum(n[k] for k in _rst.READY), "#2f80ed")
             + chip("pass", n[_rst.INSPECTED], "#15803d")
             + chip("help", n[_rst.HELP], "#dc2626")
             + chip("dnd", n[_rst.DND], "#7c3aed"))
    return (f'<div class="gbar"><div class="gtop"><b>{T("prop.game_floor")}</b>'
            f'<span class="gstars">{stars}</span><span class="gpct">{pct}%</span>'
            f'<span class="gof">{done} / {len(on)}</span></div>'
            f'<div class="gtrack"><div class="gfill" style="width:{pct}%"></div></div>'
            f'<div class="gchips">{chips}</div></div>')


GAME_CSS = """
.gbar{background:#fff;border:1px solid #d6dfea;border-radius:14px;padding:10px 14px 8px;
  margin:4px 0 10px;box-shadow:0 2px 10px rgba(22,32,46,.05)}
.gtop{display:flex;align-items:center;gap:10px;font-size:.86rem;color:#1e3350}
.gstars{color:#f5a524;font-size:1.05rem;letter-spacing:2px}
.gpct{font-weight:800;font-size:1.05rem;color:#15803d;margin-left:auto}
.gof{color:#7b8798;font-size:.78rem;font-family:ui-monospace,Menlo,monospace}
.gtrack{height:10px;border-radius:999px;background:#e6ebf2;overflow:hidden;margin:7px 0 6px}
.gfill{height:100%;border-radius:999px;
  background:linear-gradient(90deg,#e89611 0%,#2f80ed 55%,#1a9e4b 100%);
  transition:width .6s ease}
.gchips{display:flex;flex-wrap:wrap;gap:4px 14px}
.gchip{display:inline-flex;align-items:center;gap:5px;font-size:.78rem;color:#42536a}
.gchip .av{flex:none}
.avcast{display:flex;flex-wrap:wrap;gap:6px 16px;margin:2px 0 8px}
.avcast span{display:inline-flex;align-items:center;gap:6px;font-size:.78rem;color:#42536a}
"""

HTML = """
<div id="wrap">
  <div id="hud">
    <div id="hint">drag to turn · two fingers or wheel to zoom · right-drag to pan</div>
    <div id="pick"></div>
  </div>
  <div id="labels"></div>
  <div id="btns">
    <button id="mapbtn" class="ponly" type="button">&#x1F5FA;</button>
    <button id="sndbtn" class="ponly" type="button">&#x1F507;</button>
    <button id="playbtn" type="button"></button>
    <button id="fsbtn" type="button">&#x26F6;</button>
  </div>
  <div id="phud"></div>
  <canvas id="mini" width="560" height="168"></canvas>
  <div id="goto"></div>
  <div id="near"></div>
  <div id="toast"></div>
  <div id="fade"></div>
  <div id="joy"><div id="knob"></div></div>
  <div id="actbtns"><button id="runbtn" type="button">&#x1F3C3;</button><button id="jumpbtn" type="button">&#x2912;</button></div>
  <div id="liftbtns"><button id="upbtn" type="button">&#9650;</button><button id="dnbtn" type="button">&#9660;</button></div>
  <canvas id="cv" tabindex="0"></canvas>
</div>
<style>
  html,body{margin:0;padding:0;overflow:hidden;background:transparent}
  #wrap{position:relative;width:100%;height:780px;border-radius:16px;
    overflow:hidden;background:linear-gradient(180deg,#eef3f9 0%,#dfe7f1 100%);
    border:1px solid #d6dfea;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
  #wrap:fullscreen{height:100vh;border-radius:0;border:0}
  #cv{display:block;width:100%;height:100%;touch-action:none;outline:none}
  #btns{position:absolute;right:12px;top:10px;z-index:5;display:flex;gap:6px}
  #btns button,#liftbtns button{font:700 .82rem -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    border:1px solid #cbd6e2;background:rgba(255,255,255,.94);color:#1e3350;border-radius:10px;
    padding:7px 12px;cursor:pointer;box-shadow:0 2px 8px rgba(22,32,46,.12)}
  #playbtn{background:#1a9e4b !important;color:#fff !important;border-color:#15803d !important}
  #wrap.playing #playbtn{background:#334155 !important;border-color:#1f2937 !important}
  #phud{position:absolute;right:12px;top:52px;z-index:4;display:none;min-width:190px;
    font-size:.78rem;color:#16202e;background:rgba(255,255,255,.94);padding:9px 12px;
    border-radius:11px;box-shadow:0 4px 16px rgba(22,32,46,.15);line-height:1.5}
  #phud b{font-size:.9rem}
  #phud .xp{color:#b45309;font-weight:800}
  #near{position:absolute;left:50%;bottom:18px;transform:translateX(-50%);z-index:4;display:none;
    font-size:.82rem;color:#16202e;background:rgba(255,255,255,.96);padding:8px 14px;
    border-radius:12px;box-shadow:0 4px 18px rgba(22,32,46,.2);white-space:nowrap;max-width:90%}
  #near span{color:#64748b}
  #toast{position:absolute;left:50%;top:38%;transform:translate(-50%,-50%);z-index:6;
    font-weight:800;font-size:1.05rem;color:#fff;background:#1a9e4b;padding:9px 18px;
    border-radius:999px;box-shadow:0 8px 24px rgba(22,32,46,.25);opacity:0;
    transition:opacity .25s, transform .25s;pointer-events:none}
  #toast.on{opacity:1;transform:translate(-50%,-62%)}
  #joy{position:absolute;left:22px;bottom:22px;width:118px;height:118px;border-radius:50%;
    background:rgba(255,255,255,.55);border:2px solid rgba(51,69,92,.25);z-index:5;display:none;
    touch-action:none}
  #knob{position:absolute;left:39px;top:39px;width:40px;height:40px;border-radius:50%;
    background:rgba(30,51,80,.75)}
  #liftbtns{position:absolute;right:16px;bottom:22px;z-index:5;display:none;flex-direction:column;gap:8px}
  #liftbtns button{font-size:1.1rem;padding:12px 16px}
  #wrap.playing #hint,#wrap.playing #labels{display:none}
  .ponly{display:none}
  #wrap.playing .ponly{display:inline-block}
  #mini{position:absolute;left:12px;top:10px;z-index:4;width:280px;height:84px;display:none;
    border-radius:10px;background:rgba(255,255,255,.9);box-shadow:0 4px 14px rgba(22,32,46,.15);
    cursor:crosshair}
  #goto{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);z-index:7;display:none;
    width:min(560px,92%);max-height:80%;overflow:auto;background:rgba(255,255,255,.97);
    border-radius:16px;padding:14px 16px;box-shadow:0 12px 40px rgba(22,32,46,.3);
    font-size:.82rem;color:#16202e}
  #goto h5{margin:10px 0 6px;font-size:.78rem;letter-spacing:.06em;text-transform:uppercase;color:#5b6b7e}
  #goto .row{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:4px 0}
  #goto .row b{width:84px;flex:none}
  #goto button{font:600 .8rem -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;border:1px solid #cbd6e2;
    background:#f4f7fa;color:#1e3350;border-radius:8px;padding:5px 10px;cursor:pointer}
  #goto button:hover{background:#e3ecf7}
  #goto button.here{background:#1e3350;color:#fff;border-color:#1e3350}
  #goto .x{float:right;border:0;background:none;font-size:1.1rem;padding:0 4px}
  #fade{position:absolute;inset:0;z-index:6;background:#fff;opacity:0;pointer-events:none;
    transition:opacity .22s}
  #fade.on{opacity:1}
  #actbtns{position:absolute;right:86px;bottom:22px;z-index:5;display:none;flex-direction:column;gap:8px}
  #actbtns button{font-size:1.1rem;padding:12px 15px;border:1px solid #cbd6e2;
    background:rgba(255,255,255,.94);border-radius:10px;box-shadow:0 2px 8px rgba(22,32,46,.12)}
  #actbtns button.on{background:#f5a524;border-color:#d48806}
  #hud{position:absolute;left:12px;top:10px;z-index:3;pointer-events:none}
  #hint{font-size:.68rem;letter-spacing:.03em;color:#64748b;background:rgba(255,255,255,.8);
    padding:4px 9px;border-radius:7px;display:inline-block}
  #pick{margin-top:7px;font-size:.8rem;color:#16202e;background:rgba(255,255,255,.94);
    padding:7px 11px;border-radius:9px;display:none;box-shadow:0 4px 16px rgba(22,32,46,.15)}
  #pick b{font-size:.95rem}
  #pick{pointer-events:auto}
  #walkhere{margin-top:7px;font:700 .78rem -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    border:0;background:#1a9e4b;color:#fff;border-radius:8px;padding:6px 11px;cursor:pointer}
  #pick span{color:#64748b}
  #labels{position:absolute;inset:0;z-index:2;pointer-events:none}
  .lv{position:absolute;transform:translate(-50%,-50%);font-size:.62rem;font-weight:700;
    letter-spacing:.08em;color:#5b6b7e;background:rgba(255,255,255,.78);
    padding:1px 6px;border-radius:5px;white-space:nowrap}
  .bl{position:absolute;transform:translate(-50%,-50%);font-size:.8rem;font-weight:800;
    letter-spacing:.06em;color:#33455c;background:rgba(255,255,255,.85);
    padding:3px 10px;border-radius:6px;white-space:nowrap}
</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const DATA = __PAYLOAD__;

const wrap = document.getElementById("wrap");
const cv = document.getElementById("cv");
const pick = document.getElementById("pick");
const labels = document.getElementById("labels");

const renderer = new THREE.WebGLRenderer({canvas:cv, antialias:true, alpha:true});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(42, 1, 1, 4000);

/* A hemisphere light does most of the work: warm from above, cool bounce from
   below, which is what stops a box model reading as flat coloured cardboard.
   The key light casts real shadows so the stack of levels has depth. */
scene.add(new THREE.HemisphereLight(0xfdfbf7, 0x9aa8bb, 0.78));
const key = new THREE.DirectionalLight(0xfff4e2, 0.78);
key.position.set(150, 260, 170);
key.castShadow = true;
key.shadow.mapSize.width = 2048;
key.shadow.mapSize.height = 2048;
scene.add(key);
const rim = new THREE.DirectionalLight(0xbcd2ee, 0.3);
rim.position.set(-180, 70, -140); scene.add(rim);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
scene.fog = new THREE.Fog(0xdfe7f1, 380, 1000);

/* centre the whole property on the origin so orbiting feels like turning a
   model on a table rather than swinging around one corner of it */
let minX=1e9,maxX=-1e9,minY=1e9,maxY=-1e9,minZ=1e9,maxZ=-1e9;
DATA.boxes.forEach(b=>{
  minX=Math.min(minX,b.x); maxX=Math.max(maxX,b.x);
  minY=Math.min(minY,b.y); maxY=Math.max(maxY,b.y);
  minZ=Math.min(minZ,b.z); maxZ=Math.max(maxZ,b.z);
});
/* the corridor centreline is the true middle in z, whatever the boxes do */
const cx=(minX+maxX)/2, cy=(minY+maxY)/2, cz=DATA.hallD*0.5;
const root = new THREE.Group();
root.position.set(-cx,-cy,-cz);
scene.add(root);

/* 0.74 of a door width, not 0.88: the tightest pair of doors on any plate is
   0.8 apart, and a box wider than that gap grows through its neighbour. */
const RW = DATA.doorW*0.74, RH = DATA.levelH*0.6, RD = DATA.hallD*0.42;
const HALF_HALL = DATA.hallD*0.30;   /* clear corridor down the middle */
const mats = {};
function mat(hex, op){
  const k = hex+"|"+op;
  if(!mats[k]) mats[k] = new THREE.MeshLambertMaterial({
    color:new THREE.Color(hex), transparent:op<1, opacity:op});
  return mats[k];
}

/* The room number is painted onto the top face of its own box. Held as a
   texture rather than an HTML overlay because 245 absolutely-positioned divs
   reprojected every frame is what makes a page like this crawl on a phone,
   and because a label stuck to the box cannot drift off it. */
const labelCache = {};
function labelMat(code, svc, hex, forceDark, square, top){
  const k = code+"|"+svc+"|"+hex+"|"+(forceDark||0)+"|"+(square||0)+"|"+(top||0);
  if(labelCache[k]) return labelCache[k];
  /* A side face is about as tall as it is wide; a lid is twice as wide as it
     is deep. Using one canvas shape for both stretched the text on whichever
     it was not drawn for. */
  const W = 512, H = square ? 512 : 256;
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const g = c.getContext("2d");
  g.fillStyle = hex; g.fillRect(0,0,W,H);
  const col = new THREE.Color(hex);
  const lum = 0.2126*srgb(col.r) + 0.7152*srgb(col.g) + 0.0722*srgb(col.b);
  g.fillStyle = (forceDark || lum > 0.34) ? "#15202e" : "#ffffff";
  g.textAlign = "center";
  const mono = /^[0-9]{4}[A-Z]?$/.test(code);
  if(top){
    /* An avatar and its name tag stand in front of the lower half of this
       face, so the number and service go on one line across the top, where
       nothing covers them. */
    const MONO = "ui-monospace,Menlo,Consolas,monospace";
    const SANS = "system-ui,-apple-system,'Segoe UI',sans-serif";
    let size = 118, cw = 0, sw = 0;
    do {
      g.font = "bold "+size+"px "+(mono ? MONO : SANS);
      cw = g.measureText(code).width;
      g.font = "bold "+Math.round(size*0.6)+"px "+SANS;
      sw = svc ? g.measureText("  "+svc).width : 0;
      if(cw + sw <= W-42) break;
      size -= 6;
    } while(size > 34);
    g.textAlign = "left";
    const x0 = (W - cw - sw)/2, base = H*0.27;
    g.font = "bold "+size+"px "+(mono ? MONO : SANS);
    g.fillText(code, x0, base);
    if(svc){
      g.globalAlpha = 0.72;
      g.font = "bold "+Math.round(size*0.6)+"px "+SANS;
      g.fillText("  "+svc, x0+cw, base);
      g.globalAlpha = 1;
    }
    const tt = new THREE.CanvasTexture(c);
    tt.anisotropy = 8;
    return (labelCache[k] = new THREE.MeshLambertMaterial({map:tt, transparent:true}));
  }
  /* shrink to fit rather than spill: "Housekeeping office" is not a room code */
  let size = mono ? 132 : 100;
  do {
    g.font = "bold "+size+"px " +
      (mono ? "ui-monospace,Menlo,Consolas,monospace"
            : "system-ui,-apple-system,'Segoe UI',sans-serif");
    if(g.measureText(code).width <= W-42) break;
    size -= 6;
  } while(size > 34);
  const mid = H/2;
  g.fillText(code, W/2, svc ? mid + size*0.16 : mid + size*0.36);
  if(svc){
    g.globalAlpha = 0.72;
    g.font = "bold "+Math.round(size*0.62)+"px system-ui,-apple-system,sans-serif";
    g.fillText(svc, W/2, mid + size*0.98);
    g.globalAlpha = 1;
  }
  const t = new THREE.CanvasTexture(c);
  t.anisotropy = 8;
  const m = new THREE.MeshLambertMaterial({map:t, transparent:true});
  labelCache[k] = m;
  return m;
}
function srgb(v){ return v <= 0.04045 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); }

/* ---- the people: one sprite per person, at the room they marked last,
   doing what that mark was (avatars.place_people). Each action is a strip of
   four frames, stepped by moving the texture's offset, so the whole team
   costs a handful of textures. Two materials per strip, half a cycle apart,
   so two people vacuuming do not sweep in lockstep. */
const AVK = DATA.av || {};
const AH = RH*0.52, AW = AH*0.75;     /* the strip's frames are 96 x 128 */
/* walking the corridor, the people stand at the player's own scale: the
   figure fills 78% of its frame, and the player is 1.9 tall */
const AH_PLAY = 2.45;
const TAG_H = 0.36;
const CORR_Z = DATA.hallD*0.5;
let playing = false;
const avMats = {}, avList = [];
/* True size beside a room is a speck from across the property, so each
   avatar and tag is held to a smallest size on screen; close up they shrink
   back to standing in front of the lower half of the face. */
const AV_MIN_PX = 34, TAG_MIN_PX = 15;
function avMat(key, phase){
  if(!avMats[key]){
    const c = document.createElement("canvas");
    c.width = 1024; c.height = 256;      /* power of two; the sprite's scale undoes the stretch */
    const pair = [0,1].map(()=>{
      const t = new THREE.CanvasTexture(c);
      t.repeat.set(0.25, 1);
      t.minFilter = THREE.LinearFilter; t.generateMipmaps = false;
      return new THREE.SpriteMaterial({map:t, transparent:true, alphaTest:0.06});
    });
    const img = new Image();
    img.onload = ()=>{
      c.getContext("2d").drawImage(img, 0, 0, 1024, 256);
      pair.forEach(m=>{ m.map.needsUpdate = true; });
    };
    img.src = AVK[key];
    avMats[key] = pair;
  }
  return avMats[key][phase];
}
const tagCache = {};
function tagMat(text, hex){
  const k = text+"|"+hex;
  if(tagCache[k]) return tagCache[k];
  const c = document.createElement("canvas");
  const font = "700 40px system-ui,-apple-system,'Segoe UI',sans-serif";
  let g = c.getContext("2d"); g.font = font;
  c.width = Math.ceil(g.measureText(text).width) + 46; c.height = 64;
  g = c.getContext("2d"); g.font = font;           /* resizing resets the context */
  const w = c.width-6, h = 54, x = 3, y = 5, r = 27;
  g.beginPath();
  g.moveTo(x+r, y); g.lineTo(x+w-r, y); g.arc(x+w-r, y+r, r, -Math.PI/2, Math.PI/2);
  g.lineTo(x+r, y+h); g.arc(x+r, y+r, r, Math.PI/2, Math.PI*1.5); g.closePath();
  g.fillStyle = hex; g.fill();
  g.lineWidth = 4; g.strokeStyle = "rgba(255,255,255,.95)"; g.stroke();
  const col = new THREE.Color(hex);
  const lum = 0.2126*srgb(col.r) + 0.7152*srgb(col.g) + 0.0722*srgb(col.b);
  g.fillStyle = lum > 0.34 ? "#15202e" : "#ffffff";
  g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(text, c.width/2, 33);
  const t = new THREE.CanvasTexture(c);
  t.minFilter = THREE.LinearFilter; t.generateMipmaps = false;
  return (tagCache[k] = {m:new THREE.SpriteMaterial({map:t, transparent:true, depthWrite:false}),
                         aspect:c.width/c.height});
}
/* Two places for each person: just out from the room's labelled face, where
   the model is looked at from outside, and in the corridor beside the door,
   where somebody walking the floor would meet them. Feet on the floor of
   the level either way; the name floats over the head. */
function addPerson(p, b){
  const g = b._av;
  if(!g) return;
  const feet = b.y - RH*0.64 + DATA.levelH*0.05;          /* the slab's top */
  const off = (p.slot - (p.n - 1)/2) * AW * 1.05;          /* side by side */
  const s = new THREE.Sprite(avMat(p.key, avList.length % 2));
  s.userData = {person:true, p, b};
  root.add(s); meshes.push(s);
  const one = {s, feet, p, b, tag:null, aspect:1, ph:Math.random()*6.28,
               out:{x:g.ox + g.ax*off, z:g.oz + g.az*off},
               door:{x:g.dx + g.ax*(RW*0.42 + off*1.6), z:g.dz + g.az*(RW*0.42 + off*1.6)}};
  if(p.who){
    const tm = tagMat(p.who, p.col);
    const tg = new THREE.Sprite(tm.m);
    tg.renderOrder = 2;
    root.add(tg);
    one.tag = tg; one.aspect = tm.aspect;
  }
  avList.push(one);
}
const _wp = new THREE.Vector3();
function sizeAvatars(now){
  /* world units per screen pixel at distance 1 */
  const k = 2*Math.tan(camera.fov*Math.PI/360) / Math.max(wrap.clientHeight, 1);
  const base = playing ? AH_PLAY : AH;
  for(const a of avList){
    const at = playing ? a.door : a.out;
    a.s.position.x = at.x; a.s.position.z = at.z;
    _wp.copy(a.s.position).add(root.position);
    const dist = camera.position.distanceTo(_wp);
    const h = Math.max(base, AV_MIN_PX*k*dist);
    a.s.scale.set(h*0.75, h, 1);
    a.s.position.y = a.feet + h*0.5;
    if(a.tag){
      const th = Math.max(TAG_H, TAG_MIN_PX*k*dist);
      a.tag.scale.set(th*a.aspect, th, 1);
      /* the figure's head is a fifth of the way down its frame */
      a.tag.position.set(at.x, a.feet + h*0.86 + th*(0.55 + 0.12*Math.sin(now*0.0025 + a.ph)),
                         at.z);
    }
  }
}

const meshes = [];
DATA.boxes.forEach(b=>{
  const d = RD * b.depth;
  let geo, z, wingW = 0;
  if(b.wing){
    /* an end wing sits across the corridor line; its row is what separates it
       from its neighbours, so it keeps that and shows its size along x -- and
       only gently, or it reaches the main row beside it */
    wingW = RW*(0.85 + 0.3*(b.depth-0.62)/0.84);
    geo = new THREE.BoxGeometry(wingW, RH, RD*0.92);
    z = b.row * DATA.hallD;
  } else {
    /* grow away from the corridor, never across it */
    geo = new THREE.BoxGeometry(RW, RH, d);
    z = DATA.hallD*0.5 + b.side * (HALF_HALL + d*0.5);
  }
  const plain = mat(b.colour, b.on_chart ? 0.96 : 0.55);
  const face = labelMat(b.code, b.svc_short, b.colour, 0, 1, b.av ? 1 : 0);
  /* where a person stands at this room: (ox,oz) outside its labelled face,
     (dx,dz) in the corridor at its door, (ax,az) the way along the face */
  const out = 0.55;
  if(b.wing){
    const dir = (b.x > (minX + maxX)/2) ? 1 : -1;
    b._av = {ox:b.x + dir*(wingW*0.5 + out), oz:z,
             dx:b.x - dir*(wingW*0.5 + 0.9),
             dz:Math.max(CORR_Z - HALF_HALL*0.7, Math.min(CORR_Z + HALF_HALL*0.7, z)),
             ax:0, az:1};
  } else {
    b._av = {ox:b.x, oz:z + b.side*(d*0.5 + out),
             dx:b.x, dz:CORR_Z + b.side*(HALF_HALL - 0.75), ax:1, az:0};
  }
  /* The number goes on the OUTWARD-FACING SIDE, not the lid. A lid is hidden
     the moment another level sits above it, which is every level but the top
     one -- the labels were invisible on all six floors that matter. The side
     a room faces is the side it is on: north rooms show on -Z, south rooms on
     +Z, and an end wing shows on whichever end of the building it sits at.
     And on the door side too: walking the corridor in play, the doors are
     what you see. BoxGeometry material order is +X -X +Y -Y +Z -Z. */
  let mats6;
  if(b.wing){
    mats6 = [face,face,plain,plain,plain,plain];
  } else {
    mats6 = [plain,plain,plain,plain,face,face];
  }
  const m = new THREE.Mesh(geo, mats6);
  m.position.set(b.x, b.y, z);
  m.castShadow = true; m.receiveShadow = true;
  m.userData = b;
  b._z = z;
  root.add(m); meshes.push(m);
  const e = new THREE.LineSegments(new THREE.EdgesGeometry(geo),
    new THREE.LineBasicMaterial({color:0x2b3a4a, transparent:true, opacity:0.2}));
  e.position.copy(m.position); root.add(e);
});
const BOX = {};
DATA.boxes.forEach(b=>{ BOX[b.code] = b; });
(DATA.people||[]).forEach(p=>{ if(BOX[p.code]) addPerson(p, BOX[p.code]); });

/* ---- everything that is not a guest room ---------------------------------
   Distinct colour and silhouette per kind, because on a model this size a
   legend colour alone is not enough to pick a linen room out of a corridor. */
const FAC = {
  lift_svc:   {c:"#334759", h:1.00, d:0.85, label:1},
  lift_guest: {c:"#5a6f85", h:1.00, d:0.80, label:1},
  trash:      {c:"#7a6a55", h:0.72, d:0.55, label:0},
  laundry:    {c:"#b06fb0", h:0.72, d:0.80, label:1},
  closet:     {c:"#2f8f86", h:0.66, d:0.72, label:1},
  office:     {c:"#c2452f", h:0.80, d:0.85, label:1},
  breakroom:  {c:"#c98a2e", h:0.72, d:0.90, label:1},
  lockers:    {c:"#a8862f", h:0.62, d:0.75, label:0},
  stairs:     {c:"#8895a5", h:0.56, d:0.60, label:0},
  amenity:    {c:"#9fb4c9", h:0.34, d:1.30, label:1}
};
(DATA.facils||[]).forEach(f=>{
  const spec = FAC[f.kind] || FAC.closet;
  const w = DATA.doorW * f.width * 0.9;
  const h = RH * spec.h;
  const d = RD * spec.d;
  const geo = new THREE.BoxGeometry(w, h, d);
  const isAmenity = f.kind === "amenity";
  const plain = mat(spec.c, isAmenity ? 0.42 : 0.95);
  let mats6 = plain;
  if(spec.label && w > DATA.doorW*0.7){
    /* both long sides, so a service point reads from whichever side of the
       building you have turned towards -- these sit in the middle of the
       plate, not on an outward edge like a room */
    const face = labelMat(f.label, "", spec.c, isAmenity ? 1 : 0, 1);
    mats6 = [plain,plain,plain,plain,face,face];
  }
  const m = new THREE.Mesh(geo, mats6);
  /* Anything past the south row -- the service lift, the chute, the refill
     closets -- has to clear the deepest room a level can hold, not sit at its
     raw row. A 140 reaches further out than the plan's row for the lift, so
     drawing it there put the lift inside fifteen rooms. Beyond that edge the
     rows keep their relative spacing so the core still reads in plan order. */
  const southEdge = DATA.hallD*0.5 + HALF_HALL + RD*1.46 + RD*0.12;
  const fz = f.row > 1.2
    ? southEdge + d*0.5 + (f.row - 1.3) * DATA.hallD * 0.5
    : f.z;
  m.position.set(f.x, f.y - RH*0.5 + h*0.5, fz);
  m.castShadow = !isAmenity; m.receiveShadow = true;
  m.userData = {facility:true, label:f.label, kind:f.kind,
                bld:f.bld, level:f.level};
  root.add(m); meshes.push(m);
});

/* ---- the service lift shafts, drawn as the one line they really are ---- */
(DATA.cores||[]).forEach(c=>{
  const h = (c.y1 - c.y0) + RH*1.6;
  const geo = new THREE.BoxGeometry(DATA.doorW*0.85, h, RD*0.8);
  const m = new THREE.Mesh(geo, mat("#22303f", 0.20));
  /* the shaft has to stand exactly where its lifts do, so it is placed by the
     same rule rather than by the raw row, or it floats off the cars */
  const southEdge = DATA.hallD*0.5 + HALF_HALL + RD*1.46 + RD*0.12;
  const cz = southEdge + RD*0.85*0.5 + (1.55 - 1.3) * DATA.hallD * 0.5;
  m.position.set(c.x, (c.y0+c.y1)/2, cz);
  root.add(m);
  const e = new THREE.LineSegments(new THREE.EdgesGeometry(geo),
    new THREE.LineBasicMaterial({color:0x22303f, transparent:true, opacity:0.35}));
  e.position.copy(m.position); root.add(e);
});

/* the floor slab under each level of each building, so the stack reads as a
   building rather than as floating boxes */
const byPlate = {};
DATA.boxes.forEach(b=>{
  const k = b.bld+"|"+b.level;
  const p = byPlate[k] || (byPlate[k] = {x0:1e9,x1:-1e9,y:b.y,bld:b.bld,level:b.level});
  p.x0=Math.min(p.x0,b.x); p.x1=Math.max(p.x1,b.x);
});
Object.values(byPlate).forEach(p=>{
  const w = (p.x1-p.x0)+RW*2.6;
  const depth = (HALF_HALL + RD*1.5) * 2;
  const slab = new THREE.Mesh(new THREE.BoxGeometry(w, DATA.levelH*0.10, depth),
    mat("#c8d3df", 0.82));
  slab.position.set((p.x0+p.x1)/2, p.y-RH*0.64, DATA.hallD*0.5);
  slab.receiveShadow = true; slab.castShadow = true;
  root.add(slab);
});

/* the ground the three buildings stand on -- a model floating in space is
   what makes one look like a diagram instead of a building */
const site = new THREE.Mesh(
  new THREE.BoxGeometry((maxX-minX)+DATA.doorW*22, DATA.levelH*0.5,
                        DATA.hallD*4.4),
  mat("#aab8c6", 0.9));
site.position.set((minX+maxX)/2, minY-RH*1.4, DATA.hallD*0.5);
site.receiveShadow = true;
root.add(site);

/* bridges: the point of the whole drawing */
DATA.spans.forEach(s=>{
  const w = Math.abs(s.x1-s.x0);
  const br = new THREE.Mesh(new THREE.BoxGeometry(w, DATA.levelH*0.16, RD*0.9),
    mat("#12764a", 0.92));
  br.position.set((s.x0+s.x1)/2, s.y-RH*0.5, s.z);
  br.castShadow = true; br.receiveShadow = true;
  br.userData = {bridge:true, level:s.level, a:s.a, b:s.b};
  root.add(br); meshes.push(br);
});

/* the shadow camera has to be told how big the property is, or it either
   misses most of it or wastes its whole map on empty ground */
{
  const spanX = (maxX-minX), spanY = (maxY-minY);
  const r = Math.max(spanX, spanY) * 0.75 + 40;
  const sc = key.shadow.camera;
  sc.left = -r; sc.right = r; sc.top = r; sc.bottom = -r;
  sc.near = 1; sc.far = r*6;
  sc.updateProjectionMatrix();
  key.shadow.bias = -0.0016;
}

/* ---- orbit: drag to turn, wheel or pinch to zoom, right-drag to pan ---- */
let yaw=-0.62, pitch=0.42, dist=Math.max(maxX-minX,80)*0.92, panX=0, panY=0;
function place(){
  if(playing) return;               /* the follow camera owns it in play */
  const cp=Math.cos(pitch), sp=Math.sin(pitch);
  camera.position.set(Math.sin(yaw)*cp*dist + panX, sp*dist + panY, Math.cos(yaw)*cp*dist);
  camera.lookAt(panX, panY, 0);
}
let drag=null, lastTouchDist=0;
function pos(e){ const r=cv.getBoundingClientRect(); return {x:e.clientX-r.left, y:e.clientY-r.top}; }
cv.addEventListener("pointerdown", e=>{
  cv.setPointerCapture(e.pointerId);
  drag={x:e.clientX, y:e.clientY, pan:(e.button===2||e.shiftKey)};
});
cv.addEventListener("pointermove", e=>{
  if(!drag) return;
  const dx=e.clientX-drag.x, dy=e.clientY-drag.y;
  drag.x=e.clientX; drag.y=e.clientY;
  if(playing){
    pcYaw -= dx*0.008;
    pcPitch = Math.max(-0.15, Math.min(1.3, pcPitch + dy*0.005));
    return;
  }
  if(drag.pan){ panX-=dx*dist*0.0016; panY+=dy*dist*0.0016; }
  else { yaw-=dx*0.007; pitch=Math.max(-0.25, Math.min(1.45, pitch+dy*0.006)); }
  place();
});
cv.addEventListener("pointerup", e=>{ drag=null; });
cv.addEventListener("pointercancel", ()=>{ drag=null; });
cv.addEventListener("contextmenu", e=>e.preventDefault());
cv.addEventListener("wheel", e=>{
  e.preventDefault();
  if(playing){
    pcDist = Math.max(2.5, Math.min(90, pcDist * (1 + Math.sign(e.deltaY)*0.1)));
    return;
  }
  dist = Math.max(28, Math.min(900, dist * (1 + Math.sign(e.deltaY)*0.09)));
  place();
}, {passive:false});
cv.addEventListener("touchmove", e=>{
  if(e.touches.length===2){
    e.preventDefault();
    const a=e.touches[0], b=e.touches[1];
    const d=Math.hypot(a.clientX-b.clientX, a.clientY-b.clientY);
    if(lastTouchDist){
      if(playing) pcDist=Math.max(2.5, Math.min(90, pcDist*(lastTouchDist/d)));
      else dist=Math.max(28, Math.min(900, dist*(lastTouchDist/d)));
    }
    lastTouchDist=d; place();
  }
}, {passive:false});
cv.addEventListener("touchend", ()=>{ lastTouchDist=0; });

/* ---- tap a room to read it ---- */
function esc(s){ return String(s).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
/* "Ana Lopez · Cleaning · since 11:49" */
function personLine(p){
  return "<b>"+esc(p.name)+"</b> <span>&middot; "+esc((DATA.acts||{})[p.act]||p.act)+
    (p.at ? " &middot; "+esc((DATA.txt||{}).since||"since")+" "+p.at : "")+"</span>";
}
const ray = new THREE.Raycaster();
cv.addEventListener("click", e=>{
  if(playing) return;      /* in play, a drag is looking round, not a tap */
  const r=cv.getBoundingClientRect();
  const v=new THREE.Vector2(((e.clientX-r.left)/r.width)*2-1,
                            -((e.clientY-r.top)/r.height)*2+1);
  ray.setFromCamera(v, camera);
  const hit = ray.intersectObjects(meshes)[0];
  if(!hit){ pick.style.display="none"; return; }
  const d = hit.object.userData;
  pick.style.display="block";
  if(d.person){
    pick.innerHTML = personLine(d.p) + "<br><span>"+d.b.code+" &middot; building "+d.b.bld+
      " &middot; "+(isNaN(d.b.level)?d.b.level:"level "+d.b.level)+"</span>";
  } else if(d.bridge){
    pick.innerHTML = "<b>Bridge</b> <span>building "+d.a+" &harr; "+d.b+
      " &middot; "+(isNaN(d.level)?d.level:"level "+d.level)+"</span>";
  } else if(d.facility){
    pick.innerHTML = "<b>"+d.label+"</b> <span>building "+d.bld+" &middot; "+
      (isNaN(d.level)?d.level:"level "+d.level)+"</span>";
  } else {
    const where = "building "+d.bld+" &middot; "+
      (isNaN(d.level)?d.level:"level "+d.level);
    let line2 = "";
    if(d.on_chart){
      line2 = "<br><span>"+(d.svc||"")+(d.mins?" &middot; "+d.mins+" min":"")+
              (d.hk?" &middot; "+d.hk:"")+
              (d.rqs?" &middot; RQS "+d.rqs:"")+"</span>";
      if(d.status) line2 += "<br><span>"+d.status.replace(/_/g," ")+"</span>";
      (DATA.people||[]).filter(p=>p.code===d.code)
        .forEach(p=>{ line2 += "<br>"+personLine(p); });
    } else {
      line2 = "<br><span>not on a chart today</span>";
    }
    pick.innerHTML = "<b>"+d.code+"</b> <span>"+where+"</span>"+line2+
      "<br><button id='walkhere' type='button'>"+esc((DATA.txt||{}).walk||"▶ Walk here")+"</button>";
    document.getElementById("walkhere").onclick = ()=>{ pick.style.display = "none"; walkHere(d.code); };
  }
});

/* ================================================================== play ===
   Walk the property as yourself (Hari, 19 Nov). What you can walk is what a
   housekeeper walks: the corridor of every plate, the bridges between
   buildings, and the lifts and stairs between levels -- so buildings 2 and 3
   are as far apart here as they are on a cart. Rooms that need somebody
   glow: red for help, blue for ready for the RQS. Reach one and it counts.
   Nothing here writes anything; the score lives in this browser for the day. */
const TX = DATA.txt || {};
const PL = DATA.player || {look:"n", role:"rqs", name:""};
const LV_Y = {};
DATA.boxes.forEach(b=>{ LV_Y[b.level] = b.y; });
(DATA.facils||[]).forEach(f=>{ if(!(f.level in LV_Y)) LV_Y[f.level] = f.y; });
DATA.spans.forEach(s=>{ if(!(s.level in LV_Y)) LV_Y[s.level] = s.y; });
const FLOOR = lv => LV_Y[lv] - RH*0.64 + DATA.levelH*0.05;   /* slab top */
const DECK  = lv => LV_Y[lv] - RH*0.5 + DATA.levelH*0.08;    /* bridge top */
const CORR_HALF = HALF_HALL*0.85;

/* the walkable floor: a corridor strip per plate, and one per bridge */
const plates = {}, bldMid = {};
function grow(bld, lv, x0, x1){
  const k = bld+"|"+lv;
  const p = plates[k] || (plates[k] = {bld:+bld, lv, x0:1e9, x1:-1e9});
  p.x0 = Math.min(p.x0, x0); p.x1 = Math.max(p.x1, x1);
}
DATA.boxes.forEach(b=>{
  grow(b.bld, b.level, b.x - RW*0.6, b.x + RW*0.6);
  const m = bldMid[b.bld] || (bldMid[b.bld] = {s:0, n:0}); m.s += b.x; m.n++;
});
(DATA.facils||[]).forEach(f=>{
  if(f.kind === "amenity") return;   /* lobby volumes reach well past the corridor */
  const w = DATA.doorW*f.width*0.45;
  grow(f.bld, f.level, f.x - w, f.x + w);
});
/* a bridge lands on the corridor of the building at each end, even on a
   level with no guest rooms -- building 1's level 1 is the crossroads */
DATA.spans.forEach(s=>{
  const lo = Math.min(s.x0, s.x1), hi = Math.max(s.x0, s.x1);
  [s.a, s.b].forEach(bld=>{
    const m = bldMid[bld]; if(!m) return;
    const c = m.s/m.n, end = Math.abs(c - lo) < Math.abs(c - hi) ? lo : hi;
    grow(bld, s.level, end, end);
  });
});
const walk = {};
Object.values(plates).forEach(p=>{
  (walk[p.lv] || (walk[p.lv] = [])).push({x0:p.x0 - 1.2, x1:p.x1 + 1.2,
    z0:CORR_Z - CORR_HALF, z1:CORR_Z + CORR_HALF, bld:p.bld, lv:p.lv});
});
DATA.spans.forEach(s=>{
  (walk[s.level] || (walk[s.level] = [])).push({x0:Math.min(s.x0,s.x1) - 0.5,
    x1:Math.max(s.x0,s.x1) + 0.5, z0:s.z - RD*0.38, z1:s.z + RD*0.38,
    bld:0, bridge:true, a:s.a, b:s.b, lv:s.level});
});
/* the strip you are standing in -- a building's before a bridge's */
function where(lv, x, z){
  let hit = null;
  for(const r of (walk[lv]||[]))
    if(x >= r.x0 && x <= r.x1 && z >= r.z0 && z <= r.z1 && (!hit || hit.bridge)) hit = r;
  return hit;
}

const lifts = (DATA.facils||[]).filter(f=>f.kind==="lift_svc"||f.kind==="lift_guest"||f.kind==="stairs");
const playGroup = new THREE.Group();
playGroup.visible = false;
root.add(playGroup);

/* ---- you: a low-poly person in your own look, built from primitives ---- */
function buildPlayer(look, role){
  const M = c=>new THREE.MeshLambertMaterial({color:c});
  const uni = M(role==="rqs" ? 0x1e3a8a : 0x0f766e), uniD = M(role==="rqs" ? 0x172c66 : 0x0b5a54);
  const skin = M(0xd6a07a), hair = M(0x2a211d), pants = M(0x334155), shoe = M(0x1f2937),
        apron = M(0xf8fafc), ink = M(0x1f2937), tights = M(0x3b3b45);
  const g = new THREE.Group();
  const part = (geo, m, x, y, z, parent)=>{ const o = new THREE.Mesh(geo, m);
    o.position.set(x, y, z); o.castShadow = true; (parent||g).add(o); return o; };
  const limb = (r0, r1, len, m)=>{ const geo = new THREE.CylinderGeometry(r0, r1, len, 10);
    geo.translate(0, -len/2, 0); return geo; };
  /* legs swing from the hip, arms from the shoulder */
  const legs = [-0.11, 0.11].map(x=>{
    const pivot = new THREE.Group(); pivot.position.set(x, 0.86, 0); g.add(pivot);
    part(limb(0.075, 0.068, 0.78), look==="f" ? tights : pants, 0, 0, 0, pivot);
    part(new THREE.BoxGeometry(0.14, 0.08, 0.26), shoe, 0, -0.8, 0.05, pivot);
    return pivot;
  });
  part(new THREE.CylinderGeometry(0.2, 0.23, 0.62, 16), uni, 0, 1.18, 0);
  if(look === "f") part(new THREE.CylinderGeometry(0.22, 0.36, 0.46, 18), uni, 0, 0.8, 0);
  else part(new THREE.CylinderGeometry(0.23, 0.21, 0.18, 16), pants, 0, 0.9, 0);
  if(role === "hk") part(new THREE.BoxGeometry(0.26, 0.5, 0.03), apron, 0, look==="f" ? 0.98 : 1.05,
                         look==="f" ? 0.27 : 0.225);
  else part(new THREE.BoxGeometry(0.08, 0.11, 0.02), apron, 0.1, 1.28, 0.22);
  const arms = [-0.29, 0.29].map(x=>{
    const pivot = new THREE.Group(); pivot.position.set(x, 1.44, 0); g.add(pivot);
    pivot.rotation.z = x < 0 ? -0.1 : 0.1;
    part(limb(0.062, 0.056, 0.6), uni, 0, 0, 0, pivot);
    part(new THREE.SphereGeometry(0.068, 10, 8), skin, 0, -0.63, 0, pivot);
    return pivot;
  });
  part(new THREE.CylinderGeometry(0.07, 0.08, 0.12, 10), skin, 0, 1.52, 0);
  part(new THREE.SphereGeometry(0.21, 20, 16), skin, 0, 1.7, 0);
  [-0.075, 0.075].forEach(x=>part(new THREE.SphereGeometry(0.026, 8, 6), ink, x, 1.72, 0.193));
  const cap = (frac, m, tilt)=>{
    const o = part(new THREE.SphereGeometry(0.222, 20, 14, 0, Math.PI*2, 0, Math.PI*frac), m, 0, 1.7, 0);
    o.rotation.x = tilt; return o; };
  if(look === "f"){
    cap(0.5, hair, -0.35);
    part(new THREE.CylinderGeometry(0.2, 0.24, 0.42, 16, 1, true, Math.PI*0.6, Math.PI*0.8), hair, 0, 1.55, 0)
      .material.side = THREE.DoubleSide;
    part(new THREE.SphereGeometry(0.09, 12, 10), hair, 0, 1.86, -0.17);
  } else if(look === "m"){
    cap(0.38, hair, -0.3);
  } else {
    cap(0.45, uniD, -0.1);
    part(new THREE.BoxGeometry(0.3, 0.025, 0.18), uniD, 0, 1.79, 0.2);
  }
  return {g, legs, arms};
}

const P = {lv:null, x:0, z:CORR_Z, ground:0, air:0, vy:0, jumps:0, feet:0,
           head:Math.PI/2, phase:0, speed:0, xp:0, visited:new Set(), found:new Set(),
           walked:0, help:true};
let me = null, meTag = null, lamp = null, ride = null, built = false;
let runOn = false, muted = true;
let pcYaw = -Math.PI/2, pcPitch = 0.2, pcDist = 7;
const quests = [], hunt = [], bursts = [];
const decor = {snow:null, gondola:[], steam:[], fires:[]};
/* jump physics, in model units: a jump clears about 1.5, two about 2.6,
   and nobody goes through the ceiling of their own corridor */
const GRAV = 26, JUMP_V = 8.8, CEIL = 3.7, HEIGHT = 1.95;
const WALK_V = 5.5, RUN_V = 13, BACK_V = 3.2;

/* ---- the day's score, kept in this browser only ---- */
const SAVE_KEY = "bgv_play_" + (DATA.day || "");
function save(){
  try{
    localStorage.setItem(SAVE_KEY, JSON.stringify({xp:P.xp, visited:[...P.visited],
      found:[...P.found], lv:P.lv, x:P.x, z:P.z, head:P.head, yaw:pcYaw, playing}));
    localStorage.setItem("bgv_play_sound", muted ? "0" : "1");
  }catch(e){}
}
let saved = null;
try{ saved = JSON.parse(localStorage.getItem(SAVE_KEY) || "null"); }catch(e){ saved = null; }
if(saved){
  P.xp = saved.xp || 0;
  (saved.visited || []).forEach(c=>P.visited.add(c));
  (saved.found || []).forEach(c=>P.found.add(c));
}
try{ muted = localStorage.getItem("bgv_play_sound") !== "1"; }catch(e){}

const OFFICE = (DATA.facils||[]).find(f=>f.kind==="office" && /housekeeping/i.test(f.label||""))
            || (DATA.facils||[]).find(f=>f.kind==="office");
function spawn(){
  if(saved && saved.lv && where(saved.lv, saved.x, saved.z)){
    P.lv = saved.lv; P.x = saved.x; P.z = saved.z; P.head = saved.head || P.head;
    pcYaw = saved.yaw != null ? saved.yaw : pcYaw;
  } else if(OFFICE && where(OFFICE.level, OFFICE.x, CORR_Z)){
    /* the day starts at the housekeeping office */
    P.lv = OFFICE.level; P.x = OFFICE.x; P.z = CORR_Z;
  } else {
    const p = Object.values(plates)[0]; P.lv = p.lv; P.x = (p.x0 + p.x1)/2; P.z = CORR_Z;
  }
  P.ground = P.feet = groundAt(P.lv, P.x, P.z);
}
function groundAt(lv, x, z){
  const r = where(lv, x, z);
  return r && r.bridge ? DECK(lv) : FLOOR(lv);
}

/* ---- a seeded die: the same hunt for everybody, a new one every day ---- */
function rng(seed){
  return ()=>{
    seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function hashStr(s){
  let h = 2166136261;
  for(let i = 0; i < s.length; i++){ h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
const M = c=>new THREE.MeshLambertMaterial({color:c});

/* ---- the hunt: eggs, bunnies, one golden bunny, and Pico ---------------- */
const EGG_COLS = ["#fbcfe8", "#bfdbfe", "#bbf7d0", "#fde68a", "#ddd6fe"];
const EGG_INK = ["#db2777", "#2563eb", "#16a34a", "#d97706", "#7c3aed"];
const eggMats = [];
function eggMat(i){
  i = i % EGG_COLS.length;
  if(eggMats[i]) return eggMats[i];
  const c = document.createElement("canvas"); c.width = 128; c.height = 64;
  const g = c.getContext("2d");
  g.fillStyle = EGG_COLS[i]; g.fillRect(0, 0, 128, 64);
  g.strokeStyle = EGG_INK[i]; g.lineWidth = 5; g.beginPath();
  for(let x = 0; x <= 128; x += 16) g.lineTo(x, x % 32 ? 26 : 38);
  g.stroke();
  g.fillStyle = "#ffffff";
  for(let x = 8; x < 128; x += 21){ g.beginPath(); g.arc(x, 12, 3.5, 0, 7); g.fill();
                                     g.beginPath(); g.arc(x + 10, 52, 3.5, 0, 7); g.fill(); }
  return (eggMats[i] = new THREE.MeshLambertMaterial({map:new THREE.CanvasTexture(c)}));
}
function makeEgg(i){
  const m = new THREE.Mesh(new THREE.SphereGeometry(0.22, 18, 14), eggMat(i));
  m.scale.set(1, 1.3, 1); m.castShadow = true;
  const g = new THREE.Group(); m.position.y = 0.3; g.add(m);
  return g;
}
const BUNNY_COLS = [0xf8fafc, 0xe7d8c4, 0xb8a593, 0xd1d5db, 0xf3e8d2];
function makeBunny(i, golden){
  const g = new THREE.Group();
  const fur = golden ? new THREE.MeshLambertMaterial({color:0xf5c542, emissive:0x7a5600})
                     : M(BUNNY_COLS[i % BUNNY_COLS.length]);
  const pink = M(0xff9fb5), ink = M(0x1f2937), white = M(0xffffff);
  const add = (geo, m, x, y, z)=>{ const o = new THREE.Mesh(geo, m); o.position.set(x, y, z);
                                   o.castShadow = true; g.add(o); return o; };
  add(new THREE.SphereGeometry(0.26, 16, 12), fur, 0, 0.26, 0).scale.set(1, 0.9, 1.15);
  add(new THREE.SphereGeometry(0.17, 16, 12), fur, 0, 0.52, 0.2);
  [-1, 1].forEach(s=>{
    const ear = add(new THREE.CylinderGeometry(0.045, 0.06, 0.36, 10), fur, s*0.075, 0.78, 0.15);
    ear.rotation.z = -s*0.18;
    const inner = add(new THREE.BoxGeometry(0.04, 0.26, 0.01), pink, s*0.08, 0.78, 0.2);
    inner.rotation.z = -s*0.18;
    add(new THREE.SphereGeometry(0.025, 8, 6), ink, s*0.07, 0.56, 0.35);
  });
  add(new THREE.SphereGeometry(0.03, 8, 6), pink, 0, 0.5, 0.37);
  add(new THREE.SphereGeometry(0.08, 10, 8), white, 0, 0.28, -0.3);
  return g;
}
/* Pico, the peak who waves on My Home, in three dimensions */
function makePico(){
  const g = new THREE.Group();
  const peak = new THREE.Mesh(new THREE.ConeGeometry(0.55, 1.1, 6),
    new THREE.MeshPhongMaterial({color:0x2f6fc4, flatShading:true, shininess:0}));
  peak.position.y = 0.55; peak.castShadow = true; g.add(peak);
  const cap = new THREE.Mesh(new THREE.ConeGeometry(0.21, 0.42, 6),
    new THREE.MeshPhongMaterial({color:0xffffff, flatShading:true, shininess:0}));
  cap.position.y = 0.55 + 0.55 - 0.21 + 0.005; g.add(cap);
  [-1, 1].forEach(s=>{
    const eye = new THREE.Mesh(new THREE.SphereGeometry(0.075, 12, 10), M(0xffffff));
    eye.position.set(s*0.13, 0.5, 0.29); g.add(eye);
    const pup = new THREE.Mesh(new THREE.SphereGeometry(0.04, 10, 8), M(0x001b3e));
    pup.position.set(s*0.13, 0.5, 0.36); g.add(pup);
    const ck = new THREE.Mesh(new THREE.SphereGeometry(0.05, 10, 8), M(0xff8fa8));
    ck.position.set(s*0.23, 0.38, 0.27); ck.scale.z = 0.4; g.add(ck);
  });
  const arm = new THREE.Group(); arm.position.set(0.32, 0.45, 0.05); g.add(arm);
  const a = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 0.42, 8), M(0x1f4f96));
  a.geometry.translate(0, 0.21, 0); arm.add(a);
  arm.rotation.z = -0.9;
  g.userData.arm = arm;
  const spark = new THREE.Mesh(new THREE.OctahedronGeometry(0.09), new THREE.MeshBasicMaterial({color:0xffb300}));
  spark.position.set(0.0, 1.32, 0); g.add(spark);
  return g;
}
/* a glass shelf under anything that floats, so "jump for it" reads at a glance */
function shelf(){
  const m = new THREE.Mesh(new THREE.CylinderGeometry(0.45, 0.45, 0.05, 20),
    new THREE.MeshLambertMaterial({color:0xbfe3ff, transparent:true, opacity:0.55}));
  return m;
}
function huntSpots(){
  const R = rng(hashStr("hunt|" + (DATA.day || "")));
  const rects = Object.values(walk).flat();
  const total = rects.reduce((s, r)=>s + (r.x1 - r.x0), 0);
  const pickRect = pool=>{
    const tot = pool.reduce((s, r)=>s + (r.x1 - r.x0), 0);
    let t = R()*tot;
    for(const r of pool){ t -= (r.x1 - r.x0); if(t <= 0) return r; }
    return pool[pool.length - 1];
  };
  const spot = (high, pool)=>{
    const r = pickRect(pool || rects);
    const base = r.bridge ? DECK(r.lv) : FLOOR(r.lv);
    return {lv:r.lv, x:r.x0 + 1 + R()*Math.max(0.1, r.x1 - r.x0 - 2),
            z:r.z0 + 0.7 + R()*Math.max(0.1, r.z1 - r.z0 - 1.4),
            base, y:base + (high ? 2.2 + R()*0.35 : 0), high};
  };
  const out = [];
  for(let i = 0; i < 10; i++) out.push(Object.assign(spot(R() < 0.25), {kind:"egg", id:"egg"+i, pts:20, i}));
  for(let i = 0; i < 5; i++) out.push(Object.assign(spot(R() < 0.5), {kind:"bunny", id:"bunny"+i, pts:50, i}));
  out.push(Object.assign(spot(true), {kind:"golden", id:"golden", pts:150, i:0}));
  /* Pico keeps to the top floors, at a corridor's far end */
  const tops = rects.filter(r=>!r.bridge && (r.lv === "5" || r.lv === "4"));
  const pr = tops.length ? tops[Math.floor(R()*tops.length)] : rects[0];
  const end = R() < 0.5;
  out.push({kind:"pico", id:"pico", pts:100, i:0, lv:pr.lv, x:end ? pr.x0 + 1.4 : pr.x1 - 1.4,
            z:CORR_Z + (R() < 0.5 ? -1 : 1)*(CORR_HALF - 0.9), base:FLOOR(pr.lv),
            y:FLOOR(pr.lv), high:false});
  return out;
}
const HUNT_CENTRE = {egg:0.3, bunny:0.45, golden:0.45, pico:0.6, duck:0.15};

/* ---- the place around the building ------------------------------------- */
function buildCart(){
  const g = new THREE.Group();
  const add = (geo, m, x, y, z)=>{ const o = new THREE.Mesh(geo, m); o.position.set(x, y, z);
                                   o.castShadow = true; g.add(o); return o; };
  const shelfM = M(0xcbd5e1), post = M(0x64748b);
  [0.35, 0.78, 1.18].forEach(y=>add(new THREE.BoxGeometry(1.1, 0.05, 0.56), shelfM, 0, y, 0));
  [[-0.53, -0.26], [0.53, -0.26], [-0.53, 0.26], [0.53, 0.26]].forEach(([x, z])=>{
    add(new THREE.BoxGeometry(0.04, 1.1, 0.04), post, x, 0.72, z);
    add(new THREE.CylinderGeometry(0.07, 0.07, 0.04, 10), M(0x1f2937), x, 0.08, z).rotation.x = Math.PI/2;
  });
  [[0xffffff, -0.32], [0x93c5fd, 0], [0xfde68a, 0.32]].forEach(([c, x])=>
    add(new THREE.BoxGeometry(0.28, 0.2, 0.4), M(c), x, 0.9, 0));
  [[0x22c55e, -0.3], [0xf59e0b, -0.15], [0x3b82f6, 0]].forEach(([c, x])=>
    add(new THREE.CylinderGeometry(0.05, 0.05, 0.24, 10), M(c), x, 0.5, 0.05));
  add(new THREE.BoxGeometry(0.34, 0.62, 0.5), M(0x475569), 0.75, 0.6, 0);
  add(new THREE.BoxGeometry(0.04, 0.04, 0.56), post, -0.62, 1.1, 0);
  return g;
}
function buildPlant(){
  const g = new THREE.Group();
  const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.18, 0.4, 12), M(0xc2703d));
  pot.position.y = 0.2; pot.castShadow = true; g.add(pot);
  const leaf = new THREE.MeshPhongMaterial({color:0x3f9d5a, flatShading:true, shininess:0});
  [[0, 0.78, 0, 0.44], [0.12, 1.12, 0.05, 0.3], [-0.1, 1.02, -0.08, 0.28]].forEach(([x, y, z, r])=>{
    const f = new THREE.Mesh(new THREE.IcosahedronGeometry(r, 0), leaf);
    f.position.set(x, y, z); f.castShadow = true; g.add(f);
  });
  return g;
}
function buildDuck(){
  const g = new THREE.Group();
  const y = M(0xfacc15);
  const body = new THREE.Mesh(new THREE.SphereGeometry(0.16, 14, 10), y);
  body.scale.set(1, 0.8, 1.25); g.add(body);
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.1, 12, 10), y);
  head.position.set(0, 0.15, 0.12); g.add(head);
  const beak = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.03, 0.08), M(0xf97316));
  beak.position.set(0, 0.14, 0.23); g.add(beak);
  [-1, 1].forEach(s=>{ const e = new THREE.Mesh(new THREE.SphereGeometry(0.018, 6, 6), M(0x111827));
                       e.position.set(s*0.05, 0.18, 0.2); g.add(e); });
  return g;
}
function buildDecor(){
  const R = rng(hashStr("peaks"));
  const siteTop = (minY - RH*1.4) + DATA.levelH*0.25;
  const midX = (minX + maxX)/2;
  /* snow on the ground, and the Tenmile Range around it */
  const ground = new THREE.Mesh(new THREE.CylinderGeometry(900, 900, 1, 48), M(0xeef2f7));
  ground.position.set(midX, siteTop - 0.56, CORR_Z); ground.receiveShadow = true;
  playGroup.add(ground);
  for(let i = 0; i < 16; i++){
    const a = i/16*Math.PI*2 + R()*0.3, d = 380 + R()*220;
    const h = 90 + R()*140, r = h*(0.75 + R()*0.35);
    const m = new THREE.Mesh(new THREE.ConeGeometry(r, h, 7),
      new THREE.MeshPhongMaterial({color:0x6d8197, flatShading:true, shininess:0}));
    m.position.set(midX + Math.cos(a)*d, siteTop + h/2 - 2, CORR_Z + Math.sin(a)*d);
    m.rotation.y = R()*3;
    const cap = new THREE.Mesh(new THREE.ConeGeometry(r*0.36, h*0.34, 7),
      new THREE.MeshPhongMaterial({color:0xf8fafc, flatShading:true, shininess:0}));
    cap.position.y = h/2 - h*0.17 + 0.4;
    m.add(cap);
    playGroup.add(m);
  }
  /* snow falling everywhere a roof isn't */
  const N = 1400, pos = new Float32Array(N*3);
  const X0 = minX - 90, X1 = maxX + 90, Y0 = siteTop - 1, Y1 = maxY + 45, Z0 = -80, Z1 = 95;
  const plateList = Object.values(plates);
  const under = (x, z)=>z > -10 && z < 23 && plateList.some(p=>x > p.x0 - 4 && x < p.x1 + 4);
  for(let i = 0; i < N; i++){
    let x, z, n = 0;
    do { x = X0 + R()*(X1 - X0); z = Z0 + R()*(Z1 - Z0); } while(under(x, z) && ++n < 30);
    pos[i*3] = x; pos[i*3 + 1] = Y0 + R()*(Y1 - Y0); pos[i*3 + 2] = z;
  }
  const sg = new THREE.BufferGeometry();
  sg.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const snow = new THREE.Points(sg, new THREE.PointsMaterial({color:0xffffff, size:0.5,
    transparent:true, opacity:0.9, depthWrite:false}));
  playGroup.add(snow);
  decor.snow = {pos, N, Y0, Y1, geo:sg};
  /* the gondola, gliding over the back of the property */
  const gy0 = maxY + 70, gy1 = maxY + 40, gz = -150, gx0 = minX - 180, gx1 = maxX + 180;
  const cable = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(gx0, gy0, gz), new THREE.Vector3(gx1, gy1, gz)]);
  playGroup.add(new THREE.Line(cable, new THREE.LineBasicMaterial({color:0x334155})));
  [0.2, 0.5, 0.8].forEach(t=>{
    const x = gx0 + (gx1 - gx0)*t, y = gy0 + (gy1 - gy0)*t;
    const tw = new THREE.Mesh(new THREE.BoxGeometry(1.6, y - siteTop, 1.6), M(0x475569));
    tw.position.set(x, (y + siteTop)/2, gz); playGroup.add(tw);
  });
  const CAB = [0xe11d48, 0x2563eb, 0x16a34a, 0xf59e0b, 0x7c3aed, 0x0891b2, 0xdc2626];
  CAB.forEach((c, i)=>{
    const g = new THREE.Group();
    const body = new THREE.Mesh(new THREE.BoxGeometry(4.2, 3.4, 3.4), M(c)); g.add(body);
    const win = new THREE.Mesh(new THREE.BoxGeometry(4.25, 1.1, 3.45), M(0x1e293b));
    win.position.y = 0.5; g.add(win);
    const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 4, 6), M(0x334155));
    rod.position.y = 3.6; g.add(rod);
    playGroup.add(g);
    decor.gondola.push({g, t:i/CAB.length, gx0, gx1, gy0, gy1, gz});
  });
  /* a cart parked by everybody cleaning right now */
  for(const a of avList){
    if(a.p.act !== "clean") continue;
    const c = buildCart();
    const g = a.b._av;
    c.position.set(a.door.x - g.ax*RW*0.95, FLOOR(a.b.level), a.door.z + (CORR_Z - a.door.z)*0.15);
    c.rotation.y = g.ax ? 0 : Math.PI/2;
    playGroup.add(c);
  }
  /* a plant at each end of every corridor */
  Object.values(walk).flat().forEach((r, i)=>{
    if(r.bridge) return;
    [r.x0 + 0.9, r.x1 - 0.9].forEach((x, j)=>{
      const p = buildPlant();
      p.position.set(x, FLOOR(r.lv), CORR_Z + ((i + j) % 2 ? 1 : -1)*(CORR_HALF - 0.45));
      playGroup.add(p);
    });
  });
  /* the pools get water and ducks; the spa steams; the lobby has a fire */
  (DATA.facils||[]).forEach(f=>{
    const fl = FLOOR(f.level);
    if(/pool/i.test(f.label || "")){
      const w = new THREE.Mesh(new THREE.CylinderGeometry(2.2, 2.2, 0.08, 32),
        new THREE.MeshLambertMaterial({color:0x38bdf8, transparent:true, opacity:0.78}));
      const z = Math.max(CORR_Z - CORR_HALF + 2.2, Math.min(CORR_Z + CORR_HALF - 2.2, f.z));
      w.position.set(f.x, fl + 0.07, z); playGroup.add(w);
      for(let k = 0; k < 3; k++){
        const d = buildDuck(); playGroup.add(d);
        hunt.push({kind:"duck", id:"duck|" + f.bld + "|" + k, pts:5, lv:f.level, secret:true,
                   cx:f.x, cz:z, r:0.7 + k*0.5, ph:k*2.1, y:fl + 0.13, base:fl, m:d, x:f.x, z});
      }
    }
    if(/spa/i.test(f.label || "")){
      const N2 = 70, sp = new Float32Array(N2*3);
      const z = Math.max(CORR_Z - CORR_HALF + 0.8, f.z);
      for(let i = 0; i < N2; i++){
        sp[i*3] = f.x + (Math.random() - 0.5)*2.4; sp[i*3 + 1] = fl + Math.random()*2.6;
        sp[i*3 + 2] = z + (Math.random() - 0.5)*1.2;
      }
      const g2 = new THREE.BufferGeometry();
      g2.setAttribute("position", new THREE.BufferAttribute(sp, 3));
      playGroup.add(new THREE.Points(g2, new THREE.PointsMaterial({color:0xe2e8f0, size:0.42,
        transparent:true, opacity:0.55, depthWrite:false})));
      const tub = new THREE.Mesh(new THREE.CylinderGeometry(1.3, 1.3, 0.3, 24),
        new THREE.MeshLambertMaterial({color:0x67e8f9, transparent:true, opacity:0.8}));
      tub.position.set(f.x, fl + 0.15, z); playGroup.add(tub);
      decor.steam.push({pos:sp, N:N2, geo:g2, y0:fl, x:f.x, z});
    }
    if(/grand lobby/i.test(f.label || "") && f.level === "1"){
      const z = CORR_Z - CORR_HALF - 0.45;
      const stone = new THREE.Mesh(new THREE.BoxGeometry(2.4, 2.6, 0.8), M(0x78716c));
      stone.position.set(f.x, fl + 1.3, z); stone.castShadow = true; playGroup.add(stone);
      const hole = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.95, 0.1), M(0x1c1917));
      hole.position.set(f.x, fl + 0.6, z + 0.41); playGroup.add(hole);
      const flames = [0xf97316, 0xfacc15, 0xef4444].map((c, i)=>{
        const fl3 = new THREE.Mesh(new THREE.ConeGeometry(0.16, 0.55, 8),
          new THREE.MeshBasicMaterial({color:c, transparent:true, opacity:0.9}));
        fl3.position.set(f.x + (i - 1)*0.28, fl + 0.4, z + 0.46); playGroup.add(fl3);
        return fl3;
      });
      const glow = new THREE.PointLight(0xff8a3d, 1.2, 10, 1.6);
      glow.position.set(f.x, fl + 1, z + 1.2); playGroup.add(glow);
      decor.fires.push({flames, glow, y:fl + 0.4});
    }
  });
}

function buildWorld(){
  if(built) return;
  built = true;
  const B = buildPlayer(PL.look, PL.role);
  me = B; B.g.rotation.order = "YXZ"; playGroup.add(B.g);
  const tm = tagMat("★ " + (PL.name || TX.you || "You"), "#f5a524");
  meTag = new THREE.Sprite(tm.m); meTag.scale.set(0.34*tm.aspect, 0.34, 1);
  meTag.renderOrder = 3; playGroup.add(meTag);
  /* the corridors sit in the shadow of the slab above; a light that walks
     with you keeps the doors readable */
  lamp = new THREE.PointLight(0xfff6e8, 1.1, 26, 1.4);
  playGroup.add(lamp);
  /* a runner down every corridor, so the floor you can walk is the floor you see */
  const runner = mat("#d5dde7", 1);
  Object.values(walk).flat().forEach(r=>{
    const deck = r.bridge ? DECK(r.lv) : FLOOR(r.lv);
    const m = new THREE.Mesh(new THREE.BoxGeometry(r.x1 - r.x0, 0.04, r.z1 - r.z0), runner);
    m.position.set((r.x0 + r.x1)/2, deck + 0.02, (r.z0 + r.z1)/2);
    m.receiveShadow = true;
    playGroup.add(m);
  });
  /* glowing markers at the doors that need somebody */
  const qGeo = new THREE.OctahedronGeometry(0.32);
  DATA.boxes.forEach(b=>{
    if(!b.on_chart || !b._av) return;
    const kind = b.status === DATA.help ? "help"
               : (DATA.ready || []).indexOf(b.status) >= 0 ? "ready" : null;
    if(!kind) return;
    const m = new THREE.Mesh(qGeo, new THREE.MeshBasicMaterial({
      color: kind === "help" ? 0xef4444 : 0x2f80ed, transparent:true, opacity:0.92}));
    m.position.set(b._av.dx, FLOOR(b.level) + 2.85, b._av.dz);
    playGroup.add(m);
    quests.push({b, kind, m, done:P.visited.has(b.code)});
  });
  quests.forEach(q=>{ q.m.visible = !q.done; });
  buildDecor();
  /* and the day's hunt */
  huntSpots().forEach(h=>{
    h.m = h.kind === "egg" ? makeEgg(h.i) : h.kind === "pico" ? makePico()
        : makeBunny(h.i, h.kind === "golden");
    h.m.position.set(h.x, h.y, h.z);
    h.m.rotation.y = Math.random()*6.28;
    playGroup.add(h.m);
    if(h.high){
      h.shelf = shelf(); h.shelf.position.set(h.x, h.y - 0.04, h.z); playGroup.add(h.shelf);
    }
    hunt.push(h);
  });
  hunt.forEach(h=>{ const f = P.found.has(h.id); h.m.visible = !f; if(h.shelf) h.shelf.visible = !f; });
}

/* ---- getting about: floors anywhere in a building, and fast travel ----- */
function nearLift(){
  const r = where(P.lv, P.x, P.z);
  if(!r || r.bridge || ride) return null;
  let best = null, bd = 1e9;
  for(const f of lifts){
    if(f.level !== P.lv || f.bld !== r.bld) continue;
    const d = Math.abs(f.x - P.x);
    if(d < bd){ bd = d; best = f; }
  }
  return best && bd < 3.4 ? best : null;
}
/* Q / E change floor anywhere inside a building (Hari: traversing should be
   easy). At a lift you come out at the same lift; elsewhere, straight up. */
function levelStep(dir){
  if(ride) return;
  const r = where(P.lv, P.x, P.z);
  if(!r || r.bridge){ toast(TX.no_floor || "Step off the bridge to change floor", "#64748b"); return; }
  const lift = nearLift();
  const order = DATA.levels;
  for(let j = order.indexOf(P.lv) + dir; j >= 0 && j < order.length; j += dir){
    const lv = order[j];
    const t = (walk[lv] || []).find(q=>q.bld === r.bld);
    if(!t) continue;
    const there = lift ? lifts.filter(f=>f.level === lv && f.bld === lift.bld)
      .sort((a, b)=>(a.kind === lift.kind ? 0 : 1) - (b.kind === lift.kind ? 0 : 1)
                    || Math.abs(a.x - lift.x) - Math.abs(b.x - lift.x))[0] : null;
    const x = Math.max(t.x0 + 0.5, Math.min(t.x1 - 0.5, there ? there.x : P.x));
    ride = {from:P.feet, to:FLOOR(lv), t:0, lv, x};
    P.x = x; P.z = Math.max(t.z0 + 0.3, Math.min(t.z1 - 0.3, P.z));
    P.air = 0; P.vy = 0;
    sfx("lift");
    return;
  }
}
const fadeEl = document.getElementById("fade");
function travelTo(lv, x, z, head){
  ride = null;
  fadeEl.classList.add("on");
  sfx("warp");
  setTimeout(()=>{
    P.lv = lv; P.x = x; P.z = z;
    if(head != null){ P.head = head; pcYaw = head + Math.PI; }
    P.air = 0; P.vy = 0;
    P.ground = P.feet = groundAt(lv, x, z);
    save();
    setTimeout(()=>fadeEl.classList.remove("on"), 60);
  }, 230);
}
/* the nearest point you can stand on, on a level */
function snap(lv, x, z){
  let best = null, bd = 1e9;
  for(const r of (walk[lv] || [])){
    const cx = Math.max(r.x0 + 0.3, Math.min(r.x1 - 0.3, x)),
          cz = Math.max(r.z0 + 0.3, Math.min(r.z1 - 0.3, z));
    const d = Math.hypot(cx - x, cz - z);
    if(d < bd){ bd = d; best = [cx, cz]; }
  }
  return best;
}
function nextQuest(){
  const ix = lv=>DATA.levels.indexOf(lv);
  return quests.filter(q=>!q.done).sort((a, b)=>
    Math.abs(ix(a.b.level) - ix(P.lv)) - Math.abs(ix(b.b.level) - ix(P.lv))
    || Math.abs(a.b._av.dx - P.x) - Math.abs(b.b._av.dx - P.x))[0];
}
/* arrive a few steps short, facing the door: the last bit is yours to walk */
function goNear(lv, x, z){
  const s = snap(lv, x - 3.2, CORR_Z) || [x, CORR_Z];
  travelTo(lv, s[0], s[1], Math.atan2(x - s[0], z - s[1]));
}

const gotoEl = document.getElementById("goto");
function openGoto(){
  const lvBtn = lv=>lv === "Plaza" ? "P" : lv === "Terrace" ? "T" : lv;
  const r = where(P.lv, P.x, P.z);
  let h = "<button class='x' data-close='1'>✕</button><b style='font-size:.98rem'>🗺 " +
          esc(TX.map || "Go to") + "</b>";
  h += "<h5>" + esc(TX.floors || "Buildings and floors") + "</h5>";
  [3, 1, 2].forEach(bld=>{
    const lvs = DATA.levels.filter(lv=>(walk[lv] || []).some(q=>q.bld === bld));
    if(!lvs.length) return;
    h += "<div class='row'><b>" + esc(TX.bld || "Building") + " " + bld + "</b>" +
      lvs.map(lv=>"<button data-bld='" + bld + "' data-lv='" + lv + "'" +
        (r && !r.bridge && r.bld === bld && lv === P.lv ? " class='here'" : "") + ">" +
        lvBtn(lv) + "</button>").join("") + "</div>";
  });
  if(avList.length){
    h += "<h5>" + esc(TX.team || "Team") + "</h5><div class='row'>" +
      avList.map((a, i)=>"<button data-p='" + i + "'>" + esc(a.p.who || a.p.name) + " · " +
                         a.b.code + "</button>").join("") + "</div>";
  }
  h += "<h5>&nbsp;</h5><div class='row'>" +
       (OFFICE ? "<button data-office='1'>🏠 " + esc(TX.office || "Housekeeping office") + "</button>" : "") +
       (nextQuest() ? "<button data-next='1'>🎯 " + esc(TX.next || "Next room to visit") + "</button>" : "") +
       "</div>";
  gotoEl.innerHTML = h;
  gotoEl.style.display = "block";
}
function closeGoto(){ gotoEl.style.display = "none"; try{ cv.focus({preventScroll:true}); }catch(e){} }
gotoEl.addEventListener("click", e=>{
  const t = e.target.closest("button");
  if(!t) return;
  const d = t.dataset;
  if(d.bld){
    const bld = +d.bld, lv = d.lv;
    const r = (walk[lv] || []).find(q=>q.bld === bld);
    const lift = lifts.filter(f=>f.level === lv && f.bld === bld)[0];
    if(r) travelTo(lv, Math.max(r.x0 + 0.5, Math.min(r.x1 - 0.5, lift ? lift.x : (r.x0 + r.x1)/2)),
                   CORR_Z, null);
  } else if(d.p){
    const a = avList[+d.p];
    goNear(a.b.level, a.door.x, a.door.z);
  } else if(d.office){
    travelTo(OFFICE.level, OFFICE.x, CORR_Z, null);
  } else if(d.next){
    const q = nextQuest();
    if(q) goNear(q.b.level, q.b._av.dx, q.b._av.dz);
  }
  closeGoto();
});
document.getElementById("mapbtn").addEventListener("click", ()=>{
  gotoEl.style.display === "block" ? closeGoto() : openGoto(); });

/* ---- the minimap: this level from above; click it to go there ---------- */
const mini = document.getElementById("mini"), mctx = mini.getContext("2d");
const MX0 = minX - 8, MX1 = maxX + 8, MZ0 = -10, MZ1 = 23;
const m2c = (x, z)=>[(x - MX0)/(MX1 - MX0)*mini.width, (z - MZ0)/(MZ1 - MZ0)*mini.height];
function drawMini(){
  const W = mini.width, H = mini.height;
  mctx.clearRect(0, 0, W, H);
  mctx.fillStyle = "#dbe3ec";
  for(const r of (walk[P.lv] || [])){
    const [a, b] = m2c(r.x0, r.z0), [c, d] = m2c(r.x1, r.z1);
    mctx.fillStyle = r.bridge ? "#9fd3b4" : "#dbe3ec";
    mctx.fillRect(a, b, c - a, d - b);
  }
  for(const b of DATA.boxes){
    if(b.level !== P.lv) continue;
    const [x, y] = m2c(b.x, b._z);
    mctx.fillStyle = b.colour; mctx.fillRect(x - 4, y - 6, 8, 12);
  }
  for(const q of quests){
    if(q.done || q.b.level !== P.lv) continue;
    const [x, y] = m2c(q.b._av.dx, q.b._av.dz);
    mctx.fillStyle = q.kind === "help" ? "#ef4444" : "#2f80ed";
    mctx.beginPath(); mctx.moveTo(x, y - 7); mctx.lineTo(x + 6, y); mctx.lineTo(x, y + 7);
    mctx.lineTo(x - 6, y); mctx.fill();
  }
  for(const a of avList){
    if(a.b.level !== P.lv) continue;
    const [x, y] = m2c(a.door.x, a.door.z);
    mctx.fillStyle = a.p.col; mctx.strokeStyle = "#fff"; mctx.lineWidth = 2;
    mctx.beginPath(); mctx.arc(x, y, 6, 0, 7); mctx.fill(); mctx.stroke();
  }
  const [px, py] = m2c(P.x, P.z);
  const sx = Math.sin(P.head), sz = Math.cos(P.head);
  mctx.fillStyle = "#f5a524"; mctx.strokeStyle = "#1e3350"; mctx.lineWidth = 2;
  mctx.beginPath();
  mctx.moveTo(px + sx*12, py + sz*12);
  mctx.lineTo(px - sx*7 + sz*7, py - sz*7 - sx*7);
  mctx.lineTo(px - sx*7 - sz*7, py - sz*7 + sx*7);
  mctx.closePath(); mctx.fill(); mctx.stroke();
  mctx.fillStyle = "#1e3350"; mctx.font = "700 20px system-ui,-apple-system,'Segoe UI',sans-serif";
  mctx.fillText(LV_NAME(P.lv), 10, 24);
}
mini.addEventListener("click", e=>{
  const r = mini.getBoundingClientRect();
  const x = MX0 + (e.clientX - r.left)/r.width*(MX1 - MX0);
  const z = MZ0 + (e.clientY - r.top)/r.height*(MZ1 - MZ0);
  const s = snap(P.lv, x, z);
  if(s) travelTo(P.lv, s[0], s[1], null);
});

/* ---- a few sounds, off until asked for: this runs in an office ---- */
let actx = null;
const SFX = {jump:[420, 640], egg:[660, 990], bunny:[523, 1046], golden:[784, 1568],
             pico:[392, 784], quest:[523, 784], lift:[300, 460], warp:[900, 330], duck:[320, 190]};
function sfx(kind){
  if(muted) return;
  try{
    actx = actx || new (window.AudioContext || window.webkitAudioContext)();
    const o = actx.createOscillator(), g = actx.createGain(), t = actx.currentTime;
    const f = SFX[kind] || [440, 660];
    o.type = kind === "duck" ? "sawtooth" : "triangle";
    o.frequency.setValueAtTime(f[0], t);
    o.frequency.exponentialRampToValueAtTime(f[1], t + 0.12);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.16, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.24);
    o.connect(g); g.connect(actx.destination);
    o.start(t); o.stop(t + 0.26);
  }catch(e){}
}
const sndBtn = document.getElementById("sndbtn");
const labelSnd = ()=>{ sndBtn.textContent = muted ? "🔇" : "🔊";
                       sndBtn.title = TX.sound || "Sound"; };
sndBtn.addEventListener("click", ()=>{ muted = !muted; labelSnd(); save(); sfx("egg"); });
labelSnd();

/* ---- input: keys, and a thumb stick and buttons on a touch screen ---- */
const keys = {};
const joy = {x:0, y:0};
function jump(){
  if(ride || !playing) return;
  if(P.air <= 0.001){ P.vy = JUMP_V; P.jumps = 1; sfx("jump"); }
  else if(P.jumps < 2){ P.vy = JUMP_V*0.85; P.jumps = 2; sfx("jump"); }
}
const runBtn = document.getElementById("runbtn");
function setRun(on){ runOn = on; runBtn.classList.toggle("on", on); }
window.addEventListener("keydown", e=>{
  if(!playing) return;
  keys[e.code] = true;
  if(/^Arrow|^Space$|^Page/.test(e.code)) e.preventDefault();
  if(e.repeat) return;
  if(e.code === "Space") jump();
  if(e.code === "KeyR") setRun(!runOn);
  if(e.code === "KeyH") P.help = !P.help;
  if(e.code === "KeyM") gotoEl.style.display === "block" ? closeGoto() : openGoto();
  if(e.code === "KeyQ" || e.code === "PageUp") levelStep(1);
  if(e.code === "KeyE" || e.code === "PageDown") levelStep(-1);
  if(e.code === "Escape"){ if(gotoEl.style.display === "block") closeGoto(); else stopPlay(); }
});
window.addEventListener("keyup", e=>{ keys[e.code] = false; });
window.addEventListener("blur", ()=>{ for(const k in keys) keys[k] = false; });
const joyEl = document.getElementById("joy"), knob = document.getElementById("knob");
joyEl.addEventListener("pointerdown", e=>{ joyEl.setPointerCapture(e.pointerId); moveJoy(e); });
joyEl.addEventListener("pointermove", e=>{ if(e.buttons || e.pointerType === "touch") moveJoy(e); });
const endJoy = ()=>{ joy.x = joy.y = 0; knob.style.left = knob.style.top = "39px"; };
joyEl.addEventListener("pointerup", endJoy);
joyEl.addEventListener("pointercancel", endJoy);
function moveJoy(e){
  const r = joyEl.getBoundingClientRect();
  let dx = e.clientX - r.left - r.width/2, dy = e.clientY - r.top - r.height/2;
  const l = Math.hypot(dx, dy), R = 40;
  if(l > R){ dx *= R/l; dy *= R/l; }
  joy.x = dx/R; joy.y = dy/R;
  knob.style.left = (39 + dx) + "px"; knob.style.top = (39 + dy) + "px";
}
document.getElementById("upbtn").addEventListener("click", ()=>levelStep(1));
document.getElementById("dnbtn").addEventListener("click", ()=>levelStep(-1));
document.getElementById("jumpbtn").addEventListener("pointerdown", e=>{ e.preventDefault(); jump(); });
runBtn.addEventListener("click", ()=>setRun(!runOn));
const TOUCH = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;

/* ---- bursts of colour when something is found ---- */
const burstGeo = new THREE.BoxGeometry(0.09, 0.09, 0.09);
function burst(x, y, z, colours, n, power){
  for(let i = 0; i < n; i++){
    const m = new THREE.Mesh(burstGeo, new THREE.MeshBasicMaterial({
      color:colours[i % colours.length], transparent:true}));
    m.position.set(x, y, z);
    const a = Math.random()*6.28, u = (0.3 + Math.random())*(power || 1);
    bursts.push({m, vx:Math.cos(a)*u*3.5, vy:2.5 + Math.random()*4*(power || 1),
                 vz:Math.sin(a)*u*3.5, t:0});
    playGroup.add(m);
  }
}

/* ---- each frame ---- */
const phud = document.getElementById("phud"), nearEl = document.getElementById("near"),
      toastEl = document.getElementById("toast"), liftEl = document.getElementById("liftbtns"),
      actEl = document.getElementById("actbtns");
let toastT = 0, hudT = 0;
function toast(msg, colour){
  toastEl.textContent = msg; toastEl.style.background = colour || "#1a9e4b";
  toastEl.classList.add("on"); toastT = performance.now() + 1700;
}
const LV_NAME = lv => (lv === "Plaza" || lv === "Terrace") ? lv : (TX.level || "Level")+" "+lv;
const HUNT_TOAST = {egg:["egg", "🥚", "#db2777"], bunny:["bunny", "🐰", "#7c3aed"],
                    golden:["golden", "✨", "#d97706"], pico:["pico", "⛰", "#2f6fc4"],
                    duck:["duck", "🦆", "#0891b2"]};
function stepPlayer(dt, now){
  const running = (keys.ShiftLeft || keys.ShiftRight || runOn);
  if(ride){
    P.speed = 0;
    ride.t = Math.min(1, ride.t + dt/0.6);
    const k = ride.t < .5 ? 2*ride.t*ride.t : 1 - Math.pow(-2*ride.t + 2, 2)/2;
    P.feet = P.ground = ride.from + (ride.to - ride.from)*k;
    if(ride.t >= 1){ P.lv = ride.lv; ride = null; save(); }
  } else {
    /* Steer and walk: left/right turn, up/down walk. Walking relative to
       the camera made turning round in a corridor a fight with the camera;
       a corridor is a line, and this is how you walk one. */
    const turn = ((keys.KeyD||keys.ArrowRight) ? 1 : 0) - ((keys.KeyA||keys.ArrowLeft) ? 1 : 0) + joy.x;
    const fwd = ((keys.KeyW||keys.ArrowUp) ? 1 : 0) - ((keys.KeyS||keys.ArrowDown) ? 1 : 0) - joy.y;
    P.speed = 0;
    if(Math.abs(turn) > 0.08) P.head -= Math.max(-1, Math.min(1, turn))*2.6*dt;
    if(Math.abs(fwd) > 0.08){
      const f = Math.max(-1, Math.min(1, fwd));
      const sp = f > 0 ? (running ? RUN_V : WALK_V)*f : BACK_V*f;
      const mx = Math.sin(P.head), mz = Math.cos(P.head);
      const nx = P.x + mx*sp*dt, nz = P.z + mz*sp*dt;
      /* slide along a wall rather than stop dead at it */
      if(where(P.lv, nx, nz)){ P.x = nx; P.z = nz; }
      else if(where(P.lv, nx, P.z)) P.x = nx;
      else if(where(P.lv, P.x, nz)) P.z = nz;
      P.speed = Math.abs(sp);
      /* the controls line steps aside once you have the hang of it; H brings it back */
      P.walked += P.speed*dt;
      if(P.help && P.walked > 45) P.help = false;
    }
    /* the camera drifts back behind you once you move, unless you are
       holding it somewhere with the mouse */
    if((P.speed || Math.abs(turn) > 0.08) && !drag){
      let d = (P.head + Math.PI) - pcYaw;
      d = Math.atan2(Math.sin(d), Math.cos(d));
      pcYaw += d*Math.min(1, dt*3.5);
    }
    P.ground += (groundAt(P.lv, P.x, P.z) - P.ground)*Math.min(1, dt*10);
    /* in the air: up, gravity, the ceiling, and down again */
    if(P.air > 0 || P.vy > 0){
      P.vy -= GRAV*dt;
      P.air += P.vy*dt;
      const roof = CEIL - HEIGHT - (P.ground - FLOOR(P.lv));
      if(P.air > roof){ P.air = roof; P.vy = Math.min(0, P.vy); }
      if(P.air <= 0){ P.air = 0; P.vy = 0; P.jumps = 0; }
    }
    P.feet = P.ground + P.air;
  }
  /* the figure: legs and arms swing with the pace, a lean when running,
     knees up and arms high in the air */
  P.phase += dt*(P.speed ? 2.2 + P.speed*0.9 : 2);
  const sw = P.speed ? Math.sin(P.phase)*Math.min(0.95, 0.25 + P.speed*0.06) : 0;
  if(P.air > 0.02){
    me.legs[0].rotation.x = -0.6; me.legs[1].rotation.x = 0.35;
    me.arms[0].rotation.x = me.arms[1].rotation.x = P.vy > 0 ? -2.5 : -1.6;
  } else {
    me.legs[0].rotation.x = sw; me.legs[1].rotation.x = -sw;
    me.arms[0].rotation.x = -sw*0.85; me.arms[1].rotation.x = sw*0.85;
  }
  me.g.position.set(P.x, P.feet + (P.speed && P.air <= 0 ? Math.abs(Math.sin(P.phase))*0.05 : 0), P.z);
  me.g.rotation.y = P.head;
  me.g.rotation.x += ((P.speed > WALK_V + 1 ? 0.16 : 0) - me.g.rotation.x)*Math.min(1, dt*8);
  me.g.scale.y = P.speed ? 1 : 1 + Math.sin(now*0.003)*0.008;
  meTag.position.set(P.x, P.feet + 2.25, P.z);
  /* your own name is for people watching from afar; up close it is in the way */
  meTag.visible = pcDist > 9;
  lamp.position.set(P.x, P.feet + 2.9, P.z);

  /* the follow camera; it widens a little at a run */
  const fov = P.speed > WALK_V + 1 ? 52 : 42;
  if(Math.abs(camera.fov - fov) > 0.05){
    camera.fov += (fov - camera.fov)*Math.min(1, dt*5); camera.updateProjectionMatrix();
  }
  const tx = P.x + root.position.x, ty = P.feet + 1.8 + root.position.y, tz = P.z + root.position.z;
  const cp = Math.cos(pcPitch), sp = Math.sin(pcPitch);
  camera.position.set(tx + Math.sin(pcYaw)*cp*pcDist, ty + sp*pcDist, tz + Math.cos(pcYaw)*cp*pcDist);
  camera.lookAt(tx, ty, tz);

  /* the markers turn, and reaching one counts */
  for(const q of quests){
    if(q.done) continue;
    q.m.rotation.y += dt*2;
    q.m.position.y = FLOOR(q.b.level) + 2.85 + Math.sin(now*0.004 + q.b.x)*0.12;
    if(!ride && q.b.level === P.lv
       && Math.hypot(q.b._av.dx - P.x, q.b._av.dz - P.z) < 2.4){
      q.done = true; q.m.visible = false; P.visited.add(q.b.code);
      const pts = q.kind === "help" ? 25 : 10;
      P.xp += pts;
      toast("+" + pts + " " + (TX.xp || "XP") + " · " + q.b.code,
            q.kind === "help" ? "#dc2626" : "#2f80ed");
      sfx("quest");
      save();
    }
  }
  /* the hunt: everything bobs, and anything you touch is yours */
  for(const h of hunt){
    if(P.found.has(h.id)) continue;
    if(h.kind === "duck"){
      const a = now*0.0004 + h.ph;
      h.x = h.cx + Math.cos(a)*h.r; h.z = h.cz + Math.sin(a)*h.r;
      h.m.position.set(h.x, h.y + Math.sin(now*0.004 + h.ph)*0.03, h.z);
      h.m.rotation.y = -a;
    } else if(h.kind === "pico"){
      h.m.userData.arm.rotation.z = -0.9 + Math.sin(now*0.008)*0.5;
      h.m.position.y = h.y + Math.abs(Math.sin(now*0.003))*0.12;
    } else if(h.kind === "egg"){
      h.m.rotation.y += dt*1.2;
      h.m.position.y = h.y + Math.sin(now*0.003 + h.i)*0.06;
    } else {
      h.m.rotation.y += dt*(h.kind === "golden" ? 2.4 : 0.8);
      h.m.position.y = h.y + Math.abs(Math.sin(now*0.005 + h.i))*0.14;
    }
    if(ride || h.lv !== P.lv) continue;
    const cy = h.y + (HUNT_CENTRE[h.kind] || 0.3);
    if(Math.hypot(h.x - P.x, h.z - P.z) < (h.kind === "golden" || h.kind === "pico" ? 1.15 : 0.95)
       && cy > P.feet - 0.3 && cy < P.feet + HEIGHT + 0.25){
      P.found.add(h.id); h.m.visible = false; if(h.shelf) h.shelf.visible = false;
      P.xp += h.pts;
      const [k, icon, col] = HUNT_TOAST[h.kind];
      toast(icon + " " + (TX["f_" + k] || k) + " +" + h.pts + " " + (TX.xp || "XP"), col);
      burst(h.x, cy, h.z, h.kind === "golden" ? [0xf5c542, 0xfff1a8, 0xffffff]
                       : [0xf472b6, 0x60a5fa, 0x34d399, 0xfacc15, 0xa78bfa], 22, 1);
      sfx(k);
      const left = hunt.filter(q=>!q.secret && !P.found.has(q.id)).length;
      if(!h.secret && left === 0){
        setTimeout(()=>{
          toast("🎉 " + (TX.f_all || "Hunt complete!") + " +250 " + (TX.xp || "XP"), "#16a34a");
          burst(P.x, P.feet + 2, P.z, [0xf472b6, 0x60a5fa, 0x34d399, 0xfacc15, 0xa78bfa, 0xf97316], 90, 1.6);
          sfx("golden");
        }, 900);
        P.xp += 250;
      }
      save();
    }
  }
  /* bursts fall and fade */
  for(let i = bursts.length - 1; i >= 0; i--){
    const b = bursts[i];
    b.t += dt; b.vy -= 12*dt;
    b.m.position.x += b.vx*dt; b.m.position.y += b.vy*dt; b.m.position.z += b.vz*dt;
    b.m.rotation.x += dt*7; b.m.rotation.y += dt*5;
    b.m.material.opacity = Math.max(0, 1 - b.t/1.2);
    if(b.t > 1.2){ playGroup.remove(b.m); b.m.material.dispose(); bursts.splice(i, 1); }
  }
  stepDecor(dt, now);
  if(toastT && now > toastT){ toastEl.classList.remove("on"); toastT = 0; }
  if(now - hudT > 120){ hudT = now; drawHud(); drawMini(); }
}

function stepDecor(dt, now){
  const s = decor.snow;
  if(s){
    const p = s.pos;
    for(let i = 0; i < s.N; i++){
      p[i*3 + 1] -= (1.3 + (i % 7)*0.15)*dt;
      p[i*3] += Math.sin(now*0.0006 + i)*0.006;
      if(p[i*3 + 1] < s.Y0) p[i*3 + 1] = s.Y1;
    }
    s.geo.attributes.position.needsUpdate = true;
  }
  for(const c of decor.gondola){
    c.t = (c.t + dt*0.01) % 1;
    c.g.position.set(c.gx0 + (c.gx1 - c.gx0)*c.t, c.gy0 + (c.gy1 - c.gy0)*c.t - 5.6, c.gz);
  }
  for(const st of decor.steam){
    const p = st.pos;
    for(let i = 0; i < st.N; i++){
      p[i*3 + 1] += (0.5 + (i % 5)*0.1)*dt;
      p[i*3] += Math.sin(now*0.001 + i)*0.004;
      if(p[i*3 + 1] > st.y0 + 2.8){ p[i*3 + 1] = st.y0 + 0.2; p[i*3] = st.x + (Math.random() - 0.5)*2.2; }
    }
    st.geo.attributes.position.needsUpdate = true;
  }
  for(const f of decor.fires){
    f.flames.forEach((fl, i)=>{ fl.scale.y = 0.8 + Math.abs(Math.sin(now*0.012 + i*1.7))*0.6;
                                fl.position.y = f.y + fl.scale.y*0.12; });
    f.glow.intensity = 1 + Math.sin(now*0.02)*0.25 + Math.sin(now*0.047)*0.15;
  }
}

function drawHud(){
  const r = where(P.lv, P.x, P.z);
  const here = r && r.bridge
    ? "Bridge " + r.a + " ↔ " + r.b + " · " + LV_NAME(P.lv)
    : (TX.bld || "Building") + " " + (r ? r.bld : "?") + " · " + LV_NAME(P.lv);
  const left = k=>quests.filter(q=>!q.done && q.kind === k).length;
  const got = k=>hunt.filter(h=>h.kind === k && P.found.has(h.id)).length;
  const all = k=>hunt.filter(h=>h.kind === k).length;
  /* warmer: something unfound within a few doors, on this floor */
  const warm = hunt.some(h=>!h.secret && !P.found.has(h.id) && h.lv === P.lv
                            && Math.hypot(h.x - P.x, h.z - P.z) < 11);
  phud.innerHTML =
    "<b>★ " + esc(PL.name || TX.you || "You") + "</b><br>" + esc(here) +
    "<br><span class='xp'>" + P.xp + " " + esc(TX.xp || "XP") + "</span> · " +
    P.visited.size + " " + esc(TX.visited || "visited") +
    "<br>" + esc(TX.quests || "Rooms to visit") + ": <b style='color:#dc2626'>" + left("help") +
    "</b> " + esc(TX.help_q || "need help") + " · <b style='color:#2f80ed'>" + left("ready") +
    "</b> " + esc(TX.ready_q || "ready for RQS") +
    "<br>" + esc(TX.hunt || "Hunt") + ": 🥚 " + got("egg") + "/" + all("egg") +
    " · 🐰 " + got("bunny") + "/" + all("bunny") +
    " · ✨ " + got("golden") + "/" + all("golden") +
    " · ⛰ " + (got("pico") ? "Pico!" : "?") +
    (warm ? "<br><b style='color:#d97706'>👀 " + esc(TX.warm || "Something is hidden nearby…") + "</b>" : "") +
    (TOUCH || !P.help ? "" : "<br><span style='color:#64748b'>" + esc(TX.help || "") + "</span>");
  liftEl.style.display = r && !r.bridge ? "flex" : "none";
  /* who or what is right here */
  let best = null, bd = 3.2;
  for(const a of avList){
    if(a.b.level !== P.lv) continue;
    const d = Math.hypot(a.door.x - P.x, a.door.z - P.z);
    if(d < bd){ bd = d; best = personLine(a.p) + " <span>&middot; " + a.b.code + "</span>"; }
  }
  if(!best){
    let rb = null; bd = 2.6;
    for(const b of DATA.boxes){
      if(b.level !== P.lv || !b._av) continue;
      const d = Math.hypot(b._av.dx - P.x, b._av.dz - P.z);
      if(d < bd){ bd = d; rb = b; }
    }
    if(rb) best = "<b>" + rb.code + "</b> <span>" +
      (rb.on_chart ? [rb.svc, rb.mins ? rb.mins + " min" : "", rb.hk,
                      rb.status.replace(/_/g, " ")].filter(Boolean).map(esc).join(" &middot; ")
                   : "not on a chart today") + "</span>";
  }
  nearEl.innerHTML = best || "";
  nearEl.style.display = best ? "block" : "none";
}

const playBtn = document.getElementById("playbtn");
function labelPlay(){ playBtn.textContent = playing ? (TX.stop || "■ Exit") : (TX.start || "▶ Play"); }
function startPlay(){
  buildWorld();
  if(P.lv === null) spawn();
  playing = true;
  wrap.classList.add("playing");
  playGroup.visible = true;
  camera.near = 0.1; camera.far = 2000; camera.updateProjectionMatrix();
  pick.style.display = "none";
  phud.style.display = "block";
  mini.style.display = "block";
  joyEl.style.display = TOUCH ? "block" : "none";
  actEl.style.display = TOUCH ? "flex" : "none";
  document.getElementById("mapbtn").title = TX.map || "Go to";
  labelPlay(); save();
  try{ cv.focus({preventScroll:true}); }catch(e){}
}
function stopPlay(){
  playing = false;
  wrap.classList.remove("playing");
  playGroup.visible = false;
  camera.near = 1; camera.far = 4000; camera.fov = 42; camera.updateProjectionMatrix();
  for(const el of [phud, nearEl, joyEl, liftEl, mini, gotoEl, actEl]) el.style.display = "none";
  for(const k in keys) keys[k] = false;
  labelPlay(); save(); place();
}
playBtn.addEventListener("click", ()=>playing ? stopPlay() : startPlay());
labelPlay();
cv.addEventListener("pointerdown", ()=>{ if(playing){ try{ cv.focus({preventScroll:true}); }catch(e){} } });
/* from the model: tap a room, then walk from its door */
function walkHere(code){
  const b = BOX[code];
  if(!b || !b._av) return;
  if(!playing) startPlay();
  goNear(b.level, b._av.dx, b._av.dz);
}

const fsBtn = document.getElementById("fsbtn");
fsBtn.title = TX.full || "Fullscreen";
if(!document.fullscreenEnabled) fsBtn.style.display = "none";
fsBtn.addEventListener("click", ()=>{
  if(document.fullscreenElement) document.exitFullscreen();
  else wrap.requestFullscreen().catch(()=>{});
});
document.addEventListener("fullscreenchange", ()=>setTimeout(size, 60));

/* ---- level and building labels, projected each frame ---- */
const tags = [];
DATA.levels.forEach((lv,i)=>{
  /* a level with no guest rooms still has a floor -- building 1's level 1 is
     the busiest in the resort -- so facilities count towards labelling it */
  const any = DATA.boxes.filter(b=>b.level===lv)
    .concat((DATA.facils||[]).filter(f=>f.level===lv));
  if(!any.length) return;
  const el=document.createElement("div"); el.className="lv";
  el.textContent = (lv==="Plaza"||lv==="Terrace") ? lv : "L"+lv;
  labels.appendChild(el);
  tags.push({el, v:new THREE.Vector3(minX-DATA.doorW*3.2, any[0].y, DATA.hallD*0.5)});
});
[3,1,2].forEach(bld=>{
  const any = DATA.boxes.filter(b=>b.bld===bld);
  if(!any.length) return;
  const xs = any.map(b=>b.x);
  const el=document.createElement("div"); el.className="bl";
  el.textContent = "Building "+bld;
  labels.appendChild(el);
  tags.push({el, v:new THREE.Vector3((Math.min(...xs)+Math.max(...xs))/2,
                                     minY-DATA.levelH*1.5, DATA.hallD*0.5)});
});

function project(){
  tags.forEach(t=>{
    const p = t.v.clone().add(root.position).project(camera);
    if(p.z>1){ t.el.style.display="none"; return; }
    t.el.style.display="block";
    t.el.style.left = ((p.x*0.5+0.5)*100)+"%";
    t.el.style.top  = ((-p.y*0.5+0.5)*100)+"%";
  });
}

function size(){
  const w=wrap.clientWidth, h=wrap.clientHeight;
  renderer.setSize(w,h,false);
  camera.aspect=w/h; camera.updateProjectionMatrix();
  place();
}
window.addEventListener("resize", size);
size();

let avFrame = 0, avLast = 0, lastNow = 0;
/* back in the game after a refresh, where you left off */
if(saved && saved.playing) startPlay();
(function loop(now){
  requestAnimationFrame(loop);
  now = now || performance.now();
  const dt = Math.min(0.05, lastNow ? (now - lastNow)/1000 : 0.016);
  lastNow = now;
  if(playing) stepPlayer(dt, now);
  if(now - avLast > 190){          /* about five frames a second: a cartoon, not a video */
    avLast = now; avFrame = (avFrame + 1) % 4;
    for(const k in avMats){
      avMats[k][0].map.offset.x = avFrame*0.25;
      avMats[k][1].map.offset.x = ((avFrame + 2) % 4)*0.25;
    }
  }
  sizeAvatars(now);
  project();
  renderer.render(scene, camera);
})();
</script>
"""

def _ink(hexcol):
    """Dark or white text, whichever actually reads on this colour."""
    h = hexcol.lstrip("#")
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "#15202e"

    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return "#15202e" if lum > 0.34 else "#ffffff"


def _plan_html():
    """The same property flat, every label readable without turning anything.

    The model answers "how do these buildings join up"; this answers "what is
    on level 3 of building 2 right now", which is the question somebody has
    when they are standing at a desk with a radio in their hand.
    """
    per_bld = collections.defaultdict(lambda: collections.defaultdict(list))
    for b in boxes:
        per_bld[b["bld"]][b["level"]].append(b)
    fac_by = collections.defaultdict(lambda: collections.defaultdict(list))
    for f in facils:
        fac_by[f["bld"]][f["level"]].append(f)

    # Avatars stand on top of their room's tile, so with them on each row
    # gets the headroom to hold one without reaching into the row above.
    row_px = 84 if AV_MODE != "off" else 62
    pad = 26 if AV_MODE != "off" else 0
    at_door = collections.defaultdict(list)
    for p in people:
        at_door[p["code"]].append(p)
    out = []
    for bld in (3, 1, 2):
        levels = set(per_bld[bld]) | set(fac_by[bld])
        if not levels:
            continue
        xs = [b["x"] for b in boxes if b["bld"] == bld]
        xs += [f["x"] for f in facils if f["bld"] == bld]
        lo, hi = min(xs), max(xs)
        span = max(hi - lo, 1.0)
        width_px = int(span / pmap.DOOR_W * 82) + 170
        out.append(f'<div class="pb"><h4>Building {bld}</h4>')
        for lv in sorted(levels, key=lambda l: -pmap.LEVEL_IX[l]):
            rs = per_bld[bld].get(lv, [])
            fs = fac_by[bld].get(lv, [])
            rows = [x["row"] for x in rs] + [x["row"] for x in fs] or [0]
            h = int((max(rows) - min(rows)) * row_px) + 74 + pad
            cells = []
            for r in sorted(rs, key=lambda r: r["x"]):
                # inset, or a box centred on 0% or 100% loses half itself
                left = 5 + (r["x"] - lo) / span * 90
                top = (r["row"] - min(rows)) * row_px + pad
                ink = _ink(r["colour"])
                meta = " · ".join(x for x in (r["svc_short"],
                                              f'{r["mins"]:.0f}m' if r["mins"] else "") if x)
                guy = ""
                for i, p in enumerate(at_door.get(r["code"], [])):
                    title = f'{p["name"]} · {ACT_LABEL.get(p["act"], "")}' + (
                        f' · {p["at"]}' if p["at"] else "")
                    guy += (f'<i class="av av-{p["key"]} pav" style="right:{-9 + i * 24}px" '
                            f'title="{html.escape(title)}"></i>')
                    if p["who"]:
                        guy += (f'<span class="ptag" style="background:{p["col"]};'
                                f'color:{_ink(p["col"])};top:{-17 - i * 15}px">'
                                f'{html.escape(p["who"])}</span>')
                cells.append(
                    f'<div class="pr" style="left:{left:.2f}%;top:{top}px;'
                    f'background:{r["colour"]};color:{ink};'
                    f'{"opacity:.5;" if not r["on_chart"] else ""}" '
                    f'title="{r["code"]} — {html.escape(r.get("hk") or "unassigned")}">'
                    f'{guy}<b>{r["code"]}</b>'
                    + (f'<i>{meta}</i>' if meta else '') + '</div>')
            for f in sorted(fs, key=lambda f: f["x"]):
                left = 5 + (f["x"] - lo) / span * 90
                top = (f["row"] - min(rows)) * row_px + pad
                cells.append(
                    f'<div class="pf k-{f["kind"]}" style="left:{left:.2f}%;'
                    f'top:{top + 8}px">{f["label"]}</div>')
            name = lv if lv in ("Plaza", "Terrace") else f"Level {lv}"
            out.append(
                f'<div class="pl"><span class="pn">{name}</span>'
                f'<span class="pc">{len(rs)} rooms</span></div>'
                f'<div class="pscroll"><div class="pp" '
                f'style="height:{h}px;min-width:{width_px}px">'
                f'{"".join(cells)}</div></div>')
        out.append('</div>')
    return "".join(out)


PLAN_CSS = """
<style>
.pb{margin:0 0 26px}
.pb h4{margin:0 0 8px;font-size:1rem;font-weight:800;color:#1e3350;
  border-bottom:2px solid #d8e0ea;padding-bottom:5px}
.pl{display:flex;align-items:baseline;gap:9px;margin:12px 0 3px}
.pn{font-weight:800;font-size:.84rem;color:#33455c}
.pc{font-size:.72rem;color:#8794a4}
.pscroll{overflow-x:auto;padding-bottom:5px}
.pp{position:relative;background:#f4f7fa;border:1px solid #e2e8f0;
  border-radius:9px}
.pr{position:absolute;transform:translateX(-50%);width:66px;height:50px;
  border-radius:6px;display:flex;flex-direction:column;align-items:center;
  justify-content:center;box-shadow:0 1px 2px rgba(20,35,55,.14);
  border:1px solid rgba(20,35,55,.14)}
.pr b{font-size:.74rem;font-weight:800;font-family:ui-monospace,Menlo,monospace;
  letter-spacing:-.01em;line-height:1.1}
.pr i{font-size:.6rem;font-style:normal;opacity:.82;line-height:1.2;
  white-space:nowrap}
.pr i.pav{position:absolute;right:-9px;top:-28px;opacity:1;z-index:2}
.ptag{position:absolute;left:-6px;top:-17px;font-size:.56rem;font-weight:800;
  padding:1px 6px;border-radius:999px;white-space:nowrap;max-width:60px;overflow:hidden;
  text-overflow:ellipsis;border:1.5px solid #fff;box-shadow:0 1px 3px rgba(20,35,55,.25);
  z-index:3;line-height:1.35}
.pf{position:absolute;transform:translateX(-50%);font-size:.58rem;
  font-weight:700;padding:3px 6px;border-radius:5px;white-space:nowrap;
  background:#dfe6ee;color:#43566c;border:1px solid #cbd6e2}
.pf.k-lift_svc{background:#334759;color:#fff;border-color:#26374a}
.pf.k-lift_guest{background:#5a6f85;color:#fff;border-color:#4a5d71}
.pf.k-trash{background:#7a6a55;color:#fff;border-color:#665843}
.pf.k-laundry{background:#b06fb0;color:#fff;border-color:#965996}
.pf.k-closet{background:#2f8f86;color:#fff;border-color:#26766e}
.pf.k-office{background:#c2452f;color:#fff;border-color:#a53a27}
.pf.k-breakroom{background:#c98a2e;color:#fff;border-color:#ab7426}
.pf.k-lockers{background:#a8862f;color:#fff;border-color:#8d7027}
.pf.k-stairs{background:#8895a5;color:#fff;border-color:#74818f}
.pf.k-amenity{background:#e7edf3;color:#4a5c70;border-color:#d2dce6}
</style>
"""

# One sprite stylesheet for the plan, the game bar and the cast below it:
# whatever is on screen, plus the neutral faces the bar and the cast use.
CAST = [a for a in av.ORDER if AV_MODE == "all" or a in av.LIVE]
AV_CSS = ""
if AV_MODE != "off":
    AV_CSS = av.sprite_css(set(AV_KEYS) | {av.key("n", a) for a in av.ORDER}, 24, 32)
    st.markdown(f"<style>{AV_CSS}{GAME_CSS}</style>{_game_bar()}",
                unsafe_allow_html=True)

if flat:
    st.markdown(PLAN_CSS + _plan_html(), unsafe_allow_html=True)
else:
    components.html(HTML.replace("__PAYLOAD__", payload), height=800,
                    scrolling=False)

# ---------------------------------------------------------------- legend
def _chip(colour, label):
    return (f'<span style="display:inline-flex;align-items:center;gap:6px;'
            f'margin-right:14px;font-size:.78rem;color:#42536a">'
            f'<i style="width:11px;height:11px;border-radius:3px;'
            f'background:{colour};display:inline-block"></i>{label}</span>')


if MODE == "status":
    chips = "".join(_chip(v[2], v[0]) for v in _rst.META.values())
elif MODE == "service":
    chips = "".join(_chip(c, f"{SVC_SHORT.get(s, s)} — {s}")
                    for s, c in SVC_COLOUR.items())
else:
    chips = "".join(_chip(c, f"Building {b}") for b, c in BLD_COLOUR.items())
chips += _chip(OFF_TODAY, T("prop.off_today"))
st.markdown(f'<div style="margin:6px 0 4px">{chips}</div>', unsafe_allow_html=True)

# The service core gets its own row: it is a different kind of thing from a
# room, and mixing the two legends made both harder to read.
core_chips = "".join(_chip(c, l) for c, l in [
    ("#12764a", "Bridge"), ("#334759", "Service lift"),
    ("#5a6f85", "Guest lift"), ("#b06fb0", "Laundry & ice"),
    ("#2f8f86", "Refill closet"), ("#7a6a55", "Trash chute"),
    ("#c2452f", "Housekeeping office"), ("#c98a2e", "Breakroom & lockers"),
    ("#8895a5", "Stairs"), ("#9fb4c9", "Amenity"),
])
st.markdown(f'<div style="margin:0 0 4px">{core_chips}</div>',
            unsafe_allow_html=True)
if AV_MODE != "off":
    cast = "".join(f'<span><i class="av av-{av.key("n", a)}"></i>{ACT_LABEL[a]}</span>'
                   for a in CAST)
    st.markdown(f'<div style="margin:8px 0 2px;font-size:.8rem;font-weight:700;'
                f'color:#33455c">{T("prop.av_cast")}</div>'
                f'<div class="avcast">{cast}</div>', unsafe_allow_html=True)


def _looks_editor():
    """Managers say how each person is drawn. Nobody is guessed from a name."""
    import pandas as pd
    stored = _looks(st.session_state.get("prop_av_gen", 0))
    names = {n for d in today.values() for n in (d.get("hk"), d.get("rqs"))
             if av.is_person(n)}
    names |= {r.get("housekeeper") for r in statuses.values()
              if av.is_person(r.get("housekeeper"))}
    names |= set(stored)
    if not names:
        st.caption(T("prop.av_none"))
        return
    df = pd.DataFrame({"Person": sorted(names, key=str.lower)})
    df["Look"] = [av.LOOKS[av.look_of(stored, n)] for n in df["Person"]]
    st.caption(T("prop.av_looks_help"))
    with st.form("prop_av_form", border=False):
        ed = st.data_editor(
            df, hide_index=True, disabled=["Person"],
            key=f"prop_av_ed_{st.session_state.get('prop_av_gen', 0)}",
            column_config={"Look": st.column_config.SelectboxColumn(
                options=list(av.LOOKS.values()), required=True)})
        if st.form_submit_button(T("prop.av_save")):
            code = {v: k for k, v in av.LOOKS.items()}
            # neutral is the default, so only a real choice is stored
            new = {p: code[l] for p, l in zip(ed["Person"], ed["Look"])
                   if code.get(l, "n") != "n"}
            try:
                db._upsert_key(av.SETTING_KEY, new)
            except Exception as ex:
                st.error(str(ex))
                return
            st.session_state["prop_av_gen"] = st.session_state.get("prop_av_gen", 0) + 1
            _looks.clear()
            st.toast(T("prop.av_saved"))
            st.rerun()


if AV_MODE != "off" and auth.can("can_manage_users"):
    with st.expander(T("prop.av_looks")):
        _looks_editor()
st.markdown(
    f'<div style="margin:0 0 18px;font-size:.76rem;color:#7b8798">'
    f'{T("prop.size_note")}</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- the facts
st.markdown("#### " + T("prop.getting_around"))
a, b = st.columns(2)
with a:
    st.markdown(f"""
**{T("prop.bridges_title")}**

- Building 1 ↔ 2 — Plaza, Terrace, Level 1, Level 2
- Building 1 ↔ 3 — Plaza and Level 1 only
- Building 2 ↔ 3 — **no bridge.** Everything goes through building 1.

Building 1 Level 1 has no guest rooms — lobby, pool and spa — but it is the
only level that bridges both ways, so it is the crossroads of the property.
""")
with b:
    rows = "".join(
        f"<tr><td style='padding:4px 10px 4px 0;font-family:monospace;font-size:.8rem'>"
        f"{p['a']} → {p['b']}</td>"
        f"<td style='padding:4px 10px 4px 0;font-size:.8rem;color:#5b6b7e'>{p['why']}</td>"
        f"<td style='padding:4px 0;text-align:right;font-family:monospace;font-size:.8rem'>"
        f"{pmap.travel_seconds(p['a'], p['b'])/60:.1f} min</td></tr>"
        for p in [
            {"a": "1222E", "b": "1222F", "why": "next door"},
            {"a": "1222E", "b": "1226B", "why": "far end, same level"},
            {"a": "1222E", "b": "1322E", "why": "one level up"},
            {"a": "1222E", "b": "2232E", "why": "building 2, flat bridge"},
            {"a": "2232E", "b": "3240A", "why": "building 2 to 3"},
        ])
    st.markdown(f"**{T('prop.costs_title')}**", unsafe_allow_html=True)
    st.markdown(f"<table style='width:100%'>{rows}</table>", unsafe_allow_html=True)

st.caption(T("prop.caveat"))
