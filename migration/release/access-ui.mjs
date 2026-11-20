import {shortcutsUI} from '../shortcuts-ui.mjs';
import {adminLayout,globalDialog} from '../admin-layout.mjs';
export const accessScript=String.raw`
(()=>{'use strict';
const labels={visao_geral:'Visão geral / resumo',novo_lancamento:'Novo lançamento',movimentacoes:'Movimentações',cartoes:'Cartões e faturas',recebimentos:'Recebimentos',vencimentos:'Vencimentos',clientes:'Clientes',contas:'Contas',metas:'Metas',orcamentos:'Orçamentos'};
const nav={'finance-view-btn':'visao_geral','launch-view-btn':'novo_lancamento','manage-view-btn':'movimentacoes','invoices-view-btn':'cartoes','receivables-view-btn':'recebimentos','due-view-btn':'vencimentos','clients-view-btn':'clientes','accounts-view-btn':'contas','goals-view-btn':'metas','budgets-view-btn':'orcamentos'};
const app=document.getElementById('app-panel');if(!app)return;
let access=null,busy=false,adminLoaded=false,selectedUser='';
const node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
const banner=node('article');banner.className='card access-banner';banner.hidden=true;app.prepend(banner);
const lock=node('section');lock.className='access-lock';lock.hidden=true;lock.setAttribute('role','alert');app.before(lock);
function contact(parent,data){const a=node('a','Falar com o administrador');a.href='https://wa.me/'+String(data.contact||'5565992361636').replace(/\D/g,'');a.target='_blank';a.rel='noopener noreferrer';a.className='access-contact';parent.append(a);}
function apply(data){
 access=data;lock.replaceChildren();lock.hidden=data.allowed;app.style.display=data.allowed?'':'none';
 if(!data.allowed){lock.append(node('h1','Seu acesso precisa de liberação'),node('p',data.message));contact(lock,data);const out=node('button','Sair');out.onclick=()=>document.getElementById('logout-btn').click();lock.append(out);}
 for(const [id,module]of Object.entries(nav)){const button=document.getElementById(id);if(button){button.hidden=!data.modules?.[module];button.setAttribute('aria-disabled',String(!data.modules?.[module]));}}
 const active=document.querySelector('.view-nav .view-active'),activeModule=active&&nav[active.id];
 if(data.allowed&&activeModule&&!data.modules?.[activeModule]){
  for(const e of app.querySelectorAll('[id$="-content"]'))e.classList.add('hidden');
  const next=Object.keys(nav).find(id=>data.modules?.[nav[id]]);
  if(next)document.getElementById(next)?.click();
 }
 banner.hidden=!data.allowed||data.mode!=='trial';banner.replaceChildren();
 if(!banner.hidden){banner.append(node('strong','Teste gratuito de 7 dias'),node('p','Disponível até '+new Date(data.expires_at).toLocaleString('pt-BR')+'. Depois, entre em contato para contratar.'));contact(banner,data);}
 document.dispatchEvent(new Event('fp:access-ready'));
}
async function api(data){const r=await fetch('/api/admin/acessos',data?{method:'POST',headers:{'content-type':'application/json','x-financeiro-operacao':'1'},body:JSON.stringify(data)}:{});const j=await r.json();if(!r.ok)throw Error(j.erro||'Não foi possível atualizar.');return j;}
const admin=document.getElementById('admin-content'),panel=node('article');panel.className='card access-admin';
${globalDialog}
if(!admin)return;
${adminLayout}
${shortcutsUI}
const status=node('p');status.setAttribute('role','status');
async function save(data){try{status.textContent='Salvando...';await api(data);await loadAdmin();status.textContent='Acesso atualizado no site e no Telegram.';await refresh();}catch(e){status.textContent=e.message;}}
function fields(values,override=false){const grid=node('div');grid.className='access-options';for(const [key,label]of Object.entries(labels)){const wrap=node('label',label),input=node('select');input.name=key;
 for(const [value,text]of [...(override?[['default','Usar padrão']]:[]),['true','Liberado'],['false','Bloqueado']])input.append(new Option(text,value));
 input.value=Object.hasOwn(values,key)?String(values[key]):override?'default':'true';wrap.append(input);grid.append(wrap);}return grid;}
function readFields(grid){return Object.fromEntries([...grid.querySelectorAll('select')].filter(x=>x.value!=='default').map(x=>[x.name,x.value==='true']));}
async function loadAdmin(){const data=await api();adminLoaded=true;panel.replaceChildren(node('h2','Planos, teste de 7 dias e módulos'),node('p','O padrão vale para todos que não tenham exceções individuais. A liberação após pagamento remove o prazo de teste; o acesso fica ativo até você bloquear. Administradores mantêm acesso completo.'));
 const defaults=fields(data.defaults),defaultButton=node('button','Salvar módulos padrão');defaultButton.type='button';defaultButton.onclick=()=>save({acao:'padrao',dados:{modules:readFields(defaults)}});panel.append(node('h3','Módulos padrão'),defaults,defaultButton);
 const select=node('select');select.setAttribute('aria-label','Usuário para configurar acesso');for(const u of data.users.filter(u=>!u.admin))select.append(new Option(u.usuario+' · '+(u.access.mode==='trial'?'Teste':u.access.mode==='blocked'?'Bloqueado':'Liberado'),String(u.id)));if([...select.options].some(o=>o.value===selectedUser))select.value=selectedUser;
 const detail=node('div');detail.className='access-user';userPanel.replaceChildren(node('h2','Acesso por usuário'),select,detail);admin.append(status);
 function render(){detail.replaceChildren();const u=data.users.find(x=>String(x.id)===select.value);if(!u){detail.append(node('p','Nenhum usuário comum cadastrado.'));return;}
 const a=u.access;detail.append(node('p','Situação: '+(a.allowed?'Acesso ativo':'Acesso bloqueado')+(a.expires_at?' · Teste até '+new Date(a.expires_at).toLocaleString('pt-BR'):a.mode==='licensed'?' · Sem prazo de teste':'')));
 const overrides=fields(a.overrides||{},true),actions=node('div');actions.className='account-actions';
 for(const [text,mode]of [['Liberar após pagamento','licensed'],['Bloquear acesso','blocked']]){const b=node('button',text);b.type='button';b.onclick=async()=>{if(await window.fpDialog(text+' para '+u.usuario+'?'))save({acao:'usuario',id:u.id,dados:{mode,modules:readFields(overrides)}});};actions.append(b);}
 const saveModules=node('button','Salvar módulos deste usuário');saveModules.type='button';saveModules.onclick=()=>save({acao:'usuario',id:u.id,dados:{modules:readFields(overrides)}});
 detail.append(overrides,saveModules,actions);}
 select.addEventListener('change',()=>{selectedUser=select.value;render();});render();}
async function refresh(){if(busy||app.classList.contains('hidden'))return;busy=true;try{const r=await fetch('/api/acesso',{cache:'no-store'});if(r.ok)apply(await r.json());else if(r.status!==401)apply({allowed:false,message:'Não foi possível verificar seu acesso. Atualize a página para tentar novamente.',modules:{}});}catch{apply({allowed:false,message:'Não foi possível verificar seu acesso. Atualize a página para tentar novamente.',modules:{}});}finally{busy=false;}}
document.addEventListener('click',event=>{const b=event.target.closest('button'),module=b&&nav[b.id];if(module&&access&&!access.modules?.[module]){event.preventDefault();event.stopImmediatePropagation();alert('Este módulo não está liberado para sua conta.');}},true);
new MutationObserver(()=>{if(app.classList.contains('hidden')){lock.hidden=true;app.style.display='';access=null;adminLoaded=false;}else refresh();}).observe(app,{attributes:true,attributeFilter:['class']});
if(admin)new MutationObserver(()=>{if(!admin.classList.contains('hidden')&&!adminLoaded)loadAdmin().catch(e=>{panel.textContent=e.message;});}).observe(admin,{attributes:true,attributeFilter:['class']});
document.addEventListener('fp:session-reset',()=>{access=null;adminLoaded=false;lock.hidden=true;app.style.display='';});
window.addEventListener('focus',refresh);setInterval(refresh,60000);refresh();
})();`;

