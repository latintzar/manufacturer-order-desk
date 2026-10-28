/* Rocoto configurator: procedural 3D for metal stock. One WebGL renderer draws both the live view and the
   thumbnails. Needs window.THREE (three.js r160). Exposes window.Rocoto3D.
   spec = {g: geomOf(shape,dims), mat, pattern, f, grid?, real?}
     f     display length factor for the sample view ("Best fit"): depth = largest section dimension x f
     grid  true draws the floor grid in draw(); one square is a round size in mm, returned as {cell}
     real  true scale: a length in mm for bars, [length, width] in mm for sheets; the camera fits the piece */
(function(){
'use strict';
const R={ok:false,geo:{},mat:{},tex:{},thumbs:{},w:0,h:0};
const clamp=(n,a,b)=>Math.min(b,Math.max(a,n)),CPU={willReadFrequently:true};
function hash(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return h>>>0}
function rng(seed){let a=seed>>>0;return()=>{a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}

/* standard section tables: h -> [b, tw, tf] */
const IPE={80:[46,3.8,5.2],100:[55,4.1,5.7],120:[64,4.4,6.3],140:[73,4.7,6.9],160:[82,5,7.4],180:[91,5.3,8],200:[100,5.6,8.5],220:[110,5.9,9.2],240:[120,6.2,9.8],270:[135,6.6,10.2],300:[150,7.1,10.7],330:[160,7.5,11.5],360:[170,8,12.7],400:[180,8.6,13.5],450:[190,9.4,14.6],500:[200,10.2,16],550:[210,11.1,17.2],600:[220,12,19]};
const HEA={100:[100,5,8,96],120:[120,5,8,114],140:[140,5.5,8.5,133],160:[160,6,9,152],180:[180,6,9.5,171],200:[200,6.5,10,190],220:[220,7,11,210],240:[240,7.5,12,230],260:[260,7.5,12.5,250],280:[280,8,13,270],300:[300,8.5,14,290],320:[300,9,15.5,310],340:[300,9.5,16.5,330],360:[300,10,17.5,350],400:[300,11,19,390],450:[300,11.5,21,440]};
const HEB={100:[100,6,10],120:[120,6.5,11],140:[140,7,12],160:[160,8,13],180:[180,8.5,14],200:[200,9,15],220:[220,9.5,16],240:[240,10,17],260:[260,10,17.5],280:[280,10.5,18],300:[300,11,19],320:[300,11.5,20.5],340:[300,12,21.5],360:[300,12.5,22.5],400:[300,13.5,24]};
const UPN={30:[15,4,4.5],40:[20,5,5.5],50:[25,5,6],65:[42,5.5,7.5],80:[45,6,8],100:[50,6,8.5],120:[55,7,9],140:[60,7,10],160:[65,7.5,10.5],180:[70,8,11],200:[75,8.5,11.5],220:[80,9,12.5],240:[85,9.5,13],260:[90,10,14],280:[95,10,15],300:[100,10,16],400:[110,14,18]};

/* catalogue item -> geometry description */
function geomOf(form,d){
  d=d||[];
  switch(form){
    case'sq_tube':case'rect_tube':return{k:'box',a:d[0],b:d[1]||d[0],t:d[2]||Math.max(1.5,d[0]*.06)};
    case'round_tube':return{k:'tube',d:d[0],t:d[1]||Math.max(1.5,d[0]*.06)};
    case'round':return{k:'round',d:d[0]};
    case'square':return{k:'square',a:d[0]};
    case'hex':return{k:'hex',s:d[0]};
    case'flat':return{k:'flat',w:d[0],t:d[1]};
    case'angle':case'angle_u':return{k:'angle',a:d[0],b:d[1]||d[0],t:d[2]||Math.max(3,d[0]*.1)};
    case'tee':return{k:'tee',a:d[0],b:d[1]||d[0],t:d[2]||Math.max(3,d[0]*.1)};
    case'channel':return{k:'u',h:d[0],b:d[1],tw:d[2]||3,tf:d[2]||3,r:(d[2]||3)*1.4};
    case'upn':{const h=d[0],T=UPN[h]||[d[1]||h*.45,Math.max(4,h*.05),Math.max(5,h*.07)];return{k:'u',h:h,b:d[1]||T[0],tw:T[1],tf:T[2],r:0}}
    case'ipe':{const h=d[0],T=IPE[h]||[h*.5,h*.03+2,h*.045+2];return{k:'i',h:h,b:T[0],tw:T[1],tf:T[2]}}
    case'hea':{const T=HEA[d[0]]||[d[0],d[0]*.035+2,d[0]*.05+3,d[0]*.96];return{k:'i',h:T[3]||d[0],b:T[0],tw:T[1],tf:T[2]}}
    case'heb':{const T=HEB[d[0]]||[d[0],d[0]*.04+2,d[0]*.06+4];return{k:'i',h:d[0],b:T[0],tw:T[1],tf:T[2]}}
    case'sheet':case'chequer':return{k:'sheet',t:d[0],W:d[1]||1000,L:d[2]||2000};
    default:return{k:'box',a:40,b:40,t:3};
  }
}
const flatish=g=>g.k==='sheet';

/* ---------- textures ---------- */
const DRAW={
  grain(g,n,r){const d=g.createImageData(n,n);for(let i=0;i<d.data.length;i+=4){const v=150+r()*105|0;d.data[i]=d.data[i+1]=d.data[i+2]=v;d.data[i+3]=255}g.putImageData(d,0,0)},
  streak(g,n,r){g.fillStyle='#cdcdcd';g.fillRect(0,0,n,n);for(let i=0;i<1300;i++){const v=110+r()*145|0;g.fillStyle='rgba('+v+','+v+','+v+','+(.16+r()*.3)+')';const x=r()*n,w=.4+r()*1.5;if(r()<.72)g.fillRect(x,0,w,n);else{const y=r()*n,h=60+r()*320;g.fillRect(x,y,w,h);g.fillRect(x,y-n,w,h)}}},
  mottle(g,n,r){g.fillStyle='#c2c2c2';g.fillRect(0,0,n,n);for(let i=0;i<300;i++){const x=r()*n,y=r()*n,rad=14+r()*64,v=90+r()*165|0,a=.1+r()*.16;for(let ox=-n;ox<=n;ox+=n)for(let oy=-n;oy<=n;oy+=n){if(x+ox+rad<0||x+ox-rad>n||y+oy+rad<0||y+oy-rad>n)continue;const gr=g.createRadialGradient(x+ox,y+oy,0,x+ox,y+oy,rad);gr.addColorStop(0,'rgba('+v+','+v+','+v+','+a+')');gr.addColorStop(1,'rgba('+v+','+v+','+v+',0)');g.fillStyle=gr;g.fillRect(x+ox-rad,y+oy-rad,rad*2,rad*2)}}},
  spangle(g,n,r){const S=[];for(let i=0;i<64;i++)S.push([r()*n,r()*n,200+r()*55,(r()-.5)*.7,(r()-.5)*.7]);const d=g.createImageData(n,n);for(let y=0;y<n;y++)for(let x=0;x<n;x++){let b=1e9,bs=null,bx=0,by=0;for(let i=0;i<S.length;i++){let dx=Math.abs(x-S[i][0]),dy=Math.abs(y-S[i][1]);if(dx>n/2)dx=n-dx;if(dy>n/2)dy=n-dy;const q=dx*dx+dy*dy;if(q<b){b=q;bs=S[i];bx=dx;by=dy}}const v=clamp(bs[2]+bx*bs[3]+by*bs[4],170,255)|0,o=(y*n+x)*4;d.data[o]=d.data[o+1]=d.data[o+2]=v;d.data[o+3]=255}g.putImageData(d,0,0)},
  saw(g,n,r){g.fillStyle='#c8c8c8';g.fillRect(0,0,n,n);for(let rad=260;rad<1100;rad+=1.4+r()*2.2){const v=105+r()*150|0;g.strokeStyle='rgba('+v+','+v+','+v+','+(.2+r()*.3)+')';g.lineWidth=.5+r()*1.3;g.beginPath();g.arc(-260,n/2,rad,-1,1);g.stroke()}},
  /* height maps (white = raised) */
  hTear(g,n){g.fillStyle='#000';g.fillRect(0,0,n,n);try{g.filter='blur(2px)'}catch(e){}g.fillStyle='#fff';const c=n/4;for(let i=0;i<4;i++)for(let j=0;j<4;j++){const a=(i+j)%2?Math.PI/4:-Math.PI/4;g.save();g.translate(i*c+c/2,j*c+c/2);g.rotate(a);g.beginPath();g.ellipse(0,0,c*.4,c*.13,0,0,Math.PI*2);g.fill();g.restore()}},
  hBars(g,n){g.fillStyle='#000';g.fillRect(0,0,n,n);try{g.filter='blur(2.5px)'}catch(e){}g.strokeStyle='#fff';g.lineWidth=17;g.lineCap='round';const c=n/2;for(let cx=0;cx<2;cx++)for(let cy=0;cy<2;cy++){const a=(cx+cy)%2?Math.PI/4:-Math.PI/4,ux=Math.cos(a),uy=Math.sin(a),px=-uy,py=ux,ox=cx*c+c/2,oy=cy*c+c/2;for(let i=-2;i<=2;i++){const mx=ox+px*i*30,my=oy+py*i*30,L=62-Math.abs(i)*9;g.beginPath();g.moveTo(mx-ux*L,my-uy*L);g.lineTo(mx+ux*L,my+uy*L);g.stroke()}}},
  hHammer(g,n,r){g.fillStyle='#808080';g.fillRect(0,0,n,n);for(let i=0;i<150;i++){const x=r()*n,y=r()*n,rad=18+r()*40,v=r()<.5?40:215;for(let ox=-n;ox<=n;ox+=n)for(let oy=-n;oy<=n;oy+=n){if(x+ox+rad<0||x+ox-rad>n||y+oy+rad<0||y+oy-rad>n)continue;const gr=g.createRadialGradient(x+ox,y+oy,0,x+ox,y+oy,rad);gr.addColorStop(0,'rgba('+v+','+v+','+v+',.55)');gr.addColorStop(1,'rgba('+v+','+v+','+v+',0)');g.fillStyle=gr;g.fillRect(x+ox-rad,y+oy-rad,rad*2,rad*2)}}}
};
function canvasOf(name){
  if(R.tex[name])return R.tex[name];
  const n=name==='spangle'?256:512,c=document.createElement('canvas');c.width=c.height=n;const g=c.getContext('2d',CPU);
  if(name.charAt(0)==='N'){ /* normal map from a height map */
    const hc=canvasOf(name.slice(1)),src=hc.getContext('2d').getImageData(0,0,n,n).data,d=g.createImageData(n,n),D=d.data,k=name==='NhHammer'?3:7,m=n-1;
    for(let y=0,o=0;y<n;y++){const r=y*n,u=(y?y-1:m)*n,w=(y<m?y+1:0)*n;for(let x=0;x<n;x++,o+=4){
      const nx=-(src[(r+(x<m?x+1:0))*4]/255-src[(r+(x?x-1:m))*4]/255)*k,ny=(src[(w+x)*4]/255-src[(u+x)*4]/255)*k,l=Math.sqrt(nx*nx+ny*ny+1);
      D[o]=(nx/l*.5+.5)*255;D[o+1]=(ny/l*.5+.5)*255;D[o+2]=(1/l*.5+.5)*255;D[o+3]=255}}
    g.putImageData(d,0,0);
  }else DRAW[name](g,n,rng(hash(name)));
  return R.tex[name]=c;
}
function tex(name,ru,rv,color,rot){
  const key=name+'|'+ru+'|'+rv+'|'+(color?1:0)+(rot?'|'+rot:'');
  if(R.tex[key])return R.tex[key];
  const t=new THREE.CanvasTexture(canvasOf(name));t.wrapS=t.wrapT=THREE.RepeatWrapping;t.repeat.set(1/ru,1/rv);t.anisotropy=8;
  if(rot)t.rotation=rot;
  if(color)t.colorSpace=THREE.SRGBColorSpace;
  return R.tex[key]=t;
}

/* ---------- materials ---------- */
const BARE={hr:'#b4b8bd',cr:'#b9bdc2',galv:'#b4b8bd',wrought:'#b4b8bd',pvc:'#b4b8bd',inox:'#c8cbd0',alu:'#dfe2e6',copper:'#d58a63',brass:'#d8b45a',bronze:'#b98a55',lead:'#9a9da2'};
function recipe(m){
  switch(m){
    case'hr':return{c:'#4d535b',m:.9,r:.74,t:['mottle',90,90],bump:.0035,cmap:1};
    case'cr':return{c:'#aeb2b7',m:1,r:.46,t:['streak',60,600],bump:.0003};
    case'galv':return{c:'#ccd2d7',m:1,r:.5,t:['spangle',34,34],bump:.0006,cmap:1};
    case'wrought':return{c:'#33373c',m:.85,r:.62,n:['NhHammer',46,46,.9]};
    case'pvc':return{c:'#e9e7df',m:0,r:.55,cc:.3,ccr:.4};
    case'inox':return{c:BARE.inox,m:1,r:.4,an:.6,t:['streak',14,220],bump:.0005};
    case'alu':return{c:BARE.alu,m:1,r:.58,t:['streak',44,420],bump:.0005};
    case'copper':return{c:BARE.copper,m:1,r:.4,t:['streak',52,520],bump:.0003};
    case'brass':return{c:BARE.brass,m:1,r:.4,t:['streak',52,520],bump:.0003};
    case'bronze':return{c:'#a8793f',m:1,r:.56,t:['grain',16,16],bump:.0012};
    case'lead':return{c:'#7b7f85',m:1,r:.72,t:['mottle',70,70],bump:.002,cmap:1};
    default:return{c:'#b4b8bd',m:1,r:.5};
  }
}
function white(){
  if(!R.tex.white){const t=new THREE.DataTexture(new Uint8Array([255,255,255,255]),1,1);t.colorSpace=THREE.SRGBColorSpace;t.needsUpdate=true;R.tex.white=t}
  return R.tex.white;
}
/* mm: 0 for the sample view; in true scale 1 for bars and 1, 2, 4 or 8 for sheets. Texture tiles are in mm
   on the piece, so nothing stretches with length. In true scale the plate pattern repeats at its real pitch,
   the directionless surface textures (scale, spangle, grain) lie turned on the piece so a bar many tiles long
   shows no repeating stamp, and a sheet draws its surface grain mm times larger, which keeps it the size it
   has on the sample strip instead of collapsing into a weave. Rolled streaks keep running along the piece. */
function material(m,pattern,mm){
  const q=Object.assign({},recipe(m));
  if(mm&&q.t){q.t=[q.t[0],q.t[1]*mm,q.t[2]*mm];if(q.t[0]!=='streak')q.rot=.55}
  const key=m+'|'+(pattern||'')+(mm&&(pattern||q.rot||mm>1)?'|mm'+mm:'');
  if(R.mat[key])return R.mat[key];
  const mk=q=>{
    const x=new THREE.MeshPhysicalMaterial({color:new THREE.Color(q.c),metalness:q.m,roughness:q.r,envMapIntensity:1});
    if(q.cc){x.clearcoat=q.cc;x.clearcoatRoughness=q.ccr}
    if(q.t){x.roughnessMap=tex(q.t[0],q.t[1],q.t[2],false,q.rot);x.bumpMap=x.roughnessMap;x.bumpScale=q.bump||0;if(q.cmap)x.map=tex(q.t[0],q.t[1],q.t[2],true,q.rot)}
    if(q.n){x.normalMap=tex(q.n[0],q.n[1],q.n[2]);x.normalScale.set(q.n[3],q.n[3])}
    if(q.an)x.anisotropy=q.an;
    return x;
  };
  if(pattern){const b=pattern==='bars',n=mm?(b?90:110):(b?70:44);q.n=[b?'NhBars':'NhTear',n,n,1.2];delete q.an}
  const side=mk(q),cap=mk({c:BARE[m]||'#b4b8bd',m:1,r:.6,t:['saw',44,44],bump:.0012});
  /* one shader program for cap and side: the cap takes the side's extra inputs with neutral values (a white
     colour map, a normal map scaled to zero), which draws the same pixels and compiles one program fewer */
  if(q.t&&!q.an&&!q.cc){if(q.cmap)cap.map=white();if(q.n){cap.normalMap=side.normalMap;cap.normalScale.set(0,0)}}
  return R.mat[key]=[cap,side];
}

/* ---------- geometry ---------- */
function rrect(p,w,h,r){
  const x=-w/2,y=-h/2,P=Math.PI;r=Math.min(r,w/2-.01,h/2-.01);
  p.moveTo(x+r,y);p.lineTo(x+w-r,y);p.absarc(x+w-r,y+r,r,-P/2,0,false);
  p.lineTo(x+w,y+h-r);p.absarc(x+w-r,y+h-r,r,0,P/2,false);
  p.lineTo(x+r,y+h);p.absarc(x+r,y+h-r,r,P/2,P,false);
  p.lineTo(x,y+r);p.absarc(x+r,y+r,r,P,P*1.5,false);
  return p;
}
function profile(g,real){
  const S=new THREE.Shape(),P=Math.PI;let max,minT,hole;
  const poly=pts=>{S.moveTo(pts[0][0],pts[0][1]);for(let i=1;i<pts.length;i++)S.lineTo(pts[i][0],pts[i][1]);S.lineTo(pts[0][0],pts[0][1])};
  switch(g.k){
    case'flat':rrect(S,g.w,g.t,Math.min(g.t*.12,1));max=g.w;minT=g.t;break;
    case'sheet':{if(real){const t=Math.max(g.t,Math.max(real[0],real[1])/400);rrect(S,real[1],t,Math.min(.3,t*.2));max=real[1];minT=t;break}
      const t=clamp(g.t*.9,1.5,9);rrect(S,120,t,.3);max=120;minT=t;break}
    case'round':S.absarc(0,0,g.d/2,0,P*2,false);max=minT=g.d;break;
    case'square':rrect(S,g.a,g.a,g.a*.04);max=minT=g.a;break;
    case'hex':{const c=g.s/Math.sqrt(3),pts=[];for(let i=0;i<6;i++)pts.push([c*Math.cos(i*P/3),c*Math.sin(i*P/3)]);poly(pts);max=c*2;minT=g.s;break}
    case'box':rrect(S,g.a,g.b,g.t*1.6);hole=new THREE.Path();rrect(hole,g.a-2*g.t,g.b-2*g.t,g.t*.7);max=Math.max(g.a,g.b);minT=g.t;break;
    case'tube':S.absarc(0,0,g.d/2,0,P*2,false);hole=new THREE.Path();hole.absarc(0,0,g.d/2-g.t,0,P*2,true);max=g.d;minT=g.t;break;
    case'angle':{const a=g.a,b=g.b,t=g.t,x=-a/2,y=-b/2;poly([[x,y],[x+a,y],[x+a,y+t],[x+t,y+t],[x+t,y+b],[x,y+b]]);max=Math.max(a,b);minT=t;break}
    case'tee':{const a=g.a,b=g.b,t=g.t,x=a/2,y=b/2;poly([[-x,y],[x,y],[x,y-t],[t/2,y-t],[t/2,-y],[-t/2,-y],[-t/2,y-t],[-x,y-t]]);max=Math.max(a,b);minT=t;break}
    case'u':{const h=g.h,b=g.b,tw=g.tw,tf=g.tf,x=b/2,y=h/2;poly([[-x,-y],[x,-y],[x,-y+tf],[-x+tw,-y+tf],[-x+tw,y-tf],[x,y-tf],[x,y],[-x,y]]);max=Math.max(h,b);minT=Math.min(tw,tf);break}
    default:{const h=g.h,b=g.b,tw=g.tw,tf=g.tf,x=b/2,y=h/2,w=tw/2;poly([[-x,-y],[x,-y],[x,-y+tf],[w,-y+tf],[w,y-tf],[x,y-tf],[x,y],[-x,y],[-x,y-tf],[-w,y-tf],[-w,-y+tf],[-x,-y+tf]]);max=Math.max(h,b);minT=Math.min(tw,tf)}
  }
  if(hole)S.holes.push(hole);
  return{S:S,max:max,minT:minT};
}
function crease(geo,deg){
  const p=geo.attributes.position,n=p.count,cos=Math.cos(deg*Math.PI/180),fn=new Float32Array(n*3),a=new THREE.Vector3(),b=new THREE.Vector3(),c=new THREE.Vector3();
  for(let i=0;i<n;i+=3){a.fromBufferAttribute(p,i);b.fromBufferAttribute(p,i+1);c.fromBufferAttribute(p,i+2);b.sub(a);c.sub(a);b.cross(c).normalize();for(let k=0;k<3;k++){fn[(i+k)*3]=b.x;fn[(i+k)*3+1]=b.y;fn[(i+k)*3+2]=b.z}}
  const map=new Map();
  for(let i=0;i<n;i++){const key=Math.round(p.getX(i)*50)+'_'+Math.round(p.getY(i)*50)+'_'+Math.round(p.getZ(i)*50);let l=map.get(key);if(!l){l=[];map.set(key,l)}l.push(i)}
  const out=new Float32Array(n*3);
  map.forEach(l=>{for(let u=0;u<l.length;u++){const i=l[u]*3;let x=0,y=0,z=0;for(let v=0;v<l.length;v++){const j=l[v]*3;if(fn[i]*fn[j]+fn[i+1]*fn[j+1]+fn[i+2]*fn[j+2]>cos){x+=fn[j];y+=fn[j+1];z+=fn[j+2]}}const m=Math.hypot(x,y,z)||1;out[i]=x/m;out[i+1]=y/m;out[i+2]=z/m}});
  geo.setAttribute('normal',new THREE.BufferAttribute(out,3));
}
/* real: null for the sample view; a length in mm (bars) or [length, width] in mm (sheets) for true scale.
   The bevel adds to both ends, so the true-scale depth leaves room for it and the piece measures exactly `real`. */
function realOf(sp){
  const r=sp.real,n=v=>Math.round(clamp(v,1,1e5)*10)/10;
  if(flatish(sp.g)){if(!Array.isArray(r)&&!(r>0))return null;const a=Array.isArray(r)?r:[r];return[n(a[0]>0?+a[0]:sp.g.L),n(a[1]>0?+a[1]:sp.g.W)]}
  const v=Array.isArray(r)?+r[0]:+r;return v>0?n(v):null;
}
function geometry(g,f,real){
  const key=JSON.stringify(g)+'|'+(real?'R'+(real.join?real.join('x'):real):f.toFixed(2));
  if(R.geo[key])return R.geo[key];
  const p=profile(g,real),bv=Math.min(p.max*.011,p.minT*.2),curved=g.k==='round'||g.k==='tube';
  const geo=new THREE.ExtrudeGeometry(p.S,{depth:real?Math.max((real.join?real[0]:real)-2*bv,.1):p.max*f,bevelEnabled:true,bevelThickness:bv,bevelSize:bv,bevelOffset:-bv,bevelSegments:2,curveSegments:curved?72:10,steps:1});
  geo.center();crease(geo,38);geo.computeBoundingBox();geo.computeBoundingSphere();
  const b=geo.boundingBox,keys=Object.keys(R.geo);
  if(keys.length>220){keys.slice(0,60).forEach(k=>{R.geo[k].geo.dispose();delete R.geo[k]})}
  return R.geo[key]={geo:geo,x:b.max.x-b.min.x,y:b.max.y-b.min.y,z:b.max.z-b.min.z,r:geo.boundingSphere.radius};
}

/* ---------- scene ---------- */
function buildEnv(r){
  const s=new THREE.Scene();
  const room=new THREE.Mesh(new THREE.BoxGeometry(18,12,18),new THREE.MeshBasicMaterial({side:THREE.BackSide}));
  room.material.color.setRGB(.15,.155,.165);s.add(room);
  const add=(w,h,x,y,z,i,tint)=>{const t=tint||[1,1,1],m=new THREE.Mesh(new THREE.PlaneGeometry(w,h),new THREE.MeshBasicMaterial({side:THREE.DoubleSide}));m.material.color.setRGB(i*t[0],i*t[1],i*t[2]);m.position.set(x,y,z);m.lookAt(0,0,0);s.add(m)};
  add(9,9,0,5.8,.01,2.3);add(2.2,7,-7,1.5,4,11);add(1.4,7,7.5,1,-2,7,[.92,.96,1]);add(11,2.2,0,3,-8.5,5);add(16,16,0,-5.6,.01,.95,[1,.98,.95]);add(6,2.5,2,-.5,8.5,2.2,[1,.95,.88]);
  const pm=new THREE.PMREMGenerator(r),t=pm.fromScene(s,.03).texture;pm.dispose();return t;
}
/* The floor: one shader plane under the piece. It draws the grid (hairlines in kit ink, anti-aliased from
   screen-space derivatives so they stay one hairline wide at any distance and pixel ratio, fading out with
   distance from the piece and toward the frame) and, in true scale, the contact shadow as a soft box. */
const FLOOR_V='uniform float uSize;varying vec2 vP;varying vec4 vC;void main(){vP=position.xz*uSize;vC=projectionMatrix*modelViewMatrix*vec4(position,1.);gl_Position=vC;}';
const FLOOR_F=[
'uniform vec3 uInk;uniform vec4 uG;uniform vec2 uF;uniform vec4 uS;varying vec2 vP;varying vec4 vC;',
/* uG = cell, origin x, origin z (scene units), half line width (device px); uF = grid on, fade radius; uS = shadow half x, half z, blur, alpha */
'float grid(vec2 c){',
'  vec2 w=vec2(length(vec2(dFdx(c.x),dFdy(c.x))),length(vec2(dFdx(c.y),dFdy(c.y))))+1e-6;',
'  vec2 l=(1.-smoothstep(uG.w-.5,uG.w+.5,abs(fract(c-.5)-.5)/w))*(1.-smoothstep(.1,.3,w));',
'  return max(l.x,l.y);}',
'void main(){',
'  float a=0.,s=0.;',
'  if(uF.x>0.){',
'    vec2 c=(vP-uG.yz)/uG.x,q=abs(vC.xy/vC.w);',
'    a=max(grid(c)*.1,grid(c/5.)*.2)*(1.-smoothstep(.3,1.,length(vP)/uF.y))*(1.-smoothstep(.72,1.,q.x))*(1.-smoothstep(.72,1.,q.y));}',
'  if(uS.w>0.){',
'    vec2 e=abs(vP)-uS.xy;float t=clamp(1.-(length(max(e,0.))+min(max(e.x,e.y),0.))/uS.z,0.,1.);',
'    s=uS.w*t*t;}',
'  gl_FragColor=vec4(uInk*a*(1.-s),a+s-a*s);}'].join('\n');
const STEPS=[1,2,5,10,20,50,100,200,500,1000];
/* mm per grid square: the largest round step that still puts at least five squares along the piece's longest
   drawn dimension, so the piece spans 5 to 12.5 squares (more only beyond 12.5 m, fewer only under 5 mm) */
function cellOf(mm){let c=1;for(let i=0;i<STEPS.length;i++)if(mm/STEPS[i]>=5)c=STEPS[i];return c}

function init(){
  if(R.ok||R.failed)return R.ok;
  try{
    if(!window.THREE)throw new Error('three');
    const r=new THREE.WebGLRenderer({antialias:true,alpha:true});
    r.debug.checkShaderErrors=false;
    r.toneMapping=THREE.ACESFilmicToneMapping;r.toneMappingExposure=1;r.setClearColor(0x000000,0);r.setPixelRatio(1);
    const scene=new THREE.Scene();scene.environment=buildEnv(r);
    const cam=new THREE.PerspectiveCamera(26,1,.1,60);
    const k=new THREE.DirectionalLight(0xffffff,1.5);k.position.set(-3,5,4);scene.add(k);
    const f=new THREE.DirectionalLight(0xffffff,.45);f.position.set(4,2,-3);scene.add(f);
    const pivot=new THREE.Group();scene.add(pivot);
    const sc=document.createElement('canvas');sc.width=sc.height=128;const g=sc.getContext('2d',CPU),gr=g.createRadialGradient(64,64,2,64,64,64);
    gr.addColorStop(0,'rgba(0,0,0,.5)');gr.addColorStop(.55,'rgba(0,0,0,.16)');gr.addColorStop(1,'rgba(0,0,0,0)');g.fillStyle=gr;g.fillRect(0,0,128,128);
    const shadow=new THREE.Mesh(new THREE.PlaneGeometry(1,1),new THREE.MeshBasicMaterial({map:new THREE.CanvasTexture(sc),transparent:true,depthWrite:false,toneMapped:false}));
    shadow.rotation.x=-Math.PI/2;shadow.renderOrder=-1;pivot.add(shadow);
    const fm=new THREE.ShaderMaterial({vertexShader:FLOOR_V,fragmentShader:FLOOR_F,transparent:true,depthWrite:false,premultipliedAlpha:true,
      uniforms:{uInk:{value:new THREE.Color(38/255,39/255,34/255)},uSize:{value:1},uG:{value:new THREE.Vector4(1,0,0,.5)},uF:{value:new THREE.Vector2(0,1)},uS:{value:new THREE.Vector4(0,0,1,0)}}});
    fm.extensions.derivatives=true;
    const floor=new THREE.Mesh(new THREE.PlaneGeometry(1,1).rotateX(-Math.PI/2),fm);floor.renderOrder=-2;floor.frustumCulled=false;floor.visible=false;pivot.add(floor);
    const mesh=new THREE.Mesh(new THREE.BufferGeometry(),[]);pivot.add(mesh);
    Object.assign(R,{r:r,scene:scene,cam:cam,pivot:pivot,shadow:shadow,floor:floor,mesh:mesh,ok:true});
  }catch(e){R.failed=true;R.ok=false}
  return R.ok;
}
function setPiece(sp,real){
  const g=geometry(sp.g,sp.f||(flatish(sp.g)?.72:2.3),real),s=1/g.r;
  R.mesh.geometry=g.geo;R.mesh.scale.setScalar(s);
  R.mesh.material=material(sp.mat,sp.pattern,!real?0:real.join?clamp(Math.pow(2,Math.round(Math.log2(Math.min(real[0],real[1])/120))),1,8):1);
  R.shadow.scale.set(g.x*s*1.35+.22,g.z*s*1.2+.22,1);R.shadow.position.y=-g.y*s/2-.008;
  return g;
}
/* true-scale camera: the closest distance, and the sideways shift, at which all eight corners of the piece's
   bounding box (turned by yaw, seen at pitch) sit inside FIT of the frame, centred. Exact for a pinhole camera. */
const FIT=.8;
function fitBox(g,yaw,pitch,th,tv){
  const s=1/g.r,sy=Math.sin(yaw),cy=Math.cos(yaw),sp=Math.sin(pitch),cp=Math.cos(pitch),kx=FIT*th,ky=FIT*tv;
  let A=-1e9,B=-1e9,C=-1e9,D=-1e9;
  for(let i=0;i<8;i++){
    const x=(i&1?.5:-.5)*g.x*s,y=(i&2?.5:-.5)*g.y*s,z=(i&4?.5:-.5)*g.z*s,X=x*cy+z*sy,Z=z*cy-x*sy,u=y*cp-Z*sp,v=y*sp+Z*cp;
    A=Math.max(A,v+X/kx);B=Math.max(B,v-X/kx);C=Math.max(C,v+u/ky);D=Math.max(D,v-u/ky);
  }
  return{d:Math.max((A+B)/2,(C+D)/2,1.6),x:kx*(A-B)/2,y:ky*(C-D)/2};
}
/* o (live view only): {g: built geometry, sp: its description, real, cell: mm per square or 0 for no grid, dpr}.
   Thumbnails pass nothing and get the sample camera and no floor. */
function render(w,h,yaw,pitch,zoom,o){
  if(R.w!==w||R.h!==h){R.r.setSize(w,h,false);R.w=w;R.h=h}
  const cam=R.cam,asp=w/h,vf=cam.fov*Math.PI/180,tv=Math.tan(vf/2),th=tv*asp,hf=2*Math.atan(th),sp=Math.sin(pitch),cp=Math.cos(pitch);
  let dist=1.02/Math.sin(Math.min(vf,hf)/2)/zoom;
  cam.aspect=asp;
  if(o&&o.real){const b=fitBox(o.g,yaw,pitch,th,tv);dist=b.d;cam.position.set(b.x,b.y*cp+sp*dist,cp*dist-b.y*sp);cam.lookAt(b.x,b.y*cp,-b.y*sp)}
  else{cam.position.set(0,sp*dist,cp*dist);cam.lookAt(0,-.03,0)}
  cam.updateProjectionMatrix();
  const fl=R.floor;fl.visible=!!(o&&(o.cell||o.real));R.shadow.visible=!(o&&o.real);
  if(fl.visible){
    const g=o.g,s=1/g.r,u=fl.material.uniforms,hx=g.x*s/2,hy=g.y*s/2,hz=g.z*s/2,blur=clamp(hy*2.4,.012,.26);
    const rad=o.cell?1.45*Math.max(dist*Math.max(th,tv),Math.hypot(hx,hz)*1.25):0,size=2*Math.max(rad,Math.max(hx,hz)+blur);
    /* squares count from the near end of the piece; a bar lies centred on a line, a sheet has its corner on one */
    u.uG.value.set((o.cell||1)*s,flatish(o.sp)?-hx:0,hz,Math.max(.5,o.dpr*.375));
    u.uF.value.set(o.cell?1:0,rad||1);u.uS.value.set(hx,hz,blur,o.real?.42:0);u.uSize.value=size;
    fl.scale.set(size,1,size);fl.position.y=-hy-(o.real?Math.min(.008,hy*.3):.01);
  }
  R.pivot.rotation.y=yaw;R.r.render(R.scene,cam);return R.r.domElement;
}
function lengthFactor(g,lenMm,widMm){
  if(flatish(g))return clamp((lenMm||g.L)/(widMm||g.W),.4,2.2);
  return lenMm?clamp(1.6+4.2*Math.log(Math.max(lenMm,100)/100)/Math.log(60),1.4,5.5):2.3;
}
/* thumbnails are always the sample view: no grid, no true scale */
function thumb(sp,w,h){
  if(!init())return'';
  const key=JSON.stringify([sp.g,sp.mat,sp.pattern,sp.f])+'|'+w+'|'+h;
  if(R.thumbs[key])return R.thumbs[key];
  try{setPiece(sp,null);return R.thumbs[key]=render(w,h,.78,flatish(sp.g)?.52:.42,flatish(sp.g)?.84:.9).toDataURL('image/png')}catch(e){return''}
}
/* returns {cell: mm per grid square} once drawn, false when it could not draw */
function draw(canvas,sp,yaw,pitch){
  if(!init())return false;
  const dpr=Math.min(window.devicePixelRatio||1,2),w=Math.round(canvas.clientWidth*dpr),h=Math.round(canvas.clientHeight*dpr);
  if(w<8||h<8)return false;
  if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h}
  try{
    const real=realOf(sp),g=setPiece(sp,real),cell=cellOf(Math.max(g.x,g.y,g.z));
    const gl=render(w,h,yaw,flatish(sp.g)?Math.max(pitch,.5):pitch,.9,{g:g,sp:sp.g,real:real,cell:sp.grid?cell:0,dpr:dpr}),ctx=canvas.getContext('2d');
    ctx.clearRect(0,0,w,h);ctx.drawImage(gl,0,0);return{cell:cell};
  }catch(e){return false}
}
window.Rocoto3D={init:init,geomOf:geomOf,thumb:thumb,draw:draw,lengthFactor:lengthFactor,get ok(){return init()}};
})();
