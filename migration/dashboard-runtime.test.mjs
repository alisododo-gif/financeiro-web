import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';
import {optimizeDashboardSource} from './dashboard-runtime.mjs';
import worker from './release/worker.mjs';
import {script} from './release/financeiro.mjs';
import {parityScript} from './parity.mjs';
test('failed module navigation hides previous cards and offers a retry instead of stale data',async()=>{
 const start=script.indexOf('async function load(){'),end=script.indexOf('const invoicePanel=',start),messages=[];
 const c=vm.createContext({revision:0,periodFilter:{value:'2026-10'},summaryMonth:{value:'2026-10'},table:'contas',summaryCard:{hidden:false},listFilters:{hidden:false},reportControls:{hidden:false},pager:{hidden:false},
 $:()=>({replaceChildren:item=>messages.push(item),closest:()=>({})}),node:(tag,text)=>text,updateModuleHeading(){},api:async()=>{throw Error('offline');}});
 vm.runInContext(script.slice(start,end),c);await assert.rejects(vm.runInContext('load()',c),/offline/);
 for(const name of ['summaryCard','listFilters','reportControls','pager'])assert.equal(c[name].hidden,true);
 assert.match(messages.at(-1),/Verifique sua conexão.*Atualizar/);
});
test('annual charts include previous-year credit for the current invoice year and retain session owner',async()=>{
 const prior=globalThis.fetch;let input;
 globalThis.fetch=async requestUrl=>{throw Error('Unexpected request '+requestUrl);};
 try{
  globalThis.fetch=async(url,options)=>{input=JSON.parse(options.body);return Response.json({registros:[
   {id:1,data:'2026-12-28',forma_pagamento:'Cartão de Crédito',mes_fatura:'01/2027'},
   {id:2,data:'2026-12-28',forma_pagamento:'Pix',mes_fatura:'01/2027'},
   {id:3,data:'2027-12-28',forma_pagamento:'Cartão de Crédito',mes_fatura:'01/2028'},
   {id:4,data:'2027-01-03',forma_pagamento:'Boleto'}]});};
  const response=await worker.fetch(new Request('https://example.com/api/financeiro/ano?ano=2027'),{REVIEW_API:{},SUPABASE_BACKEND_KEY:'test',PROD_API:{fetch:async()=>Response.json({id:1})}});
  assert.equal(response.status,200);assert.deepEqual((await response.json()).registros.map(r=>r.id),[1,4]);
  assert.equal(input.p_usuario,1);assert.equal(input.p_modulo,'visao_geral');assert.equal(input.p_acao,'listar');assert.deepEqual(input.p_dados,{ano:'2027'});
 }finally{globalThis.fetch=prior;}
});
function fixture(){let year='2026';const calls=[],listeners={};const context=vm.createContext({Date,URLSearchParams,MutationObserver:class{observe(){}},document:{getElementById:()=>null,addEventListener:(n,f)=>listeners[n]=f},api:path=>new Promise((resolve,reject)=>calls.push({path,resolve,reject}))});vm.runInContext("const $=()=>({value:year});let loadedMovements=null,loadedYear=null,dashboardSerial=0;function dashboard(){}",Object.assign(context,{year}));vm.runInContext(optimizeDashboardSource('async function allMovements(){}\nfunction renderFlow(){}'),context);return {context,calls,listeners,read:()=>vm.runInContext('allMovements()',context),year:y=>{context.year=y;}};}
test('annual read shares concurrent request and retries after failure',async()=>{const f=fixture(),a=f.read(),b=f.read();assert.equal(f.calls.length,1);f.calls[0].reject(Error('temporary'));await Promise.allSettled([a,b]);const c=f.read();assert.equal(f.calls.length,2);f.calls[1].resolve({registros:[{id:1}]});assert.equal((await c)[0].id,1);await f.read();assert.equal(f.calls.length,2);});
test('late year response cannot overwrite current year cache',async()=>{const f=fixture(),old=f.read();f.year('2027');const current=f.read();f.calls[1].resolve({registros:[{id:2027}]});await current;f.calls[0].resolve({registros:[{id:2026}]});await old;assert.equal((await f.read())[0].id,2027);assert.equal(f.calls.length,2);});
test('logout invalidates both cached and in-flight personal data',async()=>{const f=fixture(),old=f.read();f.listeners['fp:session-reset']();f.calls[0].resolve({registros:[{id:1}]});await old;const next=f.read();assert.equal(f.calls.length,2);f.calls[1].resolve({registros:[]});await next;});
test('financial mutations invalidate overview cache',async()=>{const f=fixture(),a=f.read();f.calls[0].resolve({registros:[]});await a;f.listeners['fp:data-changed']();const b=f.read();assert.equal(f.calls.length,2);f.calls[1].resolve({registros:[]});await b;});
test('published dashboard script remains valid after runtime transforms',async()=>{const r=await worker.fetch(new Request('https://example.com/static/app.js'),{});assert.equal(r.status,200);new vm.Script(await r.text());});
test('cards load requests each table once and starts movement query in parallel',async()=>{const start=script.indexOf('async function load(){'),end=script.indexOf('const invoicePanel=',start);const calls=[];const context=vm.createContext({revision:0,periodFilter:{value:'2026-10'},summaryMonth:{value:'2026-10'},table:'cartoes',accounts:[],cards:[],rows:[],budgetMovements:[],$:()=>({replaceChildren(){},closest:()=>({})}),summaryCard:{},listFilters:{},reportControls:{},pager:{},node:()=>({}),updateModuleHeading(){},cardFilter:{value:'',replaceChildren(){},append(){},options:[]},Option:class{},api:async p=>{calls.push(p.tabela);return {registros:[]};},form(){},display(){},closeInvoice(){}});vm.runInContext(script.slice(start,end),context);await vm.runInContext('load()',context);assert.deepEqual(calls,['cartoes','movimentacoes']);});
test('simultaneous overview observers share a single three-table read',async()=>{const calls=[];let renders=0;const c=vm.createContext({Date,document:{getElementById:()=>({value:'2026'})},visible:()=>true,read:name=>new Promise(resolve=>calls.push({name,resolve})),render:()=>renders++,panel:{replaceChildren(){}},node(){}});vm.runInContext('let cache=null,loaded=0,serial=0,readBatch=null;'+parityScript.slice(parityScript.indexOf('async function refresh(){'),parityScript.indexOf("for(const id of ['month','year']")),c);const a=vm.runInContext('refresh()',c),b=vm.runInContext('refresh()',c);assert.equal(calls.length,3);for(const call of calls)call.resolve([]);await Promise.all([a,b]);assert.equal(renders,1);});
test('overview request completed after session reset cannot render personal data',async()=>{const calls=[];let renders=0;const c=vm.createContext({Date,document:{getElementById:()=>({value:'2026'})},visible:()=>true,read:()=>new Promise(resolve=>calls.push(resolve)),render:()=>renders++,panel:{replaceChildren(){}},node(){}});vm.runInContext('let cache=null,loaded=0,serial=0,readBatch=null;'+parityScript.slice(parityScript.indexOf('async function refresh(){'),parityScript.indexOf("for(const id of ['month','year']")),c);const a=vm.runInContext('refresh()',c);vm.runInContext('serial++;cache=null;readBatch=null;',c);for(const resolve of calls)resolve([]);await a;assert.equal(renders,0);assert.equal(vm.runInContext('cache',c),null);});
