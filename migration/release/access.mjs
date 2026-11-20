const base='https://hkfyvhthfshnddduckjs.supabase.co/rest/v1/rpc/';
const reply=(body,status=200)=>Response.json(body,{status,headers:{'cache-control':'no-store'}});
export async function accessRPC(env,name,data){
 const r=await fetch(base+name,{method:'POST',redirect:'manual',signal:AbortSignal.timeout(12000),headers:{apikey:env.SUPABASE_BACKEND_KEY,'content-type':'application/json'},body:JSON.stringify(data)});
 const result=await r.json();if(!r.ok)throw Error('Não foi possível atualizar o acesso. Confira os dados e tente novamente.');return result;
}
export const getAccess=(env,id,module=null)=>accessRPC(env,'fp_access_v1',{p_usuario:id,p_modulo:module});
async function identity(request,env){const r=await env.PROD_API.fetch(new Request('https://financeiroproweb.alisododo.workers.dev/api/me',{headers:{cookie:request.headers.get('cookie')||''}}));return r.ok?await r.json():null;}
export async function accessEndpoint(request,env){
 const path=new URL(request.url).pathname,admin=path==='/api/admin/acessos';
 try{
  const user=await identity(request,env);if(!user)return reply({erro:'Entre novamente.'},401);
  if(!admin)return reply(user.access||await getAccess(env,user.id));
  if(!user.admin)return reply({erro:'Somente administrador.'},403);
  if(request.method==='GET')return reply(await accessRPC(env,'fp_access_admin_v1',{p_actor:user.id,p_acao:'listar'}));
  if(request.method!=='POST'||request.headers.get('origin')!==new URL(request.url).origin||request.headers.get('x-financeiro-operacao')!=='1')return reply({erro:'Origem ou método não permitido.'},403);
  const text=await request.text();if(text.length>6000)return reply({erro:'Dados muito grandes.'},413);
  const data=JSON.parse(text);
  if(!data||Array.isArray(data)||Object.keys(data).some(k=>!['acao','id','dados'].includes(k))||!['padrao','usuario'].includes(data.acao)||(data.acao==='usuario'&&(!Number.isSafeInteger(data.id)||data.id<1)))return reply({erro:'Dados inválidos.'},400);
  return reply(await accessRPC(env,'fp_access_admin_v1',{p_actor:user.id,p_acao:data.acao,p_id:data.id??null,p_dados:data.dados??{}}));
 }catch{return reply({erro:'Não foi possível atualizar o acesso. Confira os dados e tente novamente.'},503);}
}
export async function accessGate(request,env){
 const path=new URL(request.url).pathname;
 if(!path.startsWith('/api/')||['/api/me','/api/login','/api/logout','/api/health','/api/acesso','/api/conta/cadastro','/api/conta/senha'].includes(path)||path.startsWith('/api/admin/')||path.startsWith('/api/homologacao/')||path.startsWith('/api/lab/'))return null;
 try{
  const user=await identity(request,env);if(!user)return reply({erro:'Entre novamente.'},401);
  const mapping={dashboard:'visao_geral',analise:'visao_geral',movimentacoes:'movimentacoes',contas_receber:'recebimentos',clientes:'clientes',contas:'contas',cartoes:'cartoes',metas:'metas',orcamentos:'orcamentos',vencimentos:'vencimentos'};
  const route=path.slice(5).split('/')[0];
  const module=mapping[route]||(path.startsWith('/api/planejamento/')?'movimentacoes':path.startsWith('/api/financeiro/')&&path!=='/api/financeiro/operacao'?'cartoes':null);
  const access=module?await getAccess(env,user.id,module):user.access||await getAccess(env,user.id);
  return access.allowed?null:reply({erro:access.message,access},403);
 }catch{return reply({erro:'Não foi possível verificar seu acesso agora.'},503);}
}

