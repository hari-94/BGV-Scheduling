"""Property (preview) — the resort under live weather, and the rooms beneath it.

This is the weather build, kept beside the live Property page rather than on
top of it so the two can be compared before either replaces the other. It is
deliberately not in `ui.NAV_ITEMS`: reach it at /Property_Preview.

Two views, one scene. The primary one is the property as it looks right now --
real massing off the floor plans, a sky driven by the sun's elevation at the
property's own local time, and whatever is falling out of it according to
Open-Meteo. The button strips all of that away and leaves the room grid the
live page already draws, which is the view that answers questions about work.

Original docstring follows.

Property — the building itself, in three dimensions, coloured by what is done.

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
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, db, clock, i18n
import property_map as pmap
import roomstatus as _rst
import streamlit.components.v1 as components
import ui

st.set_page_config(page_title="Property preview", page_icon="🌦️",
                   layout="wide")
# Same width family as the rest of the app, and unconditional: the plan
# view's stylesheet only renders in 2-D, so a cap in there would leave the
# 3-D view stretched across a big monitor.
st.markdown("<style>.block-container{max-width:min(1200px,97%);}</style>",
            unsafe_allow_html=True)
auth.require_login()
ui.topnav("Property")
st.caption(
    "Preview build — live weather over the real massing. The live Property "
    "page is unchanged.")

T = i18n.t

if not auth.can("can_view_insp_tab"):
    st.warning(T("prop.no_access"))
    st.stop()


@st.cache_data(ttl=3600, show_spinner=False)
def _inventory():
    return db.all_known_rooms()


@st.cache_data(ttl=20, show_spinner=False)
def _statuses(_gen):
    return db.get_room_statuses()


@st.cache_data(ttl=20, show_spinner=False)
def _today(_gen):
    """What each room is actually down for today: service, minutes, who has it.

    The inventory says the building exists; only the day's schedule says a room
    is a 140-minute Full Clean rather than a Dust n Vac touch-up, and that is
    what the boxes are sized and labelled by.
    """
    sched = db.load_full_schedule() or {}
    out = {}
    for g in (sched.get("groups_data") or []):
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


rooms = _inventory()
if not rooms:
    st.info(T("prop.no_rooms"))
    st.stop()

boxes = pmap.layout(rooms)
spans = pmap.bridge_spans()
gen = st.session_state.get("prop_gen", 0)
statuses = _statuses(gen)
today = _today(gen)

# ---------------------------------------------------------------- controls
c1, c2, c3 = st.columns([2.6, 1.2, 2.6])
with c1:
    colour_by = st.radio(T("prop.colour"),
                         [T("prop.by_status"), T("prop.by_service"),
                          T("prop.by_building")],
                         horizontal=True, key="prop_colour")
with c2:
    # The weather view is the primary one, so it is on by default. Turning it
    # off leaves exactly the scene the live page draws.
    weather_on = st.toggle("Weather view", value=True, key="prev_weather")
    flat = st.toggle(T("prop.flat"), value=False, key="prop_flat")
    show_extras = st.toggle(T("prop.show_amenities"), value=True, key="prop_extras")
    if st.button(T("prop.refresh"), use_container_width=True):
        st.session_state["prop_gen"] = st.session_state.get("prop_gen", 0) + 1
        _statuses.clear()
        _today.clear()
        st.rerun()
with c3:
    done = sum(1 for b in boxes
               if _rst.normalise((statuses.get(b["code"]) or {}).get("status"))
               in (_rst.INSPECTED, _rst.DONE, _rst.ALREADY_CLEAN))
    st.markdown(
        f'<div style="padding-top:6px;color:#5b6b7e;font-size:.86rem">'
        f'<b>{len(boxes)}</b> rooms · <b>{len(today)}</b> on a chart today · '
        f'<b>{done}</b> finished · <b>{len(spans)}</b> bridges</div>',
        unsafe_allow_html=True)

# ── weather and time ───────────────────────────────────────────────────
# Live is the point of the page; the rest are there so somebody can see what a
# storm or a sunrise looks like without waiting for one.
# ?sky=Snow&time=Midday deep-links a state, which is how a storm gets shown to
# somebody who is not standing in one.
_q = st.query_params
SKIES = ["Live", "Clear", "Cloudy", "Rain", "Snow", "Heavy snow"]
TIMES = ["Now", "Dawn", "Midday", "Sunset", "Night"]


def _from_q(name, options):
    want = (_q.get(name) or "").strip().lower()
    for i, o in enumerate(options):
        if o.lower() == want:
            return i
    return 0


w1, w2, w3 = st.columns([1.5, 1.5, 3])
with w1:
    wx_mode = st.selectbox("Sky", SKIES, index=_from_q("sky", SKIES),
                           key="prev_wx")
with w2:
    _now = clock.now()
    time_mode = st.selectbox("Time", TIMES, index=_from_q("time", TIMES),
                             key="prev_time")
with w3:
    st.caption("Live reads Open-Meteo for Peak 8 (39.49 N, 106.05 W). "
               "Time follows the property's own clock unless you pick one.")

HOURS = {"Dawn": 6.4, "Midday": 13.0, "Sunset": 19.1, "Night": 23.0}
hour_now = _now.hour + _now.minute / 60.0
hour = HOURS.get(time_mode, hour_now)

MODE = ("status" if colour_by == T("prop.by_status")
        else "service" if colour_by == T("prop.by_service") else "bld")

# roomstatus owns the vocabulary and the colours; the model must not invent
# its own or the legend here stops matching the phone in somebody's hand.
STATUS_COLOUR = {k: v[2] for k, v in _rst.META.items()}
BLD_COLOUR = {1: "#5b8cd6", 2: "#c07a3e", 3: "#4e9e78"}
SVC_COLOUR = {"Full Clean": "#2563a8", "Full Clean (IH)": "#6d5bb5",
              "Daily Service": "#0f766e", "Dust n Vac": "#b45309"}
SVC_SHORT = {"Full Clean": "FC", "Full Clean (IH)": "IH",
             "Daily Service": "DS", "Dust n Vac": "DV"}
OFF_TODAY = "#c3ccd8"        # in the building, not on a chart today


def _massing(boxes):
    """The buildings as solids rather than as a box per bedroom.

    The weather view needs walls and roofs. Each building is reduced to its
    footprint and the levels stacked inside it, and the room positions are kept
    per level and per side of the corridor -- that is where the windows and the
    balconies go, one window per real room, so the elevation counts out the
    same as the floor plan.
    """
    per = {}
    for b in boxes:
        m = per.setdefault(b["bld"], {"bld": b["bld"], "x0": 1e9, "x1": -1e9,
                                      "levels": {}})
        m["x0"] = min(m["x0"], b["x"])
        m["x1"] = max(m["x1"], b["x"])
        lv = m["levels"].setdefault(b["level"], {"y": b["y"], "n": [], "s": []})
        (lv["n"] if b["side"] < 0 else lv["s"]).append(b["x"])
    out = []
    for m in per.values():
        levels = sorted(m["levels"].values(), key=lambda l: l["y"])
        out.append({"bld": m["bld"], "x0": m["x0"], "x1": m["x1"],
                    "levels": levels})
    return sorted(out, key=lambda m: m["x0"])


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

# Everything that is not a guest room. The service core is what a housekeeper's
# day is actually spent walking between, so it is drawn by default; the amenity
# volumes are what make the levels with no guest rooms stop being blank rows.
_levels = {(b["bld"], b["level"]) for b in boxes}
facils = pmap.facilities(_levels)
cores = pmap.service_cores(_levels)
if not show_extras:
    facils = [f for f in facils if f["kind"] != "amenity"]

payload = json.dumps({"boxes": boxes, "spans": spans,
                      "facils": facils, "cores": cores,
                      "levels": pmap.LEVELS,
                      "doorW": pmap.DOOR_W, "levelH": pmap.LEVEL_H,
                      "hallD": pmap.HALL_D,
                      "mass": _massing(boxes),
                      "weather": bool(weather_on),
                      "wx": wx_mode, "hour": round(hour, 3),
                      "today": _now.date().isoformat()},
                     separators=(",", ":"))

HTML = """
<div id="wrap">
  <div id="hud">
    <div id="hint">drag to turn · two fingers or wheel to zoom · right-drag to pan</div>
    <div id="pick"></div>
  </div>
  <div id="labels"></div>
  <canvas id="cv"></canvas>
