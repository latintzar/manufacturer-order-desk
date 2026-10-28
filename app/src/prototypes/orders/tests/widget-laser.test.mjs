import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';
/* Turnaround tiers, the laser estimate on a checked drawing, and the recurring-work answer in an order.
   fixtures/laser-check.json is the answer of POST api/laser for examples/constellation-400mm.dxf under Korn Metal's laser block. */
const here=new URL('.',import.meta.url),read=path=>readFileSync(new URL(path,here),'utf8');
const check=JSON.parse(read('fixtures/laser-check.json'));
const TURNAROUND={status:'assumed',stock:[1,2],cut:[2,3],custom:[3,5]};
const catalogue={company:{en:'Example',bg:'Пример'},currency:'EUR',vat:.2,metals:[{id:'steel',en:'Steel',bg:'Стомана'}],forms:[{id:'tube',en:'Tubes',bg:'Тръби'}],cats:[
 {code:'t',en:'Square tubes',bg:'Квадратни тръби',metal:'steel',form:'tube',shape:'sq_tube',items:[{c:'T1',s:'20x20x2',d:[20,20,2],p:30,L:6,r:{k:'len',l:[2,3,6]},cut:2,w:10}]},
 {code:'h',en:'Hardware',bg:'Обков',metal:'steel',form:'tube',shape:'special',items:[{c:'HINGE',s:'Hinge',p:4,L:0,w:0,u:'pc',r:{k:'whole'}}]}]};
function widget(config={},fetch=async()=>({ok:true,json:async()=>({ok:true})}),path='/x/'){
 const session=new Map(),local=new Map();
 const context={window:{RocotoConfig:{root:'/x',lang:'bg',langs:{en:'/en/'},...config}},location:{pathname:path},document:{readyState:'loading',addEventListener(){}},__ICONS__:{},__CSS__:'',fetch,AbortController,setTimeout,clearTimeout,
  crypto:{randomUUID:()=>'key_'+Math.random().toString(36).slice(2)},localStorage:{getItem:k=>local.get(k),setItem:(k,v)=>local.set(k,v)},sessionStorage:{getItem:k=>session.get(k),setItem:(k,v)=>session.set(k,v),removeItem:k=>session.delete(k)}};
 vm.createContext(context);
 for(const file of ['../widget/pricing.js','../widget/core.js','../widget/laser.js','../laser_quote.mjs'])vm.runInContext(read(file),context);
 context.window.RocotoCore.index(structuredClone(catalogue));
 const hooks='renderAll=()=>{};renderBasket=()=>{};paintCo=()=>{};root={querySelector:()=>({innerHTML:"",scrollTop:0})};window.TEST={S,LZC,U,taTier,taText,taOf,taLine,taBasket,taHtml,catRow,basketHtml,headHtml,barHtml,laserHtml,lzBarHtml,lzNow,lzAdd,lzOpen,laserCheck,lineHtml,wire,load,save,submit,recFields,coHtml,CO,onClick,onInput,setSupply:v=>{SUPPLY=v}};';
 vm.runInContext(read('../widget/shop.js').replace('window.RocotoConfigurator={open:open,close:close,state:S};',hooks),context);
 return {...context.window.TEST,quote:context.window.RocotoLaserQuote.quote,K:context.window.RocotoCore,LZ:context.window.RocotoLaser,local};
}
const plain=value=>JSON.parse(JSON.stringify(value));
const press=(h,dataset)=>h.onClick({target:{closest:()=>({dataset})}});
const drawing=h=>{h.LZC[check.id]=check;h.S.lz={step:'material',file:{id:'a'.repeat(32),discard_token:'t'},check,material:'s235',thickness:2,n:1,busy:'',bad:'',name:check.name,editing:-1};h.S.view='laser'};

