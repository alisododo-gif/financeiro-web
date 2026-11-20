import {accessRPC} from './release/access.mjs';
const resources=['clientes_cobrar_amanha','usuarios','faturas_vencendo_hoje','movimentacoes_hoje','recebimentos_hoje'];
const reply=(body,status=200)=>Response.json(body,{status,headers:{'cache-control':'no-store','referrer-policy':'no-referrer','x-content-type-options':'nosniff'}});
const digest=async value=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)))].map(n=>n.toString(16).padStart(2,'0')).join('');
export async function shortcutsEndpoint(request,env){
 const url=new URL(request.url),personal=url.pathname==='/api/conta/atalhos',manage=personal||url.pathname==='/api/admin/atalhos';
 try{
 if(manage){
  if(!['GET','POST'].includes(request.method))return reply({erro:'Método não permitido.'},405);
  if(request.method==='POST'&&(request.headers.get('origin')!==url.origin||request.headers.get('x-financeiro-operacao')!=='1'))return reply({erro:'Origem não permitida.'},403);
  const session=await env.PROD_API.fetch(new Request('https://financeiroproweb.alisododo.workers.dev/api/me',{headers:{cookie:request.headers.get('cookie')||''}}));if(!session.ok)return reply({erro:'Entre novamente.'},401);const user=await session.json();if((!personal&&!user.admin)||!Number.isSafeInteger(user.id)||user.id<1)return reply({erro:'Acesso não autorizado.'},403);
  if(!personal&&await accessRPC(env,'fp_tv_habilitado_v1',{p_usuario:user.id})!==true)return reply({enabled:false},request.method==='GET'?200:403);
  let data={acao:'status'};if(request.method==='POST'){const text=await request.text();if(text.length>1024)return reply({erro:'Dados muito grandes.'},413);try{data=JSON.parse(text);}catch{return reply({erro:'Dados inválidos.'},400);}if(!data||Array.isArray(data)||Object.keys(data).some(k=>!['acao','hash'].includes(k))||!['criar','revogar'].includes(data.acao)||data.acao==='criar'&&!/^[a-f0-9]{64}$/.test(data.hash||''))return reply({erro:'Dados inválidos.'},400);}
  return reply(await accessRPC(env,personal?'fp_shortcut_clients_manage_v1':'fp_shortcut_manage_v1',{p_actor:user.id,p_acao:data.acao,p_hash:data.hash??null}));
 }
 if(request.method!=='GET')return reply({erro:'Este acesso permite somente consultas.'},405);
 const resource=url.pathname.slice('/api/atalhos/'.length);if(!resources.includes(resource))return reply({erro:'Consulta não encontrada.'},404);if(url.search)return reply({erro:'Use o link sem parâmetros adicionais.'},400);
 const match=/^Bearer (fp_at_[a-f0-9]{64})$/.exec(request.headers.get('authorization')||'');if(!match)return reply({erro:'Acesso do atalho ausente ou inválido.'},401);
 const hash=await digest(match[1]);
 const response=await fetch('https://hkfyvhthfshnddduckjs.supabase.co/rest/v1/rpc/fp_shortcut_read_v1',{method:'POST',redirect:'manual',signal:AbortSignal.timeout(12000),headers:{apikey:env.SUPABASE_BACKEND_KEY,'content-type':'application/json'},body:JSON.stringify({p_hash:hash,p_recurso:resource})});
 if(!response.ok)return reply({erro:'Acesso revogado, inválido ou indisponível.'},response.status===401||response.status===403?401:503);
 const data=await response.json();if(!Array.isArray(data))return reply({erro:'Resposta indisponível.'},503);return reply(data);
 }catch{return reply({erro:'Não foi possível consultar agora.'},503);}
}

