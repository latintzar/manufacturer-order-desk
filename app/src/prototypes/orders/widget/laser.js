/* Rocoto laser part views: the drawing of a checked file, the small picture of a part on an order line, and the
   3D stage that shows the part in a chosen material. Exposes window.RocotoLaser. Geometry arrives in millimetres,
   origin lower left, y up (POST api/laser). three.js is fetched the first time a 3D stage is asked for. */
(function(){
'use strict';
const MAX_POINTS=6000;            /* points extruded in 3D, across every contour */
const THUMB_POINTS=260;           /* points kept with an order line for its picture */
const n2=v=>Math.round(v*100)/100;
const area=p=>{let a=0;for(let i=0,j=p.length-1;i<p.length;j=i++)a+=(p[j][0]-p[i][0])*(p[j][1]+p[i][1]);return a/2};
function inside(pt,poly){
  let hit=false;
  for(let i=0,j=poly.length-1;i<poly.length;j=i++){const a=poly[i],b=poly[j];if((a[1]>pt[1])!==(b[1]>pt[1])&&pt[0]<(b[0]-a[0])*(pt[1]-a[1])/(b[1]-a[1])+a[0])hit=!hit}
  return hit;
}
/* a closed run without its repeated end point, thinned to `keep` points by an even stride */
function ring(points,keep){
  let p=points;const a=p[0],z=p[p.length-1];
  if(p.length>3&&Math.abs(a[0]-z[0])<1e-6&&Math.abs(a[1]-z[1])<1e-6)p=p.slice(0,-1);
  if(keep&&p.length>keep&&keep>=3){const out=[],k=p.length/keep;for(let i=0;i<keep;i++)out.push(p[Math.floor(i*k)]);p=out}
  return p;
}
/* every outer contour with the holes that lie in it; open contours are left to the drawing */
function shapes(check,budget,loose){
  const closed=(check.contours||[]).filter(c=>(c.closed||loose)&&c.points&&c.points.length>=3);
  const total=closed.reduce((a,c)=>a+c.points.length,0),share=total>budget?budget/total:1;
  const rings=closed.map(c=>({hole:!!c.hole,p:ring(c.points,share<1?Math.max(8,Math.floor(c.points.length*share)):0)})).filter(r=>r.p.length>=3);
  const outers=rings.filter(r=>!r.hole).map(r=>({outer:r.p,holes:[],a:Math.abs(area(r.p))})).sort((a,b)=>a.a-b.a);
  rings.filter(r=>r.hole).forEach(h=>{const home=outers.find(o=>inside(h.p[0],o.outer));if(home)home.holes.push(h.p)});
  return outers;
}
/* a drawing is whole when every cut line closes: only then is there a part to show as a solid */
const whole=check=>!(check.contours||[]).some(c=>!c.closed)&&shapes(check,THUMB_POINTS).length>0;
const pathOf=(p,closed,f)=>'M'+p.map(q=>f(q[0])+' '+f(q[1])).join('L')+(closed?'Z':'');

/* ---------- the drawing: every cut line as the file has it, each finding marked where it is ---------- */
function drawing(check){
  const w=check.bounds.w,h=check.bounds.h,m=Math.max(w,h)*.07,px=Math.max(w,h)/300;
  const all=(check.contours||[]).filter(c=>c.points&&c.points.length>1);
  const d=list=>list.map(c=>pathOf(c.points,c.closed,n2)).join('');
  const marks=(check.issues||[]).slice(0,60).filter(i=>Array.isArray(i.at)).map(i=>'<circle class="dw-m'+(i.fixed?' ok':'')+'" cx="'+n2(i.at[0])+'" cy="'+n2(i.at[1])+'" r="'+n2(px*7)+'"/>').join('');
  return '<svg class="dwg" viewBox="'+n2(-m)+' '+n2(-m)+' '+n2(w+2*m)+' '+n2(h+2*m)+'" preserveAspectRatio="xMidYMid meet" aria-hidden="true"><g transform="translate(0 '+n2(h)+') scale(1 -1)">'+
    '<path class="dw-f" fill-rule="evenodd" d="'+d(all.filter(c=>c.closed))+'"/><path class="dw-l" d="'+d(all.filter(c=>c.closed))+'"/><path class="dw-o" d="'+d(all.filter(c=>!c.closed))+'"/>'+marks+'</g></svg>';
}

/* ---------- the small picture: the part's outline, kept with the order line, filled in its material ---------- */
function outline(check){
  const s=shapes(check,THUMB_POINTS,!whole(check)),w=check.bounds.w,h=check.bounds.h,k=100/Math.max(w,h),f=v=>Math.round(v*k*10)/10;
  return s.map(x=>pathOf(x.outer.map(p=>[p[0],h-p[1]]),true,f)+x.holes.map(o=>pathOf(o.map(p=>[p[0],h-p[1]]),true,f)).join('')).join('');
}
const shade=(hex,k)=>{const v=/^#([0-9a-f]{6})$/i.exec(hex||'')?parseInt(hex.slice(1),16):0x8a8d91;return 'rgb('+[v>>16,v>>8&255,v&255].map(c=>Math.max(0,Math.min(255,Math.round(k>1?c+(255-c)*(k-1):c*k)))).join(',')+')'};
function picture(view,cls){
  const k=100/Math.max(view.w,view.h),w=Math.max(1,view.w*k),h=Math.max(1,view.h*k),pad=8,id='lzg'+String(view.color||'').replace(/[^0-9a-f]/gi,'');
  return '<svg class="'+(cls||'lz-pic')+'" viewBox="'+(-pad)+' '+(-pad)+' '+n2(w+2*pad)+' '+n2(h+2*pad)+'" preserveAspectRatio="xMidYMid meet" aria-hidden="true"><defs><linearGradient id="'+id+'" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="'+shade(view.color,1.42)+'"/><stop offset=".5" stop-color="'+shade(view.color,1)+'"/><stop offset="1" stop-color="'+shade(view.color,.74)+'"/></linearGradient></defs>'+
    '<path d="'+view.d+'" fill-rule="evenodd" fill="url(#'+id+')" stroke="'+shade(view.color,.5)+'" stroke-width=".8" vector-effect="non-scaling-stroke"/></svg>';
}

/* ---------- 3D: the part cut from the chosen sheet, under a studio made in code ---------- */
let lib=null;
function three(base){
  if(window.THREE)return Promise.resolve(window.THREE);
  if(!lib)lib=new Promise((done,fail)=>{const s=document.createElement('script');s.src=base+'three.min.js';s.async=true;
    s.onload=()=>window.THREE?done(window.THREE):fail(Error('three'));s.onerror=()=>{lib=null;fail(Error('three'))};document.head.appendChild(s)});
  return lib;
}
/* how a metal takes light beyond its colour: brushed, mill scale, or polished under a clear coat */
function finish(m){
  const n=(m.id+' '+(m.en||'')).toLowerCase();
  if(/inox|stainless|304|316/.test(n))return{grain:'brush',aniso:.16,coat:0,env:2.3,k:1};
  if(/alu/.test(n))return{grain:'brush',aniso:.1,coat:0,env:2.1,k:1};
  if(/brass|copper|bronze/.test(n))return{grain:'fine',aniso:0,coat:.3,env:2.4,k:.72};
  return{grain:'scale',aniso:0,coat:.2,env:3.4,k:.74};
}
/* a tile of surface grain: its green channel scales roughness */
function grain(T,kind){
  const S=256,c=document.createElement('canvas');c.width=c.height=S;const g=c.getContext('2d'),im=g.createImageData(S,S),d=im.data;
  let seed=kind.length*7919+13;const rnd=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296};
  const rows=new Float32Array(S),soft=new Float32Array(S*S);
  for(let y=0;y<S;y++)rows[y]=rnd();
  if(kind==='scale'){ /* blotches a few millimetres wide, smoothed twice */
    const low=new Float32Array(32*32);for(let i=0;i<low.length;i++)low[i]=rnd();
    for(let y=0;y<S;y++)for(let x=0;x<S;x++){const fx=x/8,fy=y/8,x0=fx|0,y0=fy|0,tx=fx-x0,ty=fy-y0,a=low[(y0%32)*32+x0%32],b=low[(y0%32)*32+(x0+1)%32],e=low[((y0+1)%32)*32+x0%32],f=low[((y0+1)%32)*32+(x0+1)%32];soft[y*S+x]=(a*(1-tx)+b*tx)*(1-ty)+(e*(1-tx)+f*tx)*ty}
  }
  for(let y=0;y<S;y++)for(let x=0;x<S;x++){
    const fine=rnd();let v;
    if(kind==='brush')v=.72+.2*rows[y]+.08*fine;
    else if(kind==='scale')v=.8+.14*soft[y*S+x]+.06*fine;
    else v=.86+.14*fine;
    const k=(y*S+x)*4,b=Math.round(v*255);d[k]=b;d[k+1]=b;d[k+2]=b;d[k+3]=255;
  }
  g.putImageData(im,0,0);
  const t=new T.CanvasTexture(c);t.wrapS=t.wrapT=T.RepeatWrapping;t.colorSpace=T.NoColorSpace;t.anisotropy=4;return t;
}
/* the studio: soft boxes painted on a panorama, then filtered for every roughness. The sheet's face mirrors the big box
   behind and above it, so the light falls off across the metal; its cut edge picks up the strips at the horizon */
function studio(T,renderer){
  const W=512,H=256,c=document.createElement('canvas');c.width=W;c.height=H;const g=c.getContext('2d');
  const sky=g.createLinearGradient(0,0,0,H);[[0,'#262728'],[.2,'#3a3b3c'],[.47,'#1b1b1c'],[.53,'#101011'],[1,'#060606']].forEach(x=>sky.addColorStop(x[0],x[1]));
  g.fillStyle=sky;g.fillRect(0,0,W,H);g.globalCompositeOperation='lighter';
  /* a soft box at longitude u (0..1), elevation in degrees, half-sizes in the panorama's width and height */
  const box=(u,el,rx,ry,v)=>[-1,0,1].forEach(k=>{const x=(u+k)*W,y=(.5-el/180)*H;g.save();g.translate(x,y);g.scale(rx*W,ry*H);
    const r=g.createRadialGradient(0,0,0,0,0,1),t=Math.round(v*255);r.addColorStop(0,'rgb('+t+','+t+','+t+')');r.addColorStop(.55,'rgba('+t+','+t+','+t+',.62)');r.addColorStop(1,'rgba('+t+','+t+','+t+',0)');
    g.fillStyle=r;g.beginPath();g.arc(0,0,1,0,7);g.fill();g.restore()});
  box(.25,60,.13,.17,1);         /* the main box, behind and above */
  box(.25,17,.2,.035,.7);        /* a strip at the horizon behind, the bright line on the far edge */
  box(.04,34,.06,.18,.8);        /* key, from the left */
  box(.48,28,.02,.2,.9);         /* rim strip, from the right */
  box(.75,-16,.2,.1,.5);         /* the floor in front, for the near edge */
  box(.75,58,.2,.14,.2);         /* a low fill overhead in front */
  const pano=new T.CanvasTexture(c);pano.mapping=T.EquirectangularReflectionMapping;pano.colorSpace=T.SRGBColorSpace;
  const pm=new T.PMREMGenerator(renderer),target=pm.fromEquirectangular(pano);pm.dispose();pano.dispose();
  return target;
}
function contact(T,parts,w,h){
  const S=256,c=document.createElement('canvas');c.width=c.height=S;const g=c.getContext('2d'),k=S/2.9/Math.max(w,h)*2;
  g.shadowColor='rgba(12,14,16,.5)';g.shadowBlur=13;g.shadowOffsetX=S*2;g.fillStyle='#000';g.beginPath();
  parts.forEach(s=>[s.outer].concat(s.holes).forEach(p=>{p.forEach((q,i)=>{const x=S/2+(q[0]-w/2)*k-S*2,y=S/2-(q[1]-h/2)*k;if(i)g.lineTo(x,y);else g.moveTo(x,y)});g.closePath()}));
  g.fill('evenodd');
  const t=new T.CanvasTexture(c);t.colorSpace=T.SRGBColorSpace;return t;
}
function webgl(){try{const c=document.createElement('canvas');return !!(window.WebGLRenderingContext&&(c.getContext('webgl2')||c.getContext('webgl')))}catch(e){return false}}

/* mount(el, check, {base, material, thickness, still}) -> a handle: set(material, thickness), snapshot(px), dispose().
   The flat picture stands in the stage until the first 3D frame, and stays where WebGL is missing. */
function mount(el,check,o){
  const w=check.bounds.w,h=check.bounds.h,flatView=m=>({w:w,h:h,d:outline(check),color:m.look&&m.look.color});
  let material=o.material,thickness=o.thickness,dead=false,live=null;
  /* a drawing with a contour still open stays a drawing: its lines as the file has them, the open one marked */
  if(!whole(check)){el.innerHTML='<div class="s3-flat">'+drawing(check)+'</div>';return{webgl:false,ready:false,set(){},snapshot(){return''},dispose(){el.innerHTML=''}}}
  el.innerHTML='<div class="s3-flat">'+picture(flatView(material),'lz-pic big')+'</div>';
  const handle={webgl:false,ready:false,
    set(m,t){material=m;thickness=t;if(live)live.set(m,t);else{const f=el.querySelector('.s3-flat');if(f)f.innerHTML=picture(flatView(m),'lz-pic big')}},
    snapshot(px){return live?live.snapshot(px):''},
    dispose(){dead=true;if(live)live.dispose();live=null;el.innerHTML=''}};
  if(!webgl())return handle;
  three(o.base).then(T=>{
    if(dead)return;
    try{live=stage(T,el,check,{material:material,thickness:thickness,still:!!o.still});handle.webgl=true;handle.ready=true;if(o.onReady)o.onReady(handle)}
    catch(e){live=null}
  }).catch(()=>{});
  return handle;
}
function stage(T,el,check,o){
  const w=check.bounds.w,h=check.bounds.h,k=2/Math.max(w,h),parts=shapes(check,MAX_POINTS);
  if(!parts.length)throw Error('empty');
  const renderer=new T.WebGLRenderer({antialias:true,alpha:true,powerPreference:'high-performance'});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1;renderer.outputColorSpace=T.SRGBColorSpace;renderer.setClearColor(0,0);
  const canvas=renderer.domElement;canvas.className='s3-c';el.appendChild(canvas);
  const env=studio(T,renderer),scene=new T.Scene();scene.environment=env.texture;
  const camera=new T.PerspectiveCamera(22,1,.1,80),turn=new T.Group();scene.add(turn);
  const flat=parts.map(s=>{const sh=new T.Shape(s.outer.map(p=>new T.Vector2((p[0]-w/2)*k,(p[1]-h/2)*k)));s.holes.forEach(x=>sh.holes.push(new T.Path(x.map(p=>new T.Vector2((p[0]-w/2)*k,(p[1]-h/2)*k)))));return sh});
  const tex={},face=new T.MeshPhysicalMaterial({metalness:1}),edge=new T.MeshPhysicalMaterial({metalness:1}),mesh=new T.Mesh(new T.BufferGeometry(),[face,edge]);turn.add(mesh);
  const shadowTex=contact(T,parts,w,h),shadowMat=new T.MeshBasicMaterial({map:shadowTex,transparent:true,depthWrite:false,toneMapped:false,opacity:.9}),shadowGeo=new T.PlaneGeometry(2.9,2.9),shadow=new T.Mesh(shadowGeo,shadowMat);
  shadow.rotation.x=-Math.PI/2;shadow.position.y=-.002;turn.add(shadow);
  const LIFT=.07,reach=parts.reduce((a,s)=>s.outer.reduce((b,p)=>Math.max(b,Math.hypot(p[0]-w/2,p[1]-h/2)*k),a),0)||1;let depth=0,built=null;
  function build(thickness){
    if(built===thickness)return;built=thickness;
    const small=check.cut&&check.cut.smallest_mm>0?check.cut.smallest_mm:4,bev=Math.max(.04,Math.min(thickness*.1,.4,small*.06))*k;
    depth=Math.max(thickness*k,bev*2.5);
    const geo=new T.ExtrudeGeometry(flat,{depth:depth-2*bev,bevelEnabled:true,bevelThickness:bev,bevelSize:bev,bevelSegments:2,curveSegments:1,steps:1});
    geo.rotateX(-Math.PI/2);geo.translate(0,bev+LIFT,0);
    mesh.geometry.dispose();mesh.geometry=geo;
  }
  function dress(m){
    const f=finish(m),look=m.look||{},rough=look.roughness==null?.5:look.roughness;
    if(!tex[f.grain])tex[f.grain]=grain(T,f.grain);
    if(!tex.cut){tex.cut=grain(T,'brush');tex.cut.rotation=Math.PI/2;tex.cut.repeat.set(26,26)}
    const t=tex[f.grain];t.repeat.set(f.grain==='brush'?2.2:3,f.grain==='brush'?2.2:3);
    face.color.set(look.color||'#8a8d91');face.metalness=look.metalness==null?1:look.metalness;face.roughness=Math.min(1,rough/.86*f.k);
    face.roughnessMap=t;face.clearcoat=f.coat;face.clearcoatRoughness=.3;face.anisotropy=f.aniso;face.envMapIntensity=f.env;face.needsUpdate=true;
    /* the cut edge: darker, matt, striated across the sheet */
    edge.color.set(look.color||'#8a8d91').multiplyScalar(.74);edge.metalness=.92;edge.roughness=Math.min(1,rough+.26);edge.roughnessMap=tex.cut;edge.envMapIntensity=f.env*.9;edge.needsUpdate=true;
  }
  let yaw=.62,pitch=.7,spin=0,drag=null,raf=0,wake=0,last=0,drawn=0,shown=true,dead=false,idleFrom=performance.now()+900;
  function place(){
    const r=reach,rect=el.getBoundingClientRect(),asp=Math.max(.2,rect.width/Math.max(1,rect.height)),vf=camera.fov*Math.PI/180,hf=2*Math.atan(Math.tan(vf/2)*asp);
    const dist=Math.max((r*Math.sin(pitch)+depth)/(Math.tan(vf/2)*.7),r/(Math.tan(hf/2)*.84))+r*Math.cos(pitch)*.5;
    camera.aspect=asp;camera.position.set(0,Math.sin(pitch)*dist+LIFT,Math.cos(pitch)*dist);camera.lookAt(0,LIFT+depth/2,0);camera.updateProjectionMatrix();
  }
  function draw(){if(dead)return;turn.rotation.y=yaw;place();renderer.render(scene,camera);drawn=performance.now();if(!el.classList.contains('on'))el.classList.add('on')}
  function kick(){if(!raf&&!dead)raf=requestAnimationFrame(frame)}
  function frame(now){
    raf=0;if(dead)return;const dt=Math.min(.05,(now-last)/1000||.016);last=now;
    if(drag){draw();return}
    if(Math.abs(spin)>.03){yaw+=spin*dt;spin*=Math.pow(.04,dt);draw();return kick()}
    spin=0;
    if(o.still||!shown||document.visibilityState==='hidden'){draw();return}
    if(now<idleFrom){draw();clearTimeout(wake);wake=setTimeout(kick,idleFrom-now+20);return}
    if(now>idleFrom+30000){draw();return}               /* the idle turn rests after half a minute */
    yaw+=.2*dt;if(now-drawn>=31)draw();kick();          /* and runs at half the screen's rate */
  }
  function size(){const r=el.getBoundingClientRect();if(r.width<2||r.height<2)return;renderer.setSize(r.width,r.height,false);draw()}
  const down=e=>{drag={x:e.clientX,y:e.clientY,t:performance.now(),touch:e.pointerType==='touch'};spin=0;try{canvas.setPointerCapture(e.pointerId)}catch(x){}el.classList.add('hold')};
  const move=e=>{if(!drag)return;const now=performance.now(),dx=e.clientX-drag.x,dy=e.clientY-drag.y,dt=Math.max(.008,(now-drag.t)/1000);
    yaw+=dx*.011;if(!drag.touch)pitch=Math.max(.2,Math.min(1.35,pitch+dy*.006));spin=Math.max(-9,Math.min(9,dx*.011/dt));drag.x=e.clientX;drag.y=e.clientY;drag.t=now;kick()};
  const up=()=>{if(!drag)return;if(performance.now()-drag.t>120)spin=0;drag=null;el.classList.remove('hold');idleFrom=performance.now()+3600;kick()};
  const lost=e=>{e.preventDefault();el.classList.remove('on')};
  const seen=()=>{if(document.visibilityState!=='hidden')kick()};
  canvas.addEventListener('pointerdown',down);canvas.addEventListener('pointermove',move);canvas.addEventListener('pointerup',up);canvas.addEventListener('pointercancel',up);canvas.addEventListener('webglcontextlost',lost);
  document.addEventListener('visibilitychange',seen);
  const ro='ResizeObserver' in window?new ResizeObserver(size):null;if(ro)ro.observe(el);
  const io='IntersectionObserver' in window?new IntersectionObserver(es=>{shown=es[es.length-1].isIntersecting;if(shown)kick()}):null;if(io)io.observe(el);
  build(o.thickness);dress(o.material);size();kick();
  return{
    set(m,t){build(t);dress(m);draw();idleFrom=Math.max(idleFrom,performance.now()+1200);kick()},
    snapshot(px){
      try{draw();const s=px||128,c=document.createElement('canvas');c.width=c.height=s;const g=c.getContext('2d'),side=Math.min(canvas.width,canvas.height);
        g.fillStyle='#f4f4f1';g.fillRect(0,0,s,s);g.drawImage(canvas,(canvas.width-side)/2,(canvas.height-side)/2,side,side,0,0,s,s);return c.toDataURL('image/jpeg',.84)}catch(e){return''}
    },
    dispose(){
      dead=true;cancelAnimationFrame(raf);clearTimeout(wake);if(ro)ro.disconnect();if(io)io.disconnect();document.removeEventListener('visibilitychange',seen);
      canvas.removeEventListener('pointerdown',down);canvas.removeEventListener('pointermove',move);canvas.removeEventListener('pointerup',up);canvas.removeEventListener('pointercancel',up);canvas.removeEventListener('webglcontextlost',lost);
      mesh.geometry.dispose();face.dispose();edge.dispose();shadowGeo.dispose();shadowMat.dispose();shadowTex.dispose();Object.keys(tex).forEach(x=>tex[x].dispose());env.dispose();
      renderer.dispose();try{renderer.forceContextLoss()}catch(e){}if(canvas.parentNode)canvas.parentNode.removeChild(canvas);
    }};
}

window.RocotoLaser={drawing:drawing,outline:outline,picture:picture,shapes:shapes,whole:whole,mount:mount,finish:finish,MAX_POINTS:MAX_POINTS};
})();
