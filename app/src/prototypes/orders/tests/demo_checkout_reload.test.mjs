import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../widget/shop.js',import.meta.url),'utf8');
const start=source.indexOf('const load=()=>');
const action=source.slice(start,source.indexOf('\n\nfunction languageHtml(',start));
assert.ok(start>=0&&action.length>0);
function restored(draft){
 const customer={company:'Практикер',coName:'Практикер — демонстрационни данни',poNumber:'DEMO-PRA-2026-001',warehouseId:'warehouse-1',warehouseConfirmed:'yes',eik:'000000000',bline1:'Демонстрационен адрес'};
 const capture={entry_path:'specification',demo_order:{demo:true,scenario:'praktiker',customer,warehouses:[{id:'warehouse-1',name:'Склад'}]}};
 const local=new Map([['basket',JSON.stringify([{code:'101353L',rows:[{x:1000,n:24}]}])],['basket-capture',JSON.stringify(capture)]]);
 const session=new Map(draft?[['basket-language-draft',JSON.stringify(draft)]]:[]);
 const S={basket:[],capture:null,co:{},inv:'person',fulfil:'pickup',billOther:false};
 const context={S,CFG:{key:'basket'},C:{items:{'101353L':{}}},localStorage:{getItem:k=>local.get(k)},sessionStorage:{getItem:k=>session.get(k),removeItem:k=>session.delete(k)}};
 vm.runInNewContext(action+';globalThis.runLoad=load;',context);context.runLoad();return {S,session};
}
test('saved uploaded demo restores invoice, PO and warehouse before opening checkout',()=>{
 const {S}=restored();
 assert.equal(S.co.company,'Практикер');assert.equal(S.co.poNumber,'DEMO-PRA-2026-001');
 assert.equal(S.co.warehouseConfirmed,'yes');assert.equal(S.co.eik,'000000000');
 assert.equal(S.inv,'company');assert.equal(S.billOther,true);
 assert.equal(S.demoOrder.warehouses[0].id,'warehouse-1');
});
test('a pending language-switch draft overrides the saved demo defaults',()=>{
 const {S,session}=restored({co:{company:'Edited company',poNumber:'EDITED-PO'},fulfil:'delivery',inv:'company',billOther:false});
 assert.equal(S.co.company,'Edited company');assert.equal(S.co.poNumber,'EDITED-PO');
 assert.equal(S.fulfil,'delivery');assert.equal(S.billOther,false);
 assert.equal(session.has('basket-language-draft'),false);
});
