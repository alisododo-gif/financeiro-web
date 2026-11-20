export const viewStateScript=String.raw`
let navigationOwner=null,restoredFor=null,currentNavigation='finance-view-btn';
const navigationIds=['finance-view-btn','launch-view-btn','manage-view-btn','invoices-view-btn','receivables-view-btn','due-view-btn','clients-view-btn','accounts-view-btn','goals-view-btn','budgets-view-btn','admin-view-btn'];
const emptyNavigation=()=>({view:'finance-view-btn',contexts:{}});
function readNavigation(){try{const s=JSON.parse(sessionStorage.getItem('fp-navigation:'+navigationOwner));return s&&navigationIds.includes(s.view)&&s.contexts&&typeof s.contexts==='object'?s:emptyNavigation();}catch{return emptyNavigation();}}
function rememberNavigation(view,context){if(!navigationOwner)return;const state=readNavigation();state.view=view;if(context)state.contexts[view]=context;try{sessionStorage.setItem('fp-navigation:'+navigationOwner,JSON.stringify(state));}catch{}}
document.addEventListener('fp:context',e=>{if(navigationIds.includes(currentNavigation))rememberNavigation(currentNavigation,e.detail);});
document.addEventListener('fp:access-ready',()=>{const app=document.getElementById('app-panel'),owner=app?.dataset.navigationOwner;if(!owner||app.classList.contains('hidden')||restoredFor===owner)return;navigationOwner=owner;restoredFor=owner;const state=readNavigation(),target=document.getElementById(state.view);if(target&&!target.hidden&&!target.classList.contains('hidden')&&target.getAttribute('aria-disabled')!=='true'){target.click();if(state.view==='finance-view-btn'){for(const key of ['month','year']){const input=document.getElementById(key),v=state.contexts[state.view]?.[key];if(input&&v&&[...input.options].some(o=>o.value===v))input.value=v;}document.getElementById('month')?.dispatchEvent(new Event('change'));}if(state.view==='admin-view-btn'&&/^admin-tab-(clients|plans|users|backup)$/.test(state.contexts[state.view]?.tab||''))document.getElementById(state.contexts[state.view].tab)?.click();}});
document.addEventListener('change',e=>{if(['month','year'].includes(e.target.id))rememberNavigation('finance-view-btn',{month:document.getElementById('month').value,year:document.getElementById('year').value});});
document.addEventListener('click',e=>{const tab=e.target.closest('[role=tab]');if(tab?.id.startsWith('admin-tab-'))rememberNavigation('admin-view-btn',{tab:tab.id});});
`;

