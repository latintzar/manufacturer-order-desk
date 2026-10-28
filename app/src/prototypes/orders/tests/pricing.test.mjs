// The widget's price engine reproduces the worked examples of the first company, to the cent.
// Loads widget/pricing.js the way the page does: as a plain script, here inside a vm context.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const here = new URL('.', import.meta.url);
const sandbox = { module: { exports: {} } };
vm.runInNewContext(readFileSync(new URL('../widget/pricing.js', here), 'utf8'), sandbox);
const pricing = sandbox.module.exports.RocotoPricing;
const worked = JSON.parse(readFileSync(new URL('fixtures/worked-examples.json', here), 'utf8'));
const cents = (value) => Math.round(value * 100) / 100;

for (const example of worked.examples) {
  test(`${example.what}: ${example.eur} EUR`, () => {
    const item = { p: example.price, L: example.stock, r: example.rule, cut: 0.5, w: 10, d: example.dims };
    const plan = example.ask.length
      ? pricing.barPlan(item, example.ask.length, example.ask.pieces)
      : pricing.sheetPlan(item, example.ask.a, example.ask.b, example.ask.pieces);
    assert.equal(plan.ok, true);
    assert.equal(cents(plan.price), example.eur);
  });
}

test('the widget holds the same part-length surcharges as the company mapping', () => {
  for (const [stock, table] of Object.entries(worked.partLengthTable)) {
    for (const [length, surcharge] of Object.entries(table)) {
      assert.equal(pricing.surcharge(Number(stock), Number(length)), surcharge);
    }
    assert.equal(pricing.surcharge(Number(stock), Number(stock)), 0);
  }
});

test('a whole bar carries its list price and a cut list buys the cheapest bars', () => {
  const item = { p: 30.97, L: 6, r: { k: 'len', l: [1, 2, 3, 4, 5, 6] }, cut: 0.5, w: 25.3 };
  assert.equal(cents(pricing.barPlan(item, 6000, 1).price), 30.97);
  const three = pricing.barPlan(item, 2000, 3);
  assert.equal(cents(three.price), 30.97);
  assert.equal(three.cuts, 2);
  assert.equal(pricing.barPlan(item, 7000, 1).ok, false);
});

test('a full chequer sheet has zero cuts; quantity buys distinct sheets', () => {
  const item = {p: 80, L: 0, r: {k: 'half'}, cut: 2, w: 35, d: [3, 1000, 2000]};
  const plan = pricing.sheetPlan(item, 2000, 1000, 3);
  assert.equal(plan.cuts, 0);
  assert.equal(plan.total, 240);
  assert.equal(plan.units[0].count, 3);
});

test('strip purchases cap at half/full sheet and use physical sheets', () => {
  const item = {p: 100, L: 0, r: {k: 'strip'}, cut: 1, w: 20, d: [2, 1000, 2000]};
  assert.equal(pricing.sheetPlan(item, 1000, 1800, 1).price, 100);
  const many = pricing.sheetPlan(item, 1000, 1500, 5);
  assert(many.units.every(u => u.len <= 2000));
  assert.equal(many.units.reduce((n, u) => n + u.count, 0), 5);
  const outsideRule = {...item, d: [2, 1500, 3000]};
  assert.equal(pricing.sheetPlan(outsideRule, 1500, 500, 1).sur, 0);
});

test('known stock bounds centimetre sales and full bars carry zero cuts', () => {
  const item = {p: 90, L: 3, r: {k: 'any'}, cut: 5, w: 30};
  assert.equal(pricing.barPlan(item, 6000, 1).ok, false);
  assert.equal(pricing.barPlan(item, 3000, 1).total, 90);
  assert.equal(pricing.listPlan(item, [{x: 3000, n: 2}]).cuts, 0);
});

test('unpublished surcharges and unknown stock are marked for confirmation', () => {
  const item = {p: 100, L: 5, r: {k: 'len', l: [2.5, 5]}, cut: 0, w: 25};
  const plan = pricing.barPlan(item, 2500, 1);
  assert.equal(plan.sur, 0);
  assert.equal(plan.pending, true);
  assert.equal(pricing.barPlan({...item, L: 1, r: {k: 'any'}}, 5000, 1).pending, true);
});

test('metre-based rows charge the metres bought independently of stock length', () => {
  const item = {p: 10, u: 'm', L: 1, r: {k: 'len', l: [6, 12]}, cut: 0, w: 2};
  assert.equal(pricing.barPlan(item, 6000, 1).price, 60);
});

test('published part-length limits apply across an order line', () => {
  const item = {p: 100, L: 6, r: {k: 'len', l: [1, 2, 3, 4, 5, 6]}, cut: 0, w: 20};
  const plan = pricing.barPlan(item, 4000, 3);
  assert(plan.units.filter(u => u.len === 4000).reduce((n, u) => n + u.count, 0) <= 1);
  assert.equal(plan.units.filter(u => u.len === 6000).reduce((n, u) => n + u.count, 0), 2);
});

