import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const script=fs.readFileSync(new URL('../widget/pick.js',import.meta.url),'utf8');
const clone=value=>JSON.parse(JSON.stringify(value));
function fixture(lang='en'){
 const window={},questions=[
  {id:'door',title:{en:'Door'},kind:'single',unsure:true,options:[{id:'interior',label:{en:'Interior'}},{id:'second',label:{en:'Second lock'}}]},
  {id:'parts',title:{en:'Parts'},kind:'multiple',unsure:true,options:[{id:'lock',label:{en:'Lock'}},{id:'handles',label:{en:'Handles'}}]},
  {id:'second',title:{en:'Second type'},kind:'single',unsure:true,when:{door:['second']},options:[{id:'surface',label:{en:'Surface'}},{id:'mortise',label:{en:'Mortise'}}]},
  {id:'details',title:{en:'Surface details'},kind:'single',when:{second:['surface']},options:[{id:'single',label:{en:'Single'}},{id:'pair',label:{en:'Pair'},when:{parts:['handles']}}]}
 ];
 const cat={form:'mortise',code:'p566',bg:'55/72',en:'55/72',items:[]};
 const rows=[['101081','никел · с насрещник','nickel · with strike plate'],['101085','никел · без насрещник','nickel · without strike plate'],['101089','цинк или полимер · с насрещник','zinc or polymer · with strike plate'],['101093','цинк или полимер · без насрещник','zinc or polymer · without strike plate']].map(([c,s,se])=>({c,s:'PZ · '+s,se:'PZ · '+se,a:{kind:'lock',fn:['PZ']},cat}));cat.items=rows;
 const K={L:{lang},C:{cats:[cat],items:Object.fromEntries(rows.map(row=>[row.c,row])),byCode:{p566:cat}}};
 const S={basket:[],view:'pick'},cfg={picker:{families:[{id:'mortise',match:{kind:['lock']},facets:[{key:'fn',options:[{value:'PZ',label:{en:'Cylinder',bg:'Секретна'}}]}]}]},questionnaire:{title:{en:'Door needs'},questions}};
 const scroll={scrollTop:0},node={hidden:false,classList:{add(){}},querySelector:()=>scroll,querySelectorAll:()=>[],focus(){},innerHTML:''};
 const root={activeElement:null,querySelector:selector=>selector==='#pick'?node:selector==='.pick-scroll'?scroll:{...node}};
 vm.runInNewContext(script,{window});
 let picker;
 picker=window.RocotoPick.ui({K,S,cfg,esc:String,ic:()=>'',pic:()=>'',save(){},render(){picker.render()},root:()=>root});
 const click=(action,extra={})=>picker.click({target:{closest:()=>({dataset:{pick:action,...extra}})}});
 return {picker,click,cfg,S,html:()=>node.innerHTML,stamp:()=>clone(picker.stamp({}))};
}
test('conditional questions and options follow explicit answers while independent sections stay available',()=>{
 const x=fixture();x.click('help');
 assert.match(x.html(),/data-section="door"/);assert.match(x.html(),/data-section="parts"/);
 assert.doesNotMatch(x.html(),/data-section="second"|data-section="details"/);
 x.click('answer',{question:'door',answer:'second'});x.click('section',{section:'second'});
 assert.match(x.html(),/data-question="second"/);
 x.click('answer',{question:'second',answer:'surface'});x.click('section',{section:'details'});
 assert.match(x.html(),/data-answer="single"/);assert.doesNotMatch(x.html(),/data-answer="pair"|data-question="details" data-answer="\?"/);
 assert.equal(x.picker.state.answers.details,undefined,'one eligible option still requires customer choice');
 x.click('answer',{question:'parts',answer:'handles'});x.click('section',{section:'details'});x.click('section',{section:'details'});
 assert.match(x.html(),/data-answer="pair"/);
});
test('changing a parent prunes dependent answers transitively and removes them from saved capture',()=>{
 const x=fixture();x.click('help');
 for(const [question,answer] of [['door','second'],['second','surface'],['parts','handles'],['details','pair']])x.click('answer',{question,answer});
 x.click('answer',{question:'door',answer:'interior'});
 assert.deepEqual(clone(x.picker.state.answers),{door:['interior'],parts:['handles']});
 const questions=x.stamp().capture.questionnaire.questions;
 assert.ok(questions.filter(q=>['second','details'].includes(q.id)).every(q=>q.status==='unanswered'&&q.answers.length===0));
 x.click('answer',{question:'details',answer:'single'});
 assert.equal(x.picker.state.answers.details,undefined,'hidden control cannot reintroduce an obsolete answer');
});
test('changing an option prerequisite prunes only that answer and keeps unrelated answers',()=>{
 const x=fixture();x.click('help');
 for(const [question,answer] of [['door','second'],['second','surface'],['parts','handles'],['details','pair']])x.click('answer',{question,answer});
 x.click('answer',{question:'parts',answer:'handles'});
 assert.equal(x.picker.state.answers.details,undefined);
 assert.deepEqual(clone(x.picker.state.answers.second),['surface']);
});
for(const lang of ['bg','en'])test('source variants remain distinct in catalogue and proposal in '+lang,()=>{
 const x=fixture(lang);x.click('families');x.picker.state.query='10108';x.picker.render();
 assert.match(x.html(),lang==='bg'?/никел · с насрещник/:/nickel · with strike plate/);
 assert.match(x.html(),lang==='bg'?/никел · без насрещник/:/nickel · without strike plate/);
 x.picker.state.query='10109';x.picker.render();
 assert.match(x.html(),lang==='bg'?/цинк или полимер · без насрещник/:/zinc or polymer · without strike plate/);
 x.picker.state.screen='proposal';x.picker.state.proposal={lines:[{c:'101089',qty:1,why:{en:'Lock',bg:'Брава'}}]};x.picker.render();
 assert.match(x.html(),lang==='bg'?/цинк или полимер · с насрещник/:/zinc or polymer · with strike plate/);
 x.picker.state.screen='spec-result';x.picker.state.spec=[{source:'PZ lock',qty:1,matches:['101081','101085']}];x.picker.render();
 assert.match(x.html(),lang==='bg'?/никел · с насрещник · 101081<\/option>/:/nickel · with strike plate · 101081<\/option>/);
 assert.match(x.html(),lang==='bg'?/никел · без насрещник · 101085<\/option>/:/nickel · without strike plate · 101085<\/option>/);
});

for(const lang of ['bg','en'])test('compact article actions keep explicit accessible names in '+lang,()=>{
 const x=fixture(lang);x.click('families');x.picker.state.query='101081';x.picker.render();
 assert.match(x.html(),new RegExp('aria-label="'+(lang==='bg'?'Добави':'Add')+' 55/72 · 101081"'));
 x.picker.state.screen='proposal';x.picker.state.proposal={lines:[],choices:[{part:'lock',title:{en:'Lock'},matches:['101081'],matching_codes:['101081'],count:1,qty:1,unresolved:[]}]};x.picker.render();
 assert.match(x.html(),new RegExp('aria-label="'+(lang==='bg'?'Избери':'Select')+' 55/72 · 101081"'));
});
