/* Section geometry of a catalogue item (shape + dimensions in mm), with the standard beam and channel tables.
   Exposes window.RocotoGeom. Used by the dimension drawing; the product pictures are path-traced stills. */
(function(){
'use strict';
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
window.RocotoGeom={geomOf:geomOf};
})();