test('a mixed cut list optimizes material plus cuts and preserves every piece', () => {
  const item = {p: 100, L: 6, r: {k: 'len', l: [1, 2, 3, 4, 5, 6]}, cut: 20, w: 20};
  const rows = [{x: 4000, n: 1}, {x: 2000, n: 1}, {x: 1000, n: 2}];
  const plan = pricing.listPlan(item, rows);
  const actual = plan.units.flatMap(u => Array.from({length: u.count}, () => [...u.cut]).flat()).sort();
  assert.deepEqual(Array.from(actual), [1000, 1000, 2000, 4000]);
  assert(plan.total <= 190);
});

test('prices respond to the catalogue rules rather than company constants', () => {
  try {
    pricing.configure({partLength: {table: {6: {2: .1}}}, kerfMm: {value: 0}, strip: {surcharge: .1}, singleSheetStrokeFactor: 3});
    assert.equal(cents(pricing.barPlan({p: 60, L: 6, r: {k: 'len', l: [2, 6]}, cut: 0, w: 12}, 2000, 1).price), 22);
    assert.equal(pricing.KERF, 0);
  } finally { pricing.configure(); }
});

test('canonical line quoting rejects invalid quantities and angle requests',()=>{
 const item={p:60,L:6,cat:{shape:'sq_tube'},r:{k:'len',l:[2,3,6]},cut:2,w:12};
 assert.equal(pricing.quoteLine(item,{rows:[{x:2000,n:-1}]}).ok,false);
 assert.equal(pricing.quoteLine(item,{rows:[{x:Infinity,n:1}]}).ok,false);
 assert.equal(pricing.quoteLine(item,{rows:[{x:2000,n:1}],angle:{degrees:10,ends:1}}).ok,false);
 assert.equal(pricing.quoteLine(item,{rows:[{x:2000,n:1}],angle:{degrees:45,ends:2}}).cutCost,6);
});

test('cut-list boundaries allow 100 sizes and 999 pieces per size only',()=>{
 const item={p:10,u:'m',L:6,cat:{shape:'round'},r:{k:'any'},cut:0,w:1};
 const hundred=Array.from({length:100},(_,n)=>({x:n+1,n:1}));
 assert.equal(pricing.quoteLine(item,{rows:hundred}).ok,true);
 assert.equal(pricing.quoteLine(item,{rows:[...hundred,{x:101,n:1}]}).ok,false);
 assert.equal(pricing.quoteLine(item,{rows:[{x:1,n:999}]}).ok,true);
 assert.equal(pricing.quoteLine(item,{rows:[{x:1,n:1000}]}).ok,false);
});

test('metre-priced published lengths work above one metre and stay provisional',()=>{
 const item={p:18.74,L:1,u:'m',stockLengthKnown:false,w:9.7,cut:2.76,r:{k:'len',l:[1,2,3,4,5]}};
 const p=pricing.barPlan(item,3000,1);assert.equal(p.ok,true);assert.equal(p.total,56.22);assert.equal(p.pending,true);
});
test('Cupal purchases use the published sheet portions',()=>{
 const item={p:147.25,cut:1.07,w:2.4,d:[.5,500,2000],r:{k:'strip',lengths:[500,1000,2000]}};
 const whole=pricing.sheetPlan(item,2000,500,1);assert.equal(whole.cuts,0);assert.equal(whole.total,147.25);
 const quarter=pricing.sheetPlan(item,500,500,1);assert.equal(quarter.units[0].len,500);assert.equal(quarter.sur,0);
});

test('held-price custom bars retain their parent material plan without quoting a price',()=>{
 const item={c:'BAR',q:1,p:100,L:6,r:{k:'len',l:[3,6]},cut:2,w:18,cat:{shape:'sq_tube'}};
 const p=pricing.quoteLine(item,{rows:[{x:2000,n:3}]});
 assert.equal(pricing.lineMode(item),'bar');
 assert.equal(p.ok,true);assert.equal(p.ask,1);assert.equal(p.total,0);
 assert.equal(p.bought,6000);assert.equal(p.units.reduce((n,u)=>n+u.count,0),1);
 const unknownStock=pricing.quoteLine({...item,L:0,r:{k:'len',l:[3,6,9]}},{rows:[{x:3000,n:3}]});
 assert.equal(unknownStock.ok,true);assert.equal(unknownStock.bought,9000);assert(Number.isFinite(unknownStock.kg));
});

test('held-price sheets validate custom dimensions and retain parent sheet demand',()=>{
 const item={c:'SHEET',q:1,p:100,d:[2,1000,2000],r:{k:'strip'},cut:2,w:32,cat:{shape:'sheet'}};
 assert.equal(pricing.lineMode(item),'sheet');
 const p=pricing.quoteLine(item,{sheet:{a:500,b:500,n:4}});
 assert.equal(p.ok,true);assert.equal(p.ask,1);assert.equal(p.total,0);
 assert.equal(p.units.reduce((n,u)=>n+u.count,0),1);
 assert.equal(pricing.quoteLine(item,{sheet:{a:2500,b:500,n:1}}).ok,false);
});
