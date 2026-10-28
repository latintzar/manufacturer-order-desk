import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import vm from 'node:vm';
const here=new URL('.',import.meta.url),delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function harness(fetch){
 const storage=new Map(),local=new Map(),element={innerHTML:'',scrollTop:0};
 const location={pathname:'/metal-m/en/',assigned:'',assign(value){this.assigned=value}};
 const context={window:{RocotoConfig:{root:'/metal-m',lang:'bg',langs:{en:'/en/'}}},location,document:{readyState:'loading',addEventListener(){}},__ICONS__:{},__CSS__:'',fetch,AbortController,setTimeout,clearTimeout,crypto:{randomUUID:()=>`test_request_${Math.random().toString(36).slice(2)}`},localStorage:{getItem:k=>local.get(k),setItem:(k,v)=>local.set(k,v)},sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)}};
 vm.createContext(context);for(const f of ['pricing.js','core.js'])vm.runInContext(readFileSync(new URL('../widget/'+f,here),'utf8'),context);
 context.window.RocotoCore.index({company:{en:'Example'},currency:'EUR',vat:.2,cats:[{code:'x',shape:'special',en:'Hinge',bg:'Панта',items:[{c:'HINGE',s:'Hinge',p:4,L:0,w:0,u:'pc',r:{k:'whole'}}]}],metals:[],forms:[]});
 let source=readFileSync(new URL('../widget/shop.js',here),'utf8').replace('window.RocotoConfigurator={open:open,close:close,state:S};',`renderAll=()=>{};renderBasket=()=>{};showMenu=()=>{S.view='menu'};root={querySelector:()=>({innerHTML:'',scrollTop:0})};window.TEST={S,WRITE,REMOTE,submit,submitClaim,scheduleQuote,currentQuote,quantity,planOf,customHtml,addCustom,addLine,uploadFile,removeCustomFile,leaveCustom,switchLanguage,onClick,onInput,onChange,setSupply:v=>SUPPLY=v};`);
 vm.runInContext(source,context);return {...context.window.TEST,item:context.window.RocotoCore.C.items.HINGE,storage,local,location};
}
const good=()=>({ok:true,json:async()=>({ok:true,id:'saved-order',state:'requested',quote:{gross:8,net:6.67,vat:1.33},ready:{}})});
test('submission retains basket on failure and retries one stable idempotency key',async()=>{
 const calls=[];let fail=true;const h=harness(async(url,request)=>{calls.push({url,request});if(fail)throw Error('temporary');return good()});
 h.S.basket=[{code:'HINGE',rows:[{x:0,n:2}]}];h.S.co={name:'Example',email:'qa@example.test',lat:42};h.S.view='co';
 await h.submit();assert.equal(h.S.basket.length,1);assert.equal(h.S.view,'co');assert.equal(h.WRITE.error,'temporary');
 fail=false;await h.submit();assert.equal(h.S.view,'done');assert.equal(h.S.done.no,'saved-order');assert.equal(h.S.basket.length,0);
 assert.equal(calls[0].request.headers['Idempotency-Key'],calls[1].request.headers['Idempotency-Key']);
 assert.equal(JSON.parse(calls[0].request.body).customer.lat,'42');assert.equal(JSON.parse(calls[0].request.body).customer.language,'en');assert(!('total' in JSON.parse(calls[0].request.body)));
});
test('language switching uses the canonical Bulgarian route and carries basket and customer data',()=>{
 const h=harness(async()=>good());h.S.basket=[{code:'HINGE',rows:[{x:0,n:2}]}];h.S.co={name:'Иван',email:'ivan@example.test'};h.S.fulfil='delivery';h.S.inv='company';
 h.switchLanguage('bg');
 assert.equal(h.location.assigned,'/metal-m/#order');
 assert.equal(JSON.parse(h.local.get('rocoto-basket-v1')||'[]').length,1);
 const draft=JSON.parse(h.storage.get('rocoto-basket-v1-language-draft'));
 assert.equal(draft.co.email,'ivan@example.test');assert.equal(draft.fulfil,'delivery');assert.equal(draft.inv,'company');
});
test('a second submit click during a request creates one network write',async()=>{
 let resolve,calls=0;const h=harness(()=>{calls++;return new Promise(r=>resolve=r)});h.S.basket=[{code:'HINGE',rows:[{x:0,n:2}]}];h.S.co={name:'Example',email:'qa@example.test'};
 const first=h.submit();await h.submit();assert.equal(calls,1);resolve(good());await first;
});
test('a stale quote response cannot replace the current basket estimate',async()=>{
 const pending=[];const h=harness((url,request)=>new Promise(resolve=>pending.push({resolve,request})));
 h.S.basket=[{code:'HINGE',rows:[{x:0,n:1}]}];h.scheduleQuote();await delay(280);
 h.S.basket[0].rows[0].n=2;h.scheduleQuote();await delay(280);
 pending[1].resolve({ok:true,json:async()=>({ok:true,quote:{gross:8},ready:{}})});await delay(5);
 pending[0].resolve({ok:true,json:async()=>({ok:true,quote:{gross:4},ready:{}})});await delay(5);
 assert.equal(h.currentQuote().quote.gross,8);assert.equal(h.REMOTE.pending,false);
});
test('company claims save a pending request and preserve form on errors',async()=>{
 const calls=[];const h=harness(async(url,request)=>{calls.push({url,request});return{ok:true,json:async()=>({ok:true,id:'claim-one',status:'pending'})}});
 Object.assign(h.WRITE.claim,{name:'Company owner',email:'owner@example.test'});await h.submitClaim();
 assert.equal(h.WRITE.claim.saved.status,'pending');assert(calls[0].url.endsWith('/api/claims'));
});
test('quantity control and quote respect supplied minimum, step and pack',()=>{
 const h=harness(async()=>good());h.setSupply({items:{HINGE:{selling:{minimum:6,step:2,pack:3,status:'confirmed'}}}});
 assert.equal(h.quantity(h.item,1),6);assert.equal(h.quantity(h.item,7),12);
 assert.equal(h.planOf(h.item,[{x:0,n:4}],{},false).ok,false);
 assert.equal(h.planOf(h.item,[{x:0,n:6}],{},false).total,24);
});


