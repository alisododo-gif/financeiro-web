import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';
import worker from './release/worker.mjs';import {mobileAppScript,appServiceWorker} from './mobile-app.mjs';
test('home screen icons are real square PNGs with platform-specific sizes',async()=>{
 const manifest=await(await worker.fetch(new Request('https://example.com/manifest.webmanifest'),{})).json();
 assert.deepEqual(manifest.icons.map(i=>i.sizes),['192x192','512x512']);
 for(const size of [32,180,192,512]){
  const response=await worker.fetch(new Request('https://example.com/static/app-icon-v2-'+size+'.png'),{});
  assert.equal(response.status,200);assert.equal(response.headers.get('content-type'),'image/png');
  const data=new Uint8Array(await response.arrayBuffer()),view=new DataView(data.buffer);
  assert.deepEqual([...data.slice(0,8)],[137,80,78,71,13,10,26,10]);assert.equal(view.getUint32(16),size);assert.equal(view.getUint32(20),size);
 }
});
test('installable app assets are public static routes without exposing the backend',async()=>{const r=await worker.fetch(new Request('https://financeiroproweb.pages.dev/manifest.webmanifest'),{}),m=await r.json();assert.equal(m.name,'FinanceiroPro Web');assert.equal(m.display,'standalone');assert.equal(m.start_url,'/');assert.equal(m.scope,'/');const sw=await worker.fetch(new Request('https://financeiroproweb.pages.dev/app-sw.js'),{});assert.equal(sw.headers.get('cache-control'),'no-cache');assert.equal(sw.headers.get('service-worker-allowed'),'/');new vm.Script(await sw.text());new vm.Script(mobileAppScript);});
test('offline shell intercepts navigation only and never queues or caches financial requests',async()=>{const handlers={};vm.runInNewContext(appServiceWorker,{self:{addEventListener:(type,fn)=>handlers[type]=fn},fetch:async()=>{throw Error('offline');},Response});let intercepted=false;handlers.fetch({request:{mode:'cors',url:'/api/financeiro/operacao',method:'POST'},respondWith(){intercepted=true;}});assert.equal(intercepted,false);let pending;handlers.fetch({request:{mode:'navigate'},respondWith:p=>pending=p});const response=await pending;assert.equal(response.status,503);assert.match(await response.text(),/sem conexão/);assert.equal(response.headers.get('cache-control'),'no-store');assert.doesNotMatch(appServiceWorker,/caches\.|indexedDB|localStorage|fetch\(.*method.*POST/);});
