-- Homologation only. This entrypoint cannot select a production schema.
-- New RPC only; no existing public object or row is overwritten.
CREATE TABLE financeiropro_restore_teste.comandos (
 usuario_id bigint NOT NULL, chave uuid NOT NULL, pedido jsonb NOT NULL,
 resposta jsonb NOT NULL, criado_em timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(usuario_id,chave)
);
ALTER TABLE financeiropro_restore_teste.comandos ENABLE ROW LEVEL SECURITY;
CREATE TABLE financeiropro_restore_teste.contadores (tabela text PRIMARY KEY, ultimo bigint NOT NULL);
ALTER TABLE financeiropro_restore_teste.contadores ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON financeiropro_restore_teste.contadores FROM PUBLIC,anon,authenticated;
REVOKE ALL ON financeiropro_restore_teste.comandos FROM PUBLIC,anon,authenticated;
GRANT USAGE ON SCHEMA financeiropro_restore_teste TO service_role;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA financeiropro_restore_teste TO service_role;

CREATE FUNCTION public.fp_homologacao_v1(p_usuario bigint,p_tabela text,p_acao text,
 p_id bigint DEFAULT NULL,p_dados jsonb DEFAULT '{}'::jsonb,p_versao text DEFAULT NULL,p_chave uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $fn$
DECLARE
 allowed text[]; required text[]; k text; v jsonb; before_row jsonb; after_row jsonb;
 answer jsonb; saved record; new_id bigint; fields text; setters text; n numeric; batch_row jsonb; batch_result jsonb;
 req jsonb; rows jsonb; invoice_version text; ref text; d date; closing integer;
BEGIN
 IF p_usuario IS NULL OR p_usuario<=0 OR NOT EXISTS(
   SELECT 1 FROM financeiropro_restore_teste.usuarios WHERE id=p_usuario AND status='ativo'
 ) THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Usuário sem acesso ativo'; END IF;
 IF p_tabela NOT IN ('contas','cartoes','movimentacoes','contas_receber','metas','orcamentos','clientes')
    OR p_tabela IS NULL OR p_acao IS NULL THEN
   RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Recurso inválido'; END IF;
 IF jsonb_typeof(p_dados) IS DISTINCT FROM 'object' THEN
   RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Dados inválidos'; END IF;
 IF p_acao='listar' THEN
   EXECUTE format('SELECT coalesce(jsonb_agg(to_jsonb(x)||jsonb_build_object(''_versao'',md5(to_jsonb(x)::text)) ORDER BY x.id),''[]''::jsonb) FROM financeiropro_restore_teste.%I x WHERE usuario_id=$1',p_tabela)
    INTO rows USING p_usuario;
   RETURN jsonb_build_object('registros',rows,'schema','financeiropro_restore_teste');
 END IF;
 -- One deterministic lock order for all commands: protects owner references,
 -- invoice membership, optimistic versions and ID allocation without public sequences.
 LOCK TABLE financeiropro_restore_teste.contas,financeiropro_restore_teste.cartoes,
 financeiropro_restore_teste.movimentacoes,financeiropro_restore_teste.contas_receber,
 financeiropro_restore_teste.metas,financeiropro_restore_teste.orcamentos,financeiropro_restore_teste.clientes,
 financeiropro_restore_teste.comandos IN EXCLUSIVE MODE;
 IF p_acao NOT IN ('criar','criar_lote','editar','excluir','quitar_fatura','fatura') THEN
   RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Ação inválida'; END IF;
 IF p_acao<>'fatura' THEN
   IF p_chave IS NULL THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Chave de repetição obrigatória'; END IF;
   req=jsonb_build_object('tabela',p_tabela,'acao',p_acao,'id',p_id,'dados',p_dados,'versao',p_versao);
   SELECT * INTO saved FROM financeiropro_restore_teste.comandos WHERE usuario_id=p_usuario AND chave=p_chave;
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
     batch_result=public.fp_homologacao_v1(p_usuario,'movimentacoes','criar',null,batch_row,null,gen_random_uuid());
     rows=rows||jsonb_build_array(batch_result->'registro');
   END LOOP;
   answer=jsonb_build_object('gravado',true,'schema','financeiropro_restore_teste','registros',rows);
 ELSIF p_acao IN ('fatura','quitar_fatura') THEN
   ref=p_dados->>'competencia';
   IF p_tabela<>'cartoes' OR ref IS NULL OR ref !~ '^(0[1-9]|1[0-2])/20[0-9]{2}$' OR NOT EXISTS(
     SELECT 1 FROM financeiropro_restore_teste.cartoes WHERE id=p_id AND usuario_id=p_usuario
   ) THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Fatura inválida'; END IF;
   SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY id),'[]'::jsonb) INTO rows
    FROM financeiropro_restore_teste.movimentacoes m WHERE usuario_id=p_usuario AND cartao_id=p_id
    AND mes_fatura=ref AND tipo='Despesa' AND forma_pagamento='Cartão de Crédito';
   invoice_version=md5(rows::text);
   IF p_acao='fatura' THEN RETURN jsonb_build_object('registros',rows,'_versao',invoice_version); END IF;
   IF p_versao IS DISTINCT FROM invoice_version THEN RAISE EXCEPTION USING ERRCODE='40001',MESSAGE='Fatura alterada. Atualize a consulta'; END IF;
   UPDATE financeiropro_restore_teste.movimentacoes SET pago=true WHERE usuario_id=p_usuario AND cartao_id=p_id
    AND mes_fatura=ref AND tipo='Despesa' AND forma_pagamento='Cartão de Crédito' AND pago IS DISTINCT FROM true;
   GET DIAGNOSTICS new_id=ROW_COUNT;
   answer=jsonb_build_object('quantidade',new_id,'gravado',true,'schema','financeiropro_restore_teste');
 ELSE
   CASE p_tabela
    WHEN 'contas' THEN allowed=ARRAY['nome','saldo']; required=ARRAY['nome','saldo'];
    WHEN 'cartoes' THEN allowed=ARRAY['nome_cartao','limite','dia_fechamento','dia_vencimento']; required=allowed;
    WHEN 'movimentacoes' THEN allowed=ARRAY['conta_id','cartao_id','descricao','valor','tipo','forma_pagamento','data','categoria','mes_fatura','tags','pago']; required=ARRAY['descricao','valor','tipo','forma_pagamento','data','categoria','pago'];
    WHEN 'contas_receber' THEN allowed=ARRAY['descricao','valor','data_recebimento','recebido']; required=allowed;
    WHEN 'metas' THEN allowed=ARRAY['nome_meta','valor_alvo','valor_poupado','prazo']; required=allowed;
    WHEN 'clientes' THEN allowed=ARRAY['nome','telefone','valor','data_vencimento','status']; required=ARRAY['nome','telefone','valor','status'];
    WHEN 'orcamentos' THEN allowed=ARRAY['categoria','limite']; required=ARRAY['limite'];
   END CASE;
   IF p_acao<>'criar' THEN
     EXECUTE format('SELECT to_jsonb(x) FROM financeiropro_restore_teste.%I x WHERE id=$1 AND usuario_id=$2 FOR UPDATE',p_tabela) INTO before_row USING p_id,p_usuario;
     IF before_row IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0002',MESSAGE='Registro não encontrado'; END IF;
     IF p_versao IS DISTINCT FROM md5(before_row::text) THEN RAISE EXCEPTION USING ERRCODE='40001',MESSAGE='Registro alterado. Atualize a consulta'; END IF;
   END IF;
   IF p_acao='excluir' THEN
     IF (p_tabela='contas' AND EXISTS(SELECT 1 FROM financeiropro_restore_teste.movimentacoes WHERE conta_id=p_id))
      OR (p_tabela='cartoes' AND EXISTS(SELECT 1 FROM financeiropro_restore_teste.movimentacoes WHERE cartao_id=p_id)) THEN
       RAISE EXCEPTION USING ERRCODE='23503',MESSAGE='O registro tem movimentações associadas. Preserve o histórico';
     END IF;
     EXECUTE format('DELETE FROM financeiropro_restore_teste.%I WHERE id=$1 AND usuario_id=$2',p_tabela) USING p_id,p_usuario;
   ELSE
     FOR k IN SELECT jsonb_object_keys(p_dados) LOOP
       IF NOT k=ANY(allowed) THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Campo não permitido: '||k; END IF;
     END LOOP;
     IF p_dados='{}'::jsonb THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Preencha os campos'; END IF;
     after_row=coalesce(before_row,'{}'::jsonb)||p_dados;
     IF p_tabela='clientes' THEN
       IF jsonb_typeof(after_row->'telefone') IS DISTINCT FROM 'string' OR length(after_row->>'telefone')>40 OR regexp_replace(after_row->>'telefone','[^0-9]','','g') !~ '^[0-9]{8,15}$' THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Telefone invalido: use DDD e numero'; END IF;
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
         SELECT dia_fechamento INTO closing FROM financeiropro_restore_teste.cartoes WHERE id=(after_row->>'cartao_id')::bigint AND usuario_id=p_usuario;
         IF after_row->>'tipo'<>'Despesa' OR closing IS NULL THEN
           RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Cartão ou competência inválida'; END IF;
         IF p_acao='criar' OR after_row->'data' IS DISTINCT FROM before_row->'data' OR after_row->'cartao_id' IS DISTINCT FROM before_row->'cartao_id' OR after_row->'forma_pagamento' IS DISTINCT FROM before_row->'forma_pagamento' THEN
           d=(after_row->>'data')::date;
           IF extract(day FROM d)>=least(closing,extract(day FROM (date_trunc('month',d)+interval '1 month - 1 day'))) THEN d=(date_trunc('month',d)+interval '1 month')::date; END IF;
           after_row=after_row||jsonb_build_object('mes_fatura',to_char(d,'MM/YYYY'));
         END IF;
         after_row=after_row||jsonb_build_object('conta_id',null);
       ELSE
         IF NOT EXISTS(SELECT 1 FROM financeiropro_restore_teste.contas WHERE id=(after_row->>'conta_id')::bigint AND usuario_id=p_usuario) THEN
           RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Conta não pertence ao usuário'; END IF;
         after_row=after_row||jsonb_build_object('cartao_id',null,'mes_fatura',null);
       END IF;
     END IF;
     IF p_acao='criar' THEN
       EXECUTE format('SELECT coalesce(max(id),0)+1 FROM financeiropro_restore_teste.%I',p_tabela) INTO new_id;
       INSERT INTO financeiropro_restore_teste.contadores(tabela,ultimo) VALUES(p_tabela,new_id)
        ON CONFLICT(tabela) DO UPDATE SET ultimo=greatest(financeiropro_restore_teste.contadores.ultimo+1,EXCLUDED.ultimo) RETURNING ultimo INTO new_id;
       after_row=after_row||jsonb_build_object('id',new_id,'usuario_id',p_usuario);
       EXECUTE format('INSERT INTO financeiropro_restore_teste.%I SELECT * FROM jsonb_populate_record(NULL::financeiropro_restore_teste.%I,$1) RETURNING to_jsonb(%I.*)',p_tabela,p_tabela,p_tabela) INTO after_row USING after_row;
     ELSE
       SELECT string_agg(format('%I=r.%I',col,col),',') INTO setters FROM unnest(allowed) AS col;
       EXECUTE format('UPDATE financeiropro_restore_teste.%I x SET %s FROM jsonb_populate_record(NULL::financeiropro_restore_teste.%I,$1) r WHERE x.id=$2 AND x.usuario_id=$3 RETURNING to_jsonb(x)',p_tabela,setters,p_tabela) INTO after_row USING after_row,p_id,p_usuario;
     END IF;
   END IF;
   answer=jsonb_build_object('gravado',true,'schema','financeiropro_restore_teste','registro',
    CASE WHEN p_acao='excluir' THEN NULL ELSE after_row||jsonb_build_object('_versao',md5(after_row::text)) END);
 END IF;
 INSERT INTO financeiropro_restore_teste.comandos(usuario_id,chave,pedido,resposta) VALUES(p_usuario,p_chave,req,answer);
 RETURN answer;
END $fn$;
REVOKE ALL ON FUNCTION public.fp_homologacao_v1(bigint,text,text,bigint,jsonb,text,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.fp_homologacao_v1(bigint,text,text,bigint,jsonb,text,uuid) TO service_role;
NOTIFY pgrst,'reload schema';