test('turnaround tiers: one day gold, two days green, three to five blue, longer or unknown neutral',()=>{
 const h=widget({turnaround:TURNAROUND});
 assert.deepEqual([[1,1],[1,2],[2,2],[2,3],[3,5],[5,5],[4,6],[7,10],null].map(h.taTier),[1,2,2,3,3,3,0,0,0]);
 assert.equal(h.taText([1,1]),'1 ден');assert.equal(h.taText([2,2]),'2 дни');assert.equal(h.taText([3,5]),'3–5 дни');assert.equal(h.taText([7,10]),'По потвърждение');assert.equal(h.taText(null),'По потвърждение');
 const en=widget({turnaround:TURNAROUND},undefined,'/x/en/');
 assert.equal(en.taText([1,1]),'1 day');assert.equal(en.taText([2,2]),'2 days');assert.equal(en.taText([3,5]),'3–5 days');assert.equal(en.taText(null),'On confirmation');
 assert.match(h.taHtml([3,5],''),/class="ta" data-t="3"[^>]*><b>3–5 дни<\/b><small>Ориентировъчно, потвърждава се по имейл<\/small>/);
 assert.match(h.taHtml([1,1],'s'),/class="ta s" data-t="1"/);assert(!h.taHtml([1,1],'s').includes('<small>'));
});
test('a line takes its days from its kind: whole stock, a cut list, custom and laser work',()=>{
 const h=widget({turnaround:TURNAROUND});
 assert.deepEqual(plain(h.taLine({code:'HINGE',rows:[{x:0,n:2}]})),[1,2]);
 assert.deepEqual(plain(h.taLine({code:'T1',rows:[{x:6000,n:1}]})),[1,2]);
 assert.deepEqual(plain(h.taLine({code:'T1',rows:[{x:1200,n:2}]})),[2,3]);
 assert.deepEqual(plain(h.taLine({custom:'Bent plate'})),[3,5]);
 assert.deepEqual(plain(h.taLine({laser:{id:check.id,material:'s235',thickness:2,quantity:1},view:{}})),[3,5]);
 h.setSupply({items:{HINGE:{turnaround:{days:[1,1],status:'confirmed'}}}});
 assert.deepEqual(plain(h.taLine({code:'HINGE',rows:[{x:0,n:2}]})),[1,1]);
 assert.match(h.catRow(h.K.C.byCode.t),/class="ta s" data-t="2"[^>]*>.*1–2 дни/);
});
test('the basket states the turnaround of its slowest line, at the top of the panel',()=>{
 const h=widget({turnaround:TURNAROUND});
 h.S.basket=[{code:'HINGE',rows:[{x:0,n:2}]}];
 assert.deepEqual(plain(h.taBasket(h.S.basket)),[1,2]);assert.match(h.basketHtml(),/<div class="b-top">.*class="ta" data-t="2"[^>]*><b>1–2 дни<\/b>/s);
 h.S.basket.push({code:'T1',rows:[{x:1200,n:2}]});assert.deepEqual(plain(h.taBasket(h.S.basket)),[2,3]);
 h.S.basket.push({custom:'Bent plate'});assert.deepEqual(plain(h.taBasket(h.S.basket)),[3,5]);
 assert.match(h.basketHtml(),/class="ta" data-t="3"[^>]*><b>3–5 дни<\/b>/);
 h.S.basket=[];assert(!h.basketHtml().includes('class="ta"'));
});
test('a company with unknown timing omits the timing card and retains confirmed timings',()=>{
 const h=widget();h.S.basket=[{code:'HINGE',rows:[{x:0,n:2}]}];
 assert.equal(h.taBasket(h.S.basket),null);assert(!h.basketHtml().includes('class="ta"'));
 h.S.item='T1';h.S.rows=[{x:1200,n:1}];assert(!h.headHtml().includes('class="ta'));assert(!h.barHtml().includes('class="ta'));
 const set=widget({turnaround:TURNAROUND});set.S.item='T1';set.S.rows=[{x:1200,n:1}];
 assert.match(set.headHtml(),/class="ta m" data-t="3"[^>]*><b>2–3 дни/);assert.match(set.barHtml(),/class="ta s" data-t="3"/);
 set.S.rows=[{x:6000,n:1}];assert.match(set.headHtml(),/class="ta m" data-t="2"[^>]*><b>1–2 дни/);
});

