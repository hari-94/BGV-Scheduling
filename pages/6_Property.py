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
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import auth, db, clock, i18n
import property_map as pmap
import roomstatus as _rst
import streamlit.components.v1 as components
import ui

st.set_page_config(page_title="Property", page_icon="🏔️", layout="wide")
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


rooms = _inventory()
if not rooms:
    st.info(T("prop.no_rooms"))
    st.stop()

boxes = pmap.layout(rooms)
spans = pmap.bridge_spans()
statuses = _statuses(st.session_state.get("prop_gen", 0))

# ---------------------------------------------------------------- controls
c1, c2, c3 = st.columns([1.5, 1.5, 3])
with c1:
    colour_by = st.radio(T("prop.colour"),
                         [T("prop.by_status"), T("prop.by_building")],
                         horizontal=True, key="prop_colour")
with c2:
    if st.button(T("prop.refresh"), use_container_width=True):
        st.session_state["prop_gen"] = st.session_state.get("prop_gen", 0) + 1
        _statuses.clear()
        st.rerun()
with c3:
    done = sum(1 for b in boxes
               if _rst.normalise((statuses.get(b["code"]) or {}).get("status"))
               in (_rst.INSPECTED, _rst.DONE, _rst.ALREADY_CLEAN))
    st.markdown(
        f'<div style="padding-top:6px;color:#5b6b7e;font-size:.86rem">'
        f'<b>{len(boxes)}</b> rooms placed · <b>{len(spans)}</b> bridges · '
        f'<b>{done}</b> finished today</div>', unsafe_allow_html=True)

BY_STATUS = colour_by == T("prop.by_status")

# roomstatus owns the vocabulary and the colours; the model must not invent
# its own or the legend here stops matching the phone in somebody's hand.
STATUS_COLOUR = {k: v[2] for k, v in _rst.META.items()}
BLD_COLOUR = {1: "#5b8cd6", 2: "#c07a3e", 3: "#4e9e78"}

for b in boxes:
    rec = statuses.get(b["code"]) or {}
    cur = _rst.normalise(rec.get("status"))
    b["status"] = cur
    b["colour"] = (STATUS_COLOUR.get(cur, "#94a3b8") if BY_STATUS
                   else BLD_COLOUR.get(b["bld"], "#94a3b8"))
    b["hk"] = rec.get("housekeeper") or ""

payload = json.dumps({"boxes": boxes, "spans": spans,
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

scene.add(new THREE.AmbientLight(0xffffff, 0.72));
const key = new THREE.DirectionalLight(0xffffff, 0.62);
key.position.set(120, 220, 160); scene.add(key);
const rim = new THREE.DirectionalLight(0xbcd2ee, 0.34);
rim.position.set(-160, 90, -120); scene.add(rim);

/* centre the whole property on the origin so orbiting feels like turning a
   model on a table rather than swinging around one corner of it */
let minX=1e9,maxX=-1e9,minY=1e9,maxY=-1e9,minZ=1e9,maxZ=-1e9;
DATA.boxes.forEach(b=>{
  minX=Math.min(minX,b.x); maxX=Math.max(maxX,b.x);
  minY=Math.min(minY,b.y); maxY=Math.max(maxY,b.y);
  minZ=Math.min(minZ,b.z); maxZ=Math.max(maxZ,b.z);
});
const cx=(minX+maxX)/2, cy=(minY+maxY)/2, cz=(minZ+maxZ)/2;
const root = new THREE.Group();
root.position.set(-cx,-cy,-cz);
scene.add(root);

const RW = DATA.doorW*0.86, RH = DATA.levelH*0.62, RD = DATA.hallD*0.74;
const geo = new THREE.BoxGeometry(RW, RH, RD);
const mats = {};
function mat(hex, op){
  const k = hex+"|"+op;
  if(!mats[k]) mats[k] = new THREE.MeshLambertMaterial({
    color:new THREE.Color(hex), transparent:op<1, opacity:op});
  return mats[k];
}

const meshes = [];
DATA.boxes.forEach(b=>{
  const m = new THREE.Mesh(geo, mat(b.colour, 0.94));
  m.position.set(b.x, b.y, b.z);
  m.userData = b;
  root.add(m); meshes.push(m);
  const e = new THREE.LineSegments(new THREE.EdgesGeometry(geo),
    new THREE.LineBasicMaterial({color:0x2b3a4a, transparent:true, opacity:0.16}));
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
  const w = (p.x1-p.x0)+RW*2.2;
  const slab = new THREE.Mesh(new THREE.BoxGeometry(w, DATA.levelH*0.09, RD*2.9),
    mat("#b9c6d6", 0.5));
  slab.position.set((p.x0+p.x1)/2, p.y-RH*0.62, DATA.hallD*0.5);
  root.add(slab);
});

/* bridges: the point of the whole drawing */
DATA.spans.forEach(s=>{
  const w = Math.abs(s.x1-s.x0);
  const br = new THREE.Mesh(new THREE.BoxGeometry(w, DATA.levelH*0.16, RD*0.9),
    mat("#12764a", 0.92));
  br.position.set((s.x0+s.x1)/2, s.y-RH*0.5, s.z);
  br.userData = {bridge:true, level:s.level, a:s.a, b:s.b};
  root.add(br); meshes.push(br);
});

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
  } else {
    pick.innerHTML = "<b>"+d.code+"</b> <span>building "+d.bld+" &middot; "+
      (isNaN(d.level)?d.level:"level "+d.level)+
      (d.hk ? " &middot; "+d.hk : "")+"</span>"+
      (d.status ? "<br><span>"+d.status.replace(/_/g," ")+"</span>" : "");
  }
});

/* ---- level and building labels, projected each frame ---- */
const tags = [];
DATA.levels.forEach((lv,i)=>{
  const any = DATA.boxes.filter(b=>b.level===lv);
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

components.html(HTML.replace("__PAYLOAD__", payload), height=640, scrolling=False)

# ---------------------------------------------------------------- legend
if BY_STATUS:
    chips = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f'margin-right:14px;font-size:.78rem;color:#42536a">'
        f'<i style="width:11px;height:11px;border-radius:3px;'
        f'background:{v[2]};display:inline-block"></i>{v[0]}'
        f'</span>' for k, v in _rst.META.items())
else:
    chips = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f'margin-right:14px;font-size:.78rem;color:#42536a">'
        f'<i style="width:11px;height:11px;border-radius:3px;'
        f'background:{c};display:inline-block"></i>Building {b}</span>'
        for b, c in BLD_COLOUR.items())
chips += ('<span style="display:inline-flex;align-items:center;gap:6px;'
          'font-size:.78rem;color:#42536a">'
          '<i style="width:11px;height:11px;border-radius:3px;'
          'background:#12764a;display:inline-block"></i>Bridge</span>')
st.markdown(f'<div style="margin:6px 0 18px">{chips}</div>', unsafe_allow_html=True)

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