</div>
<style>
  html,body{margin:0;padding:0;overflow:hidden;background:transparent}
  #wrap{position:relative;width:100%;height:620px;border-radius:16px;
    overflow:hidden;background:linear-gradient(180deg,#eef3f9 0%,#dfe7f1 100%);
    border:1px solid #d6dfea;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
  #cv{display:block;width:100%;height:100%;touch-action:none}
  #hud{position:absolute;left:12px;top:10px;z-index:3;pointer-events:none}
  #hint{font-size:.68rem;letter-spacing:.03em;color:#64748b;background:rgba(255,255,255,.8);
    padding:4px 9px;border-radius:7px;display:inline-block}
  #pick{margin-top:7px;font-size:.8rem;color:#16202e;background:rgba(255,255,255,.94);
    padding:7px 11px;border-radius:9px;display:none;box-shadow:0 4px 16px rgba(22,32,46,.15)}
  #pick b{font-size:.95rem}
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
function labelMat(code, svc, hex, forceDark, square){
  const k = code+"|"+svc+"|"+hex+"|"+(forceDark||0)+"|"+(square||0);
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

const meshes = [];
DATA.boxes.forEach(b=>{
  const d = RD * b.depth;
  let geo, z;
  if(b.wing){
    /* an end wing sits across the corridor line; its row is what separates it
       from its neighbours, so it keeps that and shows its size along x -- and
       only gently, or it reaches the main row beside it */
    geo = new THREE.BoxGeometry(RW*(0.85 + 0.3*(b.depth-0.62)/0.84), RH, RD*0.92);
    z = b.row * DATA.hallD;
  } else {
    /* grow away from the corridor, never across it */
    geo = new THREE.BoxGeometry(RW, RH, d);
    z = DATA.hallD*0.5 + b.side * (HALF_HALL + d*0.5);
  }
  const plain = mat(b.colour, b.on_chart ? 0.96 : 0.55);
  const face = labelMat(b.code, b.svc_short, b.colour, 0, 1);
  /* The number goes on the OUTWARD-FACING SIDE, not the lid. A lid is hidden
     the moment another level sits above it, which is every level but the top
     one -- the labels were invisible on all six floors that matter. The side
     a room faces is the side it is on: north rooms show on -Z, south rooms on
     +Z, and an end wing shows on whichever end of the building it sits at.
     BoxGeometry material order is +X -X +Y -Y +Z -Z. */
  const mid = (minX + maxX) / 2;
  let mats6;
  if(b.wing){
    mats6 = (b.x > mid) ? [face,plain,plain,plain,plain,plain]
                        : [plain,face,plain,plain,plain,plain];
  } else {
    mats6 = (b.side > 0) ? [plain,plain,plain,plain,face,plain]
                         : [plain,plain,plain,plain,plain,face];
  }
  const m = new THREE.Mesh(geo, mats6);
  m.position.set(b.x, b.y, z);
  m.castShadow = true; m.receiveShadow = true;
  m.userData = b;
  root.add(m); meshes.push(m);
  const e = new THREE.LineSegments(new THREE.EdgesGeometry(geo),
    new THREE.LineBasicMaterial({color:0x2b3a4a, transparent:true, opacity:0.2}));
  e.position.copy(m.position); root.add(e);
});

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
  if(drag.pan){ panX-=dx*dist*0.0016; panY+=dy*dist*0.0016; }
  else { yaw-=dx*0.007; pitch=Math.max(-0.25, Math.min(1.45, pitch+dy*0.006)); }
  place();
});
cv.addEventListener("pointerup", e=>{ drag=null; });
cv.addEventListener("pointercancel", ()=>{ drag=null; });
cv.addEventListener("contextmenu", e=>e.preventDefault());
cv.addEventListener("wheel", e=>{
  e.preventDefault();
  dist = Math.max(28, Math.min(900, dist * (1 + Math.sign(e.deltaY)*0.09)));
  place();
}, {passive:false});
cv.addEventListener("touchmove", e=>{
  if(e.touches.length===2){
    e.preventDefault();
    const a=e.touches[0], b=e.touches[1];
    const d=Math.hypot(a.clientX-b.clientX, a.clientY-b.clientY);
    if(lastTouchDist) dist=Math.max(28, Math.min(900, dist*(lastTouchDist/d)));
    lastTouchDist=d; place();
  }
}, {passive:false});
cv.addEventListener("touchend", ()=>{ lastTouchDist=0; });

/* ---- tap a room to read it ---- */
const ray = new THREE.Raycaster();
cv.addEventListener("click", e=>{
  const r=cv.getBoundingClientRect();
  const v=new THREE.Vector2(((e.clientX-r.left)/r.width)*2-1,
                            -((e.clientY-r.top)/r.height)*2+1);
  ray.setFromCamera(v, camera);
  const hit = ray.intersectObjects(meshes)[0];
  if(!hit){ pick.style.display="none"; return; }
  const d = hit.object.userData;
  pick.style.display="block";
  if(d.bridge){
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
    } else {
      line2 = "<br><span>not on a chart today</span>";
    }
    pick.innerHTML = "<b>"+d.code+"</b> <span>"+where+"</span>"+line2;
  }
});

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