test('the laser estimate follows material, thickness and quantity by the server formula',()=>{
 const h=widget({laser:true,turnaround:TURNAROUND});drawing(h);
 assert.equal(h.lzNow().gross,20.14);assert.match(h.lzBarHtml(),/20,14\s€/);
 press(h,{lzMat:'inox'});assert.equal(h.S.lz.material,'inox');assert.equal(h.S.lz.thickness,2);
 press(h,{lzTh:'3'});for(let i=0;i<4;i++)press(h,{lzD:'1'});
 assert.equal(h.S.lz.n,5);const q=h.lzNow();assert.equal(q.gross,130.22);assert.equal(q.net,108.52);assert.equal(q.piece,21.7);
 h.onInput({target:{value:'12',dataset:{lzN:''}}});assert.equal(h.S.lz.n,12);
 h.onInput({target:{value:'0',dataset:{lzN:''}}});assert.equal(h.S.lz.n,12);
 press(h,{lzMat:'brass'});press(h,{lzTh:'10'});press(h,{lzMat:'s235'});assert.equal(h.S.lz.thickness,10);
 press(h,{lzTh:'25'});press(h,{lzMat:'brass'});assert.equal(h.S.lz.thickness,10);
});
test('a checked drawing draws its lines, marks each finding and names the corrected file',()=>{
 const h=widget({laser:true,turnaround:TURNAROUND});drawing(h);h.S.lz.step='check';
 const html=h.laserHtml();
 assert.equal((html.match(/class="dw-m ok"/g)||[]).length,check.issues.filter(i=>i.fixed).length);
 assert.match(html,/400 × 400 мм/);assert.match(html,/2,05 м/);assert.match(html,/2 отворени контура/);assert.match(html,/1 дублирана линия/);
 assert.match(html,/Коригирахме чертежа/);assert.match(html,/api\/laser\/[0-9a-f]{32}\/fixed\.dxf/);assert.match(h.lzBarHtml(),/Използвай коригирания файл/);
 const parts=h.LZ.shapes(check,6000);assert.equal(parts.length,1);assert.equal(parts[0].holes.length,15);
 assert(h.LZ.shapes(check,120).reduce((n,p)=>n+p.outer.length+p.holes.reduce((a,x)=>a+x.length,0),0)<=200);
});
test('a laser line sits in the basket with its picture and estimate; the server reads its four values',()=>{
 const h=widget({laser:true,turnaround:TURNAROUND});drawing(h);h.S.lz.step='summary';
 assert.match(h.laserHtml(),/Обобщение.*constellation-400mm\.dxf.*Черна стомана · 2 мм.*20,14\s€/s);
 h.lzAdd();assert.equal(h.S.basket.length,1);assert.equal(h.S.view,'menu');
 const line=h.S.basket[0];assert.deepEqual(JSON.parse(JSON.stringify(line.laser)),{id:check.id,material:'s235',thickness:2,quantity:1});
 assert.match(line.view.d,/^[MLZ0-9 .-]+$/);assert.equal(line.view.gross,20.14);
 assert.deepEqual(plain(h.wire(h.S.basket)),[{laser:{id:check.id,material:'s235',thickness:2,quantity:1}}]);
 const html=h.basketHtml();assert.match(html,/Лазерно рязане/);assert.match(html,/20,14\s€/);assert.match(html,/ориентировъчна цена/);assert.match(html,/class="ta" data-t="3"/);
 press(h,{ld:'1',n:'0'});assert.equal(h.S.basket[0].laser.quantity,2);assert.equal(h.S.basket[0].view.gross,h.quote(check,check.materials[0],check.tariff,2,2).gross);
 h.save();const again=widget({laser:true},undefined);again.local.set('rocoto-basket-v1',h.local.get('rocoto-basket-v1'));again.load();assert.equal(again.S.basket.length,1);
 const off=widget({});off.local.set('rocoto-basket-v1',h.local.get('rocoto-basket-v1'));off.load();assert.equal(off.S.basket.length,0);
});
test('a refused drawing names its reason and can go on as a custom request',async()=>{
 const h=widget({laser:true},async()=>({ok:false,json:async()=>({ok:false,reason:'time',message:'x'})}));
 h.lzOpen();h.S.lz.file={id:'b'.repeat(32),name:'big.dxf',discard_token:'t'};h.S.lz.name='big.dxf';
 await h.laserCheck();assert.equal(h.S.lz.step,'file');assert.equal(h.S.lz.bad,'lzR_time');
 assert.match(h.laserHtml(),/Работилницата разчита този чертеж ръчно/);assert.match(h.laserHtml(),/data-act="lz-custom"/);
 press(h,{act:'lz-custom'});assert.equal(h.S.view,'custom');assert.equal(h.S.customFile.name,'big.dxf');
 const ok=widget({laser:true},async()=>({ok:true,json:async()=>check}));ok.lzOpen();ok.S.lz.file={id:'c'.repeat(32),name:check.name};
 await ok.laserCheck();assert.equal(ok.S.lz.step,'check');assert.equal(ok.S.lz.material,'s235');assert.equal(ok.S.lz.thickness,2);
});

