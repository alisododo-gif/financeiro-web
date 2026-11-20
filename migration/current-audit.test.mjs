import test from 'node:test';
import assert from 'node:assert/strict';
import auth from './release/auth.mjs';
import {launchRows} from './launch.mjs';
const origin='https://financeiroproweb.pages.dev';
const env={SUPABASE_URL:'https://example.invalid',SUPABASE_BACKEND_KEY:'sb_secret_test',SESSION_SECRET:'x'.repeat(40)};
test('uid parameter cannot authenticate without signed session',async()=>{
 const saved=globalThis.fetch;let calls=0;
 try{globalThis.fetch=async()=>{calls++;throw Error('network prohibited')};
 for(const path of ['/api/me?uid=1','/api/clientes?uid=1'])assert.equal((await auth.fetch(new Request(origin+path),env)).status,401);
 assert.equal(calls,0);
 }finally{globalThis.fetch=saved;}
});
test('forged session is rejected without database call',async()=>{
 const saved=globalThis.fetch;let calls=0;
 try{globalThis.fetch=async()=>{calls++;throw Error('network prohibited')};
 assert.equal((await auth.fetch(new Request(origin+'/api/me',{headers:{cookie:'fp_session=v1.e30.invalid'}}),env)).status,401);assert.equal(calls,0);
 }finally{globalThis.fetch=saved;}
});
test('installments preserve total cents and first date',()=>{
 const rows=launchRows({descricao:'Teste',valor:100,tipo:'Despesa',data:'2026-12-31',categoria:'Outros',forma_pagamento:'Cartão de Crédito',cartao_id:2,modalidade:'Parcelado',quantidade:3});
 assert.equal(Math.round(rows.reduce((s,r)=>s+r.valor,0)*100),10000);
 assert.equal(rows[0].data,'2026-12-31');
});
