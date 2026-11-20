import {validUsername} from '../username.mjs';
import {getAccess} from './access.mjs';
import {financialMonth} from '../monthly.mjs';
const fpCookieName='fp_session';
const fpText=new TextEncoder();
const fpJson=(x,code=200,headers={})=>new Response(JSON.stringify(x),{status:code,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff','referrer-policy':'no-referrer','x-frame-options':'DENY',...headers}});
const fpSessionValue=r=>(r.headers.get('cookie')||'').split(';').map(x=>x.trim()).find(x=>x.startsWith(fpCookieName+'='))?.slice(fpCookieName.length+1);
function fpB64(bytes){let s='';for(const b of new Uint8Array(bytes))s+=String.fromCharCode(b);return btoa(s).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'')}
function fpUnb64(s){const v=atob(s.replace(/-/g,'+').replace(/_/g,'/').padEnd(Math.ceil(s.length/4)*4,'='));return Uint8Array.from(v,c=>c.charCodeAt(0))}
async function fpKey(env){return crypto.subtle.importKey('raw',fpText.encode(env.SESSION_SECRET),{name:'HMAC',hash:'SHA-256'},false,['sign','verify'])}
async function fpMakeSession(env,id,sv=0){const now=Math.floor(Date.now()/1000);const b=fpB64(fpText.encode(JSON.stringify({id,sv,iat:now,exp:now+7200})));const sig=fpB64(await crypto.subtle.sign('HMAC',await fpKey(env),fpText.encode('v1.'+b)));return 'v1.'+b+'.'+sig}
async function fpReadSession(env,req){try{const token=fpSessionValue(req),parts=(token||'').split('.');if(parts.length!==3||parts[0]!=='v1')return null;const valid=await crypto.subtle.verify('HMAC',await fpKey(env),fpUnb64(parts[2]),fpText.encode('v1.'+parts[1]));if(!valid)return null;const s=JSON.parse(new TextDecoder().decode(fpUnb64(parts[1])));const now=Math.floor(Date.now()/1000);return Number.isSafeInteger(s.id)&&s.id>0&&s.exp>now&&s.iat<=now+30&&s.exp-s.iat<=7200?s:null}catch{return null}}
function fpEnvironmentOkay(env){return typeof env?.SUPABASE_URL==='string'&&env.SUPABASE_URL.startsWith('https://')&&typeof env.SUPABASE_BACKEND_KEY==='string'&&env.SUPABASE_BACKEND_KEY.startsWith('sb_secret_')&&typeof env.SESSION_SECRET==='string'&&env.SESSION_SECRET.length>=32}
async function fpDB(env,table,filters={},columns='*',limit=100,offset=0){const allowed=['usuarios','movimentacoes','contas','cartoes','contas_receber','metas','orcamentos','clientes'];if(!allowed.includes(table))throw Error('TABLE');const url=new URL('/rest/v1/'+table,env.SUPABASE_URL);url.searchParams.set('select',columns);for(const [key,value] of Object.entries(filters))url.searchParams.append(key,'eq.'+value);url.searchParams.set('limit',String(limit));if(offset)url.searchParams.set('offset',String(offset));const response=await fetch(url,{headers:{apikey:env.SUPABASE_BACKEND_KEY,accept:'application/json'},redirect:'follow'});if(!response.ok)throw Error('DATABASE_'+response.status);return response.json()}
async function fpUser(env,req){const token=await fpReadSession(env,req);if(!token)return null;const rows=await fpDB(env,'usuarios',{id:token.id},'id,usuario,status,role,is_admin,session_version',1);const u=rows[0];return u?.status==='ativo'&&Number(token.sv??0)===Number(u.session_version??0)?{id:u.id,usuario:u.usuario,admin:u.role==='admin'||u.is_admin===true}:null}
async function fpLogin(req,env){if(!env.LOGIN_LIMITER?.limit)return fpJson({erro:'Proteção do login indisponível'},503);const ip=req.headers.get('cf-connecting-ip')||'sem-ip';const rate=await env.LOGIN_LIMITER.limit({key:'ip:'+ip});if(!rate.success)return fpJson({erro:'Muitas tentativas. Tente novamente em um minuto.'},429,{'retry-after':'60'});let body;try{const text=await req.text();if(text.length>3000) return fpJson({erro:'Requisição muito grande'},413);body=JSON.parse(text)}catch{return fpJson({erro:'Formato inválido'},400)}const name=String(body?.usuario||'').trim(),password=body?.senha;if(!validUsername(name,1)||typeof password!=='string'||password.length>1024||password.length<1)return fpJson({erro:'Credenciais inválidas'},401);const userRate=await env.LOGIN_LIMITER.limit({key:'user:'+name.toLowerCase()});if(!userRate.success)return fpJson({erro:'Muitas tentativas para esse usuário'},429,{'retry-after':'60'});const rows=await fpDB(env,'usuarios',{usuario:name},'id,usuario,status,session_version',1);const user=rows[0];const digest=await crypto.subtle.digest('SHA-256',fpText.encode(password));const hash=Array.from(new Uint8Array(digest),x=>x.toString(16).padStart(2,'0')).join('');const verified=await fetch(new URL('/rest/v1/rpc/fp_password_verify_v1',env.SUPABASE_URL),{method:'POST',headers:{apikey:env.SUPABASE_BACKEND_KEY,'content-type':'application/json'},body:JSON.stringify({p_usuario:user?.id??0,p_digest:hash}),signal:AbortSignal.timeout(15000)});if(!verified.ok)throw Error('PASSWORD_VERIFY');if((await verified.json())!==true||!user||user.status!=='ativo')return fpJson({erro:'Usuário, senha ou status inválido'},401);const cookie=fpCookieName+'='+await fpMakeSession(env,user.id,Number(user.session_version??0))+'; Path=/; Max-Age=7200; HttpOnly; Secure; SameSite=Strict';return fpJson({ok:true},200,{'set-cookie':cookie})}

function fpPeriodo(params) {
 const agora=new Intl.DateTimeFormat('en-US',{timeZone:'America/Cuiaba',year:'numeric',month:'2-digit'}).formatToParts(new Date());
 const localYear=Number(agora.find(p=>p.type==='year').value);
 const localMonth=Number(agora.find(p=>p.type==='month').value);
 const rawYear=params?.get('ano')??String(localYear);
 const rawMonth=params?.get('mes')??String(localMonth);
 if(!/^\d{4}$/.test(rawYear)||Number(rawYear)<2000||Number(rawYear)>2100)throw Error('PERIODO_INVALIDO');
 const month=rawMonth==='Todos'?'Todos':Number(rawMonth);
 if(month!=='Todos'&&(!/^\d{1,2}$/.test(rawMonth)||month<1||month>12))throw Error('PERIODO_INVALIDO');
 return {ano:Number(rawYear),mes:month==='Todos'?'Todos':String(month).padStart(2,'0')};
}
async function fpPeriodMovements(env,userId,periodo,modulo='visao_geral'){
 const dados=periodo.mes==='Todos'?{ano:String(periodo.ano)}:{periodo:String(periodo.ano)+'-'+periodo.mes};
 const response=await fetch(new URL('/rest/v1/rpc/fp_financeiro_modulo_v1',env.SUPABASE_URL),{method:'POST',redirect:'manual',signal:AbortSignal.timeout(15000),headers:{apikey:env.SUPABASE_BACKEND_KEY,'content-type':'application/json'},body:JSON.stringify({p_usuario:userId,p_tabela:'movimentacoes',p_acao:'listar',p_dados:dados,p_modulo:modulo})});
 if(!response.ok)throw Error('DATABASE_'+response.status);const result=await response.json();if(!Array.isArray(result.registros))throw Error('DATABASE_FORMAT');return result.registros;
}
async function fpSummary(env,userId,params){
 const periodo=fpPeriodo(params);
 const totals={receitas:0,despesas:0,pendentes:0,saldo:0,movimentos:0,periodo};
 const year=String(periodo.ano);
 let truncated=false;
 for(let p=0;p<1;p++){
  const rows=await fpPeriodMovements(env,userId,periodo);
  for(const m of rows){
   const data=String(m.data||'');
   const noPeriodo=periodo.mes==='Todos'
     ?financialMonth(m).startsWith(year+'-')
     :m.forma_pagamento==='Cartão de Crédito'
       ?m.mes_fatura===periodo.mes+'/'+year
       :data.startsWith(year+'-'+periodo.mes+'-');
   if(!noPeriodo)continue;
   const value=Number(m.valor||0);
   if(!Number.isFinite(value))continue;
   if(m.tipo==='Receita')totals.receitas+=value;
   else {totals.despesas+=value;if(!m.pago)totals.pendentes+=value}
   totals.movimentos++;
  }
  if(rows.length<500)break;
  if(p===19)truncated=true;
 }
 totals.saldo=totals.receitas-totals.despesas;
 totals.eficiencia=totals.receitas>0?totals.saldo/totals.receitas*100:0;
 totals.truncated=truncated;
 return totals;
}

function fpInPeriodo(m,periodo){
 const year=String(periodo.ano),date=String(m.data||'');
 if(periodo.mes==='Todos')return financialMonth(m).startsWith(year+'-');
 return m.forma_pagamento==='Cartão de Crédito'
  ?m.mes_fatura===periodo.mes+'/'+year
  :date.startsWith(year+'-'+periodo.mes+'-');
}
async function fpAllUserMov(env,userId,periodo,modulo='visao_geral'){return {data:await fpPeriodMovements(env,userId,periodo,modulo),truncated:false};}
async function fpAnalise(env,userId,params){
 const periodo=fpPeriodo(params);
 const data=await fpAllUserMov(env,userId,{...periodo,mes:'Todos'});
 const mrotulos=['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
 const fluxo=mrotulos.map(mes=>({mes,receitas:0,despesas:0}));
 const categorias=new Map(),tags=new Map();
 let receitas=0,despesas=0;
 for(const m of data.data){
  const valor=Number(m.valor||0);if(!Number.isFinite(valor))continue;
  if(financialMonth(m).startsWith(String(periodo.ano)+'-')){
   const mm=Number(financialMonth(m).slice(5,7))-1;
   if(mm>=0&&mm<12){
    if(m.tipo==='Receita')fluxo[mm].receitas+=valor;
    else if(m.tipo==='Despesa')fluxo[mm].despesas+=valor;
   }
  }
  if(!fpInPeriodo(m,periodo))continue;
  if(m.tipo==='Receita')receitas+=valor;
  else {
   despesas+=valor;
   const cat=String(m.categoria||'Sem categoria');
   categorias.set(cat,(categorias.get(cat)||0)+valor);
  }
  if(m.tags){
   for(const rawTag of String(m.tags).split(',')){
    const tag=rawTag.trim().toLowerCase().replace(/^#+/,'');
    if(!tag)continue;
    const etiqueta='#'+tag;
    tags.set(etiqueta,(tags.get(etiqueta)||0)+valor);
   }
  }
 }
 let orcamentos=[],metas=[];
 try{orcamentos=await fpDB(env,'orcamentos',{usuario_id:userId},'categoria,limite',100);}catch(e){console.warn('Orcamentos indisponiveis',e?.message)}
 try{metas=await fpDB(env,'metas',{usuario_id:userId},'nome_meta,valor_alvo,valor_poupado,prazo',100);}catch(e){console.warn('Metas indisponiveis',e?.message)}
 const insights=[];
 if(receitas>0){
  const comprometimento=despesas/receitas*100;
  if(comprometimento>=85)insights.push({tipo:'alerta',titulo:'Alerta de comprometimento',texto:'Suas despesas representam '+comprometimento.toFixed(1)+'% das receitas deste período.'});
  else if(comprometimento<=50)insights.push({tipo:'positivo',titulo:'Boa gestão',texto:'Você comprometeu '+comprometimento.toFixed(1)+'% das receitas neste período.'});
 }
 for(const m of metas){
  const alvo=Number(m.valor_alvo||0),guardado=Number(m.valor_poupado||0);
  if(alvo<=0)continue;
  const pct=guardado/alvo*100;
  if(pct>=100)insights.push({tipo:'positivo',titulo:'Meta alcançada',texto:String(m.nome_meta||'Meta')+' atingiu o objetivo.'});
  else if(pct>=75)insights.push({tipo:'informacao',titulo:'Meta próxima',texto:String(m.nome_meta||'Meta')+' alcançou '+pct.toFixed(0)+'% do objetivo.'});
 }
 return {periodo,fluxo,categorias:[...categorias].map(([nome,valor])=>({nome,valor})).sort((a,b)=>b.valor-a.valor),tags:[...tags].map(([nome,valor])=>({nome,valor})).sort((a,b)=>b.valor-a.valor),metas:metas.map(m=>({nome:String(m.nome_meta||'Meta'),alvo:Number(m.valor_alvo||0),guardado:Number(m.valor_poupado||0),prazo:m.prazo})),orcamentos:orcamentos.map(o=>({categoria:String(o.categoria||'Geral'),limite:Number(o.limite||0)})),insights,truncated:data.truncated};
}
async function fpListaMensal(env,userId,params,page){
 const periodo=fpPeriodo(params);
 const all=await fpAllUserMov(env,userId,periodo,'movimentacoes');
 const rows=all.data.filter(m=>fpInPeriodo(m,periodo)).sort((a,b)=>String(b.data||'').localeCompare(String(a.data||''))||Number(b.id||0)-Number(a.id||0));
 const start=(page-1)*100;
 const registros=rows.slice(start,start+100).map(m=>({id:m.id,data:m.data,tipo:m.tipo,descricao:m.descricao,valor:m.valor,categoria:m.categoria,forma_pagamento:m.forma_pagamento,pago:m.pago,mes_fatura:m.mes_fatura,tags:m.tags}));
 return {registros,pagina:page,total:rows.length,total_paginas:Math.max(1,Math.ceil(rows.length/100)),truncated:all.truncated,periodo};
}

const fpActiveHandler = { async fetch(req,env){
 const u=new URL(req.url);
 if(!u.pathname.startsWith('/api/')||u.pathname==='/api/preflight')return fpJson({erro:'Rota inválida'},404);
 if(!fpEnvironmentOkay(env))return fpJson({erro:'Conexão ainda não configurada'},503);
 if(u.pathname==='/api/health')return fpJson({status:'ok',fase:5,modo:'consulta',escrita:'bloqueada'});
 if(['POST','PUT','PATCH','DELETE'].includes(req.method) && req.headers.get('origin')!==u.origin)return fpJson({erro:'Origem não autorizada'},403);
 if(!['GET','POST'].includes(req.method))return fpJson({erro:'Operação não disponível'},405);
 try{
   if(u.pathname==='/api/login'&&req.method==='POST')return await fpLogin(req,env);
   if(u.pathname==='/api/logout'&&req.method==='POST'){
    const token=await fpReadSession(env,req);
    if(token){const response=await fetch(new URL('/rest/v1/rpc/fp_sessions_revoke_v1',env.SUPABASE_URL),{method:'POST',redirect:'error',signal:AbortSignal.timeout(12000),headers:{apikey:env.SUPABASE_BACKEND_KEY,'content-type':'application/json'},body:JSON.stringify({p_usuario:token.id,p_version:token.sv??0})});if(!response.ok)return fpJson({erro:'Não foi possível encerrar as sessões. Tente novamente.'},503);}
    return fpJson({ok:true},200,{'set-cookie':fpCookieName+'=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict'});
   }
   const user=await fpUser(env,req);if(!user)return fpJson({erro:'Sessão expirada ou acesso não autorizado'},401);
   if(u.pathname==='/api/me'&&req.method==='GET')return fpJson({...user,access:await getAccess(env,user.id)});
   if(u.pathname==='/api/dashboard'&&req.method==='GET')return fpJson(await fpSummary(env,user.id,u.searchParams));
   if(u.pathname==='/api/analise'&&req.method==='GET')return fpJson(await fpAnalise(env,user.id,u.searchParams));
   const t=u.pathname.slice('/api/'.length);if(req.method!=='GET')return fpJson({erro:'A versão de teste não permite alterações'},403);
   if(!['movimentacoes','contas','cartoes','contas_receber','metas','orcamentos','clientes'].includes(t))return fpJson({erro:'Rota inválida'},404);
   const page=Number(u.searchParams.get('pagina')||1);if(!Number.isSafeInteger(page)||page<1||page>500)return fpJson({erro:'Página inválida'},400);
   const cols={movimentacoes:'id,data,tipo,descricao,valor,categoria,forma_pagamento,pago',contas:'id,nome,saldo',cartoes:'id,nome_cartao,limite,dia_vencimento,dia_fechamento',contas_receber:'id,descricao,valor,data_recebimento,recebido',metas:'id,nome_meta,valor_alvo,valor_poupado,prazo',orcamentos:'id,categoria,limite',clientes:'id,nome,telefone,valor,status,data_vencimento'};
   if(t==='movimentacoes')return fpJson(await fpListaMensal(env,user.id,u.searchParams,page));
   return fpJson({registros:await fpDB(env,t,{usuario_id:user.id},cols[t],100,(page-1)*100),pagina:page});
 }catch(e){console.error('FinanceiroPro API error',e?.name);return fpJson({erro:'Falha ao consultar dados. Verifique a conexão e tente novamente.'},500)}
}};

export default fpActiveHandler;


