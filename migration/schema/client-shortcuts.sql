CREATE OR REPLACE FUNCTION public.fp_shortcut_clients_manage_v1(p_actor bigint,p_acao text,p_hash text DEFAULT NULL) RETURNS jsonb LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE a jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.usuarios WHERE id=p_actor AND status='ativo') THEN RAISE EXCEPTION 'Acesso não autorizado' USING ERRCODE='42501';END IF;
 a=public.fp_access_v1(p_actor,'clientes');
 IF p_acao<>'revogar' AND NOT coalesce((a->>'allowed')::boolean,false) THEN RAISE EXCEPTION 'Módulo Clientes bloqueado' USING ERRCODE='42501';END IF;
 IF p_acao='criar' THEN
  IF p_hash IS NULL OR p_hash !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'Identificador inválido' USING ERRCODE='22023';END IF;
  INSERT INTO financeiropro_operacoes.shortcut_keys(usuario_id,token_hash) VALUES(p_actor,p_hash) ON CONFLICT(usuario_id) DO UPDATE SET token_hash=excluded.token_hash,created_at=now(),revoked=false;
 ELSIF p_acao='revogar' THEN UPDATE financeiropro_operacoes.shortcut_keys SET revoked=true WHERE usuario_id=p_actor;
 ELSIF p_acao<>'status' THEN RAISE EXCEPTION 'Ação inválida' USING ERRCODE='22023';END IF;
 RETURN jsonb_build_object('enabled',true,'active',EXISTS(SELECT 1 FROM financeiropro_operacoes.shortcut_keys WHERE usuario_id=p_actor AND NOT revoked));
END $fn$;
REVOKE ALL ON FUNCTION public.fp_shortcut_clients_manage_v1(bigint,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.fp_shortcut_clients_manage_v1(bigint,text,text) TO service_role;
DO $update$
DECLARE def text;
BEGIN
 def=pg_get_functiondef('public.fp_shortcut_read_v1(text,text)'::regprocedure);
 def=replace(def,$old$AND (u.is_admin OR u.role='admin')$old$,'');
 def=replace(def,'IF owner_id IS NULL OR NOT public.fp_tv_habilitado_v1(owner_id) THEN','IF owner_id IS NULL THEN');
 IF def NOT LIKE '%Somente clientes para este acesso%' THEN
  def=replace(def,'module=CASE p_recurso',$guard$IF p_recurso<>'clientes_cobrar_amanha' AND (NOT public.fp_tv_habilitado_v1(owner_id) OR NOT EXISTS(SELECT 1 FROM public.usuarios WHERE id=owner_id AND (is_admin OR role='admin'))) THEN RAISE EXCEPTION 'Somente clientes para este acesso' USING ERRCODE='42501';END IF; module=CASE p_recurso$guard$);
 END IF;
 IF def NOT LIKE '%Somente clientes para este acesso%' THEN RAISE EXCEPTION 'Estrutura inesperada';END IF;
 EXECUTE def;
END $update$;
NOTIFY pgrst,'reload schema';