test('edits made during a slow submit survive the server receipt',async()=>{
 let resolve;const h=harness(()=>new Promise(r=>resolve=r));h.S.basket=[{code:'HINGE',rows:[{x:0,n:1}]}];h.S.co={name:'Example',email:'qa@example.test'};
 const pending=h.submit();h.S.basket=[{code:'HINGE',rows:[{x:0,n:3}]}];resolve(good());await pending;
 assert.equal(h.S.basket[0].rows[0].n,3);assert.equal(h.S.done.lines[0].rows[0].n,1);
});

test('metre-stock MOQ validates purchased material rather than cut count',()=>{
 const h=harness(async()=>good());Object.assign(h.item,{u:'m',L:1,stockBasis:'metre',r:{k:'len',l:[6,12]},cut:1});
 h.setSupply({items:{HINGE:{selling:{minimum:6,step:6,pack:1,status:'confirmed'}}}});
 assert.equal(h.planOf(h.item,[{x:1000,n:1}],{},false).ok,true);
 h.setSupply({items:{HINGE:{selling:{minimum:12,step:6,pack:1,status:'confirmed'}}}});
 assert.equal(h.planOf(h.item,[{x:1000,n:1}],{},false).ok,false);
});

test('freeform custom requests validate, escape, persist and edit one basket line',()=>{
 const h=harness(async()=>good());
 h.S.custom='';h.addCustom();assert.equal(h.S.basket.length,0);assert.equal(h.S.bad,'needText');
 h.S.bad='';h.S.custom='x'.repeat(4001);h.addCustom();assert.equal(h.S.basket.length,0);assert.equal(h.S.bad,'customLimit');
 h.S.bad='';h.S.custom='  12 plates <S355>  ';assert.match(h.customHtml(),/12 plates &lt;S355&gt;/);assert.match(h.customHtml(),/maxlength="4000"/);
 h.addCustom();assert.deepEqual(JSON.parse(h.local.get('rocoto-basket-v1')),[{custom:'12 plates <S355>'}]);
 h.S.editing=0;h.S.custom='8 bent plates';h.addCustom();assert.equal(h.S.basket.length,1);assert.equal(h.S.basket[0].custom,'8 bent plates');
});

test('the widget caps product and custom additions at the backend 100-line limit',()=>{
 const h=harness(async()=>good());h.S.item='HINGE';h.S.rows=[{x:0,n:1}];h.S.basket=Array.from({length:100},()=>({code:'HINGE',rows:[{x:0,n:1}]}));
 h.addLine();assert.equal(h.S.basket.length,100);
 h.S.custom='one more';h.addCustom();assert.equal(h.S.basket.length,100);assert.equal(h.S.bad,'lineLimit');
});

test('custom textarea input with an empty data attribute retains the actual text',()=>{
 const h=harness(async()=>good());
 h.onInput({target:{dataset:{custom:''},value:'Cut 12 plates, 420 × 280 mm'}});
 assert.equal(h.S.custom,'Cut 12 plates, 420 × 280 mm');
 h.addCustom();assert.equal(h.S.basket[0].custom,'Cut 12 plates, 420 × 280 mm');
});

