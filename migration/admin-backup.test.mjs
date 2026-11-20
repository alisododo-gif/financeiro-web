import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';
import dashboard from './release/dashboard.mjs';import worker from './release/worker.mjs';
const origin='https://financeiroproweb.pages.dev';
const env={SUPABASE_BACKEND_KEY:'sb_secret_synthetic',PROD_API:{fetch:async()=>Response.json({id:1,admin:true,access:{allowed:true}})}};
test('administration includes users beyond 200 and computes complete totals',async()=>{
 const saved=globalThis.fetch;const offsets=[];
 try{globalThis.fetch=async url=>{url=new URL(url);const off=Number(url.searchParams.get('offset'));offsets.push(off);return Response.json(Array.from({length:off===0?500:17},(_,i)=>({id:off+i+1,usuario:'synthetic_'+(off+i),status:'ativo',valor_mensalidade:1})));};
 const r=await dashboard.fetch(new Request(origin+'/api/admin/usuarios'),env);assert.equal(r.status,200);const d=await r.json();assert.equal(d.usuarios.length,517);assert.equal(d.resumo.total,517);assert.equal(d.resumo.mrr,517);assert.deepEqual(offsets,[0,500]);
 }finally{globalThis.fetch=saved;}
});
test('complete snapshot export remains encrypted and browser verifier reads V2 counts',async()=>{
 const saved=globalThis.fetch;
 const snapshot={format:'FinanceiroProDatabaseBackupV2',version:2,consistent:true,definition:{tables:[]},tables:{'public.usuarios':[],'financeiropro_operacoes.user_access':[]},counts:{'public.usuarios':0,'financeiropro_operacoes.user_access':0}};
 try{globalThis.fetch=async(url,init)=>{assert.match(String(url),/fp_backup_snapshot_v2$/);assert.equal(JSON.parse(init.body).p_actor,1);return Response.json(snapshot);};
 const r=await worker.fetch(new Request(origin+'/api/backup/export',{method:'POST',headers:{origin,'content-type':'application/json','x-financeiro-backup':'1'},body:JSON.stringify({frase:'synthetic-phrase-long-enough'})}),env);assert.equal(r.status,200);assert.equal(r.headers.get('x-financeiro-encrypted-backup'),'1');const bytes=await r.arrayBuffer();assert.ok(!new TextDecoder().decode(bytes).includes('user_access'));
 const js=await(await worker.fetch(new Request(origin+'/static/app.js'),env)).text();const start=js.indexOf("const BACKUP_SIGNATURE=");const end=js.indexOf('async function exportEncryptedBackup',start);assert.ok(start>=0&&end>start);
 const context=vm.createContext({crypto,TextDecoder,TextEncoder,Uint8Array,DataView,atob});vm.runInContext(js.slice(start,end),context);context.bytes=bytes;context.phrase='synthetic-phrase-long-enough';const result=await vm.runInContext('backupDecrypt(bytes,phrase)',context);assert.equal(result.total,0);assert.ok(Object.hasOwn(result.tables,'financeiropro_operacoes.user_access'));
 }finally{globalThis.fetch=saved;}
});
