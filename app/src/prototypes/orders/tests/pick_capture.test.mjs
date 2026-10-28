import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const script=fs.readFileSync(new URL('../widget/pick.js',import.meta.url),'utf8');
const clean=value=>JSON.parse(JSON.stringify(value));
function fixture(saved=null,clarify=false,basket=null){
 const window={},S={basket:basket|| (saved?.proposal?.selected||[]).map(line=>({code:line.code,rows:[{n:line.quantity}]})),capture:saved},cfg={picker:{families:[],clarify:[]},questionnaire:{title:{en:'Door needs'},questions:[{id:'parts',title:{en:'Parts required'},kind:'multiple',options:[{id:'lock',label:{en:'Lock'}}]},{id:'hand',title:{en:'Door hand'},unsure:true,options:[{id:'left',label:{en:'Left'}}]},{id:'size',title:{en:'Dimensions'},options:[{id:'55',label:{en:'55 mm'}}]}]}};
 const K={L:{lang:'en'},C:{items:{A:{c:'A',cat:{form:'mortise'},a:{}},B:{c:'B',cat:{form:'hinge'},a:{}}}}};
 if(clarify){cfg.picker.clarify.push({title:{en:'Opening shape'},when:{purpose:['B']},options:[{value:'rectangle',label:{en:'Rectangular'}}]});K.C.items.A.a.purpose='B'}
 vm.runInNewContext(script,{window});
 const node={scrollTop:0,hidden:false,classList:{add(){}},querySelector:()=>node,querySelectorAll:()=>[],focus(){}};
 const picker=window.RocotoPick.ui({K,S,cfg,esc:String,ic:()=>'',save(){},render(){},root:()=>node});
 const click=(action,extra={})=>picker.click({target:{closest:()=>({dataset:{pick:action,...extra}})}});
 return {S,picker,click,stamp:()=>clean(picker.stamp({}))};
}
test('saved questionnaire captures labels, unknowns, unanswered questions and added proposal',()=>{
 const x=fixture();x.click('help');x.picker.state.answers={parts:['lock'],hand:['?'],project:'Twelve replacement doors'};
 x.picker.state.proposal={title:{en:'Lock proposal'},text:{en:'Confirm door dimensions.'},lines:[{c:'A',qty:12,why:{en:'Selected for the door'}}]};x.picker.state.quantities['proposal:0']=12;x.click('add-proposal');
 const capture=x.stamp().capture;
 assert.equal(capture.entry_path,'questionnaire');assert.deepEqual(capture.questionnaire.questions.map(q=>q.status),['answered','unknown','unanswered']);
 assert.equal(capture.questionnaire.questions[0].answers[0].label,'Lock');assert.equal(capture.questionnaire.project,'Twelve replacement doors');
 assert.deepEqual(capture.proposal.selected,[{code:'A',quantity:12,reason:'Selected for the door'}]);
 assert.deepEqual(fixture(capture).stamp().capture,capture);
});
test('switching to catalogue clears questionnaire and proposal from checkout',()=>{
 const x=fixture();x.click('help');x.picker.state.answers={parts:['lock'],project:'Old project'};x.click('add',{code:'A'});
 x.click('families');x.click('add',{code:'B'});const customer=x.stamp();
 assert.equal(customer.capture.entry_path,'catalogue');assert.equal(customer.capture.questionnaire,undefined);assert.equal(customer.capture.proposal,undefined);assert.equal(customer.questionnaire,undefined);
 assert.deepEqual(clean(x.picker.state.answers),{});
});
test('specification retains the original text and choices; switching clears it',()=>{
 const x=fixture();x.click('spec');x.picker.state.text='Original specification '.repeat(120);x.picker.state.spec=[{source:'12 locks A',qty:12,status:'exact',matches:['A']}];x.picker.state.chosen={0:'A'};x.picker.state.quantities['spec:0']=12;x.click('add-spec');
 const customer=x.stamp();assert.equal(customer.capture.specification.text.length,x.picker.state.text.trim().length);assert.equal(customer.specification.length,x.picker.state.text.trim().length);assert.equal(customer.capture.specification.lines[0].selected_code,'A');
 x.click('help');const next=x.stamp();assert.equal(next.specification,undefined);assert.equal(next.specification_file,undefined);assert.equal(next.capture.specification,undefined);
});
test('removing a restored recommendation removes its selection from checkout context',()=>{
 const saved={schema:'rocoto.orders.capture.v1',entry_path:'questionnaire',language:'en',proposal:{title:'Saved proposal',summary:'Confirm dimensions.',selected:[{code:'A',quantity:12,reason:'Lock selected'}]}};
 const x=fixture(saved);x.S.basket=[];assert.deepEqual(x.stamp().capture.proposal.selected,[]);
});

