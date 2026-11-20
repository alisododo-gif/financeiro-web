-- Never purge command idempotency keys or financial/access audit history.
CREATE OR REPLACE FUNCTION financeiropro_operacoes.expire_runtime_state_v1()
RETURNS jsonb LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE limits_count bigint; alerts_count bigint;
BEGIN
 DELETE FROM financeiropro_operacoes.signup_limits WHERE window_start<now()-interval '30 days';
 GET DIAGNOSTICS limits_count=ROW_COUNT;
 DELETE FROM financeiropro_operacoes.telegram_daily_alerts WHERE dia<current_date-90;
 GET DIAGNOSTICS alerts_count=ROW_COUNT;
 RETURN jsonb_build_object('limites_expirados',limits_count,'reservas_antigas',alerts_count);
END $$;
REVOKE ALL ON FUNCTION financeiropro_operacoes.expire_runtime_state_v1() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION financeiropro_operacoes.expire_runtime_state_v1() TO service_role;
SELECT cron.schedule('fp-temporary-state-cleanup','30 3 * * 0',$job$SELECT financeiropro_operacoes.expire_runtime_state_v1();$job$);
