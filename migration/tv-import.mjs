import {getAccess,accessRPC} from './release/access.mjs';
const reply=(body,status=200)=>Response.json(body,{status,headers:{'cache-control':'no-store'}});
export function validateTVImport(data){
 if(!data||Array.isArray(data)||Object.keys(data).some(k=>!['registros','aplicar'].includes(k))||typeof data.aplicar!=='boolean'||!Array.isArray(data.registros)||data.registros.length<1||data.registros.length>2000)throw Error('Importação inválida');
 const seen=new Set();for(const r of data.registros){if(!r||Array.isArray(r)||Object.keys(r).some(k=>!['origem_id','nome','telefone','valor','data_vencimento','plano','situacao_origem'].includes(k))||typeof r.origem_id!=='string'||!/^[A-Za-z0-9_-]{1,80}$/.test(r.origem_id)||seen.has(r.origem_id)||typeof r.nome!=='string'||!r.nome.trim()||r.nome.length>240||typeof r.telefone!=='string'||r.telefone.length>40||r.telefone.replace(/\D/g,'')&&!/^\d{8,15}$/.test(r.telefone.replace(/\D/g,''))||typeof r.valor!=='number'||!Number.isFinite(r.valor)||r.valor<=0||r.valor>1000000||Math.abs(r.valor*100-Math.round(r.valor*100))>.00001||!/^20\d{2}-\d{2}-\d{2}$/.test(r.data_vencimento)||!Number.isFinite(Date.parse(r.data_vencimento))||new Date(r.data_vencimento).toISOString().slice(0,10)!==r.data_vencimento||r.plano!=null&&(typeof r.plano!=='string'||r.plano.length>240)||r.situacao_origem!=null&&(typeof r.situacao_origem!=='string'||r.situacao_origem.length>80))throw Error('Confira identificadores, contatos, valores e vencimentos.');seen.add(r.origem_id);}
 return data;
}
export async function tvImportEndpoint(request,env){
 const capabilities=new URL(request.url).pathname==='/api/clientes/integracao-tv'&&request.method==='GET';
 if(!capabilities&&(request.method!=='POST'||request.headers.get('origin')!==new URL(request.url).origin||request.headers.get('x-financeiro-operacao')!=='1'))return reply({erro:'Origem ou método não permitido.'},403);
 try{
 const session=await env.PROD_API.fetch(new Request('https://financeiroproweb.alisododo.workers.dev/api/me',{headers:{cookie:request.headers.get('cookie')||''}}));if(!session.ok)return reply({erro:'Entre novamente.'},401);const user=await session.json();if(!Number.isSafeInteger(user.id)||user.id<1)return reply({erro:'Sessão inválida.'},401);
 const enabled=await accessRPC(env,'fp_tv_habilitado_v1',{p_usuario:user.id});
 if(capabilities)return reply({enabled:enabled===true});
 if(enabled!==true)return reply({erro:'Integração disponível somente para o proprietário.'},403);
 if(!(await getAccess(env,user.id,'clientes')).allowed)return reply({erro:'Módulo Clientes bloqueado.'},403);
 if(!request.headers.get('content-type')?.startsWith('application/json'))return reply({erro:'Envie JSON.'},415);
 const reader=request.body?.getReader();let length=0;const chunks=[];if(reader)while(true){const {done,value}=await reader.read();if(done)break;length+=value.length;if(length>1048576){await reader.cancel();return reply({erro:'Arquivo muito grande.'},413);}chunks.push(value);}const bytes=new Uint8Array(length);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}
 let data;try{data=validateTVImport(JSON.parse(new TextDecoder().decode(bytes)));}catch(e){return reply({erro:e.message},400);}
 if(data.aplicar&&env.FINANCIAL_WRITES_ENABLED!=='true')return reply({erro:'Gravações indisponíveis.'},503);
 return reply(await accessRPC(env,'fp_clientes_tv_v1',{p_usuario:user.id,p_registros:data.registros,p_aplicar:data.aplicar}));
 }catch{return reply({erro:'Não foi possível importar. Confira o arquivo e tente novamente.'},503);}
}

