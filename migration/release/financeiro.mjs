import {tvImportUI} from '../tv-import-ui.mjs';
import {clientShortcutsUI} from '../client-shortcuts-ui.mjs';
import {modalHelpers} from '../modal-ui.mjs';
import {quickLaunchUI} from '../quick-launch-ui.mjs';
import {goalProgress,budgetProgress,receivableTotals,cardBalances,cardMonthRows} from '../legacy-rules.mjs';
import { launchRows } from '../launch.mjs';
import {monthlyRows,monthlyTotals,invoiceState,closingNotice,dueRows,goalAmount} from '../monthly.mjs';
import {reportBrowser} from '../reports.mjs';
import {customerPeriodMatches} from '../customer-period.mjs';
import {createReadCache} from '../read-cache.mjs';
function customerList(rows,query='',state=''){
 const normalize=value=>String(value??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('pt-BR').trim();
 const term=normalize(query);
 return rows.filter(r=>(!term||normalize(r.nome).includes(term))&&(!state||(state==='done'?r.status==='Pago':r.status!=='Pago'))).sort((a,b)=>String(a.nome||'').localeCompare(String(b.nome||''),'pt-BR',{sensitivity:'base'})||Number(a.id)-Number(b.id));
}
const customerListCSS=`
#rows:has(.customer-grid){max-height:none!important;overflow:visible!important}
.customer-list-count{font-size:12px;color:var(--muted,#92a5bf);margin:0 0 12px}
.customer-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,240px),1fr));gap:12px}
.customer-compact{padding:16px;border:1px solid var(--line,#314561);border-radius:12px;background:var(--surface,#142137);min-width:0}
.customer-compact header{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;padding:0;margin:0;background:none;border:0}
.customer-compact h3{font-size:19px;line-height:1.25;overflow-wrap:anywhere;letter-spacing:-.4px;margin:0!important;color:var(--ink,#edf3fb)}
.customer-compact .customer-id{font-size:10px;white-space:nowrap;color:var(--muted,#92a5bf);padding-top:4px}
.customer-compact .customer-phone{font-size:12px;color:var(--muted,#92a5bf);margin:8px 0;overflow-wrap:anywhere}
.customer-facts{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0}
.customer-facts small{display:block;font-size:10px;color:var(--muted,#92a5bf);margin-bottom:4px}
.customer-facts strong{font-size:16px;line-height:1.3}
.customer-compact .customer-status{display:flex;align-items:center;gap:8px;min-height:24px;margin-bottom:10px}
.customer-compact details{margin:5px 0 10px;font-size:11px;color:var(--muted,#92a5bf);overflow-wrap:anywhere}
.customer-compact summary{cursor:pointer;padding:3px 0;font-size:11px}
.customer-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.customer-actions button,.customer-actions a{display:inline-flex;align-items:center;justify-content:center;flex:1 1 70px;min-height:42px;padding:9px 10px!important;font-size:12px!important;margin:0!important;line-height:1.2;border-radius:8px;white-space:normal;text-decoration:none}
.customer-actions a{border:1px solid var(--line,#314561);color:var(--ink,#edf3fb)}
.customer-name-filter{flex:2 1 250px!important}
#rows>.financial-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,240px),1fr));gap:12px;margin:0}
#rows:has(.financial-grid){max-height:none!important;overflow:visible!important}
#rows .financial-compact{padding:14px;border:1px solid var(--line);border-radius:12px;background:var(--surface);min-width:0;margin:0}
#rows .financial-compact header{display:flex;align-items:start;justify-content:space-between;gap:8px;margin:0;padding:0;background:none;border:0}
#rows .financial-compact h3{font-size:16px;line-height:1.3;margin:0 0 8px;overflow-wrap:anywhere;letter-spacing:-.2px}
#rows .financial-compact .record-id{font-size:10px;color:var(--muted);white-space:nowrap}
#rows .financial-compact .record-facts{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:6px 0 8px}
#rows .financial-compact .record-facts small{display:block;font-size:10px;color:var(--muted);margin-bottom:2px}
#rows .financial-compact .record-facts strong{font-size:16px;line-height:1.3}
#rows .financial-compact .record-date{font-size:13px!important}
#rows .financial-compact p{font-size:11px;line-height:1.4;margin:4px 0 8px;color:var(--muted);overflow-wrap:anywhere}
#rows .financial-compact>strong{display:block;font-size:18px;margin:4px 0 8px}
#rows .financial-compact .record-actions{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
#rows .financial-compact .record-actions button{flex:1 1 65px;min-width:0;min-height:38px;font-size:11px;line-height:1.25;padding:7px 8px;margin:0;white-space:normal;border-radius:8px}
#rows .financial-grid>.due-section-title{grid-column:1/-1;margin:10px 0 0;font-size:17px}
@media(max-width:600px){#rows .financial-compact{padding:12px}#rows>.financial-grid{gap:10px}#rows .financial-compact .record-actions button{min-height:40px}}
@media(max-width:600px){.customer-compact{padding:13px}.customer-grid{gap:10px}.customer-compact h3{font-size:18px}.customer-facts{margin:10px 0}.customer-actions{gap:7px;margin-top:10px}}
`;

const RPC='https://hkfyvhthfshnddduckjs.supabase.co/rest/v1/rpc/fp_financeiro_modulo_v1';
const TABLES=['contas','cartoes','movimentacoes','contas_receber','metas','orcamentos','clientes'];
const json=(value,status=200)=>Response.json(value,{status,headers:{'cache-control':'no-store','x-content-type-options':'nosniff','referrer-policy':'no-referrer'}});
export async function handle(request,env){
 const url=new URL(request.url);
 if(request.method!=='POST') return json({erro:'Método não permitido'},405);
 if(request.headers.get('origin')!==url.origin||request.headers.get('x-financeiro-operacao')!=='1') return json({erro:'Origem não autorizada'},403);
 if(!request.headers.get('content-type')?.toLowerCase().startsWith('application/json')) return json({erro:'Envie JSON'},415);
 if(!env.PROD_API?.fetch||!env.SUPABASE_BACKEND_KEY) return json({erro:'Serviço indisponível'},503);
 let stage='sessao';
 try{
  const auth=await env.PROD_API.fetch(new Request('https://financeiropro-migracao-preview.alisododo.workers.dev/api/me',{headers:{cookie:request.headers.get('cookie')||''}}));
  if(!auth.ok) return json({erro:'Entre novamente pelo login legado'},auth.status===401?401:503);
  const user=await auth.json();
  if(!Number.isSafeInteger(Number(user?.id))||Number(user.id)<=0) return json({erro:'Sessão inválida'},403);
  stage='leitura';
  const reader=request.body?.getReader();let size=0;const chunks=[];
  if(reader){while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>8192){await reader.cancel();return json({erro:'Dados muito grandes'},413);}chunks.push(value);}}
  const bytes=new Uint8Array(size);let off=0;for(const c of chunks){bytes.set(c,off);off+=c.length;}
  let input;try{input=JSON.parse(new TextDecoder().decode(bytes));}catch{return json({erro:'JSON inválido'},400);}
  if(!input||Array.isArray(input)||typeof input!=='object'||Object.keys(input).some(k=>!['tabela','acao','id','dados','versao','chave','modulo'].includes(k)))return json({erro:'Campos não permitidos'},400);
  if(!TABLES.includes(input.tabela)||!['listar','criar','lancar','editar','excluir','fatura','quitar_fatura','reabrir_fatura'].includes(input.acao))return json({erro:'Operação inválida'},400);
  if(input.id!==undefined&&(!Number.isSafeInteger(input.id)||input.id<1))return json({erro:'ID inválido'},400);
  if(input.acao!=='listar'&&input.acao!=='fatura'&&!/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(input.chave||''))return json({erro:'Chave inválida'},400);
  if(url.pathname!=='/api/financeiro/operacao')return json({erro:'Rota inexistente'},404);
  if(input.acao==='lancar'){
   if(input.tabela!=='movimentacoes')return json({erro:'Recurso inválido'},400);
   try{input.dados={registros:launchRows(input.dados)};input.acao='criar_lote';}catch(e){return json({erro:e.message},400);}
  }
  if(!['listar','fatura'].includes(input.acao)&&env.FINANCIAL_WRITES_ENABLED!=='true')return json({erro:'Acesso em validação. As gravações serão liberadas após a conferência do novo endereço.'},503);
  stage='banco';
  const response=await fetch(RPC,{method:'POST',redirect:'manual',signal:AbortSignal.timeout(15000),headers:{apikey:env.SUPABASE_BACKEND_KEY,...(env.SUPABASE_BACKEND_KEY.startsWith('eyJ')?{authorization:'Bearer '+env.SUPABASE_BACKEND_KEY}:{}),'content-type':'application/json'},body:JSON.stringify({p_usuario:Number(user.id),p_tabela:input.tabela,p_acao:input.acao,p_id:input.id??null,p_dados:input.dados??{},p_versao:input.versao??null,p_chave:input.chave??null,p_modulo:input.modulo??null})});
  if(!response.ok){const error=await response.json().catch(()=>({}));const status=error.code==='40001'||error.code==='23503'?409:error.code==='42501'?403:error.code==='P0002'?404:['22023','22007','22008','22P02','23502','23514','23505'].includes(error.code)?400:502;
   return json({erro:status===502?'Banco temporariamente indisponível':error.code==='23503'?'O registro tem movimentações associadas. Preserve o histórico.':error.message},status);}
  stage='resposta';
  return json(await response.json());
 }catch(error){console.error('Homologacao request failed',stage,error?.name);return json({erro:'Não foi possível concluir. Código H-'+stage+'. Atualize e tente novamente com a mesma chave.'},502);}
}
export const html=`<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FinanceiroPro Web</title><link rel="stylesheet" href="/static/app.css"><link rel="stylesheet" href="/static/financeiro.css"><script defer src="/static/financeiro.js"></script></head><body><main class="main"><header class="topbar"><img src="/static/financeiropro-logo.webp" width="150" alt="FinanceiroPro"><a href="/app">Dashboard e acesso</a></header><section class="card"><h1>FinanceiroPro Web</h1><p>Gerencie suas receitas, despesas, cartões, recebimentos e planejamento financeiro.</p><label>Módulo<select id="module"></select></label><button id="refresh">Atualizar</button><p id="notice" role="status"></p></section><section class="card"><h2 id="form-title">Novo registro</h2><form id="form"></form><button id="cancel" type="button" hidden>Cancelar edição</button></section><section class="card"><h2>Registros</h2><div class="table-area" id="rows"></div></section></main></body></html>`;
export const css=`[hidden]{display:none!important}body{display:block}.main{max-width:1200px;margin:auto;padding:24px}.topbar{display:flex;justify-content:space-between;align-items:center;gap:20px}.topbar img{object-fit:contain}.card{margin:18px 0;padding:24px}.card h1{font-size:30px}.card h2{font-size:21px}form{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px;align-items:end}form label{display:grid;gap:8px}button{background:#277ad0;color:white;border:1px solid #3894ed;border-radius:8px;padding:10px 16px;cursor:pointer;font:inherit}button:hover{background:#3894ed}button:disabled{opacity:.5;cursor:wait}td button{margin:3px}a{color:#96c8ff}#notice{min-height:24px;color:#9de2ba}table{width:100%;border-collapse:collapse}td,th{padding:12px;text-align:left;border-bottom:1px solid #314561}#rows{overflow:auto}select,input{min-height:42px}${customerListCSS}@media(max-width:600px){.main{padding:12px}.card{padding:18px}.topbar img{width:100px}.card h1{font-size:24px}form{grid-template-columns:1fr}}`;
export const customerStyles=customerListCSS;
export const script=String.raw`
'use strict';
const createReadCache=${createReadCache.toString()};
const readCache=createReadCache();
document.addEventListener('fp:session-reset',()=>readCache.clear());
document.addEventListener('fp:data-changed',()=>readCache.clear());

const customerPeriodMatches=${customerPeriodMatches.toString()};
const customerList=${customerList.toString()};
const monthlyRows=${monthlyRows.toString()};const monthlyTotals=${monthlyTotals.toString()};const invoiceState=${invoiceState.toString()};const closingNotice=${closingNotice.toString()};const dueRows=${dueRows.toString()};
const goalAmount=${goalAmount.toString()};
${reportBrowser}
const goalProgress=${goalProgress.toString()};const budgetProgress=${budgetProgress.toString()};const receivableTotals=${receivableTotals.toString()};
const cardBalances=${cardBalances.toString()};
const cardMonthRows=${cardMonthRows.toString()};
const $=id=>document.getElementById(id);
const modules={vencimentos:'Vencimentos',clientes:'Clientes',contas:'Contas',cartoes:'Cartões e faturas',movimentacoes:'Receitas e despesas',contas_receber:'Recebimentos',metas:'Metas',orcamentos:'Orçamentos'};
const schemas={clientes:[['nome','Nome'],['conta_id','Conta bancária','contas'],['telefone','Telefone com DDD'],['valor','Valor','number'],['data_vencimento','Vencimento','date'],['status','Situa\u00e7\u00e3o',['Pendente','Pago']]],contas:[['nome','Nome'],['saldo','Saldo inicial','number']],cartoes:[['nome_cartao','Nome'],['limite','Limite','number'],['dia_fechamento','Dia de fechamento','day'],['dia_vencimento','Dia de vencimento','day']],movimentacoes:[['descricao','Descrição'],['tipo','Tipo',['Receita','Despesa']],['valor','Valor','number'],['data','Data','date'],['categoria','Categoria'],['forma_pagamento','Pagamento',['Pix','Dinheiro','Cartão de Crédito','Cartão de Débito','Boleto']],['conta_id','Conta','contas'],['cartao_id','Cartão','cartoes'],['tags','Tags']],contas_receber:[['descricao','Descrição'],['valor','Valor','number'],['data_recebimento','Data prevista','date']],metas:[['nome_meta','Nome'],['valor_alvo','Objetivo','number'],['valor_poupado','Poupado','number'],['prazo','Prazo','date']],orcamentos:[['categoria','Categoria (vazio para orçamento geral)'],['limite','Limite','number']]};
let table=(Object.hasOwn(modules,new URLSearchParams(location.search).get('modulo'))?new URLSearchParams(location.search).get('modulo'):'contas'),editing=null,rows=[],accounts=[],cards=[],busy=false,revision=0,pending=null,invoiceCard=null,invoiceSnapshot=null;
const definitions=()=>table==='movimentacoes'&&!editing?[...schemas[table],['modalidade','Modalidade',['Único','Parcelado','Fixo / Recorrente']],['quantidade','Quantidade de parcelas ou meses','day']]:schemas[table];
const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
function notify(t){$('notice').textContent=t;for(const dialog of document.querySelectorAll('dialog[open]')){let status=dialog.querySelector('.modal-status');if(!status){status=node('p');status.className='modal-status';status.setAttribute('role','status');dialog.append(status);}status.textContent=t;}}
${modalHelpers}
${quickLaunchUI}
async function api(x){const payload={...x,modulo:table==='contas_receber'?'recebimentos':table==='movimentacoes'&&isLaunch&&!['editar','excluir'].includes(x.acao)?'novo_lancamento':table};const request=async()=>{const r=await fetch('/api/financeiro/operacao',{method:'POST',credentials:'same-origin',signal:AbortSignal.timeout(30000),headers:{'content-type':'application/json','x-financeiro-operacao':'1'},body:JSON.stringify(payload)});const d=await r.json();if(!r.ok)throw Error(d.erro||'Falha na operação');return d;};return x.acao==='listar'?readCache.read(JSON.stringify(payload),request):request();}
function button(text,action){const b=node('button',text);b.type='button';b.addEventListener('click',()=>perform(action));return b;}
async function perform(action){if(busy)return;busy=true;const controls=[...document.querySelectorAll('button,input,select,textarea')].filter(b=>!b.disabled);controls.forEach(b=>b.disabled=true);try{await action();}catch(e){notify(e.name==='TimeoutError'?'A resposta demorou. Tente novamente; sua operação mantém a mesma chave para evitar duplicidade.':e.message);}finally{busy=false;controls.forEach(b=>b.disabled=false);syncPager();}}
async function mutate(x){const serialized=JSON.stringify(x);if(!pending||pending.serialized!==serialized)pending={serialized,chave:crypto.randomUUID()};const result=await api({...x,chave:pending.chave});pending=null;document.dispatchEvent(new Event('fp:data-changed'));return result;}
const pageParams=new URLSearchParams(location.search);let isLaunch=pageParams.get('acao')==='lancar',formVisible=false;
const canCreate=()=>table!=='vencimentos'&&(table!=='movimentacoes'||isLaunch);
const formCard=$('form').parentElement,formCancel=$('cancel');
const formDialog=node('dialog');formDialog.className='fp-dialog';formDialog.setAttribute('aria-labelledby','form-title');formCard.before(formDialog);formDialog.append(formCard);
// Native validation can otherwise stop submit without an explanation in the dialog.
formDialog.addEventListener('invalid',event=>{const field=event.target;if(field!==formDialog.querySelector('input:invalid,select:invalid,textarea:invalid'))return;const label=field.closest('label');notify('Confira '+(label?.firstChild?.textContent||'o campo').trim()+': '+field.validationMessage);},true);
formDialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();});formDialog.addEventListener('close',()=>{formVisible=false;editing=null;pending=null;$('form').reset();formDialog.querySelector('.modal-status')?.remove();});
document.addEventListener('fp:session-reset',()=>{for(const d of document.querySelectorAll('dialog'))if(d.open)d.close();});
if(pageParams.get('embed')==='1'){$('form').closest('main').querySelector('.topbar').hidden=true;}
const createButton=button('Novo registro',()=>{if(!canCreate())return;formVisible=true;form();});const moduleActions=node('div');moduleActions.className='module-actions';$('refresh').before(moduleActions);moduleActions.append($('refresh'),createButton);
function updateModuleHeading(){clientShortcutButton.hidden=table!=='clientes';const header=$('module').closest('.card');header.querySelector('h1').textContent=table==='movimentacoes'?(isLaunch?'Novo lançamento':'Movimentações'):modules[table];const descriptions={clientes:'Seus clientes, vencimentos e cobranças em um só lugar.',contas:'Acompanhe suas contas e os saldos cadastrados.',cartoes:'Consulte limites, compras e a situação de cada fatura.',movimentacoes:isLaunch?'Registre entradas e saídas com os valores do mês selecionado.':'Confira seu extrato e exporte os relatórios do mês.',contas_receber:'Organize valores a receber e acompanhe as confirmações.',vencimentos:'Veja os compromissos do mês e o que ainda precisa ser pago.',metas:'Acompanhe seus objetivos e a evolução dos valores guardados.',orcamentos:'Defina limites e acompanhe os gastos por categoria.'};header.querySelector('p').textContent=descriptions[table]||'';}
function form(record=null){updateModuleHeading();createButton.hidden=!canCreate();tvButton.hidden=table!=='clientes'||!tvEnabled;formCard.hidden=!(record||(formVisible&&canCreate()));editing=record;pending=null;$('form').replaceChildren();$('form-title').textContent=record?'Editar registro':'Novo registro';formCancel.hidden=false;formCancel.textContent='Cancelar';if(!formCard.hidden){if(!formDialog.open)formDialog.showModal();}else if(formDialog.open)formDialog.close();
 quickLaunchAbort.abort();quickLaunchAbort=new AbortController();$('form').noValidate=false;$('form').classList.remove('quick-launch');
 createButton.textContent=table==='movimentacoes'&&isLaunch?'Adicionar lançamento':'Novo registro';
 for(const [key,label,type] of (table==='vencimentos'?[]:definitions())){const wrap=node('label',label);let input;
 if(Array.isArray(type)||type==='contas'||type==='cartoes'){input=node('select');const opts=Array.isArray(type)?type.map(v=>[v,v]):(type==='contas'?accounts:cards).map(r=>[r.id,r.nome||r.nome_cartao]);if(!Array.isArray(type))input.append(new Option('Selecione',''));for(const [v,t]of opts)input.append(new Option(t,v));}
 else{input=node('input');input.type=type==='number'||type==='day'?'number':type||'text';if(type==='number'){input.step='0.01';input.max='1000000';input.min=key==='saldo'?'-1000000':'0';}if(type==='day'){input.step='1';input.min='1';input.max='31';}if(type==='date'){input.min='2020-01-01';input.max='2099-12-31';}if(input.type==='text')input.maxLength=240;}
 input.name=key;if(key==='quantidade')input.max=72;input.value=record?.[key]??(key==='quantidade'?1:type==='number'?0:type==='date'?new Intl.DateTimeFormat('en-CA',{timeZone:'America/Cuiaba'}).format(new Date()):Array.isArray(type)?type[0]:'');input.required=!['tags','conta_id','cartao_id','data_vencimento'].includes(key)&&!(table==='orcamentos'&&key==='categoria');if(key==='telefone'&&record?.referencia_tv){input.required=false;input.placeholder='Preencha para habilitar a cobrança';}wrap.append(input);$('form').append(wrap);}
 if(record&&table==='clientes'){const reference=node('p','ID FinanceiroPro: '+record.id+(record.referencia_tv?' · TV: '+record.referencia_tv.usuario+' · Origem: '+record.referencia_tv.id:''));reference.className='muted';$('form').prepend(reference);}
 const submit=node('button',record?'Salvar edição':'Cadastrar');submit.type='submit';const formActions=node('div');formActions.className='account-actions';formActions.append(formCancel,submit);$('form').append(formActions);
 if(table==='movimentacoes'){
  const payment=$('form').elements.namedItem('forma_pagamento'),mode=$('form').elements.namedItem('modalidade');
  const fixedLabel=node('label','Repetição do fixo'),fixedChoice=node('select'),hint=node('p');fixedChoice.append(new Option('Único','single'),new Option('Parcelado / mensal','multiple'));fixedLabel.append(fixedChoice);hint.className='muted';hint.setAttribute('aria-live','polite');if(mode){formActions.before(fixedLabel,hint);}
  const sync=()=>{const credit=payment.value==='Cart\u00e3o de Cr\u00e9dito';for(const [key,visible]of [['cartao_id',credit],['conta_id',!credit]]){const field=$('form').elements.namedItem(key);field.parentElement.hidden=!visible;field.required=visible;}if(mode){const count=$('form').elements.namedItem('quantidade'),fixed=mode.value==='Fixo / Recorrente',single=mode.value==='\u00danico'||fixed&&fixedChoice.value==='single';fixedLabel.hidden=!fixed;count.parentElement.hidden=single;count.min=single?1:2;count.max=mode.value==='Parcelado'?72:60;if(single)count.value=1;else if(Number(count.value)<2)count.value=2;count.parentElement.firstChild.textContent=fixed?'Quantidade de parcelas mensais':'Quantidade de parcelas';const value=$('form').elements.namedItem('valor');value.parentElement.firstChild.textContent=mode.value==='Parcelado'?'Valor total':fixed?'Valor de cada parcela':'Valor';const n=Number(count.value),v=Number(value.value),parcel=mode.value==='Parcelado',cents=Math.round(v*100),each=parcel&&n>0?Math.floor(cents/n)/100:v,maxEach=parcel&&cents%n?(Math.round(each*100)+1)/100:each;hint.textContent=fixed?'O valor se repete inteiro em cada parcela. ':mode.value==='Parcelado'?'O valor total é dividido entre as parcelas. ':'';if(n>0&&v>0)hint.textContent+=n+' lançamento(s) de '+money(each)+(maxEach>each?' a '+money(maxEach):'')+' · Total: '+money(parcel?cents/100:Math.round(each*100)*n/100);}};
  payment.addEventListener('change',sync);mode?.addEventListener('change',sync);fixedChoice.addEventListener('change',sync);$('form').elements.namedItem('quantidade')?.addEventListener('input',sync);$('form').elements.namedItem('valor').addEventListener('input',sync);sync();
  if(!record&&isLaunch){$('form-title').textContent='Novo lançamento';simplifyLaunch($('form'),formActions,submit,fixedLabel,fixedChoice,hint);}
 }

}
const searchLabel=node('label','Buscar registros');const searchInput=node('input');searchInput.type='search';searchInput.placeholder='Buscar por descri\u00e7\u00e3o, telefone ou ID';searchLabel.append(searchInput);searchInput.addEventListener('input',()=>{currentPage=1;display();});
const listFilters=node('div');listFilters.className='list-filters';$('rows').before(listFilters);
searchLabel.firstChild.textContent='Buscar cliente por nome';searchInput.placeholder='Digite o nome do cliente';searchInput.setAttribute('aria-label','Buscar cliente por nome');searchLabel.className='customer-name-filter';listFilters.append(searchLabel);
const periodLabel=node('label','Per\u00edodo'),periodFilter=node('input');periodFilter.type='month';periodFilter.value=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Cuiaba'}).format(new Date()).slice(0,7);periodLabel.append(periodFilter);listFilters.append(periodLabel);
const stateLabel=node('label','Situa\u00e7\u00e3o'),stateFilter=node('select');for(const [v,t]of [['','Todas'],['pending','Pendentes'],['done','Pagos / recebidos']])stateFilter.append(new Option(t,v));stateLabel.append(stateFilter);listFilters.append(stateLabel);
if(table==='vencimentos')stateFilter.value='pending';
const clearFilters=button('Limpar filtros',()=>{searchInput.value='';periodFilter.value=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Cuiaba'}).format(new Date()).slice(0,7);stateFilter.value=table==='vencimentos'?'pending':'';currentPage=1;return load();});listFilters.append(clearFilters);
periodFilter.addEventListener('change',()=>{currentPage=1;perform(load);});
stateFilter.addEventListener('change',()=>{currentPage=1;display();});
const money=value=>new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}).format(value||0);
let currentPage=1,filteredCount=0,budgetMovements=[];
const pageSize=25,summaryCard=node('section');summaryCard.className='module-summary';formDialog.before(summaryCard);
const summaryMonth=node('input');summaryMonth.type='month';summaryMonth.value=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Cuiaba'}).format(new Date()).slice(0,7);
const pager=node('div');pager.className='pager';const pageLabel=node('span');
const cardFilter=node('select');cardFilter.id='card-filter';
const selectedCards=()=>rows.filter(r=>!cardFilter.value||String(r.id)===cardFilter.value);
cardFilter.addEventListener('change',()=>{currentPage=1;closeInvoice();invoiceSnapshot=null;display();});
summaryMonth.addEventListener('change',()=>{currentPage=1;closeInvoice();invoiceSnapshot=null;perform(load);});
const previousPage=button('Anterior',()=>{currentPage--;display();}),nextPage=button('Próxima',()=>{currentPage++;display();});pager.append(previousPage,pageLabel,nextPage);$('rows').after(pager);
function syncPager(){const pages=Math.max(1,Math.ceil(filteredCount/pageSize));previousPage.disabled=currentPage<=1;nextPage.disabled=currentPage>=pages;pageLabel.textContent=filteredCount+' registros · Página '+currentPage+' de '+pages;pager.hidden=filteredCount===0;}
function renderSummary(){searchLabel.hidden=table!=='clientes';listFilters.insertBefore(periodLabel,stateLabel);periodLabel.hidden=!['movimentacoes','contas_receber','vencimentos'].includes(table);stateLabel.hidden=!['movimentacoes','contas_receber','clientes','vencimentos'].includes(table);summaryCard.replaceChildren();const metrics=node('div');metrics.className='summary-metrics';
 const metric=(label,value)=>{const item=node('article');item.className='summary-metric';item.dataset.tone=/pendente/i.test(label)?'warning':/despesa|gasto/i.test(label)?'expense':/receita|recebido|disponível|saldo/i.test(label)?'income':'info';item.append(node('small',label),node('strong',value));metrics.append(item);};
 if(table==='contas_receber'){const t=receivableTotals(rows);metric('Pendente',money(t.pending));metric('Recebido',money(t.received));metric('Total cadastrado',money(t.total));}
 else if(table==='clientes'){metric('Clientes',rows.length);metric('Pendentes',rows.filter(r=>r.status!=='Pago').length);metric('Valor cadastrado',money(rows.reduce((s,r)=>s+Number(r.valor||0),0)));}
 else if(table==='contas'){metric('Contas cadastradas',rows.length);metric('Saldos informados',money(rows.reduce((s,r)=>s+Number(r.saldo||0),0)));}
 else if(table==='movimentacoes'){const totals=monthlyTotals(rows,periodFilter.value);metric('Receitas do mês',money(totals.income));metric('Despesas do mês',money(totals.expense));metric('Pendentes no mês',totals.pending);}
 else if(table==='cartoes'){const totals=selectedCards().map(r=>cardBalances(r,budgetMovements,summaryMonth.value));metric('Limite total',money(totals.reduce((s,r)=>s+r.limit,0)));metric('Gasto no mês da fatura',money(totals.reduce((s,r)=>s+r.spent,0)));metric('Limite disponível',money(totals.reduce((s,r)=>s+r.available,0)));}
 summaryCard.append(metrics);
 if(table==='contas'){
  const grid=node('div');grid.className='planning-grid';
  for(const row of rows){const card=node('article');card.className='planning-card account-card';card.append(node('h3',row.nome),node('p','Saldo informado'),node('strong',money(row.saldo)));const actions=node('div');actions.className='card-actions';const remove=button('Excluir',async()=>{if(!await ask('Excluir a conta '+row.nome+'? Contas com movimentações vinculadas não podem ser excluídas.'))return;await mutate({tabela:'contas',acao:'excluir',id:row.id,versao:row._versao});await load();notify('Conta excluída.');});remove.className='outlined card-delete';actions.append(button('Editar',()=>form(row)),remove);card.append(actions);grid.append(card);}
  summaryCard.append(rows.length?grid:node('p','Nenhuma conta cadastrada. Use Novo registro para adicionar uma conta.'));
 }
 if(table==='movimentacoes'&&isLaunch)summaryCard.prepend(periodLabel);
 if(table==='cartoes')renderCards();
 if(table==='cartoes'){const label=node('label','Mês da fatura');label.className='summary-month';label.append(summaryMonth);summaryCard.prepend(label);summaryCard.append(node('p','O gasto corresponde à competência escolhida. O limite disponível desconta todas as compras pendentes, inclusive parcelas futuras, e é liberado com o pagamento.'));}
 if(table==='metas'||table==='orcamentos'){
  if(table==='orcamentos'){const label=node('label','Mês de acompanhamento');label.className='summary-month';label.append(summaryMonth);summaryCard.append(label);}
  const grid=node('div');grid.className='planning-grid';
  for(const row of rows){const progress=table==='metas'?goalProgress(row):budgetProgress(row,budgetMovements,summaryMonth.value);const card=node('article');card.className='planning-card';const bar=node('progress');bar.max=1;bar.value=progress.progress;
   card.append(node('h3',row.nome_meta||row.categoria||'Orçamento geral'));
   card.append(node('strong',money(table==='metas'?progress.saved:progress.spent)),node('span',' de '+money(table==='metas'?progress.target:progress.limit)),bar);
   const text=table==='metas'?(progress.remaining>0?'Faltam '+money(progress.remaining):'Objetivo alcançado'):(progress.status==='excedido'?'Limite excedido em '+money(-progress.remaining):progress.status==='atencao'?'Atenção: restam '+money(progress.remaining):'Disponível: '+money(progress.remaining));const note=node('p',text);if(progress.status)note.dataset.state=progress.status;card.append(note,button('Editar',()=>form(row)));if(table==='orcamentos')card.append(button('Excluir',async()=>{if(!await ask('Excluir o orçamento '+(row.categoria||'geral')+'?'))return;await mutate({tabela:'orcamentos',acao:'excluir',id:row.id,versao:row._versao});await load();notify('Orçamento excluído.');}));grid.append(card);
   if(table==='metas'){for(const [text,direction]of [['Depositar',1],['Resgatar',-1]])card.append(button(text,async()=>{const entered=await askAmount(text+' · '+row.nome_meta);if(entered===null)return;const value=goalAmount(row.valor_poupado,entered,direction);await mutate({tabela:'metas',acao:'editar',id:row.id,dados:{valor_poupado:value},versao:row._versao});await load();notify('Progresso da meta atualizado.');}));card.append(button('Excluir',async()=>{if(!await ask('Excluir a meta '+row.nome_meta+'?'))return;await mutate({tabela:'metas',acao:'excluir',id:row.id,versao:row._versao});await load();notify('Meta excluída.');}));}
  }summaryCard.append(grid);
  if(table==='orcamentos')summaryCard.append(node('p','O acompanhamento usa a data das despesas, inclusive pendentes, conforme a regra original.'));
 }
}

function renderCards(){
 const controls=node('div');controls.className='list-filters';const label=node('label','Cartão');label.append(cardFilter);controls.append(label);summaryCard.prepend(controls);
 const grid=node('div');grid.className='planning-grid';
 for(const row of selectedCards()){
  const totals=cardBalances(row,budgetMovements,summaryMonth.value),card=node('article');card.className='planning-card';card.append(node('h3',row.nome_cartao),node('p','Limite total: '+money(totals.limit)),node('p','Gasto no mês: '+money(totals.spent)),node('strong','Disponível: '+money(totals.available)),node('p','Fecha '+row.dia_fechamento+' · Vence '+row.dia_vencimento));
  const state=invoiceState(row,budgetMovements,summaryMonth.value),badge=node('p','Fatura: '+state.status+' · Pendente: '+money(state.pending));badge.className='invoice-state';badge.dataset.state=state.status;const closing=node('p',closingNotice(row,summaryMonth.value));closing.className='closing-notice';card.append(badge,closing);
  card.append(button('Editar cartão',()=>form(row)),button('Excluir cartão',async()=>{if(!await ask('Excluir o cartão '+row.nome_cartao+'?'))return;await mutate({tabela:'cartoes',acao:'excluir',id:row.id,versao:row._versao});await load();notify('Cartão excluído.');}),button('Consultar / quitar fatura',async()=>{invoiceCard=row;invoiceSnapshot=null;openInvoice();invoiceMonth.value=summaryMonth.value;await consultInvoice();}));grid.append(card);
 }const details=node('details');details.open=true;details.append(node('summary','Gerenciar cartões'),grid);summaryCard.append(details);
}
function displayCardRecords(){
 const query=searchInput.value.trim().toLocaleLowerCase('pt-BR');
 const records=cardMonthRows(rows,budgetMovements,summaryMonth.value,cardFilter.value).filter(r=>!query||[r.id,r.descricao,r.categoria,rows.find(c=>Number(c.id)===Number(r.cartao_id))?.nome_cartao].some(v=>String(v??'').toLocaleLowerCase('pt-BR').includes(query))).sort((a,b)=>String(b.data).localeCompare(String(a.data))||Number(b.id)-Number(a.id));
 filteredCount=records.length;currentPage=Math.max(1,Math.min(currentPage,Math.ceil(filteredCount/pageSize)||1));
 const grid=node('table'),head=node('tr');for(const title of ['Data','Cartão','Descrição','Valor','Categoria','Situação','Ações'])head.append(node('th',title));grid.append(head);
 for(const row of records.slice((currentPage-1)*pageSize,currentPage*pageSize)){const tr=node('tr');for(const value of [String(row.data||'').split('-').reverse().join('/'),rows.find(c=>Number(c.id)===Number(row.cartao_id))?.nome_cartao||'Cartão',row.descricao,money(row.valor),row.categoria||'—',row.pago?'Pago':'Pendente'])tr.append(node('td',value));const actions=node('td');actions.append(button('Editar compra',()=>editInvoiceItem(row)),button('Excluir compra',()=>deleteInvoiceItem(row)));tr.append(actions);grid.append(tr);}
 labelTable(grid);$('rows').replaceChildren(records.length?grid:node('p','Nenhum lançamento na fatura do mês e cartão selecionados.'));syncPager();
}
function labelTable(grid){const labels=[...grid.querySelectorAll('th')].map(e=>e.textContent);for(const row of grid.querySelectorAll('tr'))[...row.querySelectorAll('td')].forEach((td,i)=>td.dataset.label=labels[i]||'Ações');}
function displayCustomers(){
 const selected=customerList(rows,searchInput.value,stateFilter.value),grid=node('div');grid.className='customer-grid';
 filteredCount=selected.length;currentPage=Math.max(1,Math.min(currentPage,Math.ceil(filteredCount/pageSize)||1));
 for(const r of selected.slice((currentPage-1)*pageSize,currentPage*pageSize)){
  const card=node('article');card.className='customer-compact';const head=node('header'),name=node('h3',r.nome),id=node('small','ID '+r.id);id.className='customer-id';head.append(name,id);card.append(head);
  const phone=node('p',r.telefone||'Telefone não informado');phone.className='customer-phone';card.append(phone);
  const facts=node('div');facts.className='customer-facts';for(const [label,value]of [['Valor',money(r.valor)],['Vencimento',r.data_vencimento?String(r.data_vencimento).split('-').reverse().join('/'):'Sem data']]){const item=node('div');item.append(node('small',label),node('strong',value));facts.append(item);}card.append(facts);
  const status=node('div');status.className='customer-status';const badge=node('span',r.status||'Pendente');badge.className='status-pill'+(r.status==='Pago'?' paid':'');status.append(badge);card.append(status);
  if(r.referencia_tv){const source=node('details');source.append(node('summary','Origem TV'),node('span',r.referencia_tv.usuario+' · '+r.referencia_tv.id));card.append(source);}
  const actions=node('div');actions.className='customer-actions';actions.append(button('Editar',()=>form(r)),button('Excluir',async()=>{if(!await ask('Excluir '+r.nome+'?'))return;await mutate({tabela:'clientes',acao:'excluir',id:r.id,versao:r._versao});await load();notify('Cliente excluído.');}));
  if(r.telefone&&r.status!=='Pago'){const link=node('a','WhatsApp'),digits=String(r.telefone).replace(/\D/g,'');link.href='https://wa.me/'+([10,11].includes(digits.length)?'55'+digits:digits)+'?text='+encodeURIComponent('Olá, '+r.nome+'! Seu pagamento de '+money(r.valor)+' está pendente. Podemos confirmar?');link.target='_blank';link.rel='noopener noreferrer';link.setAttribute('aria-label','Preparar cobrança de '+r.nome+' no WhatsApp');actions.append(link);}card.append(actions);grid.append(card);
 }
 const range=selected.length?' · Exibindo '+((currentPage-1)*pageSize+1)+'–'+Math.min(currentPage*pageSize,selected.length):'';const count=node('p',selected.length+' de '+rows.length+' clientes'+range);count.className='customer-list-count';count.setAttribute('role','status');$('rows').replaceChildren(count,selected.length?grid:node('p','Nenhum cliente encontrado para os filtros selecionados.'));syncPager();
}
function compactRecordCards(tableGrid){
 const grid=node('div');grid.className='financial-grid';
 for(const tr of tableGrid.querySelectorAll('tr')){
  const cells=[...tr.querySelectorAll('td')];if(!cells.length)continue;
  const movement=table==='movimentacoes',card=node('article'),head=node('header');card.className='financial-compact';
  const title=node('h3',cells[movement?2:1].textContent),id=node('small','ID '+cells[0].textContent);id.className='record-id';head.append(title,id);card.append(head);
  const facts=node('div');facts.className='record-facts';
  for(const [label,value,isDate]of [['Valor',cells[movement?4:2].textContent,false],[movement?'Data':'Previsão',cells[movement?1:3].textContent,true]]){const item=node('div'),valueNode=node('strong',value);if(isDate)valueNode.className='record-date';item.append(node('small',label),valueNode);facts.append(item);}card.append(facts);
  if(movement){const detail=[cells[3].textContent,cells[5].textContent];if(cells[6].textContent!=='—')detail.push('Fatura '+cells[6].textContent);card.append(node('p',detail.join(' · ')));}
  const status=cells[movement?7:4],actions=node('div');actions.className='record-actions';card.append(...status.childNodes);actions.append(...cells.at(-1).childNodes);card.append(actions);grid.append(card);
 }
 return grid;
}
function compactDueCards(grid){grid.classList.add('financial-grid');for(const card of grid.querySelectorAll('article')){card.classList.add('financial-compact');const actions=node('div');actions.className='record-actions';actions.append(...card.querySelectorAll('button'));card.append(actions);}return grid;}
function display(){
 $('rows').closest('.card').hidden=['orcamentos','metas','contas','cartoes'].includes(table);
 renderSummary();reportControls.hidden=table!=='movimentacoes'||isLaunch;
 if(['orcamentos','metas','contas','cartoes'].includes(table)){$('rows').replaceChildren();filteredCount=0;syncPager();return;}
 if(table==='vencimentos'){displayDue();return;}
 if(table==='clientes'){displayCustomers();return;}
 const query=searchInput.value.trim().toLocaleLowerCase('pt-BR');
 const filtered=rows.filter(r=>customerPeriodMatches(table,r,periodFilter.value)&&(!stateFilter.value||(stateFilter.value==='done'?Boolean(r.pago||r.recebido||r.status==='Pago'):!r.pago&&!r.recebido&&r.status!=='Pago'))).filter(r=>!query||[r.id,r.descricao,r.nome,r.nome_cartao,r.nome_meta,r.categoria,r.tags,r.forma_pagamento,r.data,r.data_recebimento,r.telefone].some(v=>String(v??'').toLocaleLowerCase('pt-BR').includes(query))).sort((a,b)=>String(b.data||b.data_recebimento||b.data_vencimento||'').localeCompare(String(a.data||a.data_recebimento||a.data_vencimento||''))||Number(b.id)-Number(a.id));
 filteredCount=filtered.length;currentPage=Math.max(1,Math.min(currentPage,Math.ceil(filteredCount/pageSize)||1));
 const grid=node('table'),head=node('tr');
 const headers=table==='clientes'?['ID','Nome','Telefone','Valor','Vencimento','Situa\u00e7\u00e3o','A\u00e7\u00f5es']:table==='movimentacoes'?['ID','Data','Descri\u00e7\u00e3o','Tipo','Valor','Pagamento','Fatura','Situa\u00e7\u00e3o','A\u00e7\u00f5es']:table==='contas_receber'?['ID','Descri\u00e7\u00e3o','Valor','Previs\u00e3o','Situa\u00e7\u00e3o','A\u00e7\u00f5es']:['ID','Descri\u00e7\u00e3o','Valor','Situa\u00e7\u00e3o','A\u00e7\u00f5es'];
 for(const title of headers)head.append(node('th',title));grid.append(head);
 if(table==='cartoes'){head.replaceChildren();for(const title of ['Cartão','Limite total','Gasto no mês','Limite disponível','Fechamento / vencimento','Ações'])head.append(node('th',title));}
 const date=value=>value?String(value).split('-').reverse().join('/'):'Sem data';
 for(const r of filtered.slice((currentPage-1)*pageSize,currentPage*pageSize)){
 const tr=node('tr');let values;
 if(table==='clientes')values=[r.id,r.nome,r.telefone,money(r.valor),date(r.data_vencimento),r.status||'Pendente'];
 else if(table==='movimentacoes')values=[r.id,date(r.data),r.descricao,r.tipo,money(r.valor),r.forma_pagamento,r.forma_pagamento==='Cartão de Crédito'?(r.mes_fatura||'—'):'—',r.pago?'Pago':'Pendente'];
 else if(table==='contas_receber')values=[r.id,r.descricao,money(r.valor),date(r.data_recebimento),r.recebido?'Recebido':'Pendente'];
 else values=[r.id,r.descricao||r.nome||r.nome_cartao||r.nome_meta||r.categoria||'Geral',money(r.valor??r.saldo??r.limite??r.valor_alvo??0),table==='cartoes'?'Fecha '+r.dia_fechamento+' \u00b7 Vence '+r.dia_vencimento:''];
 if(table==='cartoes'){const totals=cardBalances(r,budgetMovements,summaryMonth.value);values=[r.nome_cartao,money(totals.limit),money(totals.spent),money(totals.available),'Fecha '+r.dia_fechamento+' · Vence '+r.dia_vencimento];}
 values.forEach((value,index)=>{const td=node('td');if(table==='clientes'&&index===1)td.className='customer-name';if(index===values.length-1&&['Pago','Recebido','Pendente'].includes(value)){const badge=node('span',value);badge.className='status-pill'+(value==='Pendente'?'':' paid');td.append(badge);}else td.textContent=value;if(table==='clientes'&&index===1&&r.referencia_tv){const ref=node('small','TV: '+r.referencia_tv.usuario+' · '+r.referencia_tv.id);ref.className='customer-source';td.append(ref);}tr.append(td);});
 const actions=node('td');actions.append(button('Editar',()=>form(r)),button('Excluir',async()=>{if(!await ask('Excluir '+(r.nome||r.descricao||r.nome_meta||r.categoria||'este registro')+'?'))return;await mutate({tabela:table,acao:'excluir',id:r.id,versao:r._versao});await load();notify('Registro excluído.');}));
 if(table==='movimentacoes'||table==='contas_receber'){const field=table==='movimentacoes'?'pago':'recebido';actions.append(button(r[field]?'Desfazer baixa':field==='pago'?'Marcar pago':'Marcar recebido',async()=>{if(!await ask((r[field]?'Desfazer a baixa de ':'Confirmar '+(field==='pago'?'pagamento de ':'recebimento de '))+(r.descricao||r.nome||'este registro')+'?'))return;await mutate({tabela:table,acao:'editar',id:r.id,dados:{[field]:!r[field]},versao:r._versao});await load();notify('Situação atualizada.');}));}
 if(table==='cartoes')actions.append(button('Consultar / quitar fatura',async()=>{invoiceCard=r;invoiceSnapshot=null;openInvoice();invoiceMonth.value=summaryMonth.value;await consultInvoice();}));
 if(table==='clientes'&&r.telefone&&r.status!=='Pago'){const link=node('a','Preparar cobrança no WhatsApp'),digits=String(r.telefone).replace(/\D/g,'');link.href='https://wa.me/'+([10,11].includes(digits.length)?'55'+digits:digits)+'?text='+encodeURIComponent('Olá, '+r.nome+'! Seu pagamento de '+money(r.valor)+' está pendente. Podemos confirmar?');link.target='_blank';link.rel='noopener noreferrer';link.className='customer-charge-link';actions.append(link);}
 tr.append(actions);grid.append(tr);}
labelTable(grid);if(filteredCount===0){const empty=node('p','Nenhum registro encontrado.');empty.className='empty-state';$('rows').replaceChildren(empty);}else $('rows').replaceChildren(['movimentacoes','contas_receber'].includes(table)?compactRecordCards(grid):grid);syncPager();}

const reportControls=node('div');reportControls.className='report-actions';
function downloadReport(kind){rememberContext();const month=periodFilter.value;if(!month)throw Error('Selecione o mês do relatório.');const bytes=kind==='pdf'?createMonthlyPDF(rows,month,{accounts,cards}):createMonthlyXLSX(rows,month,{accounts,cards}),blob=new Blob([bytes],{type:kind==='pdf'?'application/pdf':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}),url=URL.createObjectURL(blob),link=node('a');link.href=url;link.download='FinanceiroPro-Web-'+month+'.'+kind;link.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
reportControls.append(button('Relatório mensal PDF',()=>downloadReport('pdf')),button('Relatório mensal Excel',()=>downloadReport('xlsx')));listFilters.after(reportControls);
function displayDue(){
 const month=periodFilter.value,items=dueRows(rows,month),query=searchInput.value.trim().toLocaleLowerCase('pt-BR'),grid=node('div');grid.className='planning-grid';
 const debtCards=[];
 for(const c of cards){const state=invoiceState(c,rows,month);if(!state.count)continue;debtCards.push({card:c,pago:state.pending===0,state});}
 let count=0;
 for(const paid of [false,true]){
  const bills=items.filter(r=>Boolean(r.pago)===paid&&(!query||String(r.descricao||'').toLocaleLowerCase('pt-BR').includes(query))),invoices=debtCards.filter(r=>r.pago===paid&&(!query||r.card.nome_cartao.toLocaleLowerCase('pt-BR').includes(query)));
  if((stateFilter.value==='pending'&&paid)||(stateFilter.value==='done'&&!paid)||!bills.length&&!invoices.length)continue;
  const heading=node('h2',paid?'Pagos':'Pendentes');heading.className='due-section-title';grid.append(heading);
  for(const entry of invoices){count++;const card=node('article');card.className='planning-card';card.append(node('h3',entry.card.nome_cartao),node('strong',money(paid?entry.state.total:entry.state.pending)),node('p','Fatura: '+entry.state.status),node('p','Vencimento: dia '+entry.card.dia_vencimento));card.append(button(paid?'Consultar fatura paga':'Consultar fatura',async()=>{invoiceCard=entry.card;openInvoice();invoiceMonth.value=month;await consultInvoice();}),button(paid?'Desfazer pagamento':'Registrar pagamento',()=>changeDueInvoice(entry.card,month,paid)));grid.append(card);}
  for(const r of bills){count++;const card=node('article');card.className='planning-card';card.append(node('h3',r.descricao),node('strong',money(r.valor)),node('p','Data financeira / vencimento: '+String(r.data).split('-').reverse().join('/')),node('p',(r.forma_pagamento||'')+' · '+(paid?'Pago':'Pendente')));
   card.append(button(paid?'Desfazer pagamento':'Registrar pagamento',async()=>{if(!await ask((paid?'Desfazer':'Confirmar')+' o pagamento de '+r.descricao+'?'))return;await mutate({tabela:'movimentacoes',acao:'editar',id:r.id,dados:{pago:!paid},versao:r._versao});await load();notify(paid?'Pagamento desfeito.':'Pagamento registrado.');}));grid.append(card);
  }
 }
 $('rows').replaceChildren(count?compactDueCards(grid):node('p','Nenhum vencimento para os filtros selecionados.'));filteredCount=0;syncPager();
}

async function changeDueInvoice(card,month,paid){const competencia=month.slice(5,7)+'/'+month.slice(0,4);const snapshot=await api({tabela:'cartoes',acao:'fatura',id:card.id,dados:{competencia}});if(!snapshot.registros.length||paid&&snapshot.registros.some(r=>!r.pago)||!paid&&snapshot.registros.every(r=>r.pago))throw Error('A situação da fatura mudou. Atualize a tela.');if(!await ask((paid?'Desfazer o pagamento':'Registrar o pagamento')+' da fatura de '+card.nome_cartao+' · '+competencia+'?'))return;await mutate({tabela:'cartoes',acao:paid?'reabrir_fatura':'quitar_fatura',id:card.id,dados:{competencia},versao:snapshot._versao});await load();notify(paid?'Pagamento da fatura desfeito.':'Pagamento da fatura registrado.');}
async function load(){updateModuleHeading();summaryCard.hidden=true;listFilters.hidden=true;reportControls.hidden=true;pager.hidden=true;$('rows').closest('.card').hidden=false;$('rows').replaceChildren(node('p','Carregando registros...'));const serial=++revision;const selected=table==='vencimentos'?'movimentacoes':table;const needsRefs=['movimentacoes','vencimentos'].includes(table);const reads=new Map();const read=name=>{const month=['cartoes','orcamentos'].includes(table)?summaryMonth.value:periodFilter.value;const dados=['movimentacoes','contas_receber'].includes(name)&&month?{periodo:month,...(table==='cartoes'?{pendentes_cartao:true}:{})}:{};if(!reads.has(name))reads.set(name,api({tabela:name,acao:'listar',dados}));return reads.get(name);};const empty={registros:[]};let results;try{results=await Promise.all([(needsRefs||table==='clientes')?read('contas'):empty,needsRefs||table==='cartoes'?read('cartoes'):empty,read(selected),['orcamentos','cartoes'].includes(table)?read('movimentacoes'):empty]);}catch(error){if(serial===revision)$('rows').replaceChildren(node('p','Não foi possível carregar esta tela. Verifique sua conexão e toque em Atualizar.'));throw error;}if(serial!==revision)return;const [a,c,data,movements]=results;summaryCard.hidden=false;listFilters.hidden=false;accounts=a.registros;cards=c.registros;rows=data.registros;budgetMovements=movements.registros;if(table==='cartoes'){const previous=cardFilter.value;cardFilter.replaceChildren(new Option('Todos os cartões',''));for(const card of rows)cardFilter.append(new Option(card.nome_cartao,String(card.id)));cardFilter.value=rows.some(r=>String(r.id)===previous)?previous:'';}form();display();if(table!=='cartoes'){closeInvoice();invoiceCard=null;invoiceSnapshot=null;}}
const invoicePanel=node('section');invoicePanel.className='card';invoicePanel.hidden=true;invoicePanel.id='invoice-panel';
const invoiceTitle=node('h2','Fatura'),invoiceLabel=node('label','Mês da fatura'),invoiceMonth=node('input');invoiceMonth.id='invoice-month';invoiceMonth.type='month';invoiceMonth.min='2020-01';invoiceMonth.max='2099-12';invoiceLabel.append(invoiceMonth);
const invoiceSummary=node('p'),invoiceItems=node('div'),invoiceSettle=button('Quitar fatura',async()=>{if(!invoiceSnapshot||!invoiceCard)return;const competence=invoiceMonth.value.slice(5,7)+'/'+invoiceMonth.value.slice(0,4);if(competence!==invoiceSnapshot.competencia)throw Error('Consulte a competência escolhida antes de quitar.');if(!await ask('Confirmar pagamento da fatura de '+invoiceCard.nome_cartao+'?'))return;await mutate({tabela:'cartoes',acao:'quitar_fatura',id:invoiceCard.id,dados:{competencia:competence},versao:invoiceSnapshot._versao});await consultInvoice();await load();notify('Fatura quitada.');});invoiceSettle.hidden=true;
invoicePanel.append(invoiceTitle,invoiceLabel,button('Consultar fatura',consultInvoice),invoiceSummary,invoiceItems,invoiceSettle,button('Fechar fatura',()=>{closeInvoice();invoiceSnapshot=null;}));const invoiceDialog=node('dialog');invoiceDialog.className='fp-dialog fp-invoice';invoiceDialog.setAttribute('aria-label','Consultar fatura');$('rows').parentElement.before(invoiceDialog);invoiceDialog.append(invoicePanel);
function openInvoice(){invoicePanel.hidden=false;if(!invoiceDialog.open)invoiceDialog.showModal();}
function closeInvoice(){invoicePanel.hidden=true;if(invoiceDialog.open)invoiceDialog.close();}
invoiceDialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();});invoiceDialog.addEventListener('close',()=>{invoicePanel.hidden=true;invoiceSnapshot=null;invoiceDialog.querySelector('.modal-status')?.remove();});
async function consultInvoice(){invoiceSnapshot=null;invoiceSettle.hidden=true;invoiceItems.replaceChildren();invoiceSummary.textContent='Consultando...';if(!invoiceCard||!/^20\d{2}-(0[1-9]|1[0-2])$/.test(invoiceMonth.value))throw Error('Escolha o mês da fatura.');const competencia=invoiceMonth.value.slice(5,7)+'/'+invoiceMonth.value.slice(0,4);const result=await api({tabela:'cartoes',acao:'fatura',id:invoiceCard.id,dados:{competencia}});invoiceSnapshot={...result,competencia};const pendingRows=result.registros.filter(m=>!m.pago),total=pendingRows.reduce((s,m)=>s+Math.round(Number(m.valor)*100),0)/100;invoiceTitle.textContent='Fatura · '+invoiceCard.nome_cartao+' · '+competencia;invoiceSummary.textContent=pendingRows.length+' compras pendentes · '+new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}).format(total);const list=node('div');list.className='planning-grid';for(const r of result.registros){const item=node('article');item.className='planning-card';item.append(node('h3',r.descricao),node('strong',money(r.valor)),node('p',r.pago?'Pago':'Pendente'));if(table==='cartoes')item.append(button('Editar compra',()=>editInvoiceItem(r)),button('Excluir compra',()=>deleteInvoiceItem(r)));list.append(item);}invoiceItems.append(list);invoiceSettle.hidden=pendingRows.length===0;}
async function snapshotMovement(record){if(record._versao)return record;const current=(await api({tabela:'movimentacoes',acao:'listar',id:record.id})).registros.find(r=>Number(r.id)===Number(record.id));if(!current)throw Error('Este lançamento não está mais disponível na sua conta.');return current;}
const invoiceEditDialog=node('dialog');invoiceEditDialog.className='account-dialog';invoiceEditDialog.setAttribute('aria-label','Editar compra da fatura');formCard.closest('main').append(invoiceEditDialog);
async function editInvoiceItem(record){record=await snapshotMovement(record);invoiceEditDialog.replaceChildren();const editor=node('form');editor.append(node('h2','Editar compra da fatura'));for(const [key,label,type]of [['descricao','Descrição','text'],['valor','Valor','number'],['data','Data financeira','date'],['categoria','Categoria','text'],['tags','Tags','text'],['pago','Situação','status']]){const wrap=node('label',label),input=node(type==='status'?'select':'input');input.name=key;if(type==='status'){input.append(new Option('Pendente','false'),new Option('Pago','true'));input.value=String(Boolean(record.pago));}else{input.type=type;input.value=record[key]??'';if(type==='number'){input.min='.01';input.max='1000000';input.step='.01';}if(type==='text')input.maxLength=240;}input.required=key!=='tags';wrap.append(input);editor.append(wrap);}const actions=node('div');actions.className='account-actions';actions.append(button('Cancelar',()=>invoiceEditDialog.close()));const save=node('button','Salvar edição');save.type='submit';actions.append(save);editor.append(actions);editor.addEventListener('submit',event=>{event.preventDefault();const data=Object.fromEntries([...editor.querySelectorAll('[name]')].map(e=>[e.name,e.value]));data.valor=Number(data.valor);data.pago=data.pago==='true';data.tags=data.tags.trim()||null;perform(async()=>{await mutate({tabela:'movimentacoes',acao:'editar',id:record.id,dados:data,versao:record._versao});invoiceEditDialog.close();await load();if(invoiceCard&&!invoicePanel.hidden)await consultInvoice();notify('Compra atualizada.');});});invoiceEditDialog.append(editor);invoiceEditDialog.showModal();}
async function deleteInvoiceItem(record){record=await snapshotMovement(record);if(!await ask('Excluir a compra '+record.descricao+'?'))return;await mutate({tabela:'movimentacoes',acao:'excluir',id:record.id,versao:record._versao});await load();if(invoiceCard&&!invoicePanel.hidden)await consultInvoice();notify('Compra excluída.');}
for(const [value,label]of Object.entries(modules))$('module').append(new Option(label,value));
$('module').value=table;
$('module').addEventListener('change',()=>perform(async()=>{table=$('module').value;currentPage=1;searchInput.value='';periodFilter.value='';stateFilter.value='';await load();}));$('refresh').addEventListener('click',()=>{readCache.clear();perform(load);});formCancel.addEventListener('click',()=>{formVisible=false;form();});
$('form').addEventListener('submit',e=>{e.preventDefault();perform(async()=>{if(!editing&&!canCreate())throw Error('Use Novo lançamento para cadastrar movimentações.');const dados={};for(const [key,,type]of definitions()){const raw=$('form').elements.namedItem(key).value;dados[key]=type==='number'||type==='day'||key.endsWith('_id')?(raw===''?null:Number(raw)):(key==='data_vencimento'&&raw===''?null:raw.trim());}
 if(table==='movimentacoes'){if(dados.forma_pagamento==='Cartão de Crédito'){const card=cards.find(c=>c.id===dados.cartao_id);if(!card)throw Error('Escolha um cartão');const [y,m,d]=dados.data.split('-').map(Number),close=Math.min(card.dia_fechamento,new Date(Date.UTC(y,m,0)).getUTCDate());const shift=d>=close?1:0;dados.mes_fatura=String((m+shift-1)%12+1).padStart(2,'0')+'/'+(y+(m+shift>12?1:0));dados.conta_id=null;}else{dados.cartao_id=null;dados.mes_fatura=null;}}
 const launch=table==='movimentacoes'&&!editing;if(launch){delete dados.mes_fatura;}
 await mutate({tabela:table,acao:editing?'editar':launch?'lancar':'criar',...(editing?{id:editing.id,versao:editing._versao}:{}),dados});formVisible=false;await load();notify('Salvo com sucesso.');});});
function rememberContext(){document.dispatchEvent(new CustomEvent('fp:context',{detail:{period:periodFilter.value,invoiceMonth:summaryMonth.value,card:cardFilter.value}}));}
function restoreContext(raw,render=true){let data;try{data=JSON.parse(raw||'{}');}catch{return;}for(const [input,key]of [[periodFilter,'period'],[summaryMonth,'invoiceMonth']])if(typeof data[key]==='string'&&/^20[0-9]{2}-(0[1-9]|1[0-2])$/.test(data[key]))input.value=data[key];if(typeof data.card==='string'&&[...cardFilter.options].some(o=>o.value===data.card))cardFilter.value=data.card;if(render)display();}
for(const input of [periodFilter,summaryMonth,cardFilter])input.addEventListener('change',rememberContext);
${tvImportUI}
${clientShortcutsUI}
perform(load);
`;

