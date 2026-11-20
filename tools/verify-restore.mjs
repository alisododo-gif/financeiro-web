import fs from 'node:fs/promises';import path from 'node:path';import {PGlite} from '@electric-sql/pglite';import {pgcrypto} from '@electric-sql/pglite/contrib/pgcrypto';
import {restoreApplication,validateSnapshot} from './restore-application.mjs';
const [input,target]=process.argv.slice(2),passphrase=process.env.FP_BACKUP_PASSPHRASE;
if(!input||!target||!passphrase)throw Error('Uso: configure FP_BACKUP_PASSPHRASE e execute node tools/verify-restore.mjs arquivo.fpbackup NOVA_PASTA_LOCAL');
const resolved=path.resolve(target);if(await fs.stat(resolved).then(()=>true,()=>false))throw Error('A pasta de destino já existe. Use uma NOVA pasta para proteger dados existentes.');
const bytes=await fs.readFile(input);if(bytes.subarray(0,5).toString()!=='FPWB1')throw Error('Arquivo não reconhecido');
const size=bytes.readUInt32BE(5);if(size>2048||size<20||9+size>=bytes.length)throw Error('Cabeçalho inválido');
const headerBytes=bytes.subarray(9,9+size),header=JSON.parse(headerBytes.toString());
if(header.cipher!=='AES-256-GCM'||header.kdf!=='PBKDF2-SHA256'||![100000,250000].includes(header.iterations))throw Error('Formato criptográfico não suportado');
const base=await crypto.subtle.importKey('raw',new TextEncoder().encode(passphrase),'PBKDF2',false,['deriveKey']);
const key=await crypto.subtle.deriveKey({name:'PBKDF2',hash:'SHA-256',salt:Buffer.from(header.salt,'base64url'),iterations:header.iterations},base,{name:'AES-GCM',length:256},false,['decrypt']);
const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:Buffer.from(header.iv,'base64url'),additionalData:headerBytes},key,bytes.subarray(9+size));
const snapshot=validateSnapshot(JSON.parse(new TextDecoder().decode(plain)));
await fs.mkdir(resolved,{recursive:false});const db=new PGlite(resolved,{extensions:{pgcrypto}});
try{
 await db.exec('CREATE ROLE anon;CREATE ROLE authenticated;CREATE ROLE service_role BYPASSRLS;CREATE SCHEMA extensions;CREATE EXTENSION pgcrypto WITH SCHEMA extensions;CREATE SCHEMA auth;CREATE TABLE auth.users(id uuid PRIMARY KEY);');
 // Placeholder references only, for isolated application recovery validation. These are NOT provider Auth accounts.
 for(const id of new Set((snapshot.tables['public.usuarios']||[]).map(r=>r.auth_user_id).filter(Boolean)))await db.query('INSERT INTO auth.users(id) VALUES($1)',[id]);
 const result=await restoreApplication(db,snapshot);
 for(const [table,count]of Object.entries(snapshot.counts)){const [schema,name]=table.split('.');const q='"'+schema.replaceAll('"','""')+'"."'+name.replaceAll('"','""')+'"';const actual=(await db.query('SELECT count(*)::int n FROM '+q)).rows[0].n;if(actual!==count)throw Error('Contagem divergente: '+table);}
 console.log(JSON.stringify({...result,countsVerified:true,scope:'application_database',providerAuthRestored:false,target:resolved}));
}finally{await db.close();}
