CREATE TABLE financeiropro_operacoes.access_settings(
 id boolean PRIMARY KEY DEFAULT true CHECK(id),
 modules jsonb NOT NULL DEFAULT '{"visao_geral":true,"novo_lancamento":true,"movimentacoes":true,"cartoes":true,"recebimentos":true,"vencimentos":true,"clientes":true,"contas":true,"metas":true,"orcamentos":true}',
 contact text NOT NULL DEFAULT '5565992361636'
);
INSERT INTO financeiropro_operacoes.access_settings(id) VALUES(true);
CREATE TABLE financeiropro_operacoes.user_access(
 usuario_id bigint PRIMARY KEY REFERENCES public.usuarios(id) ON DELETE CASCADE,
 mode text NOT NULL CHECK(mode IN ('trial','licensed','blocked')),
 trial_started_at timestamptz, trial_expires_at timestamptz,
 modules jsonb NOT NULL DEFAULT '{}', updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK(mode<>'trial' OR (trial_started_at IS NOT NULL AND trial_expires_at=trial_started_at+interval '7 days'))
);
CREATE TABLE financeiropro_operacoes.access_audit(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,actor bigint NOT NULL,
 target bigint,action text NOT NULL,details jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE financeiropro_operacoes.access_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE financeiropro_operacoes.user_access ENABLE ROW LEVEL SECURITY;
ALTER TABLE financeiropro_operacoes.access_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON financeiropro_operacoes.access_settings,financeiropro_operacoes.user_access,financeiropro_operacoes.access_audit FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON financeiropro_operacoes.access_settings,financeiropro_operacoes.user_access,financeiropro_operacoes.access_audit TO service_role;
GRANT USAGE,SELECT ON SEQUENCE financeiropro_operacoes.access_audit_id_seq TO service_role;

CREATE FUNCTION public.fp_access_v1(p_usuario bigint,p_modulo text DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $f$
DECLARE u record;a record;c record;m jsonb;is_admin boolean;ok boolean;reason text;state text;
BEGIN
 SELECT usr.id,usr.status,usr.role,usr.is_admin INTO u FROM public.usuarios usr WHERE usr.id=p_usuario;
 SELECT * INTO c FROM financeiropro_operacoes.access_settings WHERE id=true;
 SELECT * INTO a FROM financeiropro_operacoes.user_access WHERE usuario_id=p_usuario;
 is_admin=coalesce(u.role='admin' OR u.is_admin,false);
 m=coalesce(c.modules,'{}')||coalesce(a.modules,'{}');
 IF is_admin THEN SELECT jsonb_object_agg(key,true) INTO m FROM jsonb_object_keys(c.modules) key; END IF;
 state=coalesce(a.mode,'licensed');
 ok=u.id IS NOT NULL AND u.status='ativo' AND (is_admin OR state='licensed' OR (state='trial' AND now()<a.trial_expires_at));
 reason=CASE WHEN u.id IS NULL OR u.status<>'ativo' THEN 'Sua conta está bloqueada. Entre em contato para liberar o acesso.'
 WHEN state='trial' AND now()>=a.trial_expires_at THEN 'Seu teste de 7 dias terminou. Entre em contato para contratar. Após confirmar o pagamento, o administrador liberará seu acesso.'
 WHEN state='blocked' THEN 'Seu acesso está bloqueado. Entre em contato para contratar ou solicitar a liberação.' ELSE '' END;
 IF ok AND p_modulo IS NOT NULL AND NOT coalesce((m->>p_modulo)::boolean,false) THEN ok=false;reason='Este módulo não está liberado para sua conta. Entre em contato com o administrador.'; END IF;
 RETURN jsonb_build_object('allowed',coalesce(ok,false),'mode',CASE WHEN is_admin THEN 'admin' ELSE state END,'expires_at',CASE WHEN state='trial' AND NOT is_admin THEN a.trial_expires_at ELSE NULL END,'modules',m,'overrides',coalesce(a.modules,'{}'),'contact',c.contact,'message',reason);
END $f$;

CREATE FUNCTION financeiropro_operacoes.require_access(p_usuario bigint,p_modulo text DEFAULT NULL) RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $f$
DECLARE a jsonb;BEGIN
 a=public.fp_access_v1(p_usuario,p_modulo);
 IF NOT coalesce((a->>'allowed')::boolean,false) THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE=a->>'message'; END IF;
END $f$;

CREATE FUNCTION public.fp_access_admin_v1(p_actor bigint,p_acao text,p_id bigint DEFAULT NULL,p_dados jsonb DEFAULT '{}') RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $f$
DECLARE c record;m jsonb;k text;v jsonb;mode_value text;result jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.usuarios WHERE id=p_actor AND status='ativo' AND (role='admin' OR is_admin)) THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Somente administrador'; END IF;
 SELECT * INTO c FROM financeiropro_operacoes.access_settings WHERE id=true;
 IF p_acao='listar' THEN
  SELECT coalesce(jsonb_agg(jsonb_build_object('id',u.id,'usuario',u.usuario,'status',u.status,'admin',u.role='admin' OR coalesce(u.is_admin,false),'access',public.fp_access_v1(u.id)) ORDER BY u.id),'[]') INTO result FROM public.usuarios u;
  RETURN jsonb_build_object('users',result,'defaults',c.modules,'contact',c.contact);
 END IF;
 IF jsonb_typeof(p_dados) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Dados inválidos'; END IF;
 IF p_acao='padrao' THEN
  IF EXISTS(SELECT 1 FROM jsonb_object_keys(p_dados) x WHERE x NOT IN ('modules','contact')) THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Campos inválidos'; END IF;
  m=coalesce(p_dados->'modules',c.modules);
  IF jsonb_typeof(m) IS DISTINCT FROM 'object' OR (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(m) key) IS DISTINCT FROM (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(c.modules) key) THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Módulos inválidos'; END IF;
  FOR k,v IN SELECT * FROM jsonb_each(m) LOOP IF jsonb_typeof(v)<>'boolean' THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Permissão inválida'; END IF;END LOOP;
  IF p_dados ? 'contact' AND (p_dados->>'contact') !~ '^[0-9]{10,15}$' THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Contato inválido';END IF;
  UPDATE financeiropro_operacoes.access_settings SET modules=m,contact=coalesce(p_dados->>'contact',contact) WHERE id=true;
 ELSIF p_acao='usuario' THEN
  IF EXISTS(SELECT 1 FROM jsonb_object_keys(p_dados) x WHERE x NOT IN ('mode','modules')) OR NOT EXISTS(SELECT 1 FROM public.usuarios WHERE id=p_id) THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Usuário ou campos inválidos';END IF;
  IF EXISTS(SELECT 1 FROM public.usuarios WHERE id=p_id AND (role='admin' OR is_admin)) THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Administrador protegido';END IF;
  SELECT modules,mode INTO m,mode_value FROM financeiropro_operacoes.user_access WHERE usuario_id=p_id;
  m=coalesce(p_dados->'modules',m,'{}');mode_value=coalesce(p_dados->>'mode',mode_value,'licensed');
  IF mode_value NOT IN ('trial','licensed','blocked') OR jsonb_typeof(m) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Acesso inválido';END IF;
  FOR k,v IN SELECT * FROM jsonb_each(m) LOOP IF NOT c.modules ? k OR jsonb_typeof(v)<>'boolean' THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Módulo inválido';END IF;END LOOP;
  INSERT INTO financeiropro_operacoes.user_access(usuario_id,mode,modules,trial_started_at,trial_expires_at)
  VALUES(p_id,mode_value,m,CASE WHEN mode_value='trial' THEN now() END,CASE WHEN mode_value='trial' THEN now()+interval '7 days' END)
  ON CONFLICT(usuario_id) DO UPDATE SET mode=excluded.mode,modules=excluded.modules,updated_at=now(),
   trial_started_at=CASE WHEN excluded.mode='trial' THEN coalesce(user_access.trial_started_at,excluded.trial_started_at) ELSE user_access.trial_started_at END,
   trial_expires_at=CASE WHEN excluded.mode='trial' THEN coalesce(user_access.trial_expires_at,excluded.trial_expires_at) ELSE user_access.trial_expires_at END;
  IF mode_value='licensed' THEN UPDATE public.usuarios SET status='ativo' WHERE id=p_id;END IF;
 ELSE RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Ação inválida';END IF;
 INSERT INTO financeiropro_operacoes.access_audit(actor,target,action,details) VALUES(p_actor,p_id,p_acao,p_dados);
 RETURN jsonb_build_object('ok',true);
END $f$;

-- Keep transactional financial rules intact; add a service-only authorization wrapper.
ALTER FUNCTION public.fp_financeiro_v1(bigint,text,text,bigint,jsonb,text,uuid) SET SCHEMA financeiropro_operacoes;
ALTER FUNCTION financeiropro_operacoes.fp_financeiro_v1(bigint,text,text,bigint,jsonb,text,uuid) RENAME TO financeiro_core_v1;
CREATE FUNCTION public.fp_financeiro_modulo_v1(p_usuario bigint,p_tabela text,p_acao text,p_id bigint DEFAULT NULL,p_dados jsonb DEFAULT '{}',p_versao text DEFAULT NULL,p_chave uuid DEFAULT NULL,p_modulo text DEFAULT NULL) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $f$
DECLARE m text;ok boolean=false;
BEGIN
 m=coalesce(p_modulo,CASE p_tabela WHEN 'contas_receber' THEN 'recebimentos' WHEN 'movimentacoes' THEN CASE WHEN p_acao IN ('criar','criar_lote') THEN 'novo_lancamento' ELSE 'movimentacoes' END ELSE p_tabela END);
 PERFORM financeiropro_operacoes.require_access(p_usuario,m);
 IF m='clientes' AND p_tabela='contas' AND p_acao='listar' THEN
  RETURN jsonb_build_object('registros',(SELECT coalesce(jsonb_agg(jsonb_build_object('id',c.id,'nome',c.nome) ORDER BY c.id),'[]') FROM public.contas c WHERE c.usuario_id=p_usuario));
 END IF;
 IF p_acao='listar' THEN
  ok=(m='visao_geral' OR (m IN ('novo_lancamento','movimentacoes','cartoes','vencimentos') AND p_tabela IN ('movimentacoes','contas','cartoes')) OR (m='orcamentos' AND p_tabela IN ('orcamentos','movimentacoes')) OR (m IN ('clientes','contas','metas','recebimentos') AND p_tabela=CASE WHEN m='recebimentos' THEN 'contas_receber' ELSE m END));
 ELSE
  ok=(m='novo_lancamento' AND p_tabela='movimentacoes' AND p_acao IN ('criar','criar_lote'))
   OR (m='movimentacoes' AND p_tabela='movimentacoes' AND p_acao IN ('editar','excluir'))
   OR (m IN ('clientes','contas','metas','orcamentos','recebimentos') AND p_tabela=CASE WHEN m='recebimentos' THEN 'contas_receber' ELSE m END)
   OR (m='cartoes' AND p_tabela='cartoes')
   OR (m='vencimentos' AND p_tabela='cartoes' AND p_acao IN ('fatura','quitar_fatura'))
   OR (m='vencimentos' AND p_tabela='movimentacoes' AND p_acao='editar' AND p_dados ? 'pago' AND (p_dados-'pago')='{}' AND EXISTS(SELECT 1 FROM public.movimentacoes WHERE id=p_id AND usuario_id=p_usuario AND tipo='Despesa'))
   OR (m='cartoes' AND p_tabela='movimentacoes' AND p_acao IN ('editar','excluir') AND EXISTS(SELECT 1 FROM public.movimentacoes WHERE id=p_id AND usuario_id=p_usuario AND forma_pagamento='Cartão de Crédito'));
 END IF;
 IF NOT coalesce(ok,false) THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Operação não permitida neste módulo'; END IF;
 RETURN financeiropro_operacoes.financeiro_core_v1(p_usuario,p_tabela,p_acao,p_id,p_dados,p_versao,p_chave);
END $f$;
CREATE FUNCTION public.fp_financeiro_v1(p_usuario bigint,p_tabela text,p_acao text,p_id bigint DEFAULT NULL,p_dados jsonb DEFAULT '{}',p_versao text DEFAULT NULL,p_chave uuid DEFAULT NULL) RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path=pg_catalog AS $f$
 SELECT public.fp_financeiro_modulo_v1(p_usuario,p_tabela,p_acao,p_id,p_dados,p_versao,p_chave,NULL)
$f$;

CREATE OR REPLACE FUNCTION public.fp_signup_pending(p_usuario text,p_senha_hash text,p_telefone text,p_ip_hash text) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $f$
DECLARE count_hits integer;bucket timestamptz=date_trunc('hour',now());new_id bigint;
BEGIN
 IF p_usuario IS NULL OR length(trim(p_usuario)) NOT BETWEEN 3 AND 80 OR p_usuario ~ '[[:cntrl:]]' OR p_senha_hash IS NULL OR p_senha_hash !~ '^[a-f0-9]{64}$' OR p_telefone IS NULL OR p_telefone !~ '^[0-9]{10,15}$' OR p_ip_hash IS NULL OR p_ip_hash !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Cadastro inválido'; END IF;
 INSERT INTO financeiropro_operacoes.signup_limits(ip_hash,window_start,hits) VALUES(p_ip_hash,bucket,1) ON CONFLICT(ip_hash,window_start) DO UPDATE SET hits=signup_limits.hits+1 RETURNING hits INTO count_hits;
 IF count_hits>5 THEN RETURN jsonb_build_object('limitado',true);END IF;
 DELETE FROM financeiropro_operacoes.signup_limits WHERE window_start<now()-interval '2 days';
 PERFORM pg_advisory_xact_lock(hashtextextended('fp-signup:'||lower(trim(p_usuario)),0));
 IF NOT EXISTS(SELECT 1 FROM public.usuarios WHERE lower(usuario)=lower(trim(p_usuario))) THEN
  INSERT INTO public.usuarios(usuario,senha,is_admin,status,valor_mensalidade,role,telefone) VALUES(trim(p_usuario),p_senha_hash,false,'ativo',0,'user',p_telefone) RETURNING id INTO new_id;
  INSERT INTO financeiropro_operacoes.user_access(usuario_id,mode,trial_started_at,trial_expires_at) VALUES(new_id,'trial',now(),now()+interval '7 days');
 END IF;
 RETURN jsonb_build_object('recebido',true);
END $f$;
REVOKE ALL ON FUNCTION public.fp_access_v1(bigint,text),public.fp_access_admin_v1(bigint,text,bigint,jsonb),public.fp_financeiro_v1(bigint,text,text,bigint,jsonb,text,uuid),public.fp_financeiro_modulo_v1(bigint,text,text,bigint,jsonb,text,uuid,text),financeiropro_operacoes.require_access(bigint,text),financeiropro_operacoes.financeiro_core_v1(bigint,text,text,bigint,jsonb,text,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.fp_access_v1(bigint,text),public.fp_access_admin_v1(bigint,text,bigint,jsonb),public.fp_financeiro_v1(bigint,text,text,bigint,jsonb,text,uuid),public.fp_financeiro_modulo_v1(bigint,text,text,bigint,jsonb,text,uuid,text),financeiropro_operacoes.require_access(bigint,text),financeiropro_operacoes.financeiro_core_v1(bigint,text,text,bigint,jsonb,text,uuid) TO service_role;
NOTIFY pgrst,'reload schema';
