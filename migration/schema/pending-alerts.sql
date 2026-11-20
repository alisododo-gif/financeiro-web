CREATE OR REPLACE VIEW public.faturas_vencendo_hoje WITH (security_invoker=true) AS
 SELECT c.id AS cartao_id,c.nome_cartao,c.dia_vencimento,c.dia_fechamento,c.usuario_id,u.usuario AS nome_usuario,u.telegram_id,u.telefone
 FROM public.cartoes c LEFT JOIN public.usuarios u ON c.usuario_id=u.id
 WHERE least(c.dia_vencimento,extract(day FROM (date_trunc('month',CURRENT_TIMESTAMP AT TIME ZONE 'America/Cuiaba')+interval '1 month - 1 day'))) = extract(day FROM CURRENT_TIMESTAMP AT TIME ZONE 'America/Cuiaba')
 AND EXISTS(SELECT 1 FROM public.movimentacoes m WHERE m.usuario_id=c.usuario_id AND m.cartao_id=c.id AND m.tipo='Despesa' AND m.forma_pagamento='Cartão de Crédito' AND m.mes_fatura=to_char(CURRENT_TIMESTAMP AT TIME ZONE 'America/Cuiaba','MM/YYYY') AND m.pago IS DISTINCT FROM true);
CREATE OR REPLACE VIEW public.movimentacoes_hoje WITH (security_invoker=true) AS
 SELECT m.id,m.usuario_id,u.usuario,m.descricao,m.valor,m.data,coalesce(m.pago,false) AS pago,m.tipo,m.forma_pagamento AS forma_pag,u.telefone,u.telegram_id
 FROM public.movimentacoes m LEFT JOIN public.usuarios u ON m.usuario_id=u.id
 WHERE m.data::date=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Cuiaba')::date AND m.pago IS DISTINCT FROM true AND m.tipo='Despesa'
 AND (lower(m.forma_pagamento)='boleto' OR ((m.descricao ILIKE '%Recorrente%' OR m.descricao ILIKE '%Fixo%') AND m.forma_pagamento IN ('Boleto','Pix','Cartão de Débito','Dinheiro')));
CREATE OR REPLACE VIEW public.recebimentos_hoje WITH (security_invoker=true) AS
 SELECT cr.id,cr.usuario_id,u.usuario,u.telegram_id,trim(u.telefone) AS telefone,cr.descricao,cr.valor,cr.data_recebimento,coalesce(cr.recebido,false) AS recebido
 FROM public.contas_receber cr LEFT JOIN public.usuarios u ON cr.usuario_id=u.id
 WHERE cr.data_recebimento::date=(CURRENT_TIMESTAMP AT TIME ZONE 'America/Cuiaba')::date AND cr.recebido IS DISTINCT FROM true;

CREATE TABLE IF NOT EXISTS financeiropro_operacoes.telegram_daily_alerts(usuario_id integer NOT NULL REFERENCES public.usuarios(id),dia date NOT NULL,telegram_id bigint NOT NULL,reservado_em timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(usuario_id,dia));
ALTER TABLE financeiropro_operacoes.telegram_daily_alerts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON financeiropro_operacoes.telegram_daily_alerts FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON financeiropro_operacoes.telegram_daily_alerts TO service_role;
CREATE OR REPLACE FUNCTION public.fp_telegram_daily_claim_v1(p_usuario bigint,p_telegram bigint) RETURNS boolean LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE claimed integer; access jsonb;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.usuarios WHERE id=p_usuario AND status='ativo' AND telegram_id=p_telegram) OR EXISTS(SELECT 1 FROM public.usuarios WHERE id<>p_usuario AND status='ativo' AND telegram_id=p_telegram) THEN RETURN false;END IF;
 access=public.fp_access_v1(p_usuario);IF NOT coalesce((access->>'allowed')::boolean,false) THEN RETURN false;END IF;
 INSERT INTO financeiropro_operacoes.telegram_daily_alerts(usuario_id,dia,telegram_id) VALUES(p_usuario,(CURRENT_TIMESTAMP AT TIME ZONE 'America/Cuiaba')::date,p_telegram) ON CONFLICT(usuario_id,dia) DO NOTHING;
 GET DIAGNOSTICS claimed=ROW_COUNT;RETURN claimed=1;
END $fn$;
REVOKE ALL ON FUNCTION public.fp_telegram_daily_claim_v1(bigint,bigint) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.fp_telegram_daily_claim_v1(bigint,bigint) TO service_role;
NOTIFY pgrst,'reload schema';
