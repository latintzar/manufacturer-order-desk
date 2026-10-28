import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';
const here=new URL('.',import.meta.url);
function widget(catalogue){
 const context={window:{RocotoConfig:{lang:'en',hours:{1:[510,1050,1020]}}},location:{pathname:'/en/'},document:{readyState:'loading',addEventListener(){}},__ICONS__:{},__CSS__:''};
 vm.createContext(context);
 for(const file of ['pricing.js','core.js'])vm.runInContext(readFileSync(new URL('../widget/'+file,here),'utf8'),context);
 context.window.RocotoCore.index(structuredClone(catalogue));
 let shop=readFileSync(new URL('../widget/shop.js',here),'utf8').replace('window.RocotoConfigurator={open:open,close:close,state:S};','window.TEST={mode,rate,planOf,buyText,basketHtml,cbarHtml,doneHtml,optsHtml,headHtml,titleOf,pdHtml,catRange,S,setOf,slidesOf,setPictures:value=>{GEN=value}};');
 vm.runInContext(shop,context);return {K:context.window.RocotoCore,UI:context.window.TEST};
}
const catalog={company:{en:'Example'},currency:'EUR',vat:.2,metals:[{id:'steel',en:'Steel'}],forms:[{id:'hardware',en:'Hardware'}],cats:[
 {code:'h',en:'Gate hardware',bg:'Обков',metal:'steel',form:'hardware',shape:'special',items:[{c:'HW-001',s:'Панта регулируема M20',se:'Adjustable hinge M20',p:.123,u:'pc',L:0,r:{k:'whole'},w:0}]},
 {code:'t',en:'Square tubes',bg:'Квадратни тръби',metal:'steel',form:'tube',shape:'sq_tube',items:[{c:'T2',s:'40x40x3',d:[40,40,3],p:60,L:6,r:{k:'len',l:[2,3,6]},cut:2,w:20},{c:'T1',s:'20x20x2',d:[20,20,2],p:30,L:6,r:{k:'len',l:[2,3,6]},cut:2,w:10}]},
 {code:'s',en:'Sheet',bg:'Лист',metal:'steel',form:'sheet',shape:'sheet',items:[{c:'S1',s:'1x1000x2000',d:[1,1000,2000],p:50,L:0,r:{k:'whole'},w:0,u:'sheet'}]},
 {code:'q',en:'Pipe',bg:'Тръба',metal:'steel',form:'tube',shape:'round_tube',items:[{c:'Q1',s:'Ø920x8',d:[920,8],p:212.25,L:1,r:{k:'whole'},w:172,q:1,rate:[212.25,'m']}]}
]};
test('material variants select their own complete photo set and unresolved variants avoid type fallback',()=>{
 const {K,UI}=widget(catalog),c=K.C.byCode.t;
 UI.setPictures({variantTypes:['t'],items:{T1:'t-cold',T2:'t-hot'},sets:{t:['generic.webp'],'t-cold':['cold-whole.webp','cold-cut.webp','cold-macro.webp','cold-stack.webp'],'t-hot':['hot-whole.webp','hot-cut.webp','hot-macro.webp','hot-stack.webp']}});
 assert.match(UI.slidesOf(c,K.C.items.T1)[2],/cold-macro/);
 assert.match(UI.slidesOf(c,K.C.items.T2)[1],/hot-cut/);
 assert.equal(UI.setOf(c,{c:'UNRESOLVED'}),null);
 assert.equal(UI.slidesOf(c,{c:'UNRESOLVED'}).length,0);
 UI.setPictures({sets:{t:['legacy.webp']}});assert.match(UI.slidesOf(c,K.C.items.T1)[0],/legacy/);
});
test('search finds name-only hardware, Cyrillic names and exact SKU',()=>{
 const {K}=widget(catalog);
 assert.equal(K.search('adjustable hinge')[0].item.c,'HW-001');
 assert.equal(K.search('панта')[0].item.c,'HW-001');
 assert.equal(K.search('M20 hinge')[0].item.c,'HW-001');
 assert.equal(K.search('HW-001')[0].item.c,'HW-001');
 assert.equal(K.search('quantumunicorn').length,0);
 assert.equal(K.search('40x40x3 square tube')[0].item.c,'T2');
});
test('whole sheets stay whole and uncertain metre prices keep the unit',()=>{
 const {K,UI}=widget(catalog);
 assert.equal(UI.mode(K.C.items.S1),'piece');
 assert.equal(UI.planOf(K.C.items.S1,[{n:3}],{},false).total,150);
 assert.deepEqual(Array.from(UI.rate(K.C.items.Q1)),[212.25,'perM']);
 assert.equal(UI.planOf(K.C.items.Q1,[{x:1000,n:1}],{},false).ask,1);
});
test('display keeps three decimal unit rates and two decimal totals',()=>{
 const {K,UI}=widget(catalog);UI.S.item='HW-001';
 assert.match(UI.headHtml(),/0\.123/);
 assert.equal(K.eur(.369),'€0.37');
 assert(!UI.optsHtml().includes('0 kg'));
});
test('dimensions sort numerically and angle cuts are charged on sold lengths',()=>{
 const {K,UI}=widget(catalog);
 assert.equal(K.levels(K.C.byCode.t)[0].items[0].c,'T1');
 const p=UI.planOf(K.C.items.T2,[{x:2000,n:2}],{},{degrees:45,ends:2});
 assert.equal(p.cuts,4);assert.equal(p.cutCost,12);
});
test('delivery is chosen at checkout, pending confirmation and absent from numeric totals',()=>{
 const {UI}=widget(catalog);UI.S.basket=[{code:'HW-001',rows:[{n:1,x:0}]}];UI.S.fulfil='delivery';
 assert(!UI.basketHtml().includes('data-fulfil'));assert(!/Delivery<\/span><b>Price with your quote/.test(UI.basketHtml()));
 UI.S.view='co';UI.S.step=2;
 const html=UI.basketHtml();assert.match(html,/Delivery<\/span><b>Price with your quote/);assert(!html.includes('Discount code'));assert(!html.includes('€30.00'));assert.match(html,/VAT 20%/);
});
if(process.env.ORDERS_FULL_CATALOGUE){
 test('every complete catalogue item opens and plans without NaN',()=>{
  const {K,UI}=widget(JSON.parse(readFileSync(process.env.ORDERS_FULL_CATALOGUE,'utf8')));
  assert.equal(K.C.cats.length,150);assert.equal(K.C.n,2751);
  for(const item of Object.values(K.C.items)){
   UI.S.item=item.c;UI.S.rows=[{x:item.r.l?.length?Math.max(...item.r.l)*1000:item.L>1?item.L*1000:1000,n:1}];UI.S.sheet={a:item.d?.[2]||1000,b:item.d?.[1]||500,n:1};
   assert(!UI.optsHtml().includes('NaN'),item.c);assert(!UI.headHtml().includes('NaN'),item.c);
   const p=UI.planOf(item,UI.S.rows,UI.S.sheet,false);assert.equal(p.ok,true,item.c);assert(Number.isFinite(p.total),item.c);
   assert.equal(K.search(item.c)[0].item.c,item.c);
  }
 });
}

