import {viewStateScript} from '../view-state.mjs';
export const navigation=String.raw`
(()=>{'use strict';
const lab=document.getElementById('lab-view-btn');if(lab)lab.classList.add('hidden');
let panel;
${viewStateScript}
document.addEventListener('fp:session-reset',()=>{panel?.remove();panel=null;navigationOwner=null;restoredFor=null;delete document.getElementById('app-panel').dataset.navigationOwner;document.getElementById('operations-script')?.remove();});
const clientNav=document.createElement('button');clientNav.id='clients-view-btn';clientNav.type='button';clientNav.textContent='Clientes';document.querySelector('.view-nav')?.append(clientNav);
const labels={'Movimentações':'movimentacoes','Clientes':'clientes','Contas':'contas','Cartões':'cartoes','Contas a receber':'contas_receber','Metas':'metas','Orçamentos':'orcamentos'};
document.addEventListener('click',event=>{
 const b=event.target.closest('button');if(!b)return;
 if(b.id?.endsWith('-view-btn')||b.id==='logout-btn')document.dispatchEvent(new Event('fp:close-menu'));
 if(navigationIds.includes(b.id)){currentNavigation=b.id;rememberNavigation(b.id);}
 const routes={'due-view-btn':'vencimentos','accounts-view-btn':'contas','goals-view-btn':'metas','budgets-view-btn':'orcamentos','clients-view-btn':'clientes','launch-view-btn':'movimentacoes','manage-view-btn':'movimentacoes','invoices-view-btn':'cartoes','receivables-view-btn':'contas_receber'};
 const module=routes[b.id]||(b.closest('#tabs')?labels[b.textContent.trim()]:null)||(b.textContent.includes('Gerenciar')?'movimentacoes':null);
 if(!module){if(['finance-view-btn','due-view-btn','admin-view-btn'].includes(b.id)){for(const other of document.querySelectorAll('.view-nav button'))other.classList.toggle('view-active',other===b);}if(panel&&['finance-view-btn','due-view-btn','admin-view-btn','logout-btn'].includes(b.id))panel.hidden=true;return;}
 event.preventDefault();event.stopImmediatePropagation();
 const host=document.getElementById('app-panel');if(!host)return;
 for(const el of host.children)if(el.id?.endsWith('-content'))el.classList.add('hidden');
 if(!panel){panel=document.createElement('section');panel.id='operations-content';host.append(panel);}
 panel.classList.remove('hidden');panel.hidden=false;
 for(const btn of host.querySelectorAll('button[id$="-view-btn"]'))btn.classList.toggle('view-active',btn===b);
 panel.dataset.context=JSON.stringify(navigationOwner?readNavigation().contexts[currentNavigation]||{}:{});
 panel.dataset.query='modulo='+module+'&embed=1&acao='+(b.id==='launch-view-btn'?'lancar':'gerenciar');
 if(panel.shadowRoot){panel.dispatchEvent(new CustomEvent('fp:navigate'));}
 else if(!document.getElementById('operations-script')){const script=document.createElement('script');script.id='operations-script';script.src='/static/financial-panel.js';document.head.append(script);}
 panel.scrollIntoView({behavior:'smooth',block:'start'});
},true);
})();
`;

