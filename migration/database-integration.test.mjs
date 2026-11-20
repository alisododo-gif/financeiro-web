import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';import {pgcrypto} from '@electric-sql/pglite/contrib/pgcrypto';
import {restoreApplication} from '../tools/restore-application.mjs';
const root=new URL('../',import.meta.url);
async function database(){const db=new PGlite({extensions:{pgcrypto}});await db.exec("CREATE ROLE anon;CREATE ROLE authenticated;CREATE ROLE service_role BYPASSRLS;CREATE SCHEMA auth;CREATE TABLE auth.users(id uuid PRIMARY KEY);CREATE SCHEMA extensions;CREATE EXTENSION pgcrypto WITH SCHEMA extensions;");return db;}
test('isolated PostgreSQL: migrations, exact writes, idempotency, permissions and complete restoration',async()=>{
 const db=await database();let target;
 try{
 const d=JSON.parse(await fs.readFile(new URL('test-fixtures/baseline-schema.json',root),'utf8'));
 d.routines=JSON.parse(await fs.readFile(new URL('test-fixtures/baseline-routines.json',root),'utf8')).map(x=>({definition:x.definition}));
 const baseline={format:'FinanceiroProDatabaseBackupV2',version:2,consistent:true,definition:d,tables:Object.fromEntries(d.tables.map(t=>[t.schema+'.'+t.name,[]])),counts:Object.fromEntries(d.tables.map(t=>[t.schema+'.'+t.name,0]))};
 await restoreApplication(db,baseline);await db.exec('GRANT ALL ON ALL TABLES IN SCHEMA public,financeiropro_operacoes TO service_role;');
 for(const name of ['20261120_03_sessions_validation.sql','20261120_04_owner_concurrency.sql','20261120_05_complete_backup.sql','20261120_06_delivery_status.sql','20261120_07_revoke_sessions.sql','20261120_08_delivery_visibility.sql'])await db.exec(await fs.readFile(new URL('migration/schema/'+name,root),'utf8'));
 await db.exec("INSERT INTO public.usuarios(id,usuario,senha,status,is_admin,role) VALUES (1,'synthetic_admin',repeat('a',64),'ativo',true,'admin'),(2,'synthetic_user',repeat('b',64),'ativo',false,'user');INSERT INTO financeiropro_operacoes.access_settings(id,modules,contact) VALUES(true,'{\"contas\":true,\"novo_lancamento\":true,\"movimentacoes\":true,\"clientes\":true,\"cartoes\":true,\"visao_geral\":true}','5565999990000');");
 const call=async(owner,key)=>db.query("select public.fp_financeiro_modulo_v1($1,'contas','criar',null,$2::jsonb,null,$3::uuid,'contas') result",[owner,JSON.stringify({nome:'Synthetic '+owner,saldo:0}),key]);
 const keys=Array.from({length:60},()=>crypto.randomUUID());await Promise.all(keys.map((key,i)=>call(i%2+1,key)));
 assert.equal((await db.query('select count(*)::int n from public.contas')).rows[0].n,60);
 await call(1,keys[0]);assert.equal((await db.query('select count(*)::int n from public.contas')).rows[0].n,60);
 assert.equal((await db.query("select jsonb_array_length(public.fp_financeiro_modulo_v1(1,'contas','listar',(select min(id) from public.contas where usuario_id=2),'{}',null,null,'contas')->'registros') n")).rows[0].n,0);
 const before=(await db.query('select session_version from public.usuarios where id=2')).rows[0].session_version;
 await db.exec("UPDATE public.usuarios SET senha=repeat('c',64) WHERE id=2");assert.equal(Number((await db.query('select session_version from public.usuarios where id=2')).rows[0].session_version),Number(before)+1);
 await assert.rejects(()=>db.query("select public.fp_signup_pending('Invalid Name',repeat('a',64),'65999990000',repeat('d',64))"));
 const snapshot=(await db.query('select public.fp_backup_snapshot_v2(1) snapshot')).rows[0].snapshot;
 assert.equal(snapshot.consistent,true);assert.ok(snapshot.definition.routines.some(r=>r.identity.includes('fp_sessions_revoke_v1')));assert.ok(Object.keys(snapshot.tables).includes('financeiropro_operacoes.access_settings'));
 await assert.rejects(()=>db.query('select public.fp_backup_snapshot_v2(2)'));
 await db.exec('SET ROLE anon');await assert.rejects(()=>db.query('select public.fp_backup_snapshot_v2(1)'));await db.exec('RESET ROLE');
 target=await database();const restored=await restoreApplication(target,snapshot);assert.ok(restored.records>=62);
 assert.equal((await target.query('select count(*)::int n from public.contas')).rows[0].n,60);
 assert.equal((await target.query('select count(*)::int n from financeiropro_operacoes.comandos')).rows[0].n,60);
 assert.equal((await target.query('select session_version from public.usuarios where id=2')).rows[0].session_version,Number(before)+1);
 assert.equal((await target.query("select has_function_privilege('anon','public.fp_backup_snapshot_v2(bigint)','execute') ok")).rows[0].ok,false);
 await assert.rejects(()=>restoreApplication(target,snapshot));
 }finally{await db.close();if(target)await target.close();}
});