test('recurring work travels with the order in the customer fields, in both languages',async()=>{
 const calls=[],good=async(url,request)=>{calls.push(JSON.parse(request.body));return{ok:true,json:async()=>({ok:true,id:'saved',quote:{gross:8},ready:{}})}};
 const h=widget({checkout:{recurring:{ask:true}}},good);
 assert.match(h.coHtml(),/id="f-recurring"/);assert.match(h.CO.recurring(),/Еднократна.*Повтаряща се/s);assert(!h.CO.recurring().includes('data-recf'));
 h.S.basket=[{code:'HINGE',rows:[{x:0,n:2}]}];h.S.co={name:'Иван',email:'ivan@example.test'};
 await h.submit();assert.equal(calls[0].customer.recurring,'one-off');assert.equal(calls[0].customer.recurringBg,'Еднократна');assert.equal(calls[0].customer.recurringEn,'One-off');assert(!('recurringFrequency' in calls[0].customer));
 h.S.view='co';h.S.basket=[{code:'HINGE',rows:[{x:0,n:2}]}];press(h,{rec:'recurring'});
 assert.equal(h.S.co.recurringFrequency,'monthly');assert.match(h.CO.recurring(),/data-recf="quarterly"/);assert.match(h.CO.recurring(),/data-co="recurringNote"/);
 press(h,{recf:'quarterly'});h.onInput({target:{value:' 400 бр. ',dataset:{co:'recurringNote'}}});
 await h.submit();const c=calls[1].customer;
 assert.equal(c.recurring,'recurring');assert.equal(c.recurringFrequency,'quarterly');assert.equal(c.recurringNote,'400 бр.');
 assert.equal(c.recurringBg,'Повтаряща се · На тримесечие · 400 бр.');assert.equal(c.recurringEn,'Recurring · Quarterly · 400 бр.');
 assert(Object.values(c).every(v=>typeof v==='string'));
});
test('a company that leaves the question out sends no recurring fields',async()=>{
 const calls=[],h=widget({},async(url,request)=>{calls.push(JSON.parse(request.body));return{ok:true,json:async()=>({ok:true,id:'saved',quote:{gross:8},ready:{}})}});
 assert(!h.coHtml().includes('f-recurring'));h.S.basket=[{code:'HINGE',rows:[{x:0,n:2}]}];h.S.co={name:'Иван',email:'ivan@example.test',recurring:'recurring'};
 await h.submit();assert(!Object.keys(calls[0].customer).some(k=>k.startsWith('recurring')));
});
