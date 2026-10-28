import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const window={};
vm.runInNewContext(fs.readFileSync(new URL('../widget/pick.js',import.meta.url),'utf8'),{window});
const rows=[
 {c:'101937',cat:{bg:'НОРМА Лукс 50/70',en:'NORMA Lux 50/70'},s:'Лява',se:'Left',a:{finish:'brass'}},
 {c:'101938',cat:{bg:'НОРМА 50/70',en:'NORMA 50/70'},s:'Дясна',se:'Right',a:{finish:'nickel'}}
];
test('Bulgarian catalogue finds Latin and Cyrillic model names, codes and variant terms',()=>{
 for(const query of ['Lux','лукс','NORMA LUX','Лукс 101937','left lux','101937']){
  assert.deepEqual(rows.filter(row=>window.RocotoPick.searches(row,query)).map(row=>row.c),['101937'],query);
 }
 assert.equal(rows.filter(row=>window.RocotoPick.searches(row,'norma')).length,2);
 assert.equal(rows.filter(row=>window.RocotoPick.searches(row,'lux nickel')).length,0);
 assert.equal(rows.filter(row=>window.RocotoPick.searches(row,'  ')).length,2);
});
