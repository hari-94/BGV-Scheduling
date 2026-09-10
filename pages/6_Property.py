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
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, db, clock, i18n
import property_map as pmap
import roomstatus as _rst
import streamlit.components.v1 as components
import ui

st.set_page_config(page_title="Property", page_icon="🏔️", layout="wide")
# Same width family as the rest of the app, and unconditional: the plan
# view's stylesheet only renders in 2-D, so a cap in there would leave the
# 3-D view stretched across a big monitor.
st.markdown("<style>.block-container{max-width:min(1200px,97%);}</style>",
            unsafe_allow_html=True)
auth.require_login()
ui.topnav("Property")

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
                      "hallD": pmap.HALL_D}, separators=(",", ":"))

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
