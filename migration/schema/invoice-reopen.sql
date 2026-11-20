CREATE OR REPLACE FUNCTION financeiropro_operacoes.reabrir_fatura_v1(p_usuario bigint,p_id bigint,p_dados jsonb,p_versao text,p_chave uuid) RETURNS jsonb
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE rows jsonb;version text;saved record;req jsonb;answer jsonb;changed integer;competencia text=p_dados->>'competencia';
BEGIN
 IF p_chave IS NULL OR competencia IS NULL OR competencia !~ '^(0[1-9]|1[0-2])/20[0-9]{2}$' OR (p_dados-'competencia')<>'{}'::jsonb THEN RAISE EXCEPTION 'Dados da fatura inválidos' USING ERRCODE='22023';END IF;
 LOCK TABLE public.contas,public.cartoes,public.movimentacoes,public.contas_receber,public.metas,public.orcamentos,public.clientes,financeiropro_operacoes.comandos IN EXCLUSIVE MODE;
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
END $fn$;
REVOKE ALL ON FUNCTION financeiropro_operacoes.reabrir_fatura_v1(bigint,bigint,jsonb,text,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION financeiropro_operacoes.reabrir_fatura_v1(bigint,bigint,jsonb,text,uuid) TO service_role;
DO $update$
DECLARE def text;
BEGIN
 def=pg_get_functiondef('public.fp_financeiro_modulo_v1(bigint,text,text,bigint,jsonb,text,uuid,text)'::regprocedure);
 IF def NOT LIKE '%reabrir_fatura_v1%' THEN
  def=replace(def,$old$p_acao IN ('fatura','quitar_fatura')$old$,$new$p_acao IN ('fatura','quitar_fatura','reabrir_fatura')$new$);
  def=replace(def,'RETURN financeiropro_operacoes.financeiro_core_v1(p_usuario,p_tabela,p_acao,p_id,p_dados,p_versao,p_chave);','IF p_tabela=''cartoes'' AND p_acao=''reabrir_fatura'' THEN RETURN financeiropro_operacoes.reabrir_fatura_v1(p_usuario,p_id,p_dados,p_versao,p_chave);END IF; RETURN financeiropro_operacoes.financeiro_core_v1(p_usuario,p_tabela,p_acao,p_id,p_dados,p_versao,p_chave);');
  IF def NOT LIKE '%reabrir_fatura_v1%' THEN RAISE EXCEPTION 'Estrutura inesperada';END IF;
  EXECUTE def;
 END IF;
END $update$;
NOTIFY pgrst,'reload schema';
