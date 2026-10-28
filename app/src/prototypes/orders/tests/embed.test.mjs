import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const bootstrap=fs.readFileSync(new URL('../widget/embed.js',import.meta.url),'utf8');
const core=fs.readFileSync(new URL('../widget/core.js',import.meta.url),'utf8');
for(const src of [undefined,'','https://orders.example/sample-hardware/rocoto/configurator.js']){
  test(`inline/native or same-origin renderer skips the embed launcher: ${src}`,()=>{
    const context=vm.createContext({window:{},document:{currentScript:src===undefined?null:{src}},location:{origin:'https://orders.example'},URL});
    vm.runInContext(bootstrap,context);
    assert.equal(context.window.RocotoEmbed(),false);
  });
}
for(const [search,expected] of [['?rocoto_embed=1&lang=en','en'],['?rocoto_embed=1&lang=foreign','bg'],['?lang=en','bg']]){
  test(`embedded language remains within the company's supported languages: ${search}`,()=>{
    const context=vm.createContext({window:{RocotoConfig:{lang:'bg',langs:{en:'/en/'}}},location:{pathname:'/sample-hardware/rocoto/embed.html',search},URLSearchParams});
    vm.runInContext(core,context);
    assert.equal(context.window.RocotoCore.L.lang,expected);
  });
}
