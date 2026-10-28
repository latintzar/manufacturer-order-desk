import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';
const here=new URL('.',import.meta.url),read=f=>readFileSync(new URL(f,here),'utf8');
const fixture=JSON.parse(read('fixtures/ask-cases.json'));
function engine(){const context={window:{},setTimeout,clearTimeout};vm.createContext(context);vm.runInContext(read('../widget/ask.js'),context);return context.window.RocotoAsk}
const plain=v=>JSON.parse(JSON.stringify(v)),A=engine(),DEF=fixture.questionnaire,ROWS=A.rows(fixture.catalogue);
test('rows are the catalogue items that carry attributes',()=>{assert.equal(ROWS.length,8);assert(!ROWS.some(r=>r.c==='PLAIN'));assert.equal(ROWS[0].form,'locks');assert.equal(ROWS[5].type,'t2')});
for(const c of fixture.cases)test('engine: '+c.name,()=>{
 const w=A.walk(DEF,ROWS,c.answers);
 assert.equal(w.next?w.next.id:null,c.next);
 if(c.asked)assert.deepEqual(plain(w.steps.filter(s=>!s.auto).map(s=>s.q.id)),c.asked);
 if(c.auto)c.auto.forEach(id=>assert(w.steps.find(s=>s.q.id===id).auto,id+' answers itself'));
 if(c.live)Object.keys(c.live).forEach(id=>assert.deepEqual(plain(w.steps.find(s=>s.q.id===id).live.map(o=>o.id)),c.live[id]));
 if(c.result){const found=A.result(DEF,w),got={};found.forEach(g=>{got[g.group.title.bg]=g.rows.map(r=>r.c)});assert.deepEqual(plain(got),c.result)}
});
test('matching: a row stays unless it carries the attribute with other values',()=>{
 assert(A.keeps({a:{fn:['PZ']}},{fn:['PZ','BB']}));assert(!A.keeps({a:{fn:['BAD']}},{fn:['PZ']}));assert(A.keeps({a:{use:['x']}},{fn:['PZ']}));assert(A.keeps({a:{size:50}},{size:[50]}));assert(A.keeps({a:{}},undefined));
});
test('conditions hold when every named question has one of the listed options',()=>{
 assert(A.whenOk(undefined,{}));assert(A.whenOk({door:['a','b']},{door:['b']}));assert(!A.whenOk({door:['a']},{}));assert(!A.whenOk({door:['a'],lock:['x']},{door:['a'],lock:['y']}));assert(A.whenOk({size:['?']},{size:['?']}));
});
test('the note names each answer and the order carries every distinct note',()=>{
 const w=A.walk(DEF,ROWS,{door:['interior'],lock:['wc'],size:['50'],colour:['satin','chrome']}),note=A.note(DEF,w,'bg');
 assert.equal(note,'Намерете брава: Врата: Вътрешна; Заключване: Баня; Размер: 50 мм; Покритие: Сатин, Хром');
 const customer=A.stamp({email:'a@b.test'},[{code:'L-WC-50',why:note},{code:'H-C-SATIN',why:note},{code:'PLAIN'},{custom:'x'}]);
 assert.equal(customer.questionnaire,note);assert.equal(A.stamp({},[{code:'PLAIN'}]).questionnaire,undefined);
 assert(A.stamp({},[{why:'a'.repeat(1500)},{why:'b'.repeat(1500)}]).questionnaire.length<=2000);
});
test('the drawings the validator knows are the ones the widget holds',()=>{
 const listed=/DRAWINGS = \(([^)]*)\)/.exec(read('../pipeline/ask.py'))[1].match(/[a-z-]+/g);
 assert.deepEqual([...listed].sort(),plain(A.DRAWINGS).sort());
});
/* the screen, driven without a browser: answers, the result's quantities, the basket and the order payload */
function page(fetch){
 const local=new Map(),session=new Map(),html={},el=()=>({innerHTML:'',scrollTop:0,hidden:false,dataset:{},querySelector:()=>el(),insertAdjacentHTML(){},setAttribute(){},classList:{toggle(){},add(){},remove(){}}});
 const context={window:{RocotoConfig:{root:'/x',lang:'bg',langs:{},questionnaire:DEF}},location:{pathname:'/x/',assign(){}},document:{readyState:'loading',addEventListener(){}},__ICONS__:{},__CSS__:'',fetch,AbortController,setTimeout,clearTimeout,matchMedia:()=>({matches:false}),
  crypto:{randomUUID:()=>'test_request_'+Math.random().toString(36).slice(2)},localStorage:{getItem:k=>local.get(k),setItem:(k,v)=>local.set(k,v)},sessionStorage:{getItem:k=>session.get(k),setItem:(k,v)=>session.set(k,v),removeItem:k=>session.delete(k)}};
 vm.createContext(context);for(const f of ['pricing.js','core.js','ask.js'])vm.runInContext(read('../widget/'+f),context);
 context.window.RocotoCore.index(JSON.parse(JSON.stringify(fixture.catalogue)));
 const source=read('../widget/shop.js').replace('window.RocotoConfigurator={open:open,close:close,state:S};',"renderAll=()=>{if(ASK)ASK.render()};renderBasket=()=>{};showMenu=()=>{S.view='menu'};root={activeElement:null,querySelector:s=>s==='.main'?{insertAdjacentHTML(){}}:{innerHTML:'',scrollTop:0,hidden:false,dataset:{},querySelector:()=>({innerHTML:'',scrollTop:0})}};window.TEST={S,ASK,submit,onClick,onKey,menuHtml};");
 vm.runInContext(source,context);html.el=el;return context.window.TEST;
}
const press=(h,data,id)=>h.onClick({target:{closest:()=>({dataset:data,id:id||''})}});
test('the menu opens with the questionnaire banner and a company without one has none',()=>{
 const h=page(async()=>({}));assert(h.menuHtml().startsWith('<section class="ask-b">'));assert(h.menuHtml().includes('Намерете брава'));
});
test('answers lead to a result, the best article of each group is added, and the order carries the answers',async()=>{
 const calls=[],h=page(async(url,request)=>{calls.push({url,request});return{ok:true,json:async()=>({ok:true,id:'X-1',quote:{gross:0},ready:{}})}});
 h.S.open=true;press(h,{ask:'start'});assert.equal(h.S.view,'ask');
 const A2=h.ASK.state;A2.answers={door:['interior'],lock:['wc'],size:['50'],colour:['satin']};A2.at='result';
 press(h,{askQ:'1',code:'L-WC-50'});assert.equal(A2.qty['L-WC-50'],2);assert.equal(A2.qty['H-C-SATIN'],1);
 press(h,{ask:'add'});
 assert.equal(h.S.view,'menu');assert.deepEqual(JSON.parse(JSON.stringify(h.S.basket.map(l=>[l.code,l.rows[0].n]))),[['L-WC-50',2],['H-C-SATIN',1]]);
 assert(h.S.basket.every(l=>l.why.includes('Заключване: Баня')));assert.deepEqual(JSON.parse(JSON.stringify(A2.answers)),{});
 h.S.co={name:'QA',email:'qa@example.test'};await h.submit();
 const sent=JSON.parse(calls.find(c=>c.url.endsWith('api/orders')).request.body);
 assert.equal(sent.customer.questionnaire,'Намерете брава: Врата: Вътрешна; Заключване: Баня; Размер: 50 мм; Покритие: Сатин');assert.equal(sent.lines[0].why,sent.customer.questionnaire);
});
test('Back keeps the answers, and number keys choose',()=>{
 const h=page(async()=>({}));h.S.open=true;press(h,{ask:'start'});const st=h.ASK.state;
 assert.equal(h.onKey({key:'1',preventDefault(){}}),undefined);assert.deepEqual(JSON.parse(JSON.stringify(st.answers.door)),['interior']);
 st.at='lock';press(h,{askO:'wc'});st.at='size';press(h,{act:'back'});assert.equal(st.at,'lock');assert.deepEqual(JSON.parse(JSON.stringify(st.answers.lock)),['wc']);
 press(h,{act:'back'});assert.equal(st.at,'door');press(h,{act:'back'});assert.equal(h.S.view,'menu');assert.deepEqual(JSON.parse(JSON.stringify(st.answers.door)),['interior']);
});
