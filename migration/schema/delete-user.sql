CREATE OR REPLACE FUNCTION public.fp_admin_excluir_usuario_v1(p_actor bigint,p_id bigint,p_confirmar text,p_apagar_dados boolean DEFAULT false,p_aplicar boolean DEFAULT false,p_versao text DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE target_user record; counts jsonb; version_value text; total_value bigint;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.usuarios WHERE id=p_actor AND status='ativo' AND (role='admin' OR is_admin)) THEN RAISE EXCEPTION 'Somente administrador' USING ERRCODE='42501'; END IF;
 IF p_aplicar THEN
  LOCK TABLE public.usuarios,public.movimentacoes,public.contas_receber,public.clientes,public.cartoes,public.contas,public.metas,public.orcamentos,financeiropro_operacoes.comandos,financeiropro_operacoes.user_access,financeiropro_operacoes.shortcut_keys,financeiropro_operacoes.telegram_daily_alerts,financeiropro_operacoes.access_audit IN SHARE ROW EXCLUSIVE MODE;
 END IF;
 SELECT id,usuario,role,is_admin INTO target_user FROM public.usuarios WHERE id=p_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'Usuário não encontrado' USING ERRCODE='22023'; END IF;
 IF p_actor=p_id OR target_user.role='admin' OR coalesce(target_user.is_admin,false) OR EXISTS(SELECT 1 FROM financeiropro_operacoes.tv_integration_owner WHERE usuario_id=p_id) THEN RAISE EXCEPTION 'Administrador ou proprietário protegido' USING ERRCODE='42501'; END IF;
 IF p_confirmar IS DISTINCT FROM target_user.usuario THEN RAISE EXCEPTION 'Digite exatamente o nome do usuário' USING ERRCODE='22023'; END IF;
 -- Never cascade into another owner's records, even if an old inconsistent link exists.
 IF EXISTS(SELECT 1 FROM public.movimentacoes m JOIN public.contas c ON c.id=m.conta_id WHERE c.usuario_id=p_id AND m.usuario_id IS DISTINCT FROM p_id)
 OR EXISTS(SELECT 1 FROM public.clientes m JOIN public.contas c ON c.id=m.conta_id WHERE c.usuario_id=p_id AND m.usuario_id IS DISTINCT FROM p_id)
 OR EXISTS(SELECT 1 FROM public.movimentacoes m JOIN public.cartoes c ON c.id=m.cartao_id WHERE c.usuario_id=p_id AND m.usuario_id IS DISTINCT FROM p_id) THEN RAISE EXCEPTION 'Vínculo inconsistente entre usuários; exclusão bloqueada' USING ERRCODE='23503'; END IF;
 counts=jsonb_build_object(
 'movimentacoes',(SELECT count(*) FROM public.movimentacoes WHERE usuario_id=p_id),
 'recebimentos',(SELECT count(*) FROM public.contas_receber WHERE usuario_id=p_id),
 'clientes',(SELECT count(*) FROM public.clientes WHERE usuario_id=p_id),
 'cartoes',(SELECT count(*) FROM public.cartoes WHERE usuario_id=p_id),
 'contas',(SELECT count(*) FROM public.contas WHERE usuario_id=p_id),
 'metas',(SELECT count(*) FROM public.metas WHERE usuario_id=p_id),
 'orcamentos',(SELECT count(*) FROM public.orcamentos WHERE usuario_id=p_id),
 'operacoes',(SELECT count(*) FROM financeiropro_operacoes.comandos WHERE usuario_id=p_id),
 'permissoes',(SELECT count(*) FROM financeiropro_operacoes.user_access WHERE usuario_id=p_id),
 'atalhos',(SELECT count(*) FROM financeiropro_operacoes.shortcut_keys WHERE usuario_id=p_id),
 'alertas',(SELECT count(*) FROM financeiropro_operacoes.telegram_daily_alerts WHERE usuario_id=p_id),
 'historico_acesso',(SELECT count(*) FROM financeiropro_operacoes.access_audit WHERE actor=p_id OR target=p_id));
 SELECT sum(value::text::bigint) INTO total_value FROM jsonb_each(counts);
 version_value=md5(p_id::text||':'||counts::text);
 IF NOT p_aplicar THEN RETURN jsonb_build_object('contagens',counts,'total',total_value,'versao',version_value,'aplicado',false); END IF;
 IF p_versao IS DISTINCT FROM version_value THEN RAISE EXCEPTION 'Os dados mudaram. Confira novamente a exclusão' USING ERRCODE='40001'; END IF;
 IF total_value>0 AND p_apagar_dados IS DISTINCT FROM true THEN RAISE EXCEPTION 'Confirme também a exclusão dos dados vinculados' USING ERRCODE='22023'; END IF;
 DELETE FROM public.movimentacoes WHERE usuario_id=p_id;
 DELETE FROM public.contas_receber WHERE usuario_id=p_id;
 DELETE FROM public.clientes WHERE usuario_id=p_id;
 DELETE FROM public.cartoes WHERE usuario_id=p_id;
 DELETE FROM public.contas WHERE usuario_id=p_id;
 DELETE FROM public.metas WHERE usuario_id=p_id;
 DELETE FROM public.orcamentos WHERE usuario_id=p_id;
 DELETE FROM financeiropro_operacoes.comandos WHERE usuario_id=p_id;
 DELETE FROM financeiropro_operacoes.shortcut_keys WHERE usuario_id=p_id;
 DELETE FROM financeiropro_operacoes.telegram_daily_alerts WHERE usuario_id=p_id;
 DELETE FROM financeiropro_operacoes.user_access WHERE usuario_id=p_id;
 DELETE FROM financeiropro_operacoes.access_audit WHERE actor=p_id OR target=p_id;
 DELETE FROM public.usuarios WHERE id=p_id;
 -- Minimal administrative event, without the deleted user's name/contact/financial data.
 INSERT INTO financeiropro_operacoes.access_audit(actor,target,action,details) VALUES(p_actor,NULL,'excluir_usuario',jsonb_build_object('registros_removidos',total_value));
 RETURN jsonb_build_object('excluido',true,'contagens',counts,'total',total_value,'aplicado',true);
END $fn$;
REVOKE ALL ON FUNCTION public.fp_admin_excluir_usuario_v1(bigint,bigint,text,boolean,boolean,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.fp_admin_excluir_usuario_v1(bigint,bigint,text,boolean,boolean,text) TO service_role;