test('specification bulk quantities survive basket chunking and repeated additions',()=>{
 const x=fixture();x.click('spec');x.picker.state.spec=[{source:'1000 A',qty:1000,matches:['A']}];x.picker.state.chosen={0:'A'};x.picker.state.quantities['spec:0']=1000;
 x.click('add-spec');assert.deepEqual(clean(x.S.basket.map(line=>line.rows[0].n)),[999,1]);
 assert.equal(x.stamp().capture.specification.lines[0].quantity,1000);
 x.click('add-spec');assert.equal(x.S.basket.reduce((n,line)=>n+line.rows[0].n,0),2000);
 assert.ok(x.S.basket.every(line=>line.rows[0].n<=999));
});
test('basket capacity failure keeps the entire existing order intact',()=>{
 const x=fixture();x.click('spec');x.S.basket=Array.from({length:99},()=>({code:'B',rows:[{n:999}]}));
 x.picker.state.spec=[{source:'1000 A',qty:1000,matches:['A']}];x.picker.state.chosen={0:'A'};x.picker.state.quantities['spec:0']=1000;
 x.click('add-spec');assert.equal(x.S.basket.length,99);assert.ok(x.S.basket.every(line=>line.code==='B'));
 assert.ok(x.picker.state.error.includes('100'));
});
test('keyhole clarification gates spec bulk additions and persists the chosen shape',()=>{
 const x=fixture(null,true);x.click('spec');x.picker.state.spec=[{source:'12 A',qty:12,matches:['A']}];x.picker.state.chosen={0:'A'};x.picker.state.quantities['spec:0']=12;
 x.click('add-spec');assert.equal(x.S.basket.length,0);assert.ok(x.picker.state.clarify);
 x.click('clarify',{value:'rectangle'});assert.equal(x.S.basket[0].rows[0].n,12);assert.match(x.S.basket[0].why,/Rectangular/);
});
test('closing a keyhole question cancels the pending add',()=>{
 const x=fixture(null,true);x.click('families');x.click('add',{code:'A'});assert.ok(x.picker.state.clarify);
 x.click('clarify-close');assert.equal(x.S.basket.length,0);assert.equal(x.picker.state.after,null);
});

test('catalogue quantity controls change the stored order and remove explicitly',()=>{
 const x=fixture();x.click('families');x.click('add',{code:'A'});
 assert.equal(x.S.basket[0].rows[0].n,1);
 x.click('cart-step',{line:'0',delta:'1'});assert.equal(x.S.basket[0].rows[0].n,2);
 x.click('cart-step',{line:'0',delta:'-1'});assert.equal(x.S.basket[0].rows[0].n,1);
 x.click('cart-step',{line:'0',delta:'-1'});assert.equal(x.S.basket[0].rows[0].n,1);
 x.click('cart-remove',{line:'0'});assert.equal(x.S.basket.length,0);
});

