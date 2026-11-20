const principal='https://financeiropro-migracao-preview.alisododo.workers.dev';
const reply=(body,status=200,extra={})=>Response.json(body,{status,headers:{'cache-control':'no-store','x-content-type-options':'nosniff',...extra}});
const hash=async value=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))),n=>n.toString(16).padStart(2,'0')).join('');
export async function changePassword(request,env){
 if(request.method!=='POST')return reply({erro:'Método não permitido'},405);
 if(request.headers.get('origin')!==new URL(request.url).origin||request.headers.get('x-financeiro-operacao')!=='1')return reply({erro:'Origem não autorizada'},403);
 if(!request.headers.get('content-type')?.startsWith('application/json'))return reply({erro:'Envie JSON'},415);
 if(!env.PROD_API?.fetch||!env.SUPABASE_BACKEND_KEY)return reply({erro:'Serviço indisponível'},503);
 try{
  const cookie=request.headers.get('cookie')||'';
  const session=await env.PROD_API.fetch(new Request(principal+'/api/me',{headers:{cookie}}));
  if(!session.ok)return reply({erro:'Entre novamente para alterar sua senha'},session.status===401?401:503);
  const user=await session.json();
  if(!Number.isSafeInteger(user?.id)||user.id<=0||typeof user.usuario!=='string')return reply({erro:'Sessão inválida'},403);
  const reader=request.body?.getReader();let size=0;const chunks=[];
  if(reader)while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>8192){await reader.cancel();return reply({erro:'Dados muito grandes'},413);}chunks.push(value);}
  const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
  let data;try{data=JSON.parse(new TextDecoder().decode(bytes));}catch{return reply({erro:'Dados inválidos'},400);}
  if(!data||Array.isArray(data)||Object.keys(data).some(k=>!['atual','nova','confirmacao'].includes(k))||typeof data.atual!=='string'||data.atual.length<1||data.atual.length>1024||typeof data.nova!=='string'||data.nova.length<8||data.nova.length>128||!data.nova.trim()||data.nova!==data.confirmacao||data.nova===data.atual)return reply({erro:'Use uma nova senha de 8 a 128 caracteres e confirme os mesmos caracteres'},400);
  // Reuse the legacy login's persistent IP and username rate limits.
  const verified=await env.PROD_API.fetch(new Request(principal+'/api/login',{method:'POST',headers:{origin:principal,'content-type':'application/json','cf-connecting-ip':request.headers.get('cf-connecting-ip')||'account-change'},body:JSON.stringify({usuario:user.usuario,senha:data.atual})}));
  if(!verified.ok)return reply({erro:verified.status===429?'Muitas tentativas. Aguarde um minuto.':'Não foi possível confirmar sua senha atual'},verified.status===429?429:verified.status===401?400:503);
  const oldHash=await hash(data.atual),newHash=await hash(data.nova);
  const key=env.SUPABASE_BACKEND_KEY;
  const updated=await fetch('https://hkfyvhthfshnddduckjs.supabase.co/rest/v1/rpc/fp_password_change_v1',{method:'POST',redirect:'error',signal:AbortSignal.timeout(15000),headers:{apikey:key,'content-type':'application/json'},body:JSON.stringify({p_usuario:user.id,p_atual:oldHash,p_nova:newHash})});
  if(!updated.ok)return reply({erro:'Não foi possível alterar sua senha. Tente novamente'},502);
  if((await updated.json())!==true)return reply({erro:'Sua conta mudou durante a operação. Entre novamente'},409);
  return reply({ok:true},200,{'set-cookie':'fp_session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict'});
 }catch{return reply({erro:'Não foi possível concluir a alteração. Tente novamente'},502);}
}

