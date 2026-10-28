/* Rocoto questionnaire: a company's own guided questions that lead a customer to the right articles.
   The questions are data (`RocotoConfig.questionnaire`, written by the build from company.json); the rows they
   narrow are the catalogue's items that carry an `a` object. Two parts: the engine (no DOM, shared with the
   build-time validator's rules) and the screen, which draws into the order page's own sheet.
   Exposes window.RocotoAsk. Loaded before shop.js, which hands it what it needs through `ui(env)`. */
(function(){
'use strict';
const UNSURE='?';
const list=v=>Array.isArray(v)?v:v==null?[]:[v];

/* ---------- engine ---------- */
/* every catalogue item that carries attributes, with the group and the type it belongs to */
const rows=catalog=>catalog.cats.flatMap(c=>c.items.filter(i=>i.a).map(i=>({c:i.c,a:i.a,form:c.form,type:c.code,item:i})));
/* an earlier answer decides: every question named in `when` holds one of the listed options */
const whenOk=(when,eff)=>!when||Object.keys(when).every(k=>eff[k]&&eff[k].some(id=>when[k].indexOf(id)>=0));
/* a row stays unless it carries the attribute with none of the listed values */
const keeps=(row,match)=>!match||Object.keys(match).every(k=>row.a[k]==null||list(row.a[k]).some(v=>match[k].indexOf(v)>=0));
const option=(q,id)=>q.options.find(o=>o.id===id);
/* several chosen options widen: a row stays when any of them keeps it; «unsure» narrows nothing */
const narrow=(all,q,ids)=>ids[0]===UNSURE?all:all.filter(r=>ids.some(id=>keeps(r,(option(q,id)||{}).match)));
const inGroup=(row,g)=>list(g.category).some(c=>c===row.form||c===row.type);
/* the result groups these answers lead to; a group whose `when` names an unanswered question is undecided */
function groups(def,eff,decidedOnly){
  return def.result.groups.filter(g=>decidedOnly&&g.when&&Object.keys(g.when).some(k=>!eff[k])?false:whenOk(g.when,eff));
}
const has=(row,k,vals)=>row.a[k]!=null&&list(row.a[k]).some(v=>vals.indexOf(v)>=0);
/* an option is offered while an article left carries one of its values and every result group it leads to still holds an article */
function live(def,all,eff,q){
  return q.options.filter(o=>{
    if(!whenOk(o.when,eff))return false;
    const after=all.filter(r=>keeps(r,o.match)),then=Object.assign({},eff,{[q.id]:[o.id]});
    if(o.match&&!after.some(r=>Object.keys(o.match).some(k=>has(r,k,o.match[k]))))return false;
    return groups(def,then,true).every(g=>after.some(r=>inGroup(r,g)));
  });
}
/* walk the questions in order with the stored answers: which are asked, which answer themselves, what is left */
function walk(def,all,answers){
  const eff={},steps=[];let left=all,next=null;
  for(const q of def.questions){
    if(!whenOk(q.when,eff))continue;
    const offered=live(def,left,eff,q);
    if(!offered.length)continue;
    let ids=null,auto=false;
    if(offered.length===1){ids=[offered[0].id];auto=true}
    else{
      const given=list(answers[q.id]);
      if(given[0]===UNSURE){if(q.unsure)ids=[UNSURE]}
      else{const kept=given.filter(id=>offered.some(o=>o.id===id));if(kept.length)ids=q.kind==='multiple'?kept:[kept[0]]}
    }
    steps.push({q:q,live:offered,ids:ids,auto:auto});
    if(!ids){next=q;break}
    eff[q.id]=ids;left=narrow(left,q,ids);
  }
  return{steps:steps,eff:eff,rows:left,next:next};
}
/* the articles to show: per visible group, best first (the rows that carry the most of what was asked) */
function result(def,w){
  const asked=[];
  w.steps.forEach(s=>{if(s.ids&&s.ids[0]!==UNSURE)s.ids.forEach(id=>{const m=(option(s.q,id)||{}).match;if(m)asked.push(m)})});
  const score=r=>asked.reduce((n,m)=>n+Object.keys(m).filter(k=>has(r,k,m[k])).length,0);
  return groups(def,w.eff,false).map(g=>({group:g,rows:w.rows.filter(r=>inGroup(r,g)).map((r,n)=>({r:r,n:n,s:score(r)})).sort((a,b)=>b.s-a.s||a.n-b.n).map(x=>x.r)})).filter(g=>g.rows.length);
}
const tx=(o,lang)=>o?(o[lang]||o.bg||o.en||''):'';
/* the answers as the customer gave them: [{id, title, value}] */
function answersOf(def,w,lang){
  return w.steps.filter(s=>s.ids).map(s=>({id:s.q.id,title:tx(s.q.short||s.q.title,lang),auto:s.auto,
    value:s.ids[0]===UNSURE?STR[lang==='en'?'en':'bg'].unsure:s.ids.map(id=>tx(option(s.q,id).label,lang)+(s.q.unit?' '+tx(s.q.unit,lang):'')).join(', ')}));
}
/* one line that travels with the order, so the company sees why these articles were chosen */
const note=(def,w,lang)=>(tx(def.title,lang)+': '+answersOf(def,w,lang).map(a=>a.title+': '+a.value).join('; ')).slice(0,900);
/* the order's customer record carries every distinct note of its lines */
function stamp(customer,basket){
  const notes=[];(basket||[]).forEach(l=>{if(l&&typeof l.why==='string'&&l.why&&notes.indexOf(l.why)<0)notes.push(l.why)});
  if(notes.length)customer.questionnaire=notes.join(' | ').slice(0,1900);
  return customer;
}

/* ---------- words ---------- */
const STR={
 bg:{next:'Продължи',add:'Добави всички в поръчката',addShort:'Добави',unsure:'Не съм сигурен',change:'Промени отговорите',more:'Още {n}',
  found1:'1 подходящ артикул',found:'{n} подходящи артикула',soFar:'по вашите отговори',chosen1:'1 артикул',chosen:'{n} артикула',
  result:'Подходящи артикули',art:'№ {c}',step:'Въпрос {a} от {b}',pick:'Изберете брой за поне един артикул.',again:'Продължи'},
 en:{next:'Continue',add:'Add all to the order',addShort:'Add',unsure:'I am unsure',change:'Change the answers',more:'{n} more',
  found1:'1 matching article',found:'{n} matching articles',soFar:'for your answers',chosen1:'1 article',chosen:'{n} articles',
  result:'Matching articles',art:'No. {c}',step:'Question {a} of {b}',pick:'Set a quantity for at least one article.',again:'Continue'}};
/* small drawings a question or an option may name with `draw` */
const GLYPH={
 'hole-pz':'<circle cx="12" cy="8" r="4.5"/><path d="M9.6 11.8V19a2.4 2.4 0 0 0 4.8 0v-7.2"/>',
 'hole-bb':'<circle cx="12" cy="8" r="3.5"/><path d="M10.6 11.2 9 20h6l-1.6-8.8"/>',
 'hole-wc':'<circle cx="12" cy="12" r="7.5"/><rect x="10.25" y="6.5" width="3.5" height="11" rx="1.75"/>',
 'lever':'<rect x="3.5" y="3.5" width="6.5" height="17" rx="1.5"/><path d="M10 9.25h9a1.75 1.75 0 0 1 0 3.5h-9"/>',
 'knob':'<rect x="3.5" y="3.5" width="6.5" height="17" rx="1.5"/><path d="M10 11h2.5"/><circle cx="16.5" cy="11" r="4"/>'};
/* a lock seen from the side: the door edge on the left, the handle axis above the key. One measure is drawn strong. */
function measure(which,value){
  const strong='stroke="#1a1c1f" stroke-width="1.6" fill="none"',faint='stroke="rgba(26,28,31,.28)" stroke-width="1.2" fill="none"',
    body='fill="rgba(26,28,31,.05)" stroke="rgba(26,28,31,.44)" stroke-width="1.2" stroke-linejoin="round"',b=which!=='centres',c=which!=='backset',
    pair=String(value||'').split('/'),bv=which==='both'?pair[0]:b?value:'',cv=which==='both'?pair[1]:c?value:'';
  return '<svg viewBox="0 0 172 104" aria-hidden="true"><rect x="30" y="6" width="7" height="92" rx="1" '+body+'/><rect x="37" y="14" width="74" height="76" rx="3" '+body+'/>'+
    '<circle cx="92" cy="36" r="8" '+body+'/><rect x="88.5" y="32.5" width="7" height="7" '+faint+'/>'+
    '<circle cx="92" cy="66" r="5.5" '+body+'/><path d="M88.8 70.4V80a3.2 3.2 0 0 0 6.4 0v-9.6" '+body+'/>'+
    '<path d="M92 20v66" stroke="rgba(26,28,31,.28)" stroke-width="1" stroke-dasharray="3 3"/>'+
    '<path d="M30 52H92M30 47v10M92 47v10" '+(b?strong:faint)+'/>'+
    '<path d="M128 36V66M123 36h10M123 66h10" '+(c?strong:faint)+'/><path d="M103 36h20M100 66h23" '+faint+'/>'+
    (bv?'<text x="61" y="46" text-anchor="middle">'+bv+'</text>':'')+(cv?'<text x="138" y="55">'+cv+'</text>':'')+'</svg>';
}
const DRAW={backset:v=>measure('backset',v),centres:v=>measure('centres',v),measures:v=>measure('both',v)};

/* ---------- screen ---------- */
function ui(env){
  const K=env.K,S=env.S,CFG=env.cfg,DEF=CFG.questionnaire,esc=env.esc,ic=env.ic;
  const lang=()=>K.L.lang==='en'?'en':'bg',t=o=>tx(o,lang()),say=(k,v)=>{let s=STR[lang()][k];if(v)Object.keys(v).forEach(x=>{s=s.replace('{'+x+'}',v[x])});return s};
  const A={answers:{},at:null,qty:null,more:{},bad:false};
  let all=null,box=null;
  const state=()=>walk(DEF,all||(all=rows(K.C.data)),A.answers);
  const src=p=>(CFG.root||'')+p;
  const glyph=n=>'<svg class="i" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+GLYPH[n]+'</svg>';
  const count=w=>{const seen={};result(DEF,w).forEach(g=>g.rows.forEach(r=>{seen[r.c]=1}));return Object.keys(seen).length};
  const asked=w=>w.steps.filter(s=>!s.auto);

  /* a dark brand colour carries light words on its buttons */
  function tone(){
    const root=env.root(),m=/^#?([0-9a-f]{6})$/i.exec(CFG.accent||''),r=root&&root.querySelector('.r');if(!m||!r)return;
    const v=parseInt(m[1],16),lum=(.2126*(v>>16)+.7152*((v>>8)&255)+.0722*(v&255))/255;if(lum<.45)r.dataset.on='light';
  }
  /* the menu's first row */
  function banner(){
    setTimeout(tone,0);
    return '<section class="ask-b"><button type="button" class="ask-banner" data-ask="start"><span class="tx"><b>'+esc(t(DEF.title))+'</b>'+(DEF.help?'<small>'+esc(t(DEF.help))+'</small>':'')+'</span><span class="go">'+esc(t(DEF.start))+ic('arrow-right',18)+'</span></button></section>';
  }
  function optionsHtml(step){
    const q=step.q,ids=step.ids||[],multi=q.kind==='multiple',on=o=>ids.indexOf(o.id)>=0;
    const pressed=o=>(multi?'role="checkbox" aria-checked="':'role="radio" aria-checked="')+on(o)+'"';
    if(q.show==='tiles')return '<div class="ask-tiles" role="'+(multi?'group':'radiogroup')+'">'+step.live.map(o=>'<button type="button" class="ask-tile" data-ask-o="'+esc(o.id)+'" '+pressed(o)+'>'+(o.picture?'<span class="ph"><img src="'+esc(src(o.picture))+'" alt="" loading="lazy"></span>':'')+'<b>'+esc(t(o.label))+'</b></button>').join('')+'</div>';
    if(q.show==='cells')return '<div class="szs ask-cells" style="--w:'+(q.cell||88)+'px" role="'+(multi?'group':'radiogroup')+'">'+step.live.map(o=>'<button type="button" class="sz" data-ask-o="'+esc(o.id)+'" aria-pressed="'+on(o)+'">'+esc(t(o.label))+'</button>').join('')+'</div>';
    return '<div class="opts ask-opts" role="'+(multi?'group':'radiogroup')+'">'+step.live.map((o,n)=>{
      const visual=o.picture?'<span class="oi ph"><img src="'+esc(src(o.picture))+'" alt="" loading="lazy"></span>':o.draw&&GLYPH[o.draw]?'<span class="oi">'+glyph(o.draw)+'</span>':'';
      return '<button type="button" class="opt'+(visual?'':' plain')+(multi?' many':'')+'" data-ask-o="'+esc(o.id)+'" '+pressed(o)+'><i class="rd">'+(multi?ic('check',12,3):'')+'</i>'+visual+'<span><b>'+esc(t(o.label))+'</b>'+(o.sub?'<small>'+esc(t(o.sub))+'</small>':'')+'</span>'+(n<9?'<em class="kbd">'+(n+1)+'</em>':'')+'</button>'}).join('')+'</div>';
  }
  function questionHtml(w,step){
    const q=step.q,ids=step.ids||[],chosen=ids.length&&ids[0]!==UNSURE?t(option(q,ids[0]).label):'';
    return '<div class="q ask-q"><h1>'+esc(t(q.title))+'</h1>'+(q.help?'<p class="q-sub">'+esc(t(q.help))+'</p>':'')+
      (q.draw&&DRAW[q.draw]?'<div class="ask-draw" id="ask-draw">'+DRAW[q.draw](esc(chosen))+'</div>':'')+optionsHtml(step)+
      (q.unsure?'<button type="button" class="lnk ask-unsure" data-ask-o="'+UNSURE+'" aria-pressed="'+(ids[0]===UNSURE)+'">'+say('unsure')+'</button>':'')+'</div>';
  }
  /* quantities on the result: the best article of each group starts at one */
  function quantities(found){
    if(!A.qty){A.qty={};found.forEach(g=>{A.qty[g.rows[0].c]=1})}
    return A.qty;
  }
  function rowHtml(r,qty){
    const i=r.item,c=i.cat,a=r.a,size=a.backset&&a.centres?a.backset+'/'+a.centres:'',name=K.name({bg:c.bg,en:c.en}),sub=K.L.lang==='en'?(i.se||i.s):i.s,n=qty[r.c]||0;
    const lines=[(size&&name.indexOf(size)<0&&String(sub).indexOf(size)<0?size+' · ':'')+(sub===name?'':sub),say('art',{c:r.c})].filter(Boolean);
    return '<div class="line ask-row'+(n?'':' off')+'"><span class="lt">'+env.pic(i)+'</span><div><b>'+esc(name)+'</b>'+lines.map(x=>'<small>'+esc(x)+'</small>').join('')+'</div>'+
      '<span class="stp"><button type="button" data-ask-q="-1" data-code="'+esc(r.c)+'" aria-label="−"'+(n?'':' disabled')+'>'+ic('minus',14)+'</button><span>'+n+'</span><button type="button" data-ask-q="1" data-code="'+esc(r.c)+'" aria-label="+">'+ic('plus',14)+'</button></span></div>';
  }
  function resultHtml(w){
    const found=result(DEF,w),qty=quantities(found),given=answersOf(DEF,w,lang());
    return '<div class="q ask-q ask-r"><h1>'+esc(t(DEF.result.title)||say('result'))+'</h1>'+
      '<p class="ask-sum">'+given.map(a=>'<span>'+esc(a.value)+'</span>').join('')+'<button type="button" class="lnk" data-ask="edit">'+say('change')+'</button></p>'+
      found.map((g,k)=>{const open=A.more[k]||g.rows.length<=4,shown=open?g.rows:g.rows.slice(0,3);
        return '<section class="ask-g"><h3>'+esc(t(g.group.title))+'</h3>'+shown.map(r=>rowHtml(r,qty)).join('')+(open?'':'<button type="button" class="lnk ask-more" data-ask-more="'+k+'">'+say('more',{n:g.rows.length-shown.length})+ic('chevron-down',16)+'</button>')+'</section>'}).join('')+
      (A.bad?'<p class="ferr" role="alert">'+say('pick')+'</p>':'')+'</div>';
  }
  function barHtml(w,step){
    const act=(label,short,attr,off)=>'<button class="act" type="button" '+attr+(off?' disabled':'')+'><span class="lg">'+label+'</span><span class="sh">'+short+'</span>'+ic('arrow-right',18)+'</button>';
    if(!step){const n=Object.keys(A.qty||{}).filter(c=>A.qty[c]>0).length;
      return '<div class="tot"><span class="t1"><b class="word">'+(n===1?say('chosen1'):say('chosen',{n:n}))+'</b></span><small>'+env.u('askT')+'</small></div>'+act(say('add'),say('addShort'),'data-ask="add"',!n)}
    const n=count(w),any=w.steps.some(s=>s.ids&&!s.auto&&s!==step);
    return '<div class="tot">'+(any?'<span class="t1"><b class="word">'+(n===1?say('found1'):say('found',{n:n}))+'</b></span><small>'+say('soFar')+'</small>':'')+'</div>'+act(say('next'),say('next'),'data-ask="next"',!step.ids);
  }
  /* the question on screen: the one the customer is at, else the first one still open, else the result */
  function current(w){
    if(A.at&&A.at!=='result'){const s=w.steps.find(x=>x.q.id===A.at&&!x.auto);if(s)return s}
    if(A.at==='result'&&!w.next)return null;
    const open=w.next?w.steps[w.steps.length-1]:null;
    if(open&&!open.auto){A.at=open.q.id;return open}
    A.at='result';return null;
  }
  function paint(){
    if(!box)return;const w=state(),step=current(w),n=DEF.questions.length;
    const part=step?DEF.questions.indexOf(step.q)/n:1;
    box.querySelector('#ask-scroll').innerHTML='<div class="prog"><i style="width:'+Math.max(4,Math.round(part*100))+'%"></i></div>'+(step?questionHtml(w,step):resultHtml(w));
    box.querySelector('#ask-bar').innerHTML=barHtml(w,step);
  }
  function render(){
    const root=env.root();if(!root)return;
    if(!box){
      const main=root.querySelector('.main');if(!main)return;
      main.insertAdjacentHTML('beforeend','<div class="co ask" id="ask" hidden><div class="co-scroll" id="ask-scroll"></div><div class="i-bar" id="ask-bar"></div></div>');
      box=root.querySelector('#ask');
    }
    const on=S.open&&S.view==='ask';box.hidden=!on;
    if(!on)return;
    const logo=root.querySelector('#logo'),langs=root.querySelector('#langs');if(logo)logo.hidden=true;if(langs)langs.hidden=true;
    paint();
  }
  function start(fresh){
    if(fresh){A.answers={};A.at=null;A.qty=null;A.more={};A.bad=false}
    S.view='ask';S.bask=false;env.render();const sc=box&&box.querySelector('#ask-scroll');if(sc)sc.scrollTop=0;
  }
  function go(to){A.at=to;A.bad=false;if(to!=='result')A.qty=null;paint();box.querySelector('#ask-scroll').scrollTop=0}
  function forward(){
    const w=state(),step=current(w);if(!step)return addAll();if(!step.ids)return;
    const list=asked(w),next=list[list.indexOf(step)+1];
    go(next?next.q.id:w.next?w.next.id:'result');
  }
  function back(){
    const w=state(),step=current(w),list=asked(w).filter(s=>s.ids||s===step),at=step?list.indexOf(step):list.length;
    if(at<=0){S.view='menu';return env.render()}
    go(list[at-1].q.id);
  }
  let hop=0;
  function choose(id){
    const w=state(),step=current(w);if(!step)return;const q=step.q;
    if(id!==UNSURE&&!step.live.some(o=>o.id===id))return;
    if(id===UNSURE||q.kind!=='multiple'){A.answers[q.id]=[id];A.qty=null;paint();clearTimeout(hop);hop=setTimeout(forward,env.still&&env.still()?0:170);return}
    const had=list(A.answers[q.id]).filter(x=>x!==UNSURE),k=had.indexOf(id);if(k>=0)had.splice(k,1);else had.push(id);
    A.answers[q.id]=had;A.qty=null;paint();
  }
  function addAll(){
    const w=state();if(w.next)return;const why=note(DEF,w,lang()),picks=[];
    result(DEF,w).forEach(g=>g.rows.forEach(r=>{const n=(A.qty||{})[r.c]||0;if(n>0&&!picks.some(p=>p.code===r.c))picks.push({code:r.c,n:n})}));
    if(!picks.length){A.bad=true;return paint()}
    let last=-1;
    picks.forEach(p=>{
      const at=S.basket.findIndex(l=>!l.custom&&l.code===p.code&&!l.sheet&&l.rows&&l.rows.length===1);
      if(at>=0){S.basket[at].rows[0].n=Math.min(999,S.basket[at].rows[0].n+p.n);S.basket[at].why=why;last=at}
      else if(S.basket.length<100){S.basket.push({code:p.code,rows:[{x:1000,n:p.n}],sheet:null,angle:false,why:why});last=S.basket.length-1}
    });
    S.fresh=last;env.save();A.answers={};A.at=null;A.qty=null;A.more={};A.bad=false;
    env.showMenu();if(env.narrow&&env.narrow()){S.bask=true;env.render()}
    setTimeout(()=>{S.fresh=-1},600);
  }
  /* returns true when the click was the questionnaire's own */
  function click(e){
    const el=e.target.closest&&e.target.closest('button');if(!el)return false;const d=el.dataset;
    if(el.id==='launch'&&!S.open&&!S.basket.length){env.open();start(false);return true}
    if(d.ask==='start'){start(false);return true}
    if(S.view!=='ask')return false;
    if(d.act==='back'){back();return true}
    if(d.askO!=null){choose(d.askO);return true}
    if(d.askQ){const w=state();if(!A.qty)quantities(result(DEF,w));A.qty[d.code]=Math.max(0,Math.min(999,(A.qty[d.code]||0)+(+d.askQ)));A.bad=false;paint();return true}
    if(d.askMore!=null){A.more[d.askMore]=true;paint();return true}
    if(d.ask==='next'){forward();return true}
    if(d.ask==='add'){addAll();return true}
    if(d.ask==='edit'){const first=asked(state())[0];if(first)go(first.q.id);return true}
    return false;
  }
  function key(e){
    if(!S.open||S.view!=='ask'||e.metaKey||e.ctrlKey||e.altKey)return false;
    const ae=env.root().activeElement;
    if(e.key==='Enter'){if(ae&&ae.tagName==='BUTTON')return false;e.preventDefault();forward();return true}
    if(/^[1-9]$/.test(e.key)){const step=current(state());if(!step)return false;const o=step.live[+e.key-1];if(o){e.preventDefault();choose(o.id);return true}}
    return false;
  }
  return{banner:banner,render:render,click:click,key:key,start:start,stamp:stamp,state:A};
}
window.RocotoAsk={rows:rows,whenOk:whenOk,keeps:keeps,narrow:narrow,live:live,walk:walk,result:result,answersOf:answersOf,note:note,stamp:stamp,ui:ui,UNSURE:UNSURE,DRAWINGS:Object.keys(GLYPH).concat(Object.keys(DRAW))};
})();