test('a private design upload persists beside catalogue goods and survives editing',async()=>{
 const body=new Uint8Array([73,83,79,45,49,48,51,48,51]);
 const calls=[];const h=harness(async(url,request)=>{calls.push({url,request});return{ok:true,json:async()=>({ok:true,upload:{id:'a'.repeat(32),name:'bracket.step',content_type:'model/step',size:body.length,sha256:'b'.repeat(64)}})}});
 const file={name:'bracket.step',size:body.length,lastModified:17,type:'model/step'};
 await h.uploadFile(file);
 assert.equal(h.S.customFile.id,'a'.repeat(32));assert.equal(h.S.uploading,false);
 assert.match(calls[0].url,/\/api\/uploads$/);assert.equal(calls[0].request.body,file);
 assert.equal(calls[0].request.headers['X-File-Name'],'bracket.step');
 h.S.item='HINGE';h.S.rows=[{x:0,n:1}];h.addLine();
 h.S.custom='Bent bracket';h.addCustom();
 const saved=JSON.parse(h.local.get('rocoto-basket-v1'));
 assert.equal(saved.length,2);assert.equal(saved[0].code,'HINGE');assert.equal(saved[1].file.name,'bracket.step');assert.equal(saved[1].upload_id,'a'.repeat(32));
 h.S.customFile=saved[1].file;assert.match(h.customHtml(),/bracket\.step/);
});

test('a failed upload keeps the attached design available and reports a localized retry',async()=>{
 const h=harness(async()=>{throw new TypeError('offline')});
 const attached={id:'c'.repeat(32),name:'existing.pdf',content_type:'application/pdf',size:24,sha256:'d'.repeat(64)};
 h.S.customFile=attached;
 await h.uploadFile({name:'replacement.pdf',size:24,lastModified:18,type:'application/pdf'});
 assert.equal(h.S.customFile,attached);assert.equal(h.S.bad,'fileError');assert.equal(h.S.uploading,false);
 assert.doesNotMatch(h.customHtml(),/role="alert">undefined/);assert.match(h.customHtml(),/Choose the design file again/);
});

test('more than twenty upload and remove cycles release each staged capability',async()=>{
 const calls=[];let serial=0;const h=harness(async(url,request)=>{
  calls.push({url,request});
  if(request.method==='DELETE')return{ok:true,json:async()=>({ok:true})};
  const id=(++serial).toString(16).padStart(32,'0');
  return{ok:true,json:async()=>({ok:true,upload:{id,name:`design-${serial}.pdf`,content_type:'application/pdf',size:20,sha256:'b'.repeat(64),discard_token:'t'.repeat(43)}})};
 });
 for(let n=0;n<25;n++){
  await h.uploadFile({name:`design-${n}.pdf`,size:20,lastModified:n+1,type:'application/pdf'});
  await h.removeCustomFile();assert.equal(h.S.customFile,null);
 }
 assert.equal(calls.filter(call=>call.request.method==='POST').length,25);
 assert.equal(calls.filter(call=>call.request.method==='DELETE').length,25);
 assert(calls.filter(call=>call.request.method==='DELETE').every(call=>call.request.headers['Upload-Capability']==='t'.repeat(43)));
});

test('draft removal preserves a basket reference and committed replacement releases it',async()=>{
 const calls=[];const old={id:'a'.repeat(32),name:'old.pdf',size:20,discard_token:'o'.repeat(43)};
 const fresh={id:'b'.repeat(32),name:'new.pdf',size:21,discard_token:'n'.repeat(43)};
 const h=harness(async(url,request)=>{calls.push({url,request});return request.method==='DELETE'?{ok:true,json:async()=>({ok:true})}:{ok:true,json:async()=>({ok:true,upload:fresh})}});
 h.S.basket=[{custom:'Bracket',upload_id:old.id,file:old}];h.S.editing=0;h.S.custom='Bracket';h.S.customFile=old;
 await h.removeCustomFile();assert.equal(h.S.customFile,null);assert.equal(h.S.basket[0].upload_id,old.id);assert.equal(calls.length,0);
 h.S.customFile=old;await h.uploadFile({name:'new.pdf',size:21,lastModified:4,type:'application/pdf'});
 assert.equal(calls.filter(call=>call.request.method==='DELETE').length,0);
 h.addCustom();await delay(0);
 assert.equal(h.S.basket[0].upload_id,fresh.id);
 const removed=calls.find(call=>call.request.method==='DELETE');assert(removed.url.endsWith('/api/uploads/'+old.id));assert.equal(removed.request.headers['Upload-Capability'],old.discard_token);
});

test('removing a saved custom line releases its unclaimed upload after saving the basket',async()=>{
 const calls=[];const upload={id:'c'.repeat(32),name:'saved.pdf',size:20,discard_token:'s'.repeat(43)};
 const h=harness(async(url,request)=>{calls.push({url,request});return{ok:true,json:async()=>({ok:true})}});
 h.S.basket=[{custom:'Panel',upload_id:upload.id,file:upload}];
 h.onClick({target:{closest:()=>({dataset:{rm:'0'}})}});await delay(0);
 assert.equal(h.S.basket.length,0);assert([...h.local.values()].includes('[]'));
 const removed=calls.find(call=>call.request.method==='DELETE');assert(removed.url.endsWith('/api/uploads/'+upload.id));assert.equal(removed.request.headers['Upload-Capability'],upload.discard_token);
});
