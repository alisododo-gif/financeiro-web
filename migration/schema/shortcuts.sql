CREATE TABLE IF NOT EXISTS financeiropro_operacoes.shortcut_keys(usuario_id integer PRIMARY KEY REFERENCES public.usuarios(id),token_hash text UNIQUE NOT NULL CHECK(token_hash ~ '^[a-f0-9]{64}$'),created_at timestamptz NOT NULL DEFAULT now(),revoked boolean NOT NULL DEFAULT false);
ALTER TABLE financeiropro_operacoes.shortcut_keys ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON financeiropro_operacoes.shortcut_keys FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON financeiropro_operacoes.shortcut_keys TO service_role;
CREATE OR REPLACE FUNCTION public.fp_shortcut_manage_v1(p_actor bigint,p_acao text,p_hash text DEFAULT NULL) RETURNS jsonb LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
BEGIN
 IF NOT public.fp_tv_habilitado_v1(p_actor) OR NOT EXISTS(SELECT 1 FROM public.usuarios WHERE id=p_actor AND status='ativo' AND (is_admin OR role='admin')) THEN RAISE EXCEPTION 'Acesso não autorizado' USING ERRCODE='42501';END IF;
 IF p_acao='criar' THEN
  IF p_hash IS NULL OR p_hash !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'Identificador inválido';END IF;
  INSERT INTO financeiropro_operacoes.shortcut_keys(usuario_id,token_hash) VALUES(p_actor,p_hash) ON CONFLICT(usuario_id) DO UPDATE SET token_hash=excluded.token_hash,created_at=now(),revoked=false;
 ELSIF p_acao='revogar' THEN UPDATE financeiropro_operacoes.shortcut_keys SET revoked=true WHERE usuario_id=p_actor;
 ELSIF p_acao<>'status' THEN RAISE EXCEPTION 'Ação inválida';END IF;
 RETURN jsonb_build_object('enabled',true,'active',EXISTS(SELECT 1 FROM financeiropro_operacoes.shortcut_keys WHERE usuario_id=p_actor AND NOT revoked));
END $fn$;
CREATE OR REPLACE FUNCTION public.fp_shortcut_read_v1(p_hash text,p_recurso text) RETURNS jsonb LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE owner_id bigint; result jsonb; access jsonb; module text;
BEGIN
 IF p_hash IS NULL OR p_hash !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION 'Acesso inválido' USING ERRCODE='42501';END IF;
 SELECT k.usuario_id INTO owner_id FROM financeiropro_operacoes.shortcut_keys k JOIN public.usuarios u ON u.id=k.usuario_id WHERE k.token_hash=p_hash AND NOT k.revoked AND u.status='ativo' AND (u.is_admin OR u.role='admin');
 IF owner_id IS NULL OR NOT public.fp_tv_habilitado_v1(owner_id) THEN RAISE EXCEPTION 'Acesso inválido' USING ERRCODE='42501';END IF;
 module=CASE p_recurso WHEN 'clientes_cobrar_amanha' THEN 'clientes' WHEN 'faturas_vencendo_hoje' THEN 'cartoes' WHEN 'movimentacoes_hoje' THEN 'movimentacoes' WHEN 'recebimentos_hoje' THEN 'recebimentos' WHEN 'usuarios' THEN 'clientes' ELSE NULL END;
 IF module IS NULL THEN RAISE EXCEPTION 'Consulta inválida';END IF;
 access=public.fp_access_v1(owner_id,module);IF NOT coalesce((access->>'allowed')::boolean,false) THEN RAISE EXCEPTION 'Módulo bloqueado' USING ERRCODE='42501';END IF;
 CASE p_recurso
 WHEN 'clientes_cobrar_amanha' THEN SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.nome),'[]') INTO result FROM (SELECT nome,telefone,valor FROM public.clientes_cobrar_amanha WHERE usuario_id=owner_id) x;
 WHEN 'usuarios' THEN
  -- The configured administrator's existing billing list; never expose credential columns.
  SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.usuario),'[]') INTO result FROM (SELECT usuario,telefone,valor_mensalidade,status FROM public.usuarios WHERE status='inativo') x;
 WHEN 'faturas_vencendo_hoje' THEN SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY x.nome_cartao),'[]') INTO result FROM (SELECT nome_cartao,dia_vencimento,nome_usuario,telefone FROM public.faturas_vencendo_hoje WHERE usuario_id=owner_id) x;
 WHEN 'movimentacoes_hoje' THEN SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') INTO result FROM (SELECT descricao,valor,data,usuario,telefone FROM public.movimentacoes_hoje WHERE usuario_id=owner_id AND pago=false) x;
 WHEN 'recebimentos_hoje' THEN SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') INTO result FROM (SELECT descricao,valor,data_recebimento,telefone,usuario FROM public.recebimentos_hoje WHERE usuario_id=owner_id AND recebido=false) x;
 END CASE;
 RETURN result;
END $fn$;
REVOKE ALL ON FUNCTION public.fp_shortcut_manage_v1(bigint,text,text),public.fp_shortcut_read_v1(text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.fp_shortcut_manage_v1(bigint,text,text),public.fp_shortcut_read_v1(text,text) TO service_role;
NOTIFY pgrst,'reload schema';
