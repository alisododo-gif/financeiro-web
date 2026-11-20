export const appManifest={id:'/',name:'FinanceiroPro Web',short_name:'FinanceiroPro',lang:'pt-BR',start_url:'/',scope:'/',display:'standalone',background_color:'#0b111b',theme_color:'#0b111b',icons:[{src:'/static/app-icon-v2-192.png',sizes:'192x192',type:'image/png',purpose:'any'},{src:'/static/app-icon-v2-512.png',sizes:'512x512',type:'image/png',purpose:'any'}]};
// Network-only: never persist private pages, APIs, credentials or financial writes.
export const appServiceWorker=String.raw`
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('fetch',event=>{if(event.request.mode!=='navigate')return;event.respondWith(fetch(event.request).catch(()=>new Response('<!doctype html><html lang="pt-BR"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FinanceiroPro Web</title><body><h1>Você está sem conexão</h1><p>Conecte-se à internet e atualize esta página para acessar suas finanças.</p></body></html>',{headers:{'content-type':'text/html; charset=utf-8','cache-control':'no-store'},status:503})));});
`;
export const mobileAppScript=String.raw`
window.addEventListener('load',()=>{'use strict';
 const app=document.getElementById('app-panel');if(!app)return;
 const dock=document.createElement('nav');dock.className='mobile-dock';dock.setAttribute('aria-label','Atalhos do aplicativo');
 const routes=[['Início','finance-view-btn','⌂'],['Lançar','launch-view-btn','＋'],['Extrato','manage-view-btn','⇄'],['Menu',null,'☰']];
 for(const [label,id,icon]of routes){const b=document.createElement('button');b.type='button';b.dataset.target=id||'';b.setAttribute('aria-label',label);const i=document.createElement('span');i.textContent=icon;i.setAttribute('aria-hidden','true');b.append(i,document.createTextNode(label));b.onclick=()=>{if(id)document.getElementById(id)?.click();else document.querySelector('.mobile-menu-button')?.click();};dock.append(b);}
 document.body.append(dock);
 const sync=()=>{dock.hidden=app.classList.contains('hidden')||app.style.display==='none';for(const b of dock.children){const original=b.dataset.target&&document.getElementById(b.dataset.target);if(original){b.hidden=original.hidden||original.classList.contains('hidden');b.setAttribute('aria-current',original.classList.contains('view-active')?'page':'false');}}};
 new MutationObserver(sync).observe(app,{attributes:true,subtree:true,attributeFilter:['class','hidden','style']});sync();
 document.addEventListener('fp:access-ready',sync);
 let deferred;window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();deferred=event;});
 const install=document.createElement('button');install.type='button';install.textContent='Instalar no celular';install.className='app-install';
 install.onclick=async()=>{if(deferred){await deferred.prompt();deferred=null;return;}const d=document.createElement('dialog');d.className='account-dialog';d.setAttribute('aria-label','Instalar no celular');const h=document.createElement('h2');h.textContent='FinanceiroPro na tela inicial';const p=document.createElement('p');p.textContent='No iPhone: abra no Safari, toque em Compartilhar e em Adicionar à Tela de Início. No Android: abra no Chrome e escolha Instalar aplicativo ou Adicionar à tela inicial no menu.';const close=document.createElement('button');close.type='button';close.textContent='Entendi';close.onclick=()=>d.close();d.append(h,p,close);d.addEventListener('close',()=>d.remove());document.body.append(d);document.dispatchEvent(new Event('fp:close-menu'));d.showModal();};
 const nav=document.querySelector('.sidebar .view-nav');if(nav)nav.insertBefore(install,nav.querySelector('.sidebar-logout'));
 if('serviceWorker' in navigator)navigator.serviceWorker.register('/app-sw.js',{scope:'/'}).catch(()=>{});
},{once:true});`;

