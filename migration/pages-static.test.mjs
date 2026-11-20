import test from 'node:test';import assert from 'node:assert/strict';
import {staticPaths,staticRoutes} from './build-pages-static.mjs';import worker from './release/worker.mjs';
test('only public files bypass functions; API, login and private navigation remain dynamic',()=>{
 const excluded=p=>staticRoutes.exclude.some(x=>x.endsWith('*')?p.startsWith(x.slice(0,-1)):p===x);
 for(const p of staticPaths)assert.equal(excluded(p),true,p);
 for(const p of ['/','/app','/financeiro','/api/me','/api/login','/api/financeiro/operacao','/api/atalhos/clientes_cobrar_amanha'])assert.equal(excluded(p),false,p);
});
test('application static responses are independent of the session and carry no cookie',async()=>{
 for(const p of staticPaths.filter(p=>!p.startsWith('/site/'))){const a=await worker.fetch(new Request('https://test.invalid'+p),{}),b=await worker.fetch(new Request('https://test.invalid'+p,{headers:{cookie:'synthetic-other-session'}}),{});assert.equal(a.status,200,p);assert.equal(a.headers.has('set-cookie'),false,p);assert.deepEqual(await a.arrayBuffer(),await b.arrayBuffer(),p);}
});