test('destination allocation requires explicit review, retains receipt and omits browser assertions',()=>{
 const x=fixture();x.click('spec');
 Object.assign(x.picker.state,{spec:[{source:'A | 2',qty:2,status:'exact',matches:['A']}],chosen:{0:'A'},quantities:{'spec:0':2},readingId:'a'.repeat(32),allocationReview:{schema:'rocoto.orders.allocations.v1',issues:[],destinations:[{id:'1602',label:'Varna'}],allocations:[{line:0,sku:'A',destination_id:'1602',quantity:2}]}});
 x.click('add-spec');assert.equal(x.S.basket.length,0);
 x.picker.state.allocationConfirmed=true;x.click('add-spec');assert.equal(x.S.basket[0].rows[0].n,2);
 const capture=x.stamp().capture.specification;
 assert.equal(capture.reading_id,'a'.repeat(32));assert.equal(capture.allocations_confirmed,true);assert.equal(capture.review,undefined);
 x.picker.state.allocationReview.issues=['Check total'];x.click('add-spec');assert.equal(x.S.basket[0].rows[0].n,2);
});

function matrixFixture(){
 const x=fixture();x.click('spec');
 Object.assign(x.picker.state,{file:{id:'original-matrix',name:'branches.xlsx'},text:'',spec:[{source:'A | 2',qty:2,status:'exact',matches:['A']},{source:'B | 3',qty:3,status:'exact',matches:['B']}],chosen:{0:'A',1:'B'},quantities:{'spec:0':2,'spec:1':3},readingId:'b'.repeat(32),allocationConfirmed:true,allocationReview:{schema:'rocoto.orders.allocations.v1',issues:[],destinations:[{id:'1602',label:'Varna'}],allocations:[{line:0,sku:'A',destination_id:'1602',quantity:2},{line:1,sku:'B',destination_id:'1602',quantity:3}]}});
 x.click('add-spec');assert.equal(x.S.basket.length,2);return x;
}
test('matrix provenance follows its basket across catalogue, questionnaire and reload',()=>{
 const x=matrixFixture(),original=x.stamp(),basket=clean(x.S.basket);
 for(const path of ['families','help']){x.click(path);assert.deepEqual(x.stamp(),original);assert.deepEqual(clean(x.S.basket),basket)}
 const restored=fixture(clean(x.S.capture),false,clean(x.S.basket));restored.click('families');assert.deepEqual(restored.stamp(),original);
 restored.click('spec');assert.equal(restored.picker.state.readingId,'b'.repeat(32));assert.equal(restored.picker.state.file.id,'original-matrix');
 restored.click('add-spec');assert.deepEqual(clean(restored.S.basket),basket);
});
test('matrix basket rejects additional articles, requests and quantity changes after navigation',()=>{
 const x=matrixFixture(),original=x.stamp(),basket=clean(x.S.basket);x.click('families');
 x.click('add',{code:'A'});assert.deepEqual(clean(x.S.basket),basket);assert.ok(x.picker.state.error);
 x.click('cart-step',{line:'0',delta:'1'});assert.deepEqual(clean(x.S.basket),basket);
 x.click('help');x.picker.state.answers.project='Extra work';x.click('request-proposal');assert.deepEqual(clean(x.S.basket),basket);
 assert.deepEqual(x.stamp(),original);
});
test('matrix provenance stays through partial removal and releases after explicit removal of its last line',()=>{
 const x=matrixFixture(),original=x.stamp();x.click('families');
 x.click('cart-remove',{line:'0'});assert.equal(x.S.basket.length,1);assert.deepEqual(x.stamp(),original);
 x.click('cart-remove',{line:'0'});assert.equal(x.S.basket.length,0);
 x.click('add',{code:'A'});assert.equal(x.S.basket[0].rows[0].n,1);assert.equal(x.stamp().capture.entry_path,'catalogue');assert.equal(x.stamp().specification_file,undefined);
});
test('editing a new specification keeps the original matrix receipt attached to existing basket lines',()=>{
 const x=matrixFixture(),original=x.stamp();x.click('help');x.click('spec');
 x.click('remove-file');Object.assign(x.picker.state,{text:'A | 9',spec:[{source:'A | 9',qty:9,status:'exact',matches:['A']}],chosen:{0:'A'},quantities:{'spec:0':9},readingId:'c'.repeat(32),allocationConfirmed:true,allocationReview:{issues:[],allocations:[]}});
 x.click('add-spec');assert.deepEqual(x.stamp(),original);assert.deepEqual(clean(x.S.basket.map(line=>line.rows[0].n)),[2,3]);
});
