import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';
import {createEnvironment} from './release/services.mjs';import {panelScript} from './release/panel.mjs';
test('identity reads share only within one request and each caller receives a usable response',async()=>{
 let calls=0;const bindings={PROD_API:{fetch:async()=>{calls++;return Response.json({id:1});}}};
 const request=cookie=>new Request('https://internal/api/me',{headers:{cookie}}),env=createEnvironment(bindings);
 const results=await Promise.all([env.PROD_API.fetch(request('a')),env.PROD_API.fetch(request('a'))]);
 assert.equal(calls,1);for(const r of results)assert.equal((await r.json()).id,1);
 await env.PROD_API.fetch(request('b'));assert.equal(calls,2);
 await createEnvironment(bindings).PROD_API.fetch(request('a'));assert.equal(calls,3);
});
test('failed identity reads are retried; changes never share a cached identity response',async()=>{
 let calls=0;const env=createEnvironment({PROD_API:{fetch:async()=>{calls++;return new Response('',{status:503});}}});
 const req=new Request('https://internal/api/me');await env.PROD_API.fetch(req);await env.PROD_API.fetch(req);assert.equal(calls,2);
 await env.PROD_API.fetch(new Request('https://internal/api/logout',{method:'POST'}));assert.equal(calls,3);
});
test('changing a month reloads its new value without restoring the old navigation context',()=>{
 const match=panelScript.match(/periodFilter\.addEventListener\('change',\(\)=>\{([\s\S]*?)\}\);/);assert.ok(match);
 let loaded;const c=vm.createContext({periodFilter:{value:'2026-11'},currentPage:8,perform:f=>f(),load:()=>{loaded=c.periodFilter.value;}});
 vm.runInContext(match[1],c);assert.equal(loaded,'2026-11');assert.equal(c.currentPage,1);
});
