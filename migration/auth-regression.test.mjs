import test from 'node:test';
import assert from 'node:assert/strict';
import {signup} from './release/signup.mjs';
import auth from './release/auth.mjs';
const origin='https://financeiroproweb.pages.dev';
const env={SUPABASE_URL:'https://hkfyvhthfshnddduckjs.supabase.co',SUPABASE_BACKEND_KEY:'sb_secret_synthetic',SESSION_SECRET:'synthetic-session-secret-for-audit-only-12345',LOGIN_LIMITER:{limit:async()=>({success:true})}};
const post=(path,data)=>new Request(origin+path,{method:'POST',headers:{origin,'content-type':'application/json','x-financeiro-operacao':'1','cf-connecting-ip':'203.0.113.1'},body:JSON.stringify(data)});
test('evidence: signup rejects names which cannot be used for login',async()=>{
 const saved=globalThis.fetch;let calls=0;
 try{globalThis.fetch=async()=>{calls++;return Response.json({ok:true});};
 const r=await signup(post('/api/conta/cadastro',{usuario:'Joao Teste',telefone:'65999990000',senha:'synthetic-password',confirmacao:'synthetic-password'}),env);
 assert.equal(r.status,400);assert.equal(calls,0);
 assert.equal((await auth.fetch(post('/api/login',{usuario:'Joao Teste',senha:'synthetic-password'}),env)).status,401);assert.equal(calls,0);
 }finally{globalThis.fetch=saved;}
});
test('evidence: a previously issued session is rejected after password replacement',async()=>{
 const saved=globalThis.fetch;let currentPassword='synthetic-old';let verifies=0;let version=1;
 try{globalThis.fetch=async(url,init)=>{const p=new URL(url).pathname;
  if(p.endsWith('/usuarios'))return Response.json([{id:42,usuario:'synthetic',status:'ativo',role:'user',is_admin:false,session_version:version}]);
  if(p.endsWith('/fp_access_v1'))return Response.json({allowed:true,modules:{}});
  if(p.endsWith('/fp_password_verify_v1')){verifies++;const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(currentPassword)))].map(b=>b.toString(16).padStart(2,'0')).join('');return Response.json(JSON.parse(init.body).p_digest===hash);}
  throw Error('Unexpected path');};
 const login=await auth.fetch(post('/api/login',{usuario:'synthetic',senha:currentPassword}),env);assert.equal(login.status,200);
 const cookie=login.headers.get('set-cookie').split(';')[0];currentPassword='synthetic-replacement';version++;
 const oldSession=await auth.fetch(new Request(origin+'/api/me',{headers:{cookie}}),env);assert.equal(oldSession.status,401);assert.equal(verifies,1);
 assert.equal((await auth.fetch(post('/api/login',{usuario:'synthetic',senha:'synthetic-old'}),env)).status,401);
 }finally{globalThis.fetch=saved;}
});