(function loop(){
  requestAnimationFrame(loop);
  project();
  renderer.render(scene, camera);
})();
</script>
<script>
/* ── The resort under whatever the sky is doing ─────────────────────────────
   Two views share one scene. This builds the primary one -- the property as a
   solid, under a sky driven by the sun's elevation at the property's own local
   time, with whatever Open-Meteo says is falling out of it. The button hands
   the scene back to the room grid the live page draws, which is `root`.

   The massing is not invented. Every wall runs between the first and last door
   on that level of that building, and every window is a real room in its real
   place along the corridor, so the elevation counts out the same as the floor
   plan. What is invented is what the plans do not carry: the roof pitch, the
   cladding, the colour of the stone.

   Three things here were learned the hard way on an earlier build and are
   load-bearing:

   * An ExtrudeGeometry runs 0..depth along its own z. Centre it before turning
     it, or the roof lands half a building away from the walls it belongs to.
   * Snow on a pitched roof is a second prism of the same shape, slightly
     smaller and lifted straight up -- not two tilted slabs. Slabs positioned by
     eye either bury themselves in the roof or stand off it like blades.
   * The ground stays flat. A plane tilted a few degrees over a thousand units
     rises far enough at its near edge to hide the entire resort behind a sheet
     of white, and it looks like a slope from exactly one angle.
*/
(function () {
  if (!DATA.weather) return;

  /* ── the scene hands itself over ───────────────────────────────────── */
  root.visible = false;
  labels.style.display = "none";
  scene.remove(key);
  scene.remove(rim);

  var W = DATA.doorW, LH = DATA.levelH, HD = DATA.hallD;
  var GY = -LH * 1.35;                      /* the ground the buildings stand on */
  var real = new THREE.Group();
  real.position.copy(root.position);
  scene.add(real);

  function rnd(seed) {
    var s = seed;
    return function () { s = (s * 9301 + 49297) % 233280; return s / 233280; };
  }
  var R = rnd(8081);

  function mat(hex, op) {
    return new THREE.MeshLambertMaterial({
      color: new THREE.Color(hex),
      transparent: op !== undefined && op < 1,
      opacity: op === undefined ? 1 : op});
  }
  function box(w, h, d, m) {
    return new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m);
  }
  function add(m, x, y, z, sh) {
    m.position.set(x, y, z);
    if (sh !== false) { m.castShadow = true; m.receiveShadow = true; }
    real.add(m); return m;
  }

  var SNOW   = mat("#fbfdff"),
      CEDAR  = mat("#b5661f"), PANEL = mat("#867f78"), PANEL2 = mat("#9a938b"),
      ROOF   = mat("#44413e"),
      GLASS  = mat("#1d2830"), RAILG = mat("#8aa8bd", 0.5),
      SOFFIT = mat("#3f3a35"), STEEL = mat("#4a4f55"),
      PINE   = mat("#16301f"), PINE2 = mat("#1e3f2b"), TRUNK = mat("#3b2e23");

  /* ── cladding, drawn once and repeated at a real size on every wall ── */
  function siding(base, hi, lo) {
    var c = document.createElement("canvas");
    c.width = 64; c.height = 128;
    var g = c.getContext("2d");
    g.fillStyle = base; g.fillRect(0, 0, 64, 128);
    for (var i = 0; i < 10; i++) {
      var y = i * 12.8;
      g.fillStyle = hi; g.fillRect(0, y + 1, 64, 4);
      g.fillStyle = lo; g.fillRect(0, y + 11, 64, 1.8);
    }
    for (var j = 0; j < 80; j++) {
      g.fillStyle = "rgba(40,22,8," + (0.04 + Math.random() * 0.08) + ")";
      g.fillRect(Math.random() * 64, Math.random() * 128, 5 + Math.random() * 18, 1);
    }
    var t = new THREE.CanvasTexture(c);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    return t;
  }
  function stoneTex() {
    var c = document.createElement("canvas");
    c.width = 256; c.height = 256;
    var g = c.getContext("2d");
    g.fillStyle = "#6f6659"; g.fillRect(0, 0, 256, 256);
    for (var r = 0; r < 8; r++) {
      var x = -Math.random() * 40;
      while (x < 256) {
        var w2 = 26 + Math.random() * 34, v = 104 + Math.random() * 36;
        g.fillStyle = "rgb(" + Math.round(v) + "," + Math.round(v * 0.95)
                    + "," + Math.round(v * 0.86) + ")";
        g.fillRect(x + 1.4, r * 32 + 1.4, w2 - 2.8, 29.2);
        x += w2;
      }
    }
    var t = new THREE.CanvasTexture(c);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    return t;
  }
  var CEDAR_TEX = siding("#b5661f", "rgba(255,214,160,0.16)", "rgba(46,22,4,0.34)"),
      PANEL_TEX = siding("#867f78", "rgba(255,255,255,0.12)", "rgba(20,20,20,0.26)"),
      STONE_TEX = stoneTex();

  function clad(tex, w, h, sx, sy) {
    var t = tex.clone();
    t.needsUpdate = true;
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(Math.max(1, Math.round(w / (sx || 7))),
                 Math.max(1, Math.round(h / (sy || 3.2))));
    return new THREE.MeshLambertMaterial({map: t});
  }

  var MX0 = 1e9, MX1 = -1e9;
  (DATA.mass || []).forEach(function (m) {
    MX0 = Math.min(MX0, m.x0); MX1 = Math.max(MX1, m.x1);
  });
  if (MX0 > MX1) { MX0 = 0; MX1 = 200; }
  var MIDX = (MX0 + MX1) / 2, SPAN = MX1 - MX0;
  var WALL_D = HD * 2.5, MIDZ = HD * 0.5, FRONT = MIDZ + WALL_D / 2;

  /* ── the snowfield ─────────────────────────────────────────────────── */
  var gc = document.createElement("canvas");
  gc.width = gc.height = 512;
  var gx = gc.getContext("2d");
  gx.fillStyle = "#eff5fb"; gx.fillRect(0, 0, 512, 512);
  for (var gi = 0; gi < 240; gi++) {
    var cx0 = Math.random() * 512, cy0 = Math.random() * 512,
        gr = 24 + Math.random() * 74;
    var gg = gx.createRadialGradient(cx0, cy0, 0, cx0, cy0, gr);
    var tint = Math.random() < 0.55 ? "196,213,232" : "255,255,255";
    gg.addColorStop(0, "rgba(" + tint + ",0.7)");
    gg.addColorStop(1, "rgba(" + tint + ",0)");
    gx.fillStyle = gg;
    gx.fillRect(cx0 - gr, cy0 - gr, gr * 2, gr * 2);
  }
  for (var ci = 0; ci < 512; ci += 7) {
    gx.fillStyle = "rgba(190,208,228,0.30)";
    gx.fillRect(ci, 0, 2.4, 512);        /* the groomer's corduroy */
  }
  var gTex = new THREE.CanvasTexture(gc);
  gTex.wrapS = gTex.wrapT = THREE.RepeatWrapping;
  gTex.repeat.set(16, 16);
  var GROUND = new THREE.MeshLambertMaterial({map: gTex, color: 0xcfdeed});
  var ground = new THREE.Mesh(new THREE.PlaneGeometry(4000, 4000), GROUND);
  ground.rotation.x = -Math.PI / 2;
  ground.position.set(MIDX, GY, MIDZ);
  ground.receiveShadow = true;
  real.add(ground);

  var PLAZA = mat("#9aa0a6");
  var plaza = new THREE.Mesh(new THREE.PlaneGeometry(SPAN * 1.05, 34), PLAZA);
  plaza.rotation.x = -Math.PI / 2;
  plaza.position.set(MIDX, GY + 0.14, FRONT + 19);
  plaza.receiveShadow = true;
  real.add(plaza);

  /* ── the range behind ──────────────────────────────────────────────── */
  var ridges = [];
  function ridge(back, height, colour, seed, jag) {
    var n = 78, rr = rnd(seed);
    var shape = new THREE.Shape();
    var w = SPAN * 14, x0 = MIDX - w / 2;
    shape.moveTo(x0, -SPAN);
    for (var i = 0; i <= n; i++) {
      var t = i / n;
      var h = height * (0.30 + 0.70 * Math.abs(Math.sin(t * jag + seed)))
              * (0.70 + 0.30 * rr());
      shape.lineTo(x0 + t * w, h);
    }
    shape.lineTo(x0 + w, -SPAN); shape.lineTo(x0, -SPAN);
    var m = new THREE.Mesh(new THREE.ShapeGeometry(shape),
                           new THREE.MeshBasicMaterial({color: colour}));
    m.position.set(0, GY, MIDZ - back);
    m.userData.base = new THREE.Color(colour);
    ridges.push(m);
    real.add(m);
  }
  ridge(3400, 900, "#c3d6e8", 5, 7.3);
  ridge(2900, 700, "#adc4dc", 19, 9.1);
  ridge(2350, 470, "#8fa6b4", 31, 6.2);
  ridge(1850, 320, "#5d7a68", 43, 8.4);
  ridge(1400, 215, "#3a5a46", 57, 11.0);

  /* ── the forest, which is what a white roof reads against ──────────── */
  var coneGeo = new THREE.ConeGeometry(1, 1, 8);
  var trunkGeo = new THREE.CylinderGeometry(0.16, 0.24, 1, 5);
  (function forest() {
    var N = 1000;
    var cones = new THREE.InstancedMesh(coneGeo, PINE, N);
    var cone2 = new THREE.InstancedMesh(coneGeo, PINE2, N);
    var caps = new THREE.InstancedMesh(coneGeo, SNOW, N);
    var trunks = new THREE.InstancedMesh(trunkGeo, TRUNK, N);
    var d = new THREE.Object3D(), k = 0, guard = 0, nil = new THREE.Matrix4();
    nil.makeScale(0, 0, 0);
    while (k < N && guard < N * 16) {
      guard++;
      var x, z;
      if (Math.random() < 0.70) {
        x = MIDX + (Math.random() - 0.5) * SPAN * 3.0;
        z = MIDZ - 46 - Math.random() * 700;
      } else {
        x = MIDX + (Math.random() < 0.5 ? -1 : 1)
                 * (SPAN * 0.78 + Math.random() * SPAN * 1.5);
        z = MIDZ - 900 + Math.random() * 1000;
      }
      if (x > MX0 - 110 && x < MX1 + 110 && z > MIDZ - 42 && z < FRONT + 520) continue;
      if (Math.abs(x - (MIDX + SPAN * 0.66)) < 90 && z > MIDZ - 60) continue;
      /* the ground climbs away from the resort, so the trees climb with it */
      var up = Math.min(96, Math.max(0, MIDZ - z) * 0.105);
      var h = 12 + Math.random() * 14, r = h * 0.23;
      d.position.set(x, GY + up + h * 0.5, z); d.scale.set(r, h, r);
      d.rotation.set(0, Math.random() * 3, 0); d.updateMatrix();
      if (Math.random() < 0.5) { cones.setMatrixAt(k, d.matrix); cone2.setMatrixAt(k, nil); }
      else { cone2.setMatrixAt(k, d.matrix); cones.setMatrixAt(k, nil); }
      d.position.set(x, GY + up + h * 0.86, z);
      d.scale.set(r * 0.44, h * 0.26, r * 0.44);
      d.updateMatrix(); caps.setMatrixAt(k, d.matrix);
      d.position.set(x, GY + up + 2.0, z); d.scale.set(1, 4.2, 1);
      d.updateMatrix(); trunks.setMatrixAt(k, d.matrix);
      k++;
    }
    cones.castShadow = true; cone2.castShadow = true;
    [cones, cone2, caps, trunks].forEach(function (m) { m.count = k; real.add(m); });
  })();

  /* ── a gable roof, wherever one is wanted ──────────────────────────── */
  function gable(cx, cy, cz, halfW, rise, len, axis) {
    var tri = new THREE.Shape();
    tri.moveTo(-halfW, 0); tri.lineTo(0, rise); tri.lineTo(halfW, 0);
    tri.lineTo(-halfW, 0);
    var g = new THREE.ExtrudeGeometry(tri, {depth: len, bevelEnabled: false});
    g.translate(0, 0, -len / 2);              /* centre before turning */
    if (axis === "x") g.rotateY(Math.PI / 2);
    var m = new THREE.Mesh(g, ROOF);
    m.position.set(cx, cy, cz);
    m.castShadow = true; m.receiveShadow = true;
    real.add(m);

    var k = 0.86, lift = rise * (1 - k) + 0.30;
    var st = new THREE.Shape();
    st.moveTo(-halfW * k, 0); st.lineTo(0, rise * k); st.lineTo(halfW * k, 0);
    st.lineTo(-halfW * k, 0);
    var sg = new THREE.ExtrudeGeometry(st, {depth: len * 1.02, bevelEnabled: false});
    sg.translate(0, 0, -len * 1.02 / 2);
    if (axis === "x") sg.rotateY(Math.PI / 2);
    var snow = new THREE.Mesh(sg, SNOW);
    snow.position.set(cx, cy + lift, cz);
    snow.castShadow = true; snow.receiveShadow = true;
    real.add(snow);

    if (axis === "x") {
      var cap = box(len * 1.02, 0.5, 0.7, ROOF);
      cap.position.set(cx, cy + lift + rise * k + 0.16, cz);
      cap.receiveShadow = true;
      real.add(cap);
    }
  }

  /* ── the buildings ─────────────────────────────────────────────────── */
  (DATA.mass || []).forEach(function (m) {
    var pad = W * 1.8;
    var x0 = m.x0 - pad, x1 = m.x1 + pad;
    var wide = x1 - x0, midX = (x0 + x1) / 2;
    var levels = m.levels;
    if (!levels.length) return;
    var yBot = levels[0].y, yTop = levels[levels.length - 1].y;

    var baseH = (yBot - GY) + LH * 0.5;
    add(box(wide + W, baseH, WALL_D + 3.6, clad(STONE_TEX, wide, baseH * 2.4, 9, 3)),
        midX, GY + baseH / 2 - LH * 0.5, MIDZ);

    var wallA = clad(CEDAR_TEX, wide, LH), wallB = clad(PANEL_TEX, wide, LH);

    levels.forEach(function (lv, li) {
      var top = li === levels.length - 1;
      var dep = top ? WALL_D * 0.86 : WALL_D;
      add(box(wide, LH * 0.92, dep, li % 2 ? wallB : wallA), midX, lv.y, MIDZ);
      add(box(wide + 0.8, LH * 0.10, dep + 0.8, SOFFIT),
          midX, lv.y - LH * 0.46, MIDZ, false);

      [["n", -1], ["s", 1]].forEach(function (pair) {
        var side = pair[1], zf = MIDZ + side * (dep / 2);
        (lv[pair[0]] || []).forEach(function (rx) {
          add(box(W * 0.70, LH * 0.52, 0.5, GLASS), rx, lv.y + LH * 0.02,
              zf + side * 0.28, false);
          if (li > 0) {
            add(box(W * 0.96, 0.30, 2.9, SOFFIT), rx, lv.y - LH * 0.30,
                zf + side * 1.6);
            add(box(W * 0.96, LH * 0.30, 0.14, RAILG), rx, lv.y - LH * 0.14,
                zf + side * 3.0, false);
          }
        });
      });

      var bays = Math.max(2, Math.round(wide / (W * 4.4)));
      for (var bi = 1; bi < bays; bi++) {
        var bx = x0 + wide * bi / bays;
        [-1, 1].forEach(function (side) {
          add(box(W * 0.9, LH * 0.92, 0.55, li % 2 ? PANEL : PANEL2),
              bx, lv.y, MIDZ + side * (dep / 2 + 0.2), false);
        });
      }
    });

    var eave = 3.2, half = WALL_D / 2 + eave, rise = LH * 2.15;
    var ridgeY = yTop + LH * 0.46;
    gable(midX, ridgeY, MIDZ, half, rise, wide + W * 0.6, "x");

    var wings = Math.max(3, Math.round(wide / (W * 4.6)));
    for (var wi = 0; wi < wings; wi++) {
      var wx = x0 + wide * (wi + 0.5) / wings;
      var ww = W * (1.7 + R() * 0.8);
      var proj = W * (1.7 + R() * 1.1);
      var lift2 = LH * (0.10 + R() * 0.34);
      [1, -1].forEach(function (side) {
        if (side < 0 && R() < 0.42) return;
        var zf = MIDZ + side * (WALL_D / 2 + proj / 2 - 0.4);
        for (var t2 = 0; t2 < 2; t2++) {
          var lv2 = levels[levels.length - 1 - t2];
          if (!lv2) continue;
          var yy = lv2.y + (t2 === 0 ? lift2 : 0);
          add(box(ww * 2, LH * 0.92, proj, t2 % 2 ? wallB : wallA), wx, yy, zf);
          add(box(ww * 1.3, LH * 0.52, 0.5, GLASS), wx, yy + LH * 0.02,
              MIDZ + side * (WALL_D / 2 + proj - 0.1), false);
        }
        var glen = WALL_D / 2 + proj + eave * 0.8;
        gable(wx, ridgeY + lift2, MIDZ + side * (glen / 2 - 1.2),
              ww + eave * 0.6, rise * 0.88, glen, "z");
      });
    }

    var chs = Math.max(2, Math.round(wide / (W * 9)));
    for (var chi = 0; chi < chs; chi++) {
      var chx = x0 + wide * (chi + 0.5) / chs + (R() - 0.5) * W * 2;
      var chh = LH * (0.9 + R() * 0.5);
      add(box(W * 1.0, chh, W * 1.0, clad(STONE_TEX, W * 2, chh * 2, 4, 2.4)),
          chx, ridgeY + rise + chh * 0.30, MIDZ);
      add(box(W * 1.2, 0.5, W * 1.2, SNOW), chx,
          ridgeY + rise + chh * 0.80, MIDZ, false);
    }
  });

  (DATA.spans || []).forEach(function (s) {
    var w = Math.abs(s.x1 - s.x0);
    add(box(w, LH * 0.72, HD * 0.55, PANEL), (s.x0 + s.x1) / 2, s.y, MIDZ);
    add(box(w, LH * 0.40, HD * 0.58, GLASS), (s.x0 + s.x1) / 2,
        s.y + LH * 0.08, MIDZ, false);
    add(box(w, 0.5, HD * 0.62, SNOW), (s.x0 + s.x1) / 2,
        s.y + LH * 0.40, MIDZ, false);
  });

  /* ── the lift out of the plaza ─────────────────────────────────────── */
  var liftLights = [];
  (function lift() {
    var lx = MIDX + SPAN * 0.66, z0 = FRONT + 150, z1 = MIDZ - 1250, N = 9;
    var pts = [];
    for (var i = 0; i <= N; i++) {
      var f = i / N, z = z0 + (z1 - z0) * f, h = 26 + f * 5;
      add(box(2.0, h, 2.0, STEEL), lx, GY + h / 2, z);
      add(box(14, 1.1, 1.1, STEEL), lx, GY + h, z, false);
    }
    for (var j = 0; j <= 48; j++) {
      var f2 = j / 48;
      pts.push(new THREE.Vector3(lx - 6.0, GY + 25.4 + f2 * 5, z0 + (z1 - z0) * f2));
    }
    real.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts),
                            new THREE.LineBasicMaterial({color: 0x2a3037})));
    for (var c = 0; c < 16; c++) {
      var f3 = c / 16, z3 = z0 + (z1 - z0) * f3, y3 = GY + 25.4 + f3 * 5;
      add(box(0.36, 3.2, 0.36, STEEL), lx - 6.0, y3 - 1.6, z3, false);
      add(box(3.6, 0.55, 2.0, mat("#b1362c")), lx - 6.0, y3 - 3.4, z3, false);
    }
  })();

  /* ── windows that light up after dark ──────────────────────────────── */
  var WINDOW_LIT = new THREE.MeshBasicMaterial({color: 0xffd98a});
  var lit = [];
  real.traverse(function (o) {
    if (o.isMesh && o.material === GLASS && R() < 0.42) lit.push(o);
  });

  /* ── sky, sun, moon, stars ─────────────────────────────────────────── */
  var skyCv = document.createElement("canvas");
  skyCv.width = 8; skyCv.height = 256;
  var skyCtx = skyCv.getContext("2d");
  var skyTex = new THREE.CanvasTexture(skyCv);
  skyTex.magFilter = THREE.LinearFilter;
  scene.background = skyTex;

  var sun = new THREE.DirectionalLight(0xfff6e8, 1.0);
  sun.castShadow = true;
  sun.shadow.mapSize.width = 2048;
  sun.shadow.mapSize.height = 2048;
  var shc = sun.shadow.camera;
  shc.left = -340; shc.right = 340; shc.top = 260; shc.bottom = -260;
  shc.near = 1; shc.far = 1800; shc.updateProjectionMatrix();
  sun.shadow.bias = -0.0014;
  scene.add(sun);
  var hemi = new THREE.HemisphereLight(0xdaeaff, 0x8fa3b6, 0.45);
  scene.add(hemi);

  var starGeo = new THREE.BufferGeometry();
  var sp = new Float32Array(1400 * 3);
  for (var si = 0; si < 1400; si++) {
    var th = Math.random() * Math.PI * 2, ph = Math.acos(Math.random() * 0.85 + 0.12);
    var rad = 2600;
    sp[si * 3] = MIDX + rad * Math.sin(ph) * Math.cos(th);
    sp[si * 3 + 1] = GY + rad * Math.cos(ph);
    sp[si * 3 + 2] = MIDZ + rad * Math.sin(ph) * Math.sin(th);
  }
  starGeo.setAttribute("position", new THREE.BufferAttribute(sp, 3));
  var starMat = new THREE.PointsMaterial({color: 0xffffff, size: 3.2,
                                          transparent: true, opacity: 0,
                                          sizeAttenuation: false, fog: false});
  var stars = new THREE.Points(starGeo, starMat);
  real.add(stars);

  var moon = new THREE.Mesh(new THREE.SphereGeometry(26, 20, 16),
                            new THREE.MeshBasicMaterial({color: 0xdfe8f5,
                                                         fog: false}));
  moon.visible = false;
  real.add(moon);
  var sunDisc = new THREE.Mesh(new THREE.SphereGeometry(30, 20, 16),
                               new THREE.MeshBasicMaterial({color: 0xfff3d0,
                                                            fog: false}));
  real.add(sunDisc);

  /* ── precipitation ─────────────────────────────────────────────────── */
  function dot(soft) {
    var c = document.createElement("canvas");
    c.width = c.height = 32;
    var g = c.getContext("2d");
    var gr = g.createRadialGradient(16, 16, 0, 16, 16, 16);
    gr.addColorStop(0, "rgba(255,255,255,1)");
    gr.addColorStop(soft ? 0.45 : 0.75, "rgba(255,255,255,0.85)");
    gr.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = gr; g.fillRect(0, 0, 32, 32);
    return new THREE.CanvasTexture(c);
  }
  var FLAKE = dot(true), DROP = dot(false);

  var BOXW = SPAN * 2.6, BOXH = 380, BOXD = 620;
  function field(n, size, tex, colour, op) {
    var g = new THREE.BufferGeometry();
    var pos = new Float32Array(n * 3), vel = new Float32Array(n * 3);
    for (var i = 0; i < n; i++) {
      pos[i * 3] = (Math.random() - 0.5) * BOXW;
      pos[i * 3 + 1] = Math.random() * BOXH;
      pos[i * 3 + 2] = (Math.random() - 0.5) * BOXD;
      vel[i * 3] = Math.random() * 6.283;      /* drift phase */
      vel[i * 3 + 1] = 0.7 + Math.random() * 0.6;
      vel[i * 3 + 2] = Math.random() * 6.283;
    }
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    var m = new THREE.PointsMaterial({
      size: size, map: tex, color: colour, transparent: true, opacity: op,
      depthWrite: false, sizeAttenuation: true,
      blending: THREE.NormalBlending});
    var p = new THREE.Points(g, m);
    p.frustumCulled = false;
    p.visible = false;
    p.userData.vel = vel;
    real.add(p);
    return p;
  }
  var snowP = field(7000, 3.1, FLAKE, 0xffffff, 0.95);
  var RAIN_N = 5200, RAIN_LEN = 7.5;
  var rainGeo = new THREE.BufferGeometry();
  var rpos = new Float32Array(RAIN_N * 6);       /* two ends per drop */
  var rvel = new Float32Array(RAIN_N);
  for (var ri = 0; ri < RAIN_N; ri++) {
    var bx = (Math.random() - 0.5) * BOXW,
        by = Math.random() * BOXH,
        bz = (Math.random() - 0.5) * BOXD;
    rvel[ri] = 0.75 + Math.random() * 0.5;
    rpos[ri * 6] = bx; rpos[ri * 6 + 1] = by; rpos[ri * 6 + 2] = bz;
    rpos[ri * 6 + 3] = bx; rpos[ri * 6 + 4] = by + RAIN_LEN; rpos[ri * 6 + 5] = bz;
  }
  rainGeo.setAttribute("position", new THREE.BufferAttribute(rpos, 3));
  var rainP = new THREE.LineSegments(rainGeo, new THREE.LineBasicMaterial({
    color: 0xc2d2e6, transparent: true, opacity: 0.42, fog: true}));
  rainP.frustumCulled = false;
  rainP.visible = false;
  real.add(rainP);

  /* ── what the sky is doing ─────────────────────────────────────────── */
  var WMO = {0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
             45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle",
             55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
             61: "Light rain", 63: "Rain", 65: "Heavy rain",
             66: "Freezing rain", 67: "Freezing rain",
             71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
             80: "Rain showers", 81: "Rain showers", 82: "Violent showers",
             85: "Snow showers", 86: "Heavy snow showers",
             95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm"};

  function readCode(code) {
    /* cloud 0..1, rain 0..1, snow 0..1 */
    if (code == null) return {cloud: 0.15, rain: 0, snow: 0};
    if (code === 0) return {cloud: 0.05, rain: 0, snow: 0};
    if (code === 1) return {cloud: 0.25, rain: 0, snow: 0};
    if (code === 2) return {cloud: 0.5, rain: 0, snow: 0};
    if (code === 3) return {cloud: 0.85, rain: 0, snow: 0};
    if (code === 45 || code === 48) return {cloud: 0.9, rain: 0, snow: 0, fog: 1};
    if (code >= 51 && code <= 57) return {cloud: 0.8, rain: 0.35, snow: 0};
    if (code >= 61 && code <= 67) return {cloud: 0.9, rain: code >= 65 ? 1 : 0.65, snow: 0};
    if (code >= 71 && code <= 77) return {cloud: 0.85, rain: 0, snow: code >= 75 ? 1 : 0.55};
    if (code >= 80 && code <= 82) return {cloud: 0.9, rain: code >= 82 ? 1 : 0.7, snow: 0};
    if (code === 85 || code === 86) return {cloud: 0.9, rain: 0, snow: code === 86 ? 1 : 0.6};
    if (code >= 95) return {cloud: 1, rain: 1, snow: 0, storm: 1};
    return {cloud: 0.3, rain: 0, snow: 0};
  }

  var OVERRIDE = {
    "Clear":      {cloud: 0.05, rain: 0, snow: 0, label: "Clear"},
    "Cloudy":     {cloud: 0.85, rain: 0, snow: 0, label: "Overcast"},
    "Rain":       {cloud: 0.9, rain: 0.8, snow: 0, label: "Rain"},
    "Snow":       {cloud: 0.8, rain: 0, snow: 0.55, label: "Snow"},
    "Heavy snow": {cloud: 0.95, rain: 0, snow: 1, label: "Heavy snow"}
  };

  var wx = OVERRIDE[DATA.wx] || {cloud: 0.2, rain: 0, snow: 0, label: "…"};
  var hud = {temp: null, label: wx.label, wind: null, days: []};

  /* ── the sun's arc ─────────────────────────────────────────────────── */
  var SUNRISE = 6.6, SUNSET = 19.1;
  function sunAt(hour) {
    var t = (hour - SUNRISE) / (SUNSET - SUNRISE);
    var elev = Math.sin(t * Math.PI);            /* <0 before dawn / after dusk */
    if (hour < SUNRISE || hour > SUNSET) {
      var nt = hour < SUNRISE ? (hour + 24 - SUNSET) / (24 - SUNSET + SUNRISE)
                              : (hour - SUNSET) / (24 - SUNSET + SUNRISE);
      elev = -Math.sin(nt * Math.PI) * 0.8;
    }
    return {elev: elev, az: (t - 0.5) * Math.PI * 1.1};
  }

  function lerp(a, b, t) { return a + (b - a) * t; }
  function mix(c1, c2, t) {
    return [Math.round(lerp(c1[0], c2[0], t)), Math.round(lerp(c1[1], c2[1], t)),
            Math.round(lerp(c1[2], c2[2], t))];
  }
  function rgb(c) { return "rgb(" + c[0] + "," + c[1] + "," + c[2] + ")"; }

  /* top and horizon, by how high the sun is */
  var NIGHT_T = [7, 12, 30], NIGHT_H = [22, 33, 58];
  var DUSK_T = [40, 58, 110], DUSK_H = [216, 124, 74];
  var LOW_T = [60, 116, 184], LOW_H = [249, 190, 133];
  var DAY_T = [22, 99, 180], DAY_H = [200, 226, 242];

  function paintSky(elev, cloud) {
    var top, hor;
    if (elev <= -0.12) { top = NIGHT_T; hor = NIGHT_H; }
    else if (elev < 0.02) {
      var t = (elev + 0.12) / 0.14;
      top = mix(NIGHT_T, DUSK_T, t); hor = mix(NIGHT_H, DUSK_H, t);
    } else if (elev < 0.22) {
      var t2 = elev / 0.22;
      top = mix(DUSK_T, LOW_T, t2); hor = mix(DUSK_H, LOW_H, t2);
    } else {
      var t3 = Math.min(1, (elev - 0.22) / 0.5);
      top = mix(LOW_T, DAY_T, t3); hor = mix(LOW_H, DAY_H, t3);
    }
    if (cloud > 0.25) {
      var grey = [Math.round(lerp(96, 150, Math.max(0, elev))),
                  Math.round(lerp(104, 158, Math.max(0, elev))),
                  Math.round(lerp(116, 168, Math.max(0, elev)))];
      var c = (cloud - 0.25) / 0.75;
      top = mix(top, grey, c * 0.85); hor = mix(hor, grey, c * 0.7);
    }
    var g = skyCtx.createLinearGradient(0, 0, 0, 256);
    g.addColorStop(0, rgb(top));
    g.addColorStop(0.62, rgb(mix(top, hor, 0.62)));
    g.addColorStop(1, rgb(hor));
    skyCtx.fillStyle = g;
    skyCtx.fillRect(0, 0, 8, 256);
    skyTex.needsUpdate = true;
    return {top: top, hor: hor};
  }

  /* ── the overlay ───────────────────────────────────────────────────── */
  var panel = document.createElement("div");
  panel.style.cssText = "position:absolute;left:12px;top:12px;z-index:6;" +
    "font:13px/1.35 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;" +
    "background:rgba(255,255,255,.86);backdrop-filter:blur(6px);" +
    "border:1px solid rgba(120,140,165,.35);border-radius:12px;" +
    "padding:10px 13px;color:#22303f;box-shadow:0 2px 10px rgba(20,35,60,.13);" +
    "min-width:172px";
  wrap.appendChild(panel);

  var btn = document.createElement("button");
  btn.textContent = "Show the rooms";
  btn.style.cssText = "position:absolute;right:12px;top:12px;z-index:6;" +
    "font:600 12.5px system-ui,-apple-system,Segoe UI,Roboto,sans-serif;" +
    "background:rgba(255,255,255,.9);border:1px solid rgba(120,140,165,.4);" +
    "border-radius:9px;padding:8px 13px;cursor:pointer;color:#22303f;" +
    "box-shadow:0 2px 8px rgba(20,35,60,.13)";
  wrap.appendChild(btn);

  var showingRooms = false;
  var camFor = {rooms: {yaw: yaw, pitch: pitch, dist: dist,
                        panX: panX, panY: panY}, wx: null};
  btn.addEventListener("click", function () {
    var store = showingRooms ? "rooms" : "wx";
    camFor[store] = {yaw: yaw, pitch: pitch, dist: dist, panX: panX, panY: panY};
    showingRooms = !showingRooms;
    var want = camFor[showingRooms ? "rooms" : "wx"];
    if (want) {
      yaw = want.yaw; pitch = want.pitch; dist = want.dist;
      panX = want.panX; panY = want.panY;
      place();
    }
    root.visible = showingRooms;
    real.visible = !showingRooms;
    labels.style.display = showingRooms ? "" : "none";
    panel.style.display = showingRooms ? "none" : "";
    btn.textContent = showingRooms ? "Back to the weather" : "Show the rooms";
    scene.background = showingRooms ? null : skyTex;
    scene.fog = showingRooms ? roomFog : wxFog;
    if (showingRooms) { scene.add(key); scene.add(rim); }
    else { scene.remove(key); scene.remove(rim); }
    hemi.intensity = showingRooms ? 0 : hemiBase;
    sun.visible = !showingRooms;
    frame(true);
  });

  var roomFog = new THREE.Fog(0xdfe7f1, 380, 1000);
  var wxFog = new THREE.Fog(0xd9e7f2, 900, 3600);
  scene.fog = wxFog;
  var hemiBase = 0.40;

  function paintPanel(elev) {
    var t = hud.temp == null ? "—" : Math.round(hud.temp) + "°F";
    var rows = "";
    hud.days.forEach(function (d) {
      rows += '<div style="display:flex;justify-content:space-between;gap:10px;' +
              'font-size:11.5px;color:#4a5b6d"><span>' + d.day + '</span>' +
              '<span>' + d.label + '</span>' +
              '<b style="color:#22303f">' + d.hi + '°/' + d.lo + '°</b></div>';
    });
    panel.innerHTML =
      '<div style="font-size:23px;font-weight:700;line-height:1">' + t + '</div>' +
      '<div style="font-size:12.5px;color:#48596b;margin:1px 0 6px">' +
        hud.label + (hud.wind != null ? ' · ' + Math.round(hud.wind) + ' km/h' : '') +
      '</div>' +
      (rows ? '<div style="border-top:1px solid rgba(120,140,165,.3);' +
              'padding-top:6px;display:grid;gap:2px">' + rows + '</div>' : '') +
      '<div style="font-size:10.5px;color:#7b8a99;margin-top:6px">' +
        (elev > 0 ? 'Daylight' : 'After dark') + ' · Peak 8</div>';
  }

  /* ── per-frame ─────────────────────────────────────────────────────── */
  var hour = DATA.hour, lastPaint = -99, clock0 = performance.now();
  function frame(force) {
    var s = sunAt(hour);
    var elev = s.elev;
    if (force || Math.abs(elev - lastPaint) > 0.012) {
      lastPaint = elev;
      var sky = paintSky(elev, wx.cloud);
      wxFog.color.setRGB(sky.hor[0] / 255, sky.hor[1] / 255, sky.hor[2] / 255);
      var lightAmt = Math.max(0, Math.min(1, (elev + 0.2) / 0.7));
      GROUND.color.setRGB(lerp(0.26, 0.74, lightAmt), lerp(0.30, 0.79, lightAmt),
                          lerp(0.42, 0.86, lightAmt));
      PLAZA.color.setRGB(lerp(0.19, 0.60, lightAmt), lerp(0.21, 0.63, lightAmt),
                         lerp(0.28, 0.67, lightAmt));
      ridges.forEach(function (m) {
        var b = m.userData.base;
        /* toward the night sky rather than toward black, so a ridge at
           midnight is a silhouette and not a hole */
        m.material.color.setRGB(lerp(b.r * 0.20 + 0.03, b.r, lightAmt),
                                lerp(b.g * 0.20 + 0.05, b.g, lightAmt),
                                lerp(b.b * 0.22 + 0.11, b.b, lightAmt));
      });
      paintPanel(elev);
    }

    var up = Math.max(0, elev);
    var D = 900;
    sun.position.set(MIDX + Math.sin(s.az) * D, GY + elev * D * 0.9,
                     MIDZ + Math.cos(s.az) * D * 0.55);
    sun.target.position.set(MIDX, GY, MIDZ);
    sun.target.updateMatrixWorld();
    /* warm and weak on the horizon, white and strong overhead, and whatever
       the cloud lets through */
    var clear = 1 - wx.cloud * 0.72;
    sun.intensity = (elev > 0 ? 0.12 + up * 0.70 : 0.0) * clear;
    sun.color.setRGB(1, lerp(0.74, 0.96, Math.min(1, up * 2.2)),
                     lerp(0.52, 0.90, Math.min(1, up * 2.2)));
    sunDisc.position.copy(sun.position);
    sunDisc.visible = elev > -0.05 && wx.cloud < 0.6;
    sunDisc.material.color.copy(sun.color);

    var night = Math.max(0, Math.min(1, (-elev - 0.02) / 0.18));
    moon.visible = night > 0.05;
    moon.position.set(MIDX - Math.sin(s.az) * D, GY + Math.abs(elev) * D * 0.7,
                      MIDZ - Math.cos(s.az) * D * 0.5);
    starMat.opacity = night * 0.9 * (1 - wx.cloud * 0.85);
    hemi.intensity = showingRooms ? 0
      : lerp(0.10, hemiBase * (1 - up * 0.35), Math.min(1, up * 3));
    if (night > 0.02) {
      sun.intensity = Math.max(sun.intensity, 0.05 + night * 0.10);
      if (elev <= 0) sun.color.setRGB(0.62, 0.70, 0.92);
      sun.position.copy(moon.position);
    }

    /* the windows come on */
    var want = night > 0.25;
    if (want !== frame._lit) {
      frame._lit = want;
      lit.forEach(function (o) { o.material = want ? WINDOW_LIT : GLASS; });
    }
  }

  function precip(dt) {
    var wind = (hud.wind == null ? 6 : hud.wind) * 0.06;
    snowP.visible = wx.snow > 0.02 && !showingRooms;
    if (snowP.visible) {
      var a = snowP.geometry.attributes.position.array, v = snowP.userData.vel;
      var n = Math.floor(a.length / 3 * Math.min(1, 0.22 + wx.snow * 0.78));
      snowP.geometry.setDrawRange(0, n);
      var t = performance.now() * 0.001;
      for (var i = 0; i < n; i++) {
        var j = i * 3;
        a[j + 1] -= 9 * v[j + 1] * dt;
        a[j] += (Math.sin(t * 0.7 + v[j]) * 6 + wind) * dt;
        a[j + 2] += Math.cos(t * 0.5 + v[j + 2]) * 3 * dt;
        if (a[j + 1] < 0) {
          a[j + 1] = BOXH;
          a[j] = (Math.random() - 0.5) * BOXW;
          a[j + 2] = (Math.random() - 0.5) * BOXD;
        }
      }
      snowP.geometry.attributes.position.needsUpdate = true;
    }

    rainP.visible = wx.rain > 0.02 && !showingRooms;
    if (rainP.visible) {
      var ra = rainP.geometry.attributes.position.array;
      var rn = Math.floor(RAIN_N * Math.min(1, 0.3 + wx.rain * 0.7));
      rainP.geometry.setDrawRange(0, rn * 2);
      var lean = wind * 0.09;
      for (var k2 = 0; k2 < rn; k2++) {
        var o = k2 * 6, drop = 210 * rvel[k2] * dt, side = lean * dt * 30;
        ra[o + 1] -= drop; ra[o + 4] -= drop;
        ra[o] += side; ra[o + 3] += side;
        if (ra[o + 1] < 0) {
          var nx = (Math.random() - 0.5) * BOXW, nz = (Math.random() - 0.5) * BOXD;
          ra[o] = nx; ra[o + 1] = BOXH; ra[o + 2] = nz;
          /* the tail leans back along the fall, so a drop looks like it is
             moving rather than standing on end */
          ra[o + 3] = nx - lean * 2.2; ra[o + 4] = BOXH + RAIN_LEN; ra[o + 5] = nz;
        }
      }
      rainP.geometry.attributes.position.needsUpdate = true;
    }
    /* the field follows the camera so it is always where you are looking */
    var tx = camera.position.x - real.position.x,
        tz = camera.position.z - real.position.z;
    snowP.position.set(tx, GY, tz);
    rainP.position.set(tx, GY, tz);
    /* rain darkens the day as well as filling it */
    if (wx.rain > 0.3) wxFog.far = 2200; else wxFog.far = 3600;
  }

  /* ── frame it ──────────────────────────────────────────────────────── */
  yaw = -0.26; pitch = 0.245; dist = SPAN * 1.28; panX = 0; panY = LH * 2.6;
  place();

  var prev = performance.now();
  (function anim() {
    requestAnimationFrame(anim);
    var now = performance.now();
    var dt = Math.min(0.05, (now - prev) / 1000);
    prev = now;
    frame(false);
    precip(dt);
  })();
  frame(true);

  /* ── live weather ──────────────────────────────────────────────────── */
  (function () {
    var url = "https://api.open-meteo.com/v1/forecast?latitude=39.4817" +
      "&longitude=-106.0384&current=temperature_2m,weather_code," +
      "wind_speed_10m,is_day&daily=weather_code,temperature_2m_max," +
      "temperature_2m_min&timezone=America%2FDenver&forecast_days=4" +
      "&temperature_unit=fahrenheit";
    fetch(url).then(function (r) { return r.json(); }).then(function (d) {
      var c = d.current || {};
      if (DATA.wx === "Live") {
        var got = readCode(c.weather_code);
        wx = {cloud: got.cloud, rain: got.rain, snow: got.snow,
              label: WMO[c.weather_code] || "—"};
      }
      hud.temp = c.temperature_2m;
      hud.wind = c.wind_speed_10m;
      hud.label = wx.label + (DATA.wx === "Live" ? "" : " · shown, not live");
      var dd = d.daily || {};
      var names = ["Today", "Tomorrow"];
      hud.days = (dd.time || []).slice(1, 4).map(function (iso, i) {
        var dt2 = new Date(iso + "T12:00:00");
        return {day: i === 0 ? "Tomorrow"
                             : dt2.toLocaleDateString(undefined, {weekday: "short"}),
                label: WMO[dd.weather_code[i + 1]] || "—",
                hi: Math.round(dd.temperature_2m_max[i + 1]),
                lo: Math.round(dd.temperature_2m_min[i + 1])};
      });
      frame(true);
    }).catch(function (e) {
      hud.label = wx.label + " · live data unavailable";
      paintPanel(sunAt(hour).elev);
    });
  })();
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
            h = int((max(rows) - min(rows)) * 62) + 74
            cells = []
            for r in sorted(rs, key=lambda r: r["x"]):
                # inset, or a box centred on 0% or 100% loses half itself
                left = 5 + (r["x"] - lo) / span * 90
                top = (r["row"] - min(rows)) * 62
                ink = _ink(r["colour"])
                meta = " · ".join(x for x in (r["svc_short"],
                                              f'{r["mins"]:.0f}m' if r["mins"] else "") if x)
                cells.append(
                    f'<div class="pr" style="left:{left:.2f}%;top:{top}px;'
                    f'background:{r["colour"]};color:{ink};'
                    f'{"opacity:.5;" if not r["on_chart"] else ""}" '
                    f'title="{r["code"]} — {r.get("hk") or "unassigned"}">'
                    f'<b>{r["code"]}</b>'
                    + (f'<i>{meta}</i>' if meta else '') + '</div>')
            for f in sorted(fs, key=lambda f: f["x"]):
                left = 5 + (f["x"] - lo) / span * 90
                top = (f["row"] - min(rows)) * 62
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

if flat:
    st.markdown(PLAN_CSS + _plan_html(), unsafe_allow_html=True)
else:
    components.html(HTML.replace("__PAYLOAD__", payload), height=640,
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
