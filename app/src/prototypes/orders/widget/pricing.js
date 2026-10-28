/* Purchase plans use the catalogue's selling rules. All prices include VAT.
   A missing selling rule produces an estimate requiring company confirmation. */
(function(root){
'use strict';
const DEFAULT={partLength:{table:{6:{1:.5,2:.4,3:.3,4:.2,5:.1},12:{3:.5,6:.3,9:.2}},limits:{6:{4:1,5:1},12:{9:1}}},strip:{surcharge:.2},kerfMm:{value:2},angleCutFactor:1.5,singleSheetStrokeFactor:2};
let RULES=DEFAULT;
function configure(rules){RULES=rules||DEFAULT;return API}
const kerf=()=>Number(RULES.kerfMm?.value||0);
function surcharge(L,l){if(Math.abs(l-L)<1e-6)return 0;return Number(RULES.partLength?.table?.[L]?.[l]||0)}
const base=(it,mm)=>it.p*(mm/1000)/(it.u==='m'?1:it.L);
const cost=(it,mm)=>base(it,mm)*(1+(it.u==='m'?0:surcharge(it.L,mm/1000)));
const lengths=it=>(it.r?.l||[]).map(m=>Math.round(m*1000)).filter(x=>x>0).sort((a,b)=>a-b);
const unknownSurcharge=(it,mm)=>it.u!=='m'&&mm<it.L*1000&&RULES.partLength?.table?.[it.L]?.[mm/1000]==null;
const limits=it=>RULES.partLength?.limits?.[it.L]||{};
const cutCount=(len,parts)=>{const sum=parts.reduce((a,b)=>a+b,0);return sum===len?parts.length-1:parts.length};
const fits=(len,parts)=>{const sum=parts.reduce((a,b)=>a+b,0);return sum===len||sum+kerf()*(parts.length-1)<=len};
function finish(pl,it){
  let raw=0,price=0;pl.pending=false;
  pl.units.forEach(u=>{raw+=base(it,u.len)*u.count;price+=(pl.any?base(it,u.len):cost(it,u.len))*u.count;if(!pl.any&&unknownSurcharge(it,u.len))pl.pending=true});
  if(it.u==='m'&&it.stockLengthKnown===false)pl.pending=true;
  pl.ok=true;pl.base=raw;pl.sur=price-raw;pl.price=price;pl.cutCost=pl.cuts*(it.cut||0);pl.kg=(it.w||0)*pl.bought/1000/(it.u==='m'?1:it.L);pl.total=price+pl.cutCost;return pl;
}
function fromBars(it,bars,any){
 const groups={};let bought=0,cuts=0,used=0;
 for(const b of bars){const key=b.len+'|'+b.cut.join(',');(groups[key]||(groups[key]={len:b.len,count:0,cut:b.cut})).count++;bought+=b.len;used+=b.cut.reduce((a,x)=>a+x,0);cuts+=it.r.nocut?0:cutCount(b.len,b.cut)}
 return finish({any:!!any,units:Object.values(groups).sort((a,b)=>b.len-a.len),bought,cuts,offcut:bought-used},it);
}
function valid(rows){return rows.length<=100&&rows.length>0&&rows.every(q=>Number.isFinite(q.x)&&q.x>0&&Number.isInteger(q.n)&&q.n>0&&q.n<=999)&&rows.reduce((s,r)=>s+r.n,0)<=3000}
function anyPlan(it,rows){
 const max=it.L>1?it.L*1000:Number(it.r.max||0)*1000;
 if(max&&rows.some(r=>r.x>max))return{ok:false,why:'long',max};
 const bought=rows.reduce((a,r)=>a+r.x*r.n,0),cuts=rows.reduce((a,r)=>a+(max&&r.x===max?0:r.n),0);
 const p=finish({any:true,units:rows.map(r=>({len:r.x,count:r.n,cut:[r.x]})),bought,cuts,offcut:0},it);
 if(!max)p.pending=true;return p;
}
/* Exact dynamic programming includes cutting and the catalogue's per-line sale limits. */
function barPlan(it,x,n){
 if(!valid([{x,n}]))return{ok:false,why:'empty'};
 if(it.r.k==='any')return anyPlan(it,[{x,n}]);
 const lens=lengths(it),max=lens.at(-1);if(!max)return{ok:false,why:'whole'};
 if(x>max)return{ok:false,why:'long',max};
 if(it.r.nocut&&lens.indexOf(x)<0)return{ok:false,why:'nocut',lens};
 if(it.r.nocut)return fromBars(it,Array.from({length:n},()=>({len:x,cut:[x]})));
 const lim=limits(it),limited=lens.filter(l=>lim[l/1000]!=null),memo=new Map();
 function solve(left,counts){
  if(!left)return{c:0,bars:[]};const key=left+'|'+counts.join(',');if(memo.has(key))return memo.get(key);
  let best=null;
  lens.forEach(l=>{const li=limited.indexOf(l);if(li>=0&&(counts[li]>=lim[l/1000]||counts.reduce((a,b)=>a+b,0)>=(RULES.partLength?.limitTotal?.[it.L]||1)))return;
   const cap=l%x===0?l/x:Math.floor((l+kerf())/(x+kerf()));
   // All occupancies matter: a partial bar may save a later cut.
   for(let take=1;take<=Math.min(cap,left);take++){
    const next=counts.slice();if(li>=0)next[li]++;const rest=solve(left-take,next);if(!rest)continue;
    const parts=new Array(take).fill(x),c=rest.c+cost(it,l)+cutCount(l,parts)*(it.cut||0);
    if(!best||c<best.c-1e-9)best={c,bars:[{len:l,cut:parts},...rest.bars]};
   }
  });memo.set(key,best);return best;
 }
 // For large orders, the bounded packing fallback avoids recursive browser work.
 if(n>100)return packed(it,new Array(n).fill(x),lens);
 const best=solve(n,new Array(limited.length).fill(0));return best?fromBars(it,best.bars):{ok:false,why:'long',max};
}
function packed(it,pieces,lens){
 function attempt(wholeOnly){
  const left=pieces.slice().sort((a,b)=>b-a),bars=[],counts={},lim=limits(it);
  while(left.length){let best=null;
   for(const l of (wholeOnly?[lens.at(-1)]:lens)){
    if(l<left[0]||(lim[l/1000]!=null&&((counts[l]||0)>=lim[l/1000]||Object.keys(counts).filter(k=>lim[k/1000]!=null).reduce((n,k)=>n+counts[k],0)>=(RULES.partLength?.limitTotal?.[it.L]||1))))continue;
    const take=[],parts=[];for(let j=0;j<left.length;j++)if(fits(l,[...parts,left[j]])){parts.push(left[j]);take.push(j)}
    if(!parts.length)continue;const used=parts.reduce((a,b)=>a+b,0),score=(cost(it,l)+cutCount(l,parts)*(it.cut||0))/used;
    if(!best||score<best.score)best={l,take,parts,score};
   }
   if(!best)return null;best.take.reverse().forEach(j=>left.splice(j,1));counts[best.l]=(counts[best.l]||0)+1;bars.push({len:best.l,cut:best.parts});
  }return fromBars(it,bars);
 }
 const choices=[attempt(false),attempt(true)].filter(Boolean).sort((a,b)=>a.total-b.total);return choices[0]||{ok:false,why:'whole'};
}
function listPlan(it,rows){
 if(!valid(rows))return{ok:false,why:'empty'};
 if(it.r.k==='any')return anyPlan(it,rows);
 const lens=lengths(it),max=lens.at(-1);if(!max)return{ok:false,why:'whole'};
 if(rows.some(q=>q.x>max))return{ok:false,why:'long',max};
 if(it.r.nocut){if(rows.some(q=>!lens.includes(q.x)))return{ok:false,why:'nocut',lens};return fromBars(it,rows.flatMap(q=>Array.from({length:q.n},()=>({len:q.x,cut:[q.x]}))))}
 if(rows.length===1)return barPlan(it,rows[0].x,rows[0].n);
 const pieces=rows.flatMap(q=>new Array(q.n).fill(q.x)).sort((a,b)=>b-a);
 if(pieces.length>12)return packed(it,pieces,lens);
 const lim=limits(it),limited=lens.filter(l=>lim[l/1000]!=null),memo=new Map(),groups=[];
 for(let mask=1;mask<(1<<pieces.length);mask++){const part=pieces.filter((_,j)=>mask&(1<<j));for(const len of lens)if(fits(len,part))groups.push({mask,len,cut:part,c:cost(it,len)+cutCount(len,part)*(it.cut||0)})}
 function solve(mask,counts){if(!mask)return{c:0,bars:[]};const key=mask+'|'+counts.join(',');if(memo.has(key))return memo.get(key);let best=null;const first=mask&-mask;
  for(const g of groups){if(!(g.mask&first)||(mask&g.mask)!==g.mask)continue;const li=limited.indexOf(g.len);if(li>=0&&(counts[li]>=lim[g.len/1000]||counts.reduce((a,b)=>a+b,0)>=(RULES.partLength?.limitTotal?.[it.L]||1)))continue;const next=counts.slice();if(li>=0)next[li]++;const rest=solve(mask^g.mask,next);if(rest&&(!best||rest.c+g.c<best.c-1e-9))best={c:rest.c+g.c,bars:[g,...rest.bars]}}
  memo.set(key,best);return best;
 }
 const best=solve((1<<pieces.length)-1,new Array(limited.length).fill(0));return best?fromBars(it,best.bars):packed(it,pieces,lens);
}
/* A purchased unit is at most one sheet. Choose full, half or strip by total price. */
function sheetPlan(it,a,b,n){
 const [_,W,L]=it.d,r=it.r;if(!valid([{x:a,n}])||!Number.isFinite(b)||b<=0)return{ok:false,why:'empty'};
 const orientations=[];
 for(const [x,y] of [[a,b],[b,a]]){
  if(x>W||y>L||x<1||y<1)continue;
  const across=Math.floor(W/x),down=Math.floor(L/y),capacity=across*down;
  const full=Math.floor(n/capacity),remaining=n%capacity,parts=[];
  if(full)parts.push({len:L,count:full,pcs:capacity});
  if(remaining){const rows=Math.ceil(remaining/across),needed=rows*y;
   let options=r.lengths|| (r.k==='strip'?[needed,L/2,L]:r.k==='half'?[L/2,L]:[L]);
   options=[...new Set(options)].filter(len=>len>=needed);
   const sur=len=>r.k==='strip'&&[[1000,2000],[1250,2500]].some(d=>d[0]===W&&d[1]===L)&&len<L&&len!==L/2?Number(RULES.strip?.surcharge||0):0;
   const cutsFor=len=>{let cuts=len<L?1:0,left=remaining;for(let row=0;row<rows;row++){const pcs=Math.min(left,across);cuts+=pcs*x===W?pcs-1:pcs;left-=pcs}cuts+=needed===len?rows-1:rows;return cuts};
   options.sort((l,m)=>it.p*l/L*(1+sur(l))+cutsFor(l)*(it.cut||0)-it.p*m/L*(1+sur(m))-cutsFor(m)*(it.cut||0));
   const len=options[0];parts.push({len,count:1,pcs:remaining,sur:sur(len)});
  }
  let price=0,surchargeTotal=0,cuts=0,boughtArea=0;
  for(const p of parts){const rows=Math.ceil(p.pcs/across);let count=p.len<L?1:0,left=p.pcs;
   for(let row=0;row<rows;row++){const pcs=Math.min(left,across);count+=pcs*x===W?pcs-1:pcs;left-=pcs}count+=rows*y===p.len?rows-1:rows;
   cuts+=count*p.count;const raw=it.p*p.len/L*p.count;price+=raw*(1+(p.sur||0));surchargeTotal+=raw*(p.sur||0);boughtArea+=p.len*W*p.count;
  }
  const cutCost=cuts*(it.cut||0)*(cuts===1?Number(RULES.singleSheetStrokeFactor||1):1);
  orientations.push({ok:true,units:parts.map(p=>({w:W,len:p.len,count:p.count})),frac:boughtArea/(W*L),cuts,price,base:price-surchargeTotal,sur:surchargeTotal,boughtArea,cutCost,kg:(it.w||0)*boughtArea/(W*L),total:price+cutCost,offcutArea:boughtArea-n*a*b});
 }
 return orientations.sort((p,q)=>p.total-q.total)[0]||{ok:false,why:'big',max:[W,L]};
}
/* The browser and server use this same entrypoint; callers persist only its result. */
function lineMode(i){return(i.cat?.shape==='sheet'||i.cat?.shape==='chequer')&&i.d&&i.r.k!=='whole'?'sheet':i.q&&(i.rate?.[1]==='m'||i.r?.k==='len')?'bar':((i.u&&i.u!=='m')||!i.L||i.r.k==='whole')?'piece':'bar'}
function held(plan){
 if(!plan.ok)return plan;
 return{...plan,ask:1,pending:true,base:0,sur:0,price:0,cutCost:0,total:0};
}
function quoteLine(item,line){
 if(line?.custom)return{ok:true,ask:1,total:0,cuts:0};
 if(!item||!line)return{ok:false,why:'item'};
 const mode=lineMode(item),rows=line.rows||[],sheet=line.sheet||{},angle=line.angle;
 const quantity=mode==='sheet'?sheet.n:rows.reduce((n,r)=>n+Number(r.n||0),0);
 if(!Number.isInteger(quantity)||quantity<1||quantity>3000)return{ok:false,why:'quantity'};
 if(mode==='bar'&&!valid(rows))return{ok:false,why:'empty'};
 if(mode==='piece'&&(rows.length!==1||!Number.isInteger(rows[0].n)))return{ok:false,why:'quantity'};
 /* Held-price items still need a physical material plan. It validates the requested
    geometry and records parent bar/sheet demand without publishing a guessed price. */
 const planning=item.q?{...item,p:item.p>0?item.p:(item.u==='m'?1:(item.L||1)),cut:item.cut||0}:item;
 if(item.q&&planning.L<=0&&item.r.l?.length)planning.L=Math.max(...item.r.l);
 if(item.q&&item.rate?.[1]==='m'){planning.u='m';planning.L=1}
 if(mode==='sheet')return item.q?held(sheetPlan(planning,sheet.a,sheet.b,sheet.n)):sheetPlan(item,sheet.a,sheet.b,sheet.n);
 if(mode==='bar'){
  if(item.q&&item.r.k==='whole'&&item.rate?.[1]==='m')planning.r={...item.r,k:'any'};
  const p=listPlan(planning,rows);
  if(p.ok&&angle){const degrees=typeof angle==='object'?angle.degrees:90,ends=typeof angle==='object'?angle.ends:1;
   if(!Number.isFinite(degrees)||degrees<30||degrees>150||![1,2].includes(ends))return{ok:false,why:'angle'};
   p.angle=1;p.cuts=Math.max(p.cuts,quantity*ends);p.cutCost=p.cuts*(planning.cut||0)*Number(RULES.angleCutFactor||1);p.total=p.price+p.cutCost;
  }return item.q?held(p):p;
 }
 if(item.q)return{ok:true,ask:1,pending:true,piece:1,n:quantity,units:[],cuts:0,base:0,sur:0,price:0,cutCost:0,kg:item.u==='kg'?quantity:(item.w||0)*quantity,total:0,offcut:0};
 const total=item.p*quantity;return{ok:true,piece:1,n:quantity,units:[],cuts:0,base:total,sur:0,price:total,cutCost:0,kg:item.u==='kg'?quantity:(item.w||0)*quantity,total,offcut:0};
}
const API={barPlan,listPlan,sheetPlan,surcharge,configure,lineMode,quoteLine,get KERF(){return kerf()},get rules(){return RULES}};
root.RocotoPricing=API;
})(typeof module!=='undefined'?module.exports:window);
