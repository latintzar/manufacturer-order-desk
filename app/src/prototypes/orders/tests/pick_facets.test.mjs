import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source = fs.readFileSync(new URL('../widget/pick.js', import.meta.url), 'utf8');
const window = {};
vm.runInNewContext(source, {window});
const {matches, values} = window.RocotoPick;
const plain = value => JSON.parse(JSON.stringify(value));

function fixture(attributes, facets = []) {
  const cat = {code:'model',form:'test',bg:'Model',en:'Model',items:[]};
  cat.items = attributes.map((a,i) => ({c:'article-'+i,a,cat,s:'Source specification '+i}));
  const K = {L:{lang:'en'},C:{cats:[cat],byCode:{model:cat},items:Object.fromEntries(cat.items.map(row=>[row.c,row]))}};
  const S = {basket:[],view:'pick'};
  const cfg = {picker:{families:[{id:'test',title:{en:'Products'},match:{form:'test'},facets}]}};
  const scroll = {scrollTop:0};
  const node = {hidden:false,classList:{add(){}},querySelector:()=>scroll,querySelectorAll:()=>[],focus(){},innerHTML:''};
  const root = {activeElement:null,querySelector:selector=>selector==='#pick'?node:selector==='.pick-scroll'?scroll:{...node}};
  let picker;
  picker = window.RocotoPick.ui({K,S,cfg,esc:String,ic:()=>'',pic:()=>'',save(){},render(){picker.render()},root:()=>root});
  picker.state.family='test'; picker.state.screen='facets'; picker.render();
  const click=(action,extra={})=>picker.click({target:{closest:()=>({dataset:{pick:action,...extra}})}});
  return {picker,S,click,html:()=>node.innerHTML};
}

test('equivalent decimal dimensions select the same articles', () => {
  const row = {a:{A:'30.0',B:35,backset:'35.0'},cat:{code:'model'}};
  assert.ok(matches(row,{A:30,B:'35.0',backset:35}));
  assert.deepEqual(plain(values(row,'_size')),['30/35']);
  assert.ok(matches(row,{_size:'30/35'}));
  assert.equal(matches(row,{A:35}),false);
});

test('unknown zero dimensions never become purchasable paired sizes', () => {
  for (const a of [{backset:0,centres:0},{A:0,B:35},{backset:35},{A:'',B:35}]) {
    assert.deepEqual(plain(values({a},'_size')),[]);
  }
  assert.deepEqual(plain(values({a:{backset:35,centres:47}},'_size')),['35/47']);
});

test('dimension options merge decimal spellings while retaining both articles', () => {
  const x=fixture([{A:30,B:35},{A:'30.0',B:35}], [{key:'A',title:{en:'Outside length'},options:[{value:30,label:'30'},{value:'30.0',label:'30.0'}]}]);
  assert.equal((x.html().match(/data-key="A" data-value="30"/g)||[]).length,1);
  assert.match(x.html(),/data-key="A" data-value="30"[^>]*><span>30<\/span><small>2<\/small>/);
  x.picker.state.filters={A:'30'};x.picker.render();
  assert.match(x.html(),/Articles <span>2<\/span>/);
});

test('shared application metadata does not open a question that cannot narrow the products', () => {
  const x=fixture([{use:['entrance','interior'],width:740},{use:['entrance','interior'],width:840}], [{key:'use',title:{en:'Application'},options:[{value:'entrance',label:'Entrance'},{value:'interior',label:'Interior'}]}]);
  assert.doesNotMatch(x.html(),/<details class="pick-facet" open><summary[^>]*><h2>Application<\/h2>/);
  assert.match(x.html(),/<details class="pick-facet" open><summary[^>]*><h2>Width · mm<\/h2>/);
});

test('derived details expose recorded dimensions and materials without inventing absent ones', () => {
  const x=fixture([{plate:18,latch:'alloy',hand:'L'},{plate:22,latch:'ceramic',hand:'R'}]);
  for(const key of ['plate','latch','hand'])assert.match(x.html(),new RegExp('data-key="'+key+'"'));
  assert.match(x.html(),/Forend width · mm/);
  assert.match(x.html(),/Latch material/);
  assert.match(x.html(),/Zinc alloy/);
  assert.doesNotMatch(x.html(),/data-key="width"|data-key="diameter"|data-key="_size"/);
  const plainRows=fixture([{},{}]);
  assert.doesNotMatch(plainRows.html(),/data-key="(?:plate|width|latch|hand|_size)"/);
});


test('same article keeps selected colour in separate order lines and independent quantities', () => {
  const x=fixture([{colour:['white','black']}], [{key:'colour',title:{en:'Colour'},options:[{value:'white',label:'White'},{value:'black',label:'Black'}]}]);
  x.picker.state.entry='catalogue';
  x.picker.state.filters={colour:'white'};x.picker.render();
  x.click('add',{code:'article-0'});
  assert.equal(x.S.basket.length,1);assert.match(x.S.basket[0].why,/Colour: White/);
  assert.match(x.html(),/pick-cart-quantity/);
  x.picker.state.filters={colour:'black'};x.picker.render();
  assert.doesNotMatch(x.html(),/pick-cart-quantity/);
  x.click('add',{code:'article-0'});
  assert.equal(x.S.basket.length,2);assert.match(x.S.basket[1].why,/Colour: Black/);
  x.click('cart-step',{line:'1',delta:'1'});
  assert.equal(x.S.basket[0].rows[0].n,1);assert.equal(x.S.basket[1].rows[0].n,2);
  x.picker.state.filters={colour:'white'};x.picker.render();
  assert.match(x.html(),/value="1" data-pick-cart-qty="0"/);
  assert.doesNotMatch(x.S.basket[0].why,/Black/);assert.doesNotMatch(x.S.basket[1].why,/White/);
});

test('the same variant retains its counter and basket line after choices are reordered', () => {
  const x=fixture([{colour:['white','black']}], [
    {key:'model',title:{en:'Model'},options:[{value:'model',label:'Model'}]},
    {key:'colour',title:{en:'Colour'},options:[{value:'white',label:'White'},{value:'black',label:'Black'}]}
  ]);
  x.picker.state.entry='catalogue';
  x.picker.state.filters={model:'model',colour:'white'};x.picker.render();
  x.click('add',{code:'article-0'});
  const originalNote=x.S.basket[0].why;
  x.click('filter',{key:'model',value:'model'});
  x.click('filter',{key:'model',value:'model'});
  assert.match(x.html(),/value="1" data-pick-cart-qty="0"/);
  x.click('add',{code:'article-0'});
  assert.equal(x.S.basket.length,1);
  assert.equal(x.S.basket[0].rows[0].n,2);
  assert.equal(x.S.basket[0].why,originalNote);
  assert.match(originalNote,/^Model: Model; Colour: White$/);
});
