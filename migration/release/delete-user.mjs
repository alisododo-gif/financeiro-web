const base='https://hkfyvhthfshnddduckjs.supabase.co/rest/v1/rpc/fp_admin_excluir_usuario_v1';
const reply=(data,status=200)=>Response.json(data,{status,headers:{'cache-control':'no-store'}});
export async function deleteUserEndpoint(request,env){
 const url=new URL(request.url),match=url.pathname.match(/^\/api\/admin\/usuarios\/(\d+)(\/exclusao)?$/);
 if(!match)return reply({erro:'Rota inválida'},404);
 const preview=Boolean(match[2]);
 if(request.method!==(preview?'POST':'DELETE'))return reply({erro:'Método não permitido'},405);
 if(request.headers.get('origin')!==url.origin||request.headers.get('x-financeiro-admin')!=='1')return reply({erro:'Origem não autorizada'},403);
 try{
  const session=await env.PROD_API.fetch(new Request('https://financeiroproweb.alisododo.workers.dev/api/me',{headers:{cookie:request.headers.get('cookie')||''}}));
  if(!session.ok)return reply({erro:'Entre novamente.'},401);
  const actor=await session.json();if(actor.admin!==true)return reply({erro:'Somente administrador.'},403);
  const id=Number(match[1]);if(!Number.isSafeInteger(id)||id<1||id===actor.id)return reply({erro:'Usuário protegido ou inválido.'},403);
  const text=await request.text();if(text.length>1200)return reply({erro:'Dados muito grandes.'},413);
  const data=JSON.parse(text);
  if(!data||Array.isArray(data)||typeof data.confirmar!=='string'||Object.keys(data).some(k=>!['confirmar','apagar_dados','versao'].includes(k))||(!preview&&(typeof data.apagar_dados!=='boolean'||typeof data.versao!=='string')))return reply({erro:'Confirmação inválida.'},400);
  const response=await fetch(base,{method:'POST',redirect:'manual',signal:AbortSignal.timeout(20000),headers:{apikey:env.SUPABASE_BACKEND_KEY,'content-type':'application/json'},body:JSON.stringify({p_actor:actor.id,p_id:id,p_confirmar:data.confirmar,p_apagar_dados:data.apagar_dados===true,p_aplicar:!preview,p_versao:data.versao??null})});
  const result=await response.json();
  if(!response.ok){const statuses={'42501':403,'22023':400,'23503':409,'40001':409};return reply({erro:statuses[result.code]?result.message:'Não foi possível excluir. Nenhuma alteração foi concluída.'},statuses[result.code]||503);}
  return reply(result);
 }catch{return reply({erro:'Não foi possível concluir. Confira a lista antes de tentar novamente.'},503);}
}
export function simplifyDeleteConfirmation(source){
 const start=source.indexOf(" }else if(action==='excluir'){");
 const end=source.indexOf(' }else{return;}',start);
 if(start<0||end<0)throw Error('Fluxo administrativo não encontrado');
 return source.slice(0,start)+` }else if(action==='excluir'){
  const typed=await window.fpPrompt('Excluir o usuário '+name+'? Digite o nome exato para continuar.');
  if(typed===null)return;
  if(typed!==name){adminMessage('O nome informado não confere. Nada foi excluído.');return;}
  btn.disabled=true;
  try{
   const preview=await adminWrite('admin/usuarios/'+encodeURIComponent(user.id)+'/exclusao','POST',{confirmar:typed});
   const labels={movimentacoes:'movimentações',recebimentos:'recebimentos',clientes:'clientes',cartoes:'cartões',contas:'contas',metas:'metas',orcamentos:'orçamentos',operacoes:'operações',permissoes:'permissões',atalhos:'acessos de atalhos',alertas:'alertas',historico_acesso:'registros de acesso'};
   const summary=Object.entries(preview.contagens||{}).filter(([,n])=>n>0).map(([key,n])=>n+' '+(labels[key]||key)).join(', ');
   const question=preview.total>0?'Confirma excluir '+name+' e TODOS os dados vinculados? Serão removidos: '+summary+'. Não há desfazer.':'Confirma excluir definitivamente '+name+'? Não há dados vinculados e não há desfazer.';
   if(!await window.fpDialog(question))return;
   await adminWrite('admin/usuarios/'+encodeURIComponent(user.id),'DELETE',{confirmar:typed,apagar_dados:preview.total>0,versao:preview.versao});
   await loadAdmin();adminMessage('Usuário e dados vinculados excluídos.',true);
  }catch(error){adminMessage(error.message);}finally{btn.disabled=false;}
  return;
`+source.slice(end);
}

