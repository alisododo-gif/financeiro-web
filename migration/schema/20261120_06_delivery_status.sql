ALTER TABLE financeiropro_operacoes.telegram_daily_alerts
 ADD COLUMN estado text NOT NULL DEFAULT 'uncertain' CHECK(estado IN ('reserved','sent','retry','failed','uncertain')),
 ADD COLUMN tentativas integer NOT NULL DEFAULT 1,
 ADD COLUMN tentar_em timestamptz,
 ADD COLUMN message_id bigint;
CREATE OR REPLACE FUNCTION public.fp_telegram_daily_claim_v2(p_usuario bigint,p_telegram bigint) RETURNS boolean
LANGUAGE plpgsql SET search_path=pg_catalog AS $f$
DECLARE claimed integer;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.usuarios WHERE id=p_usuario AND telegram_id=p_telegram AND status='ativo') THEN RETURN false;END IF;
 IF NOT coalesce((public.fp_access_v1(p_usuario)->>'allowed')::boolean,false) THEN RETURN false;END IF;
 INSERT INTO financeiropro_operacoes.telegram_daily_alerts(usuario_id,dia,telegram_id,estado,tentativas)
 VALUES(p_usuario,(now() AT TIME ZONE 'America/Cuiaba')::date,p_telegram,'reserved',1)
 ON CONFLICT(usuario_id,dia) DO UPDATE SET estado='reserved',tentativas=telegram_daily_alerts.tentativas+1,reservado_em=now()
 WHERE telegram_daily_alerts.estado='retry' AND telegram_daily_alerts.tentativas<3 AND telegram_daily_alerts.tentar_em<=now() AND telegram_daily_alerts.telegram_id=p_telegram;
 GET DIAGNOSTICS claimed=ROW_COUNT;RETURN claimed=1;
END $f$;
CREATE OR REPLACE FUNCTION public.fp_telegram_daily_finish_v2(p_usuario bigint,p_telegram bigint,p_estado text,p_message_id bigint DEFAULT NULL,p_retry_seconds integer DEFAULT 0) RETURNS boolean
LANGUAGE plpgsql SET search_path=pg_catalog AS $f$
BEGIN
 IF p_estado NOT IN ('sent','retry','failed','uncertain') OR p_retry_seconds NOT BETWEEN 0 AND 3600 THEN RAISE EXCEPTION 'Estado inválido'; END IF;
 UPDATE financeiropro_operacoes.telegram_daily_alerts SET estado=p_estado,message_id=p_message_id,tentar_em=CASE WHEN p_estado='retry' THEN now()+make_interval(secs=>p_retry_seconds) ELSE NULL END
 WHERE usuario_id=p_usuario AND telegram_id=p_telegram AND dia=(now() AT TIME ZONE 'America/Cuiaba')::date AND estado='reserved';
 RETURN FOUND;
END $f$;
REVOKE ALL ON FUNCTION public.fp_telegram_daily_claim_v2(bigint,bigint),public.fp_telegram_daily_finish_v2(bigint,bigint,text,bigint,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.fp_telegram_daily_claim_v2(bigint,bigint),public.fp_telegram_daily_finish_v2(bigint,bigint,text,bigint,integer) TO service_role;
