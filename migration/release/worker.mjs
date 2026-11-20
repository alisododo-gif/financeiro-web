import {deliveryStatusUI} from '../delivery-status-ui.mjs';
import {optimizeDashboardSource} from '../dashboard-runtime.mjs';
import {deleteUserEndpoint,simplifyDeleteConfirmation} from './delete-user.mjs';
import {appIcon} from '../app-icons.mjs';
import {financialMonth} from '../monthly.mjs';
import {appManifest,appServiceWorker,mobileAppScript} from '../mobile-app.mjs';
import {shortcutsEndpoint} from '../shortcuts.mjs';
import {tvImportEndpoint} from '../tv-import.mjs';
import {premiumCSS} from './premium.mjs';
import {createEnvironment} from './services.mjs';
import {accessEndpoint,accessGate,accessRPC} from './access.mjs';
import {accessScript} from './access-ui.mjs';
import {parityScript} from '../parity.mjs';
import {changePassword} from './account.mjs';
import {signup,signupScript} from './signup.mjs';
import {experience} from './experience.mjs';
import {panelScript} from './panel.mjs';
import {navigation} from './navigation.mjs';
import {handle,html,script,css} from './financeiro.mjs';
export default {
 async fetch(request,bindings){
  const env=createEnvironment(bindings);
  const url=new URL(request.url);
  if(url.pathname==='/api/admin/entregas'){
   if(request.method!=='GET')return Response.json({erro:'Método não permitido'},{status:405});
   const response=await env.PROD_API.fetch(new Request(url.origin+'/api/me',{headers:{cookie:request.headers.get('cookie')||''}}));
   if(!response.ok)return Response.json({erro:'Entre novamente'},{status:401});const user=await response.json();
   if(user.admin!==true)return Response.json({erro:'Somente administrador'},{status:403});
   try{return Response.json(await accessRPC(env,'fp_delivery_status_v1',{p_actor:user.id}),{headers:{'cache-control':'no-store'}});}catch{return Response.json({erro:'Consulta indisponível'},{status:503});}
  }
  if(/^\/api\/admin\/usuarios\/\d+\/exclusao$/.test(url.pathname)||(request.method==='DELETE'&&/^\/api\/admin\/usuarios\/\d+$/.test(url.pathname)))return deleteUserEndpoint(request,env);
  const icon=appIcon(url.pathname);if(icon&&['GET','HEAD'].includes(request.method))return icon;
  if(url.pathname==='/manifest.webmanifest')return Response.json(appManifest,{headers:{'content-type':'application/manifest+json','cache-control':'no-cache'}});
  if(url.pathname==='/app-sw.js')return new Response(appServiceWorker,{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'no-cache','service-worker-allowed':'/'}});
  if(url.pathname==='/static/mobile-app.js')return new Response(mobileAppScript,{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'no-store'}});
  if(['/api/admin/atalhos','/api/conta/atalhos'].includes(url.pathname)||url.pathname.startsWith('/api/atalhos/'))return shortcutsEndpoint(request,env);
  if(['/api/clientes/importar-tv','/api/clientes/integracao-tv'].includes(url.pathname))return tvImportEndpoint(request,env);
  if(url.pathname==='/api/acesso'||url.pathname==='/api/admin/acessos')return accessEndpoint(request,env);
  if(url.pathname==='/static/access.js')return new Response(accessScript,{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'no-store'}});
  if(!env.REVIEW_API){const denied=await accessGate(request,env);if(denied)return denied;}
  if(url.pathname==='/api/health'&&request.method==='GET')return Response.json({status:'ok',aplicacao:'FinanceiroPro Web',estrutura:'unificada'},{headers:{'cache-control':'no-store'}});
  if(url.pathname==='/api/conta/senha')return changePassword(request,env);
  if(url.pathname==='/api/conta/cadastro')return signup(request,env);
  if(url.pathname==='/api/financeiro/ano'&&request.method==='GET'){
   const year=url.searchParams.get('ano');if(!/^20\d{2}$/.test(year||''))return Response.json({erro:'Ano inválido'},{status:400});
   const headers=new Headers(request.headers);headers.set('origin',url.origin);headers.set('content-type','application/json');headers.set('x-financeiro-operacao','1');
   const result=await handle(new Request(url.origin+'/api/financeiro/operacao',{method:'POST',headers,body:JSON.stringify({tabela:'movimentacoes',acao:'listar',modulo:'visao_geral',dados:{ano:year}})}),env);
   if(!result.ok)return result;
   const data=await result.json(),registros=data.registros.filter(row=>financialMonth(row).startsWith(year+'-'));
   return Response.json({ano:Number(year),registros,total:registros.length},{headers:{'cache-control':'no-store'}});
  }
  if(url.pathname==='/app'||(url.pathname==='/financeiro'&&!url.searchParams.has('modulo')))return Response.redirect(url.origin+'/'+url.search,302);
  if(url.pathname==='/api/financeiro/operacao'){
   if(env.REVIEW_API?.fetch){
    if(request.method!=='POST'||request.headers.get('origin')!==url.origin||request.headers.get('x-financeiro-operacao')!=='1')return Response.json({erro:'Origem não autorizada'},{status:403});
    let input;try{input=await request.clone().json();}catch{return Response.json({erro:'JSON inválido'},{status:400});}
    if(!['listar','fatura'].includes(input?.acao))return Response.json({erro:'Homologação somente leitura'},{status:403});
    const forward=new Request('https://financeiroproweb.alisododo.workers.dev/api/financeiro/operacao',request);forward.headers.set('origin','https://financeiroproweb.alisododo.workers.dev');return env.REVIEW_API.fetch(forward);
   }
   return handle(request,env);
  }
  if(url.pathname.startsWith('/api/lab/'))return new Response('Laboratorio encerrado',{status:410,headers:{'cache-control':'no-store'}});
  if(url.pathname.startsWith('/api/homologacao/'))return new Response('Rota indisponível',{status:404});
  if(url.pathname==='/financeiro')return new Response(html,{headers:{'content-type':'text/html; charset=utf-8','cache-control':'no-store','x-frame-options':'DENY','content-security-policy':"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"}});
  if(url.pathname==='/static/financeiro.js')return new Response(script,{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'}});
  if(url.pathname==='/static/financeiro.css')return new Response(css,{headers:{'content-type':'text/css; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'}});
  if(url.pathname==='/static/premium.css')return new Response(premiumCSS,{headers:{'content-type':'text/css; charset=utf-8','cache-control':'no-store'}});
  if(url.pathname==='/static/experience.js')return new Response(experience,{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'no-store'}});
  if(url.pathname==='/static/parity.js')return new Response(parityScript,{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'no-store'}});
  if(url.pathname==='/static/signup.js')return new Response(signupScript,{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'no-store'}});
  if(url.pathname==='/static/financial-panel.js')return new Response(panelScript,{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'no-store'}});
  if(url.pathname==='/static/production-navigation.js')return new Response(navigation,{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'no-store'}});
  if(!env.LEGACY_API?.fetch)return new Response('Acesso temporariamente indisponível',{status:503});
  const upstream=new URL((url.pathname==='/'?'/app':url.pathname)+url.search,'https://financeiropro-homologacao.alisododo.workers.dev');
  const forwarded=new Request(upstream,request);
  if(!['GET','HEAD','OPTIONS'].includes(request.method)&&request.headers.get('origin')===url.origin)forwarded.headers.set('origin',upstream.origin);
  const response=await env.LEGACY_API.fetch(forwarded);
  if(url.pathname==='/static/app.js'&&response.ok){
   let body=await response.text();
   const login="$('senha').value='';show(await api('me'));";
   const logout="async function logout(){try{await api('logout',{method:'POST'});}catch{}show(null);}";
   if(!body.includes(login)||!body.includes(logout))return new Response('Atualizacao de acesso indisponivel',{status:503,headers:{'cache-control':'no-store'}});
   body=body.replace(login,"$('senha').value='';try{localStorage.setItem('fp-last-activity',String(Date.now()));}catch{}location.replace('/app');")
    .replace(logout,"async function logout(){try{await api('logout',{method:'POST'});document.dispatchEvent(new Event('fp:session-reset'));location.replace('/app');}catch(error){setMessage('app-error','Nao foi possivel sair. Tente novamente.');}}")
    .replace('function show(user){',"function show(user){document.dispatchEvent(new Event('fp:session-reset'));");
   body=body.replace("applyPeriod();bind();","document.getElementById('logout-btn').textContent='Sair de todos os aparelhos';applyPeriod();bind();");
   body+=deliveryStatusUI;
   body=body.replace('isAdmin=user.admin===true;',"document.getElementById('app-panel').dataset.navigationOwner=String(user.id);isAdmin=user.admin===true;");
   body=body.replaceAll('confirm(', 'await window.fpDialog(').replaceAll('prompt(', 'await window.fpPrompt(');
   body=simplifyDeleteConfirmation(body);
   body=body.replace('function adminMessage(text,success=false){',"function adminMessage(text,success=false){const dialog=document.getElementById('admin-create-form')?.closest('dialog');if(dialog?.open){let message=dialog.querySelector('.admin-modal-message');if(!message){message=document.createElement('p');message.className='admin-modal-message';message.setAttribute('role','status');dialog.append(message);}message.textContent=text;}")
    .replace("$('admin-create-form').reset();$('new-senha').value='';","$('admin-create-form').reset();$('new-senha').value='';$('admin-create-form').closest('dialog')?.close();");
   body=optimizeDashboardSource(body);
   const headers=new Headers(response.headers);headers.delete('content-length');headers.delete('etag');headers.set('cache-control','no-store');
   return new Response(body,{status:response.status,headers});
  }
  if(url.pathname==='/'&&response.ok){
   const body=(await response.text()).replace('<h1>Acesse seu financeiro</h1>','').replace('width=device-width,initial-scale=1','width=device-width,initial-scale=1,viewport-fit=cover').replace('</head>','<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#0b111b"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="FinanceiroPro Web"><link rel="apple-touch-icon" sizes="180x180" href="/static/app-icon-v2-180.png"><link rel="icon" type="image/png" sizes="32x32" href="/static/app-icon-v2-32.png"><script defer src="/static/mobile-app.js"></script></head>')
    .replace('</head>','<link rel="stylesheet" href="/static/premium.css?v=mobile-parity-3"><script defer src="/static/production-navigation.js"></script><script defer src="/static/experience.js?v=mobile-parity-3"></script><script defer src="/static/parity.js"></script><script defer src="/static/signup.js"></script><script defer src="/static/access.js"></script></head>')
    .replace(/<p>Entre com[^<]+<\/p>/,'<p>Entre com seu usu\u00e1rio e senha para acompanhar suas finan\u00e7as.</p>').replace(/<small class=\"hint\">[^<]+<\/small>/,'<small class=\"hint\">Acesso protegido. Seus dados e hist\u00f3rico em um s\u00f3 lugar.</small>')
    .replaceAll('Por data dos lançamentos','Crédito por fatura; demais por data').replaceAll('Extrato por data','Por competência financeira')
    .replaceAll('FinanceiroPro — Homologação','FinanceiroPro Web').replaceAll('HOMOLOGAÇÃO','FINANCEIROPRO WEB')
    .replaceAll('FinanceiroPro • Homologação separada • Painel financeiro em consulta • Administração restrita • Sistema antigo preservado','FinanceiroPro Web • Seus dados no Supabase • Acesso autenticado');
   const updatedBody=body.replace('Suspender mantém os lançamentos financeiros. Exclusão só é permitida para usuários sem dados vinculados, com confirmação do nome.','Suspender mantém os dados. Excluir exige o nome do usuário e uma confirmação final para apagar o cadastro e todos os dados vinculados.');
   const headers=new Headers(response.headers);headers.delete('content-length');headers.set('cache-control','no-store');headers.set('content-security-policy',(headers.get('content-security-policy')||"default-src 'self'")+"; manifest-src 'self'; worker-src 'self'");
   return new Response(updatedBody.replace('</head>', "<style id=\"fp-admin-tab-contrast\">#admin-content .admin-tabs [role=\"tab\"]{color:var(--ink)!important;background:var(--surface-2)!important;border:1px solid var(--line)!important}#admin-content .admin-tabs [role=\"tab\"][aria-selected=\"true\"]{color:var(--accent-ink)!important;background:var(--accent)!important;border-color:var(--accent)!important}#admin-content .admin-tabs [role=\"tab\"]:focus-visible{outline:3px solid var(--blue);outline-offset:2px}</style></head>"),{status:response.status,headers});
  }
  return response;
 }
};

