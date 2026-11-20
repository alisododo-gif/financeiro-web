import {html,script,css} from './financeiro.mjs';
const body=html.slice(html.indexOf('<body>')+6,html.indexOf('</body>'));
export const panelScript=`(()=>{'use strict';
const host=document.getElementById('operations-content');
if(!host||host.shadowRoot)return;
const operationsRoot=host.attachShadow({mode:'open'});let navigationQueued=false;
const template=document.createElement('template');
template.innerHTML=${JSON.stringify('<link rel="stylesheet" href="/static/app.css"><link rel="stylesheet" href="/static/financeiro.css"><link rel="stylesheet" href="/static/premium.css">'+body)};
operationsRoot.append(template.content.cloneNode(true));
operationsRoot.querySelector('#module')?.closest('label')?.setAttribute('hidden','');
${script.replaceAll('document.getElementById(id)',"operationsRoot.querySelector('#'+id)").replaceAll('document.querySelectorAll(', 'operationsRoot.querySelectorAll(').replaceAll('new URLSearchParams(location.search)','new URLSearchParams(host.dataset.query)').replace(/\nperform\(load\);\s*$/,'\nperform(async()=>{restoreContext(host.dataset.context,false);await load();restoreContext(host.dataset.context);});\n').replace('controls.forEach(b=>b.disabled=false);','controls.forEach(b=>b.disabled=false);if(navigationQueued){navigationQueued=false;queueMicrotask(()=>host.dispatchEvent(new CustomEvent(\'fp:navigate\')));}')}
host.addEventListener('fp:navigate',()=>{if(busy){navigationQueued=true;return;}const params=new URLSearchParams(host.dataset.query);currentPage=1;searchInput.value='';periodFilter.value=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Cuiaba'}).format(new Date()).slice(0,7);stateFilter.value='';table=Object.hasOwn(modules,params.get('modulo'))?params.get('modulo'):'movimentacoes';isLaunch=params.get('acao')==='lancar';if(table==='vencimentos')stateFilter.value='pending';formVisible=false;$('module').value=table;notify('');perform(async()=>{restoreContext(host.dataset.context,false);await load();restoreContext(host.dataset.context);});});
})();`;

