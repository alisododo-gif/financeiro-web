CREATE OR REPLACE FUNCTION public.fp_delivery_status_v1(p_actor bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path=pg_catalog AS $f$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.usuarios WHERE id=p_actor AND status='ativo' AND (is_admin OR role='admin')) THEN RAISE EXCEPTION 'Somente administrador' USING ERRCODE='42501';END IF;
 RETURN (SELECT coalesce(jsonb_object_agg(estado,n),'{}') FROM (SELECT CASE WHEN estado='reserved' AND reservado_em<now()-interval '10 minutes' THEN 'uncertain' ELSE estado END estado,count(*) n FROM financeiropro_operacoes.telegram_daily_alerts WHERE dia=(now() AT TIME ZONE 'America/Cuiaba')::date GROUP BY 1) t);
END $f$;
REVOKE ALL ON FUNCTION public.fp_delivery_status_v1(bigint) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.fp_delivery_status_v1(bigint) TO service_role;
