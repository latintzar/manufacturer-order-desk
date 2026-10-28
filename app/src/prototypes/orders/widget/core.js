/* Rocoto configurator core: language, formatting, the catalogue index and search.
   Exposes window.RocotoCore. No DOM here. */
(function(){
'use strict';
const X=' × ';
const STR={
 en:{launch:'Instant quote',launchGo:'Configure',search:'Search {n} sizes: 40x40x3 square tube',basket:'Basket',close:'Close',
  metal:'Metal',form:'Form',type:'Type',size:'Size',cut:'Cut list',sheetCut:'Pieces',len:'Length',wid:'Width',qty:'Pieces',mm:'mm',
  addLen:'Add a length',addSize:'Add a size',remove:'Remove',fullBar:'{l} m',
  outside:'Outside',wall:'Wall',width:'Width',thick:'Thickness',dia:'Diameter',legs:'Legs',format:'Sheet',grade:'Grade',side:'Side',af:'Across flats',item:'Item',
  total:'Total',incVat:'incl. VAT',exVat:'{v} excl. VAT',each:'each',
  youBuy:'You buy',bar:'{n} × {l} m',strip:'{n} × strip {w} × {l} mm',halfSheet:'{n} × half sheet',wholeSheet:'{n} × sheet {w} × {l} mm',piece:'{n} × {l} mm',
  material:'Material',cutting:'Cutting',cuts:'{n} cuts',cut1:'1 cut',noCuts:'Sold uncut',kg:'{v} kg',
  offcut:'The {v} mm offcut comes with your order.',offcuts:'{v} mm of offcuts come with your order.',exact:'Cut with nothing left over.',
  ready:'Ready {when}',delivered:'Delivered {when}',pickup:'Pickup',add:'Add to basket',update:'Update basket',
  today:'today',tomorrow:'tomorrow',at:'{d}, {t}',
  tooLong:'The longest piece we sell is {v} mm.',tooBig:'The largest sheet is {w} × {l} mm.',wholeOnly:'Sold in whole lengths of {v}.',enterLen:'Enter a length in millimetres.',
  basketEmpty:'Your pieces collect here as you add them.',keep:'Keep configuring',checkout:'Checkout',edit:'Edit',
  contact:'Contact',email:'Email',phone:'Phone',receive:'Receiving',pick:'Pickup',pickSub:'',deliver:'Delivery',deliverSub:'By our truck, to your address',free:'Free',
  address:'Address',city:'City',invoice:'Invoice',person:'Individual',company:'Company',name:'Name',coName:'Company name',eik:'Company ID (EIK)',vatNo:'VAT number',mol:'Accountable person',
  notes:'Extra processing',notesPh:'Bending, threads, powder coating: describe it and we confirm the price before you pay.',
  pay:'Payment',card:'Card',cardSub:'Visa, Mastercard',bank:'Bank transfer',bankSub:'Proforma invoice by email',onPickup:'On pickup',onPickupSub:'Card or cash at the counter',
  payNow:'Pay {v}',placeOrder:'Place order',summary:'Order',discount:'Discount code',apply:'Apply',subtotal:'Subtotal excl. VAT',vat:'VAT 20%',delivery:'Delivery',back:'Back to basket',
  payNote:'Card payment opens here once Stripe is connected.',tryQ:['40x40x3 square tube','stainless sheet 2','brass hex 17','IPE 200'],noRes:'Try a size like 40x40x3, or a metal and a form like stainless tube.',
  sizes:'{n} sizes',from:'from {v}',perBar:'per {l} m',perSheet:'per sheet',perM:'per m',inStock:'In stock',preview:'Preview by Rocoto',order:'Order',lines:'{n} pieces'},
 bg:{launch:'Моментална оферта',launchGo:'Конфигурирай',search:'Търси в {n} размера: 40х40х3 квадратна тръба',basket:'Количка',close:'Затвори',
  metal:'Метал',form:'Форма',type:'Вид',size:'Размер',cut:'Разкрой',sheetCut:'Детайли',len:'Дължина',wid:'Ширина',qty:'Брой',mm:'мм',
  addLen:'Добави дължина',addSize:'Добави размер',remove:'Премахни',fullBar:'{l} м',
  outside:'Външен размер',wall:'Дебелина на стената',width:'Ширина',thick:'Дебелина',dia:'Диаметър',legs:'Рамене',format:'Лист',grade:'Марка',side:'Страна',af:'Размер S',item:'Артикул',
  total:'Общо',incVat:'с ДДС',exVat:'{v} без ДДС',each:'за брой',
  youBuy:'Купувате',bar:'{n} × {l} м',strip:'{n} × лента {w} × {l} мм',halfSheet:'{n} × половин лист',wholeSheet:'{n} × лист {w} × {l} мм',piece:'{n} × {l} мм',
  material:'Материал',cutting:'Рязане',cuts:'{n} среза',cut1:'1 срез',noCuts:'Продава се цяло',kg:'{v} кг',
  offcut:'Остатъкът от {v} мм идва с поръчката.',offcuts:'Остатъците от {v} мм идват с поръчката.',exact:'Разкрой без остатък.',
  ready:'Готово {when}',delivered:'Доставка {when}',pickup:'Вземане',add:'Добави в количката',update:'Обнови количката',
  today:'днес',tomorrow:'утре',at:'{d} в {t}',
  tooLong:'Най-дългото парче е {v} мм.',tooBig:'Най-големият лист е {w} × {l} мм.',wholeOnly:'Продава се на цели дължини от {v}.',enterLen:'Въведете дължина в милиметри.',
  basketEmpty:'Тук се събират детайлите, които добавяте.',keep:'Продължи',checkout:'Към поръчка',edit:'Промени',
  contact:'Контакт',email:'Имейл',phone:'Телефон',receive:'Получаване',pick:'Вземане от склада',pickSub:'',deliver:'Доставка',deliverSub:'С наш камион до вашия адрес',free:'Безплатно',
  address:'Адрес',city:'Град',invoice:'Фактура',person:'Физическо лице',company:'Фирма',name:'Име',coName:'Име на фирмата',eik:'ЕИК',vatNo:'ДДС номер',mol:'МОЛ',
  notes:'Допълнителна обработка',notesPh:'Огъване, резби, прахово боядисване: опишете го и потвърждаваме цената преди плащане.',
  pay:'Плащане',card:'Карта',cardSub:'Visa, Mastercard',bank:'Банков превод',bankSub:'Проформа фактура по имейл',onPickup:'При получаване',onPickupSub:'С карта или в брой на касата',
  payNow:'Плати {v}',placeOrder:'Поръчай',summary:'Поръчка',discount:'Код за отстъпка',apply:'Приложи',subtotal:'Сума без ДДС',vat:'ДДС 20%',delivery:'Доставка',back:'Към количката',
  payNote:'Плащането с карта се отваря тук след свързване със Stripe.',tryQ:['40х40х3 квадратна тръба','неръждаема ламарина 2','месинг шестостен 17','IPE 200'],noRes:'Опитайте размер като 40х40х3 или метал и форма, например неръждаема тръба.',
  sizes:'{n} размера',from:'от {v}',perBar:'за {l} м',perSheet:'за лист',perM:'за м',inStock:'Налично',preview:'Preview by Rocoto',order:'Поръчай',lines:'{n} бр.'}
};
const DAYS={en:['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'],bg:['неделя','понеделник','вторник','сряда','четвъртък','петък','събота']};
const RC=window.RocotoConfig||{};
/* language from the host page's path: {root:'/metal-m', langs:{bg:'/bg/', en:'/en/'}, lang:'bg'} */
const L={lang:(function(){const embedded=/(?:[?&])rocoto_embed=1(?:&|$)/.test(location.search||'')?new URLSearchParams(location.search).get('lang'):null;if(embedded&&(embedded===RC.lang||Object.hasOwn(RC.langs||{},embedded)))return embedded;const p=location.pathname,r=RC.root||'',m=RC.langs||{en:'/en/'};for(const k in m){const pre=r+m[k];if(p===pre.replace(/\/$/,'')||p.indexOf(pre)===0)return k}return RC.lang||'bg'})()};
const OVR=RC.strings||{};
function t(k,v){let s=(OVR[L.lang]||{})[k];if(s==null)s=(STR[L.lang]||STR.en)[k];if(s==null)s=STR.en[k];if(typeof s!=='string')return s;if(v)Object.keys(v).forEach(x=>{s=s.replace('{'+x+'}',v[x])});return s}
const loc=()=>L.lang==='bg'?'bg-BG':'en-GB';
const num=(n,d)=>n.toLocaleString(loc(),{maximumFractionDigits:d==null?0:d,minimumFractionDigits:0});
const eur=(n,d=2)=>new Intl.NumberFormat(loc(),{style:'currency',currency:C.data?.currency||'EUR',maximumFractionDigits:d,minimumFractionDigits:2}).format(n);
const dimStr=d=>String(d).replace('.',L.lang==='bg'?',':'.');
const name=o=>o?(o[L.lang]||o.en||o.bg):'';

/* ---------- catalogue ---------- */
const C={ready:false,cats:[],byCode:{},items:{},metals:[],forms:[]};
const TWO={sq_tube:2,rect_tube:2,angle:2,angle_u:2,tee:2,channel:2,flat:1,round_tube:1,sheet:1,chequer:1};
const HEAD={sq_tube:['outside','wall'],rect_tube:['outside','wall'],flat:['width','thick'],round_tube:['dia','wall'],angle:['legs','thick'],angle_u:['legs','thick'],tee:['size','thick'],
  channel:['size','thick'],sheet:['thick','format'],chequer:['thick','format'],round:['dia','grade'],square:['side','grade'],hex:['af','grade'],ipe:['size','grade'],hea:['size','grade'],heb:['size','grade'],upn:['size','grade'],special:['item','grade']};
function tail(it){return L.lang==='en'?(it.te||it.t||''):(it.t||'')}
function k1(it){
  const sh=it.cat.shape,d=it.d;
  if(!d)return L.lang==='en'?(it.se||it.s):it.s;
  const a=d.slice(0,TWO[sh]||d.length).map(dimStr);
  switch(sh){
    case'round_tube':case'round':return'Ø '+a[0];
    case'square':return a[0];
    case'hex':return(L.lang==='en'?'AF ':'S ')+a[0];
    case'ipe':return'IPE '+a[0];case'hea':return'HEA '+a[0];case'heb':return'HEB '+a[0];
    case'upn':return(/ГОСТ|GOST/.test(it.t||it.te||'')?'GOST ':'UPN ')+a.join(X);
    default:return a.join(X);
  }
}
function k2(it){
  const sh=it.cat.shape,d=it.d;if(!d)return'';
  const rest=d.slice(TWO[sh]||d.length).map(dimStr).join(X),tl=tail(it);
  return(rest+(rest&&tl?' ':'')+tl).trim();
}
function label(it){
  const d=it.d,sh=it.cat.shape;
  if(!d)return k1(it);
  const all=d.map(dimStr);let s;
  switch(sh){
    case'round_tube':s='Ø '+all.join(X);break;
    case'round':s='Ø '+all[0];break;
    case'square':s=all[0]+X+all[0];break;
    case'hex':s=(L.lang==='en'?'AF ':'S ')+all[0];break;
    case'ipe':case'hea':case'heb':s=sh.toUpperCase()+' '+all[0];break;
    case'upn':s=(/ГОСТ|GOST/.test(it.t||it.te||'')?'GOST ':'UPN ')+all.join(X);break;
    default:s=all.join(X);
  }
  const tl=sh==='upn'?tail(it).replace(/ГОСТ|GOST/g,'').trim():tail(it);return s+(tl?' '+tl:'');
}
function index(data){
  C.data=data;C.cats=data.cats;C.metals=data.metals;C.forms=data.forms;C.n=0;C.byCode={};C.items={};
  if(window.RocotoPricing)window.RocotoPricing.configure(data.rules);
  data.cats.forEach(c=>{C.byCode[c.code]=c;c.items.forEach((it,i)=>{it.cat=c;it.i=i;it.mat=it.m||c.mat;C.items[it.c]=it;C.n++})});
  C.ready=true;
}
const formsOf=m=>C.forms.filter(f=>C.cats.some(c=>c.metal===m&&c.form===f.id));
const catsOf=(m,f)=>C.cats.filter(c=>c.metal===m&&c.form===f);
function levels(cat){
  /* -> [{key,label,items:[...]}] grouped by the first size level, in catalogue order */
  const out=[],map={};
  cat.items.forEach(it=>{const k=k1(it);if(!map[k]){map[k]={key:k,items:[]};out.push(map[k])}map[k].items.push(it)});
  const compare=(a,b)=>{const x=a.d||[],y=b.d||[];for(let j=0;j<Math.max(x.length,y.length);j++){const d=(x[j]||0)-(y[j]||0);if(d)return d}return (a.L||0)-(b.L||0)||k1(a).localeCompare(k1(b),loc(),{numeric:true})};
  out.forEach(g=>g.items.sort(compare));return out.sort((a,b)=>compare(a.items[0],b.items[0]));
}
const mid=cat=>cat.items[Math.min(cat.items.length-1,Math.floor(cat.items.length*.42))];
function unitNote(it){
  if(!it.L)return t('perSheet');
  return it.L===1?t('perM'):t('perBar',{l:dimStr(it.L)});
}

/* ---------- search ---------- */
const SYN={
 cherni:['black','steel','mild','черна','черни','черен','стомана','желязо','s235','s355'],
 potsinkovani:['galvanised','galvanized','galv','zinc','поцинкована','поцинковани','поцинк'],
 nerazhdaemi:['stainless','inox','ss','304','316','неръждаема','неръждаеми','инокс','неръждавейка'],
 aluminievi:['aluminium','aluminum','alu','алуминиева','алуминиеви','алуминий'],
 medni:['copper','cu','медна','медни','мед'],mesingovi:['brass','месинг','месингова','месингови'],
 bronzovi:['bronze','бронз','бронзови'],olovni:['lead','олово','оловна'],
 sq_tube:['square','tube','box','hollow','shs','квадратна','квадратни','тръба','тръби','профил','кух'],
 rect_tube:['rectangular','tube','box','hollow','rhs','правоъгълна','правоъгълни','тръба','тръби','профил','кух'],
 round_tube:['tube','round','pipe','chs','кръгла','кръгли','тръба','тръби'],
 flat:['flat','bar','strip','шина','шини','планка'],round:['round','bar','rod','кръг','кръгове','прът'],
 square:['square','bar','квадрат','квадрати'],hex:['hexagon','hex','шестостен','шестостени'],
 angle:['angle','винкел','винкели','ъглов'],angle_u:['angle','unequal','винкел','винкели','разностранен'],
 tee:['tee','t','т-профил','тпрофил'],ipe:['ipe','beam','греда','двойно'],hea:['hea','beam','греда'],heb:['heb','beam','греда'],
 channel:['channel','u','п-профил','ппрофил','швелер'],upn:['upn','channel','u','швелер','п-профил'],
 sheet:['sheet','plate','ламарина','ламарини','лист'],chequer:['chequer','checker','tread','floor','plate','рифелова','рифелови','ламарина'],special:[]
};
const STOP={x:1,mm:1,'мм':1,m:1,'м':1,'на':1,'за':1,'от':1,of:1,the:1,'х':1};
function lev(a,b){
  if(Math.abs(a.length-b.length)>2)return 9;
  let p=[];for(let j=0;j<=b.length;j++)p[j]=j;
  for(let i=1;i<=a.length;i++){const c=[i];for(let j=1;j<=b.length;j++)c[j]=Math.min(p[j]+1,c[j-1]+1,p[j-1]+(a[i-1]===b[j-1]?0:1));p=c}
  return p[b.length];
}
function tok(w,al){
  let best=0;
  for(let i=0;i<al.length;i++){
    const a=al[i];let s=0;
    if(a===w)s=1;
    else if(w.length>=3&&a.indexOf(w)===0)s=.8;
    else if(a.length>=5&&w.length>=5&&a.slice(0,5)===w.slice(0,5))s=.75;
    else if(w.length>=4&&lev(w,a)<=(w.length>=7?2:1))s=.6;
    if(s>best)best=s;
  }
  return best;
}
function aliases(c){
  if(c._al)return c._al;
  const words=(c.bg+' '+c.en).toLowerCase().split(/[^a-zа-я0-9]+/).filter(w=>w.length>2);
  return c._al=(SYN[c.metal]||[]).concat(SYN[c.shape]||[],words);
}
function search(raw,limit){
 const input=raw.trim().toLowerCase(),exact=Object.values(C.items).find(i=>String(i.c).toLowerCase()===input);
 if(exact)return[{item:exact,score:1000}];
 const q=input.replace(/(\d)[х×*x](?=\d)/g,'$1 ').replace(/(\d),(\d)/g,'$1.$2').replace(/[фø]/g,' ').replace(/(\d)\s*(mm|мм)/g,'$1 ');
 const nums=[],words=[];
 q.split(/[^a-zа-я0-9.]+/).filter(Boolean).forEach(w=>{if(/^\d+(\.\d+)?$/.test(w)&&!/^(304|316|235|355)$/.test(w))nums.push(String(parseFloat(w)));else if(!STOP[w])words.push(w)});
 if(!nums.length&&!words.length)return null;
 const out=[],partial=/\d$/.test(raw);
 C.cats.forEach((c,ci)=>{
  const al=aliases(c),categoryScores=words.map(w=>tok(w,al)),categoryMatch=words.length&&categoryScores.every(Boolean);
  if(!nums.length&&categoryMatch)out.push({cat:c,score:categoryScores.reduce((a,b)=>a+b,0)*2-ci*.001});
  c.items.forEach(it=>{
   const text=[it.c,it.s,it.se,it.t,it.te,it.grp].filter(Boolean).join(' ').toLowerCase(),itemWords=text.split(/[^a-zа-я0-9]+/).filter(Boolean);
   const scores=words.map((w,j)=>Math.max(categoryScores[j],tok(w,itemWords)));if(scores.some(x=>!x))return;
   if(!nums.length){if(!categoryMatch&&words.some(w=>tok(w,itemWords)>0))out.push({item:it,score:scores.reduce((a,b)=>a+b,0)*2+1-ci*.001});return}
   const dims=(it.d?(c.shape==='square'?[it.d[0],it.d[0]]:it.d):(((it.s||it.se||'').match(/\d+(?:[.,]\d+)?/g)||[]).map(v=>Number(v.replace(',','.'))))).map(String),used=[];let score=0,len=null;
   for(let k=0;k<nums.length;k++){
    const n=nums[k];let j=dims.findIndex((d,x)=>!used[x]&&d===n);
    if(j<0&&k===nums.length-1&&partial)j=dims.findIndex((d,x)=>!used[x]&&d.startsWith(n));
    if(j>=0){used[j]=1;score+=dims[j]===n?3:1;continue}
    const max=it.r?.l?.length?Math.max(...it.r.l)*1000:it.L>1?it.L*1000:0;
    if(it.d&&k===nums.length-1&&k>0&&Number(n)>=100&&Number(n)<=max){len=Number(n);continue}return;
   }
   out.push({item:it,len,score:scores.reduce((a,b)=>a+b,0)*2+score+(used.filter(Boolean).length===dims.length?1:0)-ci*.001-it.i*.00001});
  });
 });
 return out.sort((a,b)=>b.score-a.score).slice(0,limit||7);
}

window.RocotoCore={L:L,OVR:OVR,t:t,num:num,eur:eur,dimStr:dimStr,name:name,C:C,index:index,formsOf:formsOf,catsOf:catsOf,levels:levels,mid:mid,k1:k1,k2:k2,label:label,tail:tail,
  HEAD:HEAD,TWO:TWO,unitNote:unitNote,search:search,X:X};
})();
