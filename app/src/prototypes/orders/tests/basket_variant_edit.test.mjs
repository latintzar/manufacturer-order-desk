import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../widget/shop.js',import.meta.url),'utf8');
const start=source.indexOf('function addLine(){');
const action=source.slice(start,source.indexOf('\nfunction setQuery(',start));
assert.ok(start>=0&&action.length>0);

function fixture(note,editing=1){
 const S={item:'151600PП70',rows:[{x:1000,n:3}],sheet:{},angle:false,editing,basket:[
  {code:'151600PП70',rows:[{x:1000,n:1}],why:'Модел: АЛАНИА; Цвят: Бял'},
  {code:'151600PП70',rows:[{x:1000,n:2}],why:'Модел: АЛАНИА; Цвят: Черен'}
 ]};
 let saved;
 const context={S,C:{items:{'151600PП70':{c:'151600PП70'}}},PICK:{note:()=>note},mode:()=> 'piece',curPlan:()=>({ok:true}),save:()=>{saved=JSON.parse(JSON.stringify(S.basket))},showMenu(){},root:{querySelector:()=>null},setTimeout(){}};
 vm.runInNewContext(action,context);context.addLine();
 return {S,saved};
}
for(const currentNote of ['Модел: АЛАНИА; Цвят: Бял',''])test('editing keeps the saved variant with '+(currentNote?'opposite filters':'fresh page state'),()=>{
 const {saved}=fixture(currentNote);
 assert.equal(saved[1].why,'Модел: АЛАНИА; Цвят: Черен');
 assert.equal(saved[1].rows[0].n,3);
 assert.equal(saved[0].why,'Модел: АЛАНИА; Цвят: Бял');
 assert.equal(saved[0].rows[0].n,1);
});
test('a newly added product takes the current catalogue choice',()=>{
 const {saved}=fixture('Модел: АЛАНИА; Цвят: Черен',-1);
 assert.equal(saved.length,3);
 assert.equal(saved[2].why,'Модел: АЛАНИА; Цвят: Черен');
});