test('dimension searches exclude article-number digits and repeated translation tokens',()=>{
 const data=structuredClone(catalog);data.cats[0].items.push({c:'HW-3-40',s:'Профил 20/40/50',se:'Profile 20/40/50',p:1,u:'pc',L:0,r:{k:'whole'},w:0});
 const {K}=widget(data);assert(K.search('40x40x3').every(r=>r.item?.c!=='HW-3-40'));
});


test('site displayed date is not presented as a price revision',()=>{
 const data=structuredClone(catalog);data.asOf='11/10/2026';data.asOfKind='site_displayed_date';
 const {UI}=widget(data);UI.S.basket=[{code:'HW-001',rows:[{n:1,x:0}]}];
 const html=UI.basketHtml();assert.match(html,/Published catalogue prices/);assert(!html.includes('price list of'));assert(!html.includes('11 Oct'));
});
test('Bulgarian fixed-price note does not make the quote provisional',()=>{
 const data=structuredClone(catalog);data.asOf='11/10/2026';
 const {K,UI}=widget(data);K.L.lang='bg';UI.S.basket=[{code:'HW-001',rows:[{n:1,x:0}]}];
 const html=UI.basketHtml();assert.match(html,/Публикувани цени от каталога/);assert(!html.includes('потвърждават се'));
});
test('held-price checkout and receipt never present a partial amount as the final total',()=>{
 const {UI}=widget(catalog);
 UI.S.basket=[{code:'Q1',rows:[{x:1000,n:1}]}];
 assert.match(UI.cbarHtml(),/Quote by email/);assert(!UI.cbarHtml().includes('€0.00'));
 assert(!UI.basketHtml().includes('€0.00'));
 UI.S.basket.unshift({code:'HW-001',rows:[{x:0,n:2}]});
 assert.match(UI.cbarHtml(),/Priced items/);
 UI.S.done={no:'abc',total:.25,quote:{confirmation:true}};
 const receipt=UI.doneHtml();assert.match(receipt,/Priced items/);assert(!receipt.includes('ABC · €0.25'));
});
test('shape labels and Bulgarian product nouns follow the actual item',()=>{
 const data=structuredClone(catalog);data.cats[1].product={bg:'Квадратна тръба'};
 data.cats[1].items.push({c:'RECT',s:'30x20x2',d:[30,20,2],p:30,L:6,r:{k:'len',l:[6]},cut:2});
 const {K,UI}=widget(data);assert.match(UI.titleOf(K.C.items.RECT),/rectangular/i);
 K.L.lang='bg';assert.match(UI.titleOf(K.C.items.T1),/^Квадратна тръба /);assert.match(UI.titleOf(K.C.items.RECT),/^Правоъгълна тръба /);
});
test('same-size same-length variants retain distinct article labels',()=>{
 const data=structuredClone(catalog);data.cats[1].items.push({...data.cats[1].items[0],c:'T3',p:63});
 const {UI}=widget(data);UI.S.item='T2';const html=UI.optsHtml();assert.match(html,/6 m · T2/);assert.match(html,/6 m · T3/);
});
