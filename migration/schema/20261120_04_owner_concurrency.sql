CREATE OR REPLACE FUNCTION financeiropro_operacoes.financeiro_core_v1(p_usuario bigint, p_tabela text, p_acao text, p_id bigint DEFAULT NULL::bigint, p_dados jsonb DEFAULT '{}'::jsonb, p_versao text DEFAULT NULL::text, p_chave uuid DEFAULT NULL::uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE
 allowed text[]; required text[]; k text; v jsonb; before_row jsonb; after_row jsonb;
 answer jsonb; saved record; new_id bigint; fields text; setters text; n numeric; batch_row jsonb; batch_result jsonb;
 req jsonb; rows jsonb; invoice_version text; ref text; d date; closing integer; sequence_name text;
BEGIN
 IF p_usuario IS NULL OR p_usuario<=0 OR NOT EXISTS(
   SELECT 1 FROM public.usuarios WHERE id=p_usuario AND status='ativo'
 ) THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Usuário sem acesso ativo'; END IF;
 IF p_tabela NOT IN ('contas','cartoes','movimentacoes','contas_receber','metas','orcamentos','clientes')
    OR p_tabela IS NULL OR p_acao IS NULL THEN
   RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Recurso inválido'; END IF;
 IF jsonb_typeof(p_dados) IS DISTINCT FROM 'object' THEN
   RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Dados inválidos'; END IF;
 IF p_acao='listar' THEN
   IF p_dados ? 'periodo' AND (p_dados->>'periodo') !~ '^20[0-9]{2}-(0[1-9]|1[0-2])$' THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Período inválido'; END IF;
   IF p_dados ? 'ano' AND (p_dados->>'ano') !~ '^20[0-9]{2}$' THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Ano inválido'; END IF;
   IF p_dados ? 'periodo' AND p_dados ? 'ano' THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Escolha mês ou ano'; END IF;
   IF p_id IS NOT NULL THEN
    EXECUTE format('SELECT coalesce(jsonb_agg(to_jsonb(x)||jsonb_build_object(''_versao'',md5(to_jsonb(x)::text))),''[]''::jsonb) FROM public.%I x WHERE usuario_id=$1 AND id=$2',p_tabela) INTO rows USING p_usuario,p_id;
   ELSIF p_tabela='movimentacoes' AND (p_dados ? 'periodo' OR p_dados ? 'ano') THEN
    SELECT coalesce(jsonb_agg(to_jsonb(x)||jsonb_build_object('_versao',md5(to_jsonb(x)::text)) ORDER BY x.id),'[]'::jsonb) INTO rows
    FROM public.movimentacoes x WHERE x.usuario_id=p_usuario AND (
      (p_dados ? 'periodo' AND financeiropro_operacoes.competencia_v1(x.data,x.forma_pagamento,x.mes_fatura)=p_dados->>'periodo')
      OR (p_dados ? 'ano' AND financeiropro_operacoes.competencia_v1(x.data,x.forma_pagamento,x.mes_fatura)>=p_dados->>'ano'||'-01'
         AND financeiropro_operacoes.competencia_v1(x.data,x.forma_pagamento,x.mes_fatura)<=p_dados->>'ano'||'-12')
      OR (p_dados->>'pendentes_cartao'='true' AND x.forma_pagamento='Cartão de Crédito' AND x.tipo='Despesa' AND x.pago IS DISTINCT FROM true));
   ELSIF p_tabela='contas_receber' AND p_dados ? 'periodo' THEN
    SELECT coalesce(jsonb_agg(to_jsonb(x)||jsonb_build_object('_versao',md5(to_jsonb(x)::text)) ORDER BY x.id),'[]'::jsonb) INTO rows
    FROM public.contas_receber x WHERE x.usuario_id=p_usuario AND left(x.data_recebimento,7)=p_dados->>'periodo';
   ELSE
    EXECUTE format('SELECT coalesce(jsonb_agg(to_jsonb(x)||jsonb_build_object(''_versao'',md5(to_jsonb(x)::text)) ORDER BY x.id),''[]''::jsonb) FROM public.%I x WHERE usuario_id=$1',p_tabela) INTO rows USING p_usuario;
   END IF;
   RETURN jsonb_build_object('registros',rows,'schema','public');
 END IF;
 -- Serialize writes only within this owner; sequences remain globally atomic.
 IF p_acao<>'fatura' THEN PERFORM pg_advisory_xact_lock(hashtextextended('fp-owner:'||p_usuario::text,0)); END IF;
 IF p_acao NOT IN ('criar','criar_lote','editar','excluir','quitar_fatura','fatura') THEN
   RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Ação inválida'; END IF;
 IF p_acao<>'fatura' THEN
   IF p_chave IS NULL THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Chave de repetição obrigatória'; END IF;
   req=jsonb_build_object('tabela',p_tabela,'acao',p_acao,'id',p_id,'dados',p_dados,'versao',p_versao);
   SELECT * INTO saved FROM financeiropro_operacoes.comandos WHERE usuario_id=p_usuario AND chave=p_chave;
   IF FOUND THEN
     IF saved.pedido<>req THEN RAISE EXCEPTION USING ERRCODE='40001',MESSAGE='Chave já utilizada com outros dados'; END IF;
     RETURN saved.resposta;
   END IF;
 END IF;
 IF p_acao='criar_lote' THEN
   IF p_tabela<>'movimentacoes' OR jsonb_typeof(p_dados->'registros') IS DISTINCT FROM 'array' THEN
     RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Lote inválido'; END IF;
   IF jsonb_array_length(p_dados->'registros') NOT BETWEEN 1 AND 72 THEN
     RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Quantidade inválida'; END IF;
   rows='[]'::jsonb;
   FOR batch_row IN SELECT * FROM jsonb_array_elements(p_dados->'registros') LOOP
     batch_result=public.fp_financeiro_v1(p_usuario,'movimentacoes','criar',null,batch_row,null,gen_random_uuid());
     rows=rows||jsonb_build_array(batch_result->'registro');
   END LOOP;
   answer=jsonb_build_object('gravado',true,'schema','public','registros',rows);
 ELSIF p_acao IN ('fatura','quitar_fatura') THEN
   ref=p_dados->>'competencia';
   IF p_tabela<>'cartoes' OR ref IS NULL OR ref !~ '^(0[1-9]|1[0-2])/20[0-9]{2}$' OR NOT EXISTS(
     SELECT 1 FROM public.cartoes WHERE id=p_id AND usuario_id=p_usuario
   ) THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Fatura inválida'; END IF;
   SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY id),'[]'::jsonb) INTO rows
    FROM public.movimentacoes m WHERE usuario_id=p_usuario AND cartao_id=p_id
    AND mes_fatura=ref AND tipo='Despesa' AND forma_pagamento='Cartão de Crédito';
   invoice_version=md5(rows::text);
   IF p_acao='fatura' THEN RETURN jsonb_build_object('registros',rows,'_versao',invoice_version); END IF;
   IF p_versao IS DISTINCT FROM invoice_version THEN RAISE EXCEPTION USING ERRCODE='40001',MESSAGE='Fatura alterada. Atualize a consulta'; END IF;
   UPDATE public.movimentacoes SET pago=true WHERE usuario_id=p_usuario AND cartao_id=p_id
    AND mes_fatura=ref AND tipo='Despesa' AND forma_pagamento='Cartão de Crédito' AND pago IS DISTINCT FROM true;
   GET DIAGNOSTICS new_id=ROW_COUNT;
   answer=jsonb_build_object('quantidade',new_id,'gravado',true,'schema','public');
 ELSE
   CASE p_tabela
    WHEN 'contas' THEN allowed=ARRAY['nome','saldo']; required=ARRAY['nome','saldo'];
    WHEN 'cartoes' THEN allowed=ARRAY['nome_cartao','limite','dia_fechamento','dia_vencimento']; required=allowed;
    WHEN 'movimentacoes' THEN allowed=ARRAY['conta_id','cartao_id','descricao','valor','tipo','forma_pagamento','data','categoria','mes_fatura','tags','pago']; required=ARRAY['descricao','valor','tipo','forma_pagamento','data','categoria','pago'];
    WHEN 'contas_receber' THEN allowed=ARRAY['descricao','valor','data_recebimento','recebido']; required=allowed;
    WHEN 'metas' THEN allowed=ARRAY['nome_meta','valor_alvo','valor_poupado','prazo']; required=allowed;
    WHEN 'clientes' THEN allowed=ARRAY['nome','telefone','valor','data_vencimento','status','conta_id']; required=ARRAY['nome','telefone','valor','status'];
    WHEN 'orcamentos' THEN allowed=ARRAY['categoria','limite']; required=ARRAY['limite'];
   END CASE;
   IF p_acao<>'criar' THEN
     EXECUTE format('SELECT to_jsonb(x) FROM public.%I x WHERE id=$1 AND usuario_id=$2 FOR UPDATE',p_tabela) INTO before_row USING p_id,p_usuario;
     IF before_row IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0002',MESSAGE='Registro não encontrado'; END IF;
     IF p_versao IS DISTINCT FROM md5(before_row::text) THEN RAISE EXCEPTION USING ERRCODE='40001',MESSAGE='Registro alterado. Atualize a consulta'; END IF;
   END IF;
   IF p_acao='excluir' THEN
     IF (p_tabela='contas' AND EXISTS(SELECT 1 FROM public.movimentacoes WHERE conta_id=p_id))
      OR (p_tabela='cartoes' AND EXISTS(SELECT 1 FROM public.movimentacoes WHERE cartao_id=p_id)) THEN
       RAISE EXCEPTION USING ERRCODE='23503',MESSAGE='O registro tem movimentações associadas. Preserve o histórico';
     END IF;
     EXECUTE format('DELETE FROM public.%I WHERE id=$1 AND usuario_id=$2',p_tabela) USING p_id,p_usuario;
   ELSE
     FOR k IN SELECT jsonb_object_keys(p_dados) LOOP
       IF NOT k=ANY(allowed) THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Campo não permitido: '||k; END IF;
     END LOOP;
     IF p_dados='{}'::jsonb THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Preencha os campos'; END IF;
     after_row=coalesce(before_row,'{}'::jsonb)||p_dados;
     IF p_tabela='clientes' THEN
       IF jsonb_typeof(after_row->'telefone') IS DISTINCT FROM 'string' OR length(after_row->>'telefone')>40 OR (regexp_replace(after_row->>'telefone','[^0-9]','','g') !~ '^[0-9]{8,15}$' AND NOT (after_row->>'telefone'='' AND after_row->'referencia_tv' IS NOT NULL AND after_row->'referencia_tv'<>'null'::jsonb)) THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Telefone invalido: use DDD e numero'; END IF;
       after_row=after_row||jsonb_build_object('telefone',regexp_replace(after_row->>'telefone','[^0-9]','','g'));
       IF after_row->>'status' IS NOT NULL AND after_row->>'status' NOT IN ('Pendente','Pago') THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Situacao invalida'; END IF;
     END IF;
     IF p_tabela='orcamentos' AND coalesce(trim(after_row->>'categoria'),'')='' THEN
       after_row=after_row||jsonb_build_object('categoria',null);
     END IF;
     IF p_acao='criar' THEN
       IF p_tabela='movimentacoes' THEN after_row=jsonb_build_object('pago',false)||after_row; END IF;
       IF p_tabela='contas_receber' THEN after_row=jsonb_build_object('recebido',false,'created_at',now())||after_row; END IF;
       IF p_tabela='clientes' THEN after_row=jsonb_build_object('status','Pendente')||after_row; END IF;
       IF p_tabela='metas' THEN after_row=jsonb_build_object('valor_poupado',0)||after_row; END IF;
       IF p_tabela='cartoes' THEN after_row=jsonb_build_object('criado_em',now())||after_row; END IF;
     END IF;
     FOREACH k IN ARRAY required LOOP
       IF after_row->k IS NULL OR after_row->k='null'::jsonb THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Campo obrigatório: '||k; END IF;
     END LOOP;
     FOR k,v IN SELECT * FROM jsonb_each(after_row) LOOP
       IF k=ANY(ARRAY['nome','nome_cartao','nome_meta','descricao','categoria','tags']) AND v<>'null'::jsonb THEN
         IF jsonb_typeof(v)<>'string' OR length(v#>>'{}')>240 OR (k<>'tags' AND length(trim(v#>>'{}'))<1) THEN
           RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Texto inválido: '||k; END IF;
       END IF;
       IF k=ANY(ARRAY['saldo','limite','valor','valor_alvo','valor_poupado']) THEN
         IF jsonb_typeof(v)<>'number' THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Valor inválido'; END IF;
         n=(v#>>'{}')::numeric;
         IF abs(n)>1000000 OR n<>round(n,2) OR (k<>'saldo' AND n<0) OR (k IN ('valor','valor_alvo') AND n=0) THEN
           RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Valor fora dos limites ou sem centavos válidos'; END IF;
       END IF;
       IF k IN ('pago','recebido') AND jsonb_typeof(v)<>'boolean' THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Situação inválida'; END IF;
       IF k IN ('data','data_recebimento','prazo','data_vencimento') AND v<>'null'::jsonb THEN
         IF jsonb_typeof(v)<>'string' OR (v#>>'{}') !~ '^20[0-9]{2}-[0-9]{2}-[0-9]{2}$' THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Data inválida'; END IF;
         d=(v#>>'{}')::date;
         IF d NOT BETWEEN date '2020-01-01' AND date '2099-12-31' THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Data fora dos limites'; END IF;
       END IF;
     END LOOP;
     IF p_tabela='cartoes' AND ((after_row->>'dia_fechamento')::numeric NOT BETWEEN 1 AND 31
        OR (after_row->>'dia_vencimento')::numeric NOT BETWEEN 1 AND 31
        OR (after_row->>'dia_fechamento')::numeric<>trunc((after_row->>'dia_fechamento')::numeric)
        OR (after_row->>'dia_vencimento')::numeric<>trunc((after_row->>'dia_vencimento')::numeric)) THEN
       RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Dia do cartão inválido'; END IF;
     IF p_tabela='movimentacoes' THEN
       IF after_row->>'tipo' NOT IN ('Receita','Despesa') OR after_row->>'forma_pagamento' NOT IN ('Pix','Dinheiro','Cartão de Crédito','Cartão de Débito','Boleto') THEN
         RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Tipo ou forma inválida'; END IF;
       IF after_row->>'forma_pagamento'='Cartão de Crédito' THEN
         SELECT dia_fechamento INTO closing FROM public.cartoes WHERE id=(after_row->>'cartao_id')::bigint AND usuario_id=p_usuario;
         IF after_row->>'tipo'<>'Despesa' OR closing IS NULL THEN
           RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Cartão ou competência inválida'; END IF;
         IF p_acao='criar' OR after_row->'data' IS DISTINCT FROM before_row->'data' OR after_row->'cartao_id' IS DISTINCT FROM before_row->'cartao_id' OR after_row->'forma_pagamento' IS DISTINCT FROM before_row->'forma_pagamento' THEN
           d=(after_row->>'data')::date;
           IF extract(day FROM d)>=least(closing,extract(day FROM (date_trunc('month',d)+interval '1 month - 1 day'))) THEN d=(date_trunc('month',d)+interval '1 month')::date; END IF;
           after_row=after_row||jsonb_build_object('mes_fatura',to_char(d,'MM/YYYY'));
         END IF;
         after_row=after_row||jsonb_build_object('conta_id',null);
       ELSE
         IF NOT EXISTS(SELECT 1 FROM public.contas WHERE id=(after_row->>'conta_id')::bigint AND usuario_id=p_usuario) THEN
           RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Conta não pertence ao usuário'; END IF;
         after_row=after_row||jsonb_build_object('cartao_id',null,'mes_fatura',null);
       END IF;
     END IF;
     IF p_acao='criar' THEN
       sequence_name=pg_get_serial_sequence('public.'||p_tabela,'id');
       IF sequence_name IS NULL THEN RAISE EXCEPTION USING ERRCODE='55000',MESSAGE='Sequência de identificadores indisponível'; END IF;
       new_id=nextval(sequence_name::regclass);
       after_row=after_row||jsonb_build_object('id',new_id,'usuario_id',p_usuario);
       EXECUTE format('INSERT INTO public.%I OVERRIDING SYSTEM VALUE SELECT * FROM jsonb_populate_record(NULL::public.%I,$1) RETURNING to_jsonb(%I.*)',p_tabela,p_tabela,p_tabela) INTO after_row USING after_row;
     ELSE
       SELECT string_agg(format('%I=r.%I',col,col),',') INTO setters FROM unnest(allowed) AS col;
       EXECUTE format('UPDATE public.%I x SET %s FROM jsonb_populate_record(NULL::public.%I,$1) r WHERE x.id=$2 AND x.usuario_id=$3 RETURNING to_jsonb(x)',p_tabela,setters,p_tabela) INTO after_row USING after_row,p_id,p_usuario;
     END IF;
   END IF;
   answer=jsonb_build_object('gravado',true,'schema','public','registro',
    CASE WHEN p_acao='excluir' THEN NULL ELSE after_row||jsonb_build_object('_versao',md5(after_row::text)) END);
 END IF;
 INSERT INTO financeiropro_operacoes.comandos(usuario_id,chave,pedido,resposta) VALUES(p_usuario,p_chave,req,answer);
 RETURN answer;
END $function$;

CREATE OR REPLACE FUNCTION financeiropro_operacoes.reabrir_fatura_v1(p_usuario bigint, p_id bigint, p_dados jsonb, p_versao text, p_chave uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE rows jsonb;version text;saved record;req jsonb;answer jsonb;changed integer;competencia text=p_dados->>'competencia';
BEGIN
 IF p_chave IS NULL OR competencia IS NULL OR competencia !~ '^(0[1-9]|1[0-2])/20[0-9]{2}$' OR (p_dados-'competencia')<>'{}'::jsonb THEN RAISE EXCEPTION 'Dados da fatura inválidos' USING ERRCODE='22023';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('fp-owner:'||p_usuario::text,0));
 IF NOT EXISTS(SELECT 1 FROM public.usuarios WHERE id=p_usuario AND status='ativo') OR NOT EXISTS(SELECT 1 FROM public.cartoes WHERE id=p_id AND usuario_id=p_usuario) THEN RAISE EXCEPTION 'Fatura não encontrada' USING ERRCODE='42501';END IF;
 req=jsonb_build_object('tabela','cartoes','acao','reabrir_fatura','id',p_id,'dados',p_dados,'versao',p_versao);
 SELECT * INTO saved FROM financeiropro_operacoes.comandos WHERE usuario_id=p_usuario AND chave=p_chave;
 IF FOUND THEN IF saved.pedido<>req THEN RAISE EXCEPTION 'Chave utilizada com outros dados' USING ERRCODE='40001';END IF;RETURN saved.resposta;END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY id),'[]') INTO rows FROM public.movimentacoes m WHERE usuario_id=p_usuario AND cartao_id=p_id AND mes_fatura=competencia AND tipo='Despesa' AND forma_pagamento='Cartão de Crédito';
 version=md5(rows::text);IF p_versao IS DISTINCT FROM version THEN RAISE EXCEPTION 'Fatura alterada. Atualize a consulta' USING ERRCODE='40001';END IF;
 IF jsonb_array_length(rows)=0 OR EXISTS(SELECT 1 FROM jsonb_array_elements(rows) r WHERE (r->>'pago')::boolean IS DISTINCT FROM true) THEN RAISE EXCEPTION 'Somente uma fatura totalmente paga pode ter o pagamento desfeito' USING ERRCODE='22023';END IF;
 UPDATE public.movimentacoes SET pago=false WHERE usuario_id=p_usuario AND cartao_id=p_id AND mes_fatura=competencia AND tipo='Despesa' AND forma_pagamento='Cartão de Crédito' AND pago=true;
 GET DIAGNOSTICS changed=ROW_COUNT;answer=jsonb_build_object('gravado',true,'quantidade',changed,'schema','public');
 INSERT INTO financeiropro_operacoes.comandos(usuario_id,chave,pedido,resposta) VALUES(p_usuario,p_chave,req,answer);
 RETURN answer;
END $function$;

CREATE OR REPLACE FUNCTION public.fp_admin_excluir_usuario_v1(p_actor bigint, p_id bigint, p_confirmar text, p_apagar_dados boolean DEFAULT false, p_aplicar boolean DEFAULT false, p_versao text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE target_user record; counts jsonb; version_value text; total_value bigint;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.usuarios WHERE id=p_actor AND status='ativo' AND (role='admin' OR is_admin)) THEN RAISE EXCEPTION 'Somente administrador' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('fp-owner:'||p_id::text,0));

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
END $function$;

CREATE OR REPLACE FUNCTION public.fp_clientes_tv_v1(p_usuario bigint, p_registros jsonb, p_aplicar boolean DEFAULT false)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE r jsonb; due date; amount numeric; phone text; identifier text; seen text[]='{}'; existing bigint; created integer=0; updated integer=0; unchanged integer=0; access jsonb;
BEGIN
 IF NOT public.fp_tv_habilitado_v1(p_usuario) THEN RAISE EXCEPTION 'Integração exclusiva do proprietário' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.usuarios WHERE id=p_usuario AND status='ativo') THEN RAISE EXCEPTION 'Usuário sem acesso ativo' USING ERRCODE='42501'; END IF;
 access=public.fp_access_v1(p_usuario,'clientes');
 IF NOT coalesce((access->>'allowed')::boolean,false) THEN RAISE EXCEPTION 'Módulo sem acesso' USING ERRCODE='42501'; END IF;
 IF jsonb_typeof(p_registros) IS DISTINCT FROM 'array' OR jsonb_array_length(p_registros) NOT BETWEEN 1 AND 2000 THEN RAISE EXCEPTION 'Importação inválida'; END IF;
 -- Validate the entire batch before any insertion; no credentials are accepted.
 FOR r IN SELECT * FROM jsonb_array_elements(p_registros) LOOP
  IF jsonb_typeof(r) IS DISTINCT FROM 'object' OR EXISTS(SELECT 1 FROM jsonb_object_keys(r) k WHERE k NOT IN ('origem_id','nome','telefone','valor','data_vencimento','plano','situacao_origem')) THEN RAISE EXCEPTION 'Campos inválidos'; END IF;
  identifier=r->>'origem_id';
  IF identifier IS NULL OR identifier !~ '^[A-Za-z0-9_-]{1,80}$' OR identifier=ANY(seen) THEN RAISE EXCEPTION 'Identificador de origem inválido ou repetido'; END IF;
  seen=array_append(seen,identifier);
  IF jsonb_typeof(r->'nome') IS DISTINCT FROM 'string' OR length(trim(r->>'nome')) NOT BETWEEN 1 AND 240 OR coalesce(length(r->>'plano'),0)>240 OR coalesce(length(r->>'situacao_origem'),0)>80 THEN RAISE EXCEPTION 'Nome ou plano inválido'; END IF;
  IF jsonb_typeof(r->'valor') IS DISTINCT FROM 'number' THEN RAISE EXCEPTION 'Valor inválido'; END IF;
  amount=(r->>'valor')::numeric;
  IF amount NOT BETWEEN .01 AND 1000000 OR amount<>round(amount,2) THEN RAISE EXCEPTION 'Valor inválido'; END IF;
  IF coalesce(r->>'data_vencimento','') !~ '^20[0-9]{2}-[0-9]{2}-[0-9]{2}$' THEN RAISE EXCEPTION 'Vencimento inválido'; END IF;
  due=(r->>'data_vencimento')::date;
  IF due NOT BETWEEN date '2020-01-01' AND date '2099-12-31' THEN RAISE EXCEPTION 'Vencimento inválido'; END IF;
  IF jsonb_typeof(r->'telefone') IS DISTINCT FROM 'string' OR length(r->>'telefone')>40 THEN RAISE EXCEPTION 'Telefone inválido'; END IF;
  phone=regexp_replace(r->>'telefone','[^0-9]','','g');
  IF phone<>'' AND phone !~ '^[0-9]{8,15}$' THEN RAISE EXCEPTION 'Telefone inválido'; END IF;
 END LOOP;
 IF p_aplicar THEN PERFORM pg_advisory_xact_lock(hashtextextended('fp-owner:'||p_usuario::text,0)); END IF;
 FOR r IN SELECT * FROM jsonb_array_elements(p_registros) LOOP
  SELECT id INTO existing FROM public.clientes WHERE usuario_id=p_usuario AND referencia_tv->>'origem'='painel.newbr.top' AND referencia_tv->>'id'=r->>'origem_id';
  IF existing IS NULL THEN
   created=created+1;
   IF p_aplicar THEN
    INSERT INTO public.clientes(nome,telefone,valor,status,data_vencimento,usuario_id,referencia_tv)
    VALUES(trim(r->>'nome'),regexp_replace(r->>'telefone','[^0-9]','','g'),(r->>'valor')::numeric,'Pendente',(r->>'data_vencimento')::date,p_usuario,
      jsonb_build_object('id',r->>'origem_id','usuario',r->>'nome','plano',r->>'plano','situacao',r->>'situacao_origem','origem','painel.newbr.top'));
   END IF;
  ELSE
   IF NOT EXISTS(SELECT 1 FROM public.clientes c WHERE c.id=existing AND c.usuario_id=p_usuario AND
      (c.valor IS DISTINCT FROM (r->>'valor')::numeric OR c.data_vencimento IS DISTINCT FROM (r->>'data_vencimento')::date OR
       c.referencia_tv IS DISTINCT FROM jsonb_build_object('id',r->>'origem_id','usuario',r->>'nome','plano',r->>'plano','situacao',r->>'situacao_origem','origem','painel.newbr.top'))) THEN
    unchanged=unchanged+1;CONTINUE;
   END IF;
   updated=updated+1;
   IF p_aplicar THEN
    -- Local name, contact, payment status and bank association remain user-managed.
    UPDATE public.clientes SET valor=(r->>'valor')::numeric,data_vencimento=(r->>'data_vencimento')::date,
     referencia_tv=jsonb_build_object('id',r->>'origem_id','usuario',r->>'nome','plano',r->>'plano','situacao',r->>'situacao_origem','origem','painel.newbr.top')
     WHERE id=existing AND usuario_id=p_usuario;
   END IF;
  END IF;
 END LOOP;
 RETURN jsonb_build_object('novos',created,'atualizados',updated,'inalterados',unchanged,'total',jsonb_array_length(p_registros),'aplicado',p_aplicar);
END $function$;
