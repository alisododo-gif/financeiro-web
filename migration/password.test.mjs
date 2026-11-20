import test from 'node:test';
import assert from 'node:assert/strict';
import auth from './release/auth.mjs';
import {changePassword} from './release/account.mjs';
const origin='https://financeiroproweb.pages.dev';
const env={SUPABASE_URL:'https://hkfyvhthfshnddduckjs.supabase.co',SUPABASE_BACKEND_KEY:'sb_secret_test',SESSION_SECRET:'x'.repeat(40),LOGIN_LIMITER:{limit:async()=>({success:true})}};
const request=()=>new Request(origin+'/api/login',{method:'POST',headers:{origin,'content-type':'application/json'},body:JSON.stringify({usuario:'synthetic',senha:'synthetic-password'})});
test('login verifies through service RPC without reading stored hashes',async()=>{
 const saved=globalThis.fetch;let calls=0;
 try{globalThis.fetch=async(url,init)=>{calls++;url=new URL(url);if(url.pathname.endsWith('/usuarios')){assert.equal(url.searchParams.get('select'),'id,usuario,status');return Response.json([{id:42,usuario:'synthetic',status:'ativo'}]);}assert.equal(url.pathname,'/rest/v1/rpc/fp_password_verify_v1');const data=JSON.parse(init.body);assert.equal(data.p_usuario,42);assert.match(data.p_digest,/^[0-9a-f]{64}$/);assert.equal(init.headers.apikey,env.SUPABASE_BACKEND_KEY);return Response.json(true);};
 const r=await auth.fetch(request(),env);assert.equal(r.status,200);assert.match(r.headers.get('set-cookie'),/HttpOnly; Secure; SameSite=Strict/);assert.deepEqual(await r.json(),{ok:true});assert.equal(calls,2);
 }finally{globalThis.fetch=saved;}
});
test('wrong credentials, database failure and rate limits cannot authenticate',async()=>{
 const saved=globalThis.fetch;
 try{for(const result of [false,'true',null]){globalThis.fetch=async url=>new URL(url).pathname.endsWith('/usuarios')?Response.json([{id:42,usuario:'synthetic',status:'ativo'}]):Response.json(result);assert.equal((await auth.fetch(request(),env)).status,401);}
 globalThis.fetch=async()=>{throw Error('unavailable');};assert.equal((await auth.fetch(request(),env)).status,500);
 assert.equal((await auth.fetch(request(),{...env,LOGIN_LIMITER:{limit:async()=>({success:false})}})).status,429);
 }finally{globalThis.fetch=saved;}
});
const payload={atual:'synthetic-current',nova:'synthetic-replacement',confirmacao:'synthetic-replacement'};
const changeRequest=(data=payload,headers={})=>new Request(origin+'/api/conta/senha',{method:'POST',headers:{origin,'content-type':'application/json','x-financeiro-operacao':'1',...headers},body:JSON.stringify(data)});
const changeEnv=(status=200)=>({...env,PROD_API:{fetch:async req=>req.url.endsWith('/me')?Response.json({id:42,usuario:'synthetic'}):new Response('{}',{status})}});
test('password change uses verified owner and atomic comparison RPC',async()=>{
 const saved=globalThis.fetch;
 try{globalThis.fetch=async(url,init)=>{assert.match(String(url),/\/rpc\/fp_password_change_v1$/);const data=JSON.parse(init.body);assert.deepEqual(Object.keys(data),['p_usuario','p_atual','p_nova']);assert.equal(data.p_usuario,42);assert.match(data.p_atual,/^[0-9a-f]{64}$/);assert.match(data.p_nova,/^[0-9a-f]{64}$/);assert.notEqual(data.p_atual,data.p_nova);return Response.json(true);};
 const r=await changePassword(changeRequest(),changeEnv());assert.equal(r.status,200);assert.match(r.headers.get('set-cookie'),/Max-Age=0/);
 globalThis.fetch=async()=>Response.json(false);assert.equal((await changePassword(changeRequest(),changeEnv())).status,409);
 }finally{globalThis.fetch=saved;}
});
test('invalid password changes and wrong current password never write',async()=>{
 const saved=globalThis.fetch;let writes=0;
 try{globalThis.fetch=async()=>{writes++;throw Error('unexpected');};
 assert.equal((await changePassword(changeRequest(payload,{origin:'https://other.invalid'}),changeEnv())).status,403);
 assert.equal((await changePassword(changeRequest({...payload,usuario_id:5}),changeEnv())).status,400);
 assert.equal((await changePassword(changeRequest({...payload,nova:'short'}),changeEnv())).status,400);
 assert.equal((await changePassword(changeRequest(),changeEnv(401))).status,400);
 assert.equal((await changePassword(changeRequest(),changeEnv(429))).status,429);assert.equal(writes,0);
 }finally{globalThis.fetch=saved;}
});
