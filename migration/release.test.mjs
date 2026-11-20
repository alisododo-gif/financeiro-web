import {navigation} from './release/navigation.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {handle,script} from './release/financeiro.mjs';
import worker from './release/worker.mjs';
const origin='https://financeiroproweb.alisododo.workers.dev';
const env={SUPABASE_BACKEND_KEY:'eyJ.test-key',PROD_API:{fetch:async()=>Response.json({id:1})},FINANCIAL_WRITES_ENABLED:'false'};
const request=body=>new Request(origin+'/api/financeiro/operacao',{method:'POST',headers:{origin,'content-type':'application/json','x-financeiro-operacao':'1'},body:JSON.stringify(body)});
test('release browser script parses',()=>{new vm.Script(script);});
test('mutations blocked until access validation',async()=>{const r=await handle(request({tabela:'contas',acao:'criar',dados:{nome:'Teste',saldo:0},chave:'11111111-1111-4111-8111-111111111111'}),env);assert.equal(r.status,503);});
test('enabled mutations use verified session owner',async()=>{const original=globalThis.fetch;try{globalThis.fetch=async(url,init)=>{const body=JSON.parse(init.body);assert.equal(body.p_usuario,1);assert.equal(body.p_acao,'criar');return Response.json({gravado:true});};assert.equal((await handle(request({tabela:'contas',acao:'criar',dados:{nome:'Teste',saldo:0},chave:'11111111-1111-4111-8111-111111111111'}),{...env,FINANCIAL_WRITES_ENABLED:'true'})).status,200);}finally{globalThis.fetch=original;}});
test('read uses fixed production RPC and legacy backend authorization',async()=>{const original=globalThis.fetch;try{globalThis.fetch=async(url,init)=>{assert.equal(url,'https://hkfyvhthfshnddduckjs.supabase.co/rest/v1/rpc/fp_financeiro_modulo_v1');assert.equal(JSON.parse(init.body).p_usuario,1);assert.equal(init.headers.authorization,'Bearer eyJ.test-key');return Response.json({registros:[]});};assert.equal((await handle(request({tabela:'contas',acao:'listar'}),env)).status,200);}finally{globalThis.fetch=original;}});
test('test mutation endpoint unavailable in final Worker',async()=>assert.equal((await worker.fetch(new Request(origin+'/api/homologacao/operacao'),env)).status,404));
test('official entry opens dashboard',async()=>{for(const route of ['/app', '/financeiro'])assert.equal((await worker.fetch(new Request(origin+route),env)).headers.get('location'),origin+'/');});
test('explicit financial module remains available',async()=>{const r=await worker.fetch(new Request(origin+'/financeiro?modulo=movimentacoes'),env);assert.equal(r.status,200);assert.match(await r.text(),/Novo registro/);});
test('clean address serves login directly and old links preserve inactivity reason',async()=>{
 const r=await worker.fetch(new Request(origin+'/'),{LEGACY_API:{fetch:async request=>{assert.equal(new URL(request.url).pathname,'/app');return new Response('<html><head></head><body>Login</body></html>');}}});assert.equal(r.status,200);assert.match(await r.text(),/Login/);
 const redirect=await worker.fetch(new Request(origin+'/app?motivo=inatividade'),{});assert.equal(redirect.headers.get('location'),origin+'/?motivo=inatividade');
});
test('login omits redundant heading and top operations link',async()=>{const r=await worker.fetch(new Request(origin+'/'),{...env,LEGACY_API:{fetch:async()=>new Response('<html><head></head><body><h1>Acesse seu financeiro</h1><form>Login</form></body></html>')}});const html=await r.text();assert.doesNotMatch(html,/Acesse seu financeiro|Abrir opera/);assert.match(html,/<form>Login<\/form>/);});

test('navigation is isolated from dashboard globals',()=>{new vm.Script('const labels={};const lab=null;let panel;'+navigation);});
test('financial modules are integrated without frames',async()=>{const r=await worker.fetch(new Request(origin+'/static/financial-panel.js'),env);const body=await r.text();new vm.Script(body);assert.match(body,/attachShadow/);assert.doesNotMatch(navigation,/createElement\('iframe'\)/);});
