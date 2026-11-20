import worker from './release/worker.mjs';
import proxy from './pages-proxy.mjs';
import fs from 'node:fs/promises';import path from 'node:path';import crypto from 'node:crypto';import {fileURLToPath} from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
export const staticPaths=[
 '/static/app.js','/static/app.css','/static/financeiropro-logo.webp',
 '/static/financeiro.js','/static/financeiro.css','/static/premium.css','/static/experience.js',
 '/static/parity.js','/static/signup.js','/static/financial-panel.js','/static/production-navigation.js',
 '/static/access.js','/static/mobile-app.js',
 ...[32,180,192,512].map(n=>'/static/app-icon-v2-'+n+'.png'),
 '/manifest.webmanifest','/app-sw.js','/site/styles.css','/site/script.js'
];
export const staticRoutes={version:1,include:['/*'],exclude:['/static/*','/manifest.webmanifest','/app-sw.js','/site/styles.css','/site/script.js']};
export async function buildPagesStatic(outDir=path.join(root,'pages-dist')){
 await fs.mkdir(outDir,{recursive:true});const manifest={},assets=[];
 for(const name of staticPaths){
  const response=await (name.startsWith('/site/')?proxy:worker).fetch(new Request('https://financeiroproweb.pages.dev'+name),{});
  if(response.status!==200||response.headers.has('set-cookie'))throw Error('Asset unavailable or personalized: '+name);
  const buffer=Buffer.from(await response.arrayBuffer());if(!buffer.length)throw Error('Empty asset: '+name);
  const file=path.join(outDir,name.slice(1));await fs.mkdir(path.dirname(file),{recursive:true});await fs.writeFile(file,buffer);
  const key=crypto.createHash('md5').update(buffer).digest('hex');manifest[name]=key;
  assets.push({key,value:buffer.toString('base64'),base64:true,metadata:{contentType:response.headers.get('content-type')||'application/octet-stream'}});
 }
 const headers=`/static/*
  Cache-Control: public, max-age=0, must-revalidate
  X-Financeiro-Delivery: pages-static
  X-Content-Type-Options: nosniff
/manifest.webmanifest
  Cache-Control: public, max-age=300
  X-Financeiro-Delivery: pages-static
/app-sw.js
  Cache-Control: no-cache
  Service-Worker-Allowed: /
  X-Financeiro-Delivery: pages-static
/site/styles.css
  Cache-Control: public, max-age=0, must-revalidate
  X-Financeiro-Delivery: pages-static
/site/script.js
  Cache-Control: public, max-age=0, must-revalidate
  X-Financeiro-Delivery: pages-static
`;
 await fs.writeFile(path.join(outDir,'_routes.json'),JSON.stringify(staticRoutes));
 await fs.writeFile(path.join(outDir,'_headers'),headers);
 await fs.copyFile(path.join(root,'pages-proxy.mjs'),path.join(outDir,'_worker.js'));
 const bundle={manifest,assets,routes:staticRoutes,headers,worker:await fs.readFile(path.join(root,'pages-proxy.mjs'),'utf8')};
 await fs.mkdir(path.join(root,'qa'),{recursive:true});
 await fs.writeFile(path.join(root,'qa/pages-static-upload.json'),JSON.stringify(bundle));
 return {files:assets.length,bytes:assets.reduce((n,a)=>n+Buffer.from(a.value,'base64').length,0),outDir};
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))console.log(JSON.stringify(await buildPagesStatic()));
