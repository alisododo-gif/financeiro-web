CREATE TABLE IF NOT EXISTS financeiropro_operacoes.tv_integration_owner(id boolean PRIMARY KEY DEFAULT true CHECK(id),usuario_id integer NOT NULL REFERENCES public.usuarios(id));
ALTER TABLE financeiropro_operacoes.tv_integration_owner ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON financeiropro_operacoes.tv_integration_owner FROM PUBLIC,anon,authenticated;
GRANT SELECT ON financeiropro_operacoes.tv_integration_owner TO service_role;
-- Owner ID explicitly supplied in the user's existing shortcut URL and verified in the session.
INSERT INTO financeiropro_operacoes.tv_integration_owner(id,usuario_id) SELECT true,id FROM public.usuarios WHERE id=1 AND status='ativo' AND (is_admin OR role='admin') ON CONFLICT(id) DO NOTHING;
CREATE OR REPLACE FUNCTION public.fp_tv_habilitado_v1(p_usuario bigint) RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog AS $fn$
 SELECT EXISTS(SELECT 1 FROM financeiropro_operacoes.tv_integration_owner WHERE usuario_id=p_usuario);
$fn$;
REVOKE ALL ON FUNCTION public.fp_tv_habilitado_v1(bigint) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.fp_tv_habilitado_v1(bigint) TO service_role;
DO $change$
DECLARE definition text;
BEGIN
 SELECT pg_get_functiondef(p.oid) INTO definition FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='fp_clientes_tv_v1';
 IF definition IS NULL THEN RAISE EXCEPTION 'Importador não encontrado';END IF;
 EXECUTE replace(definition,E'BEGIN\n',E'BEGIN\n IF NOT public.fp_tv_habilitado_v1(p_usuario) THEN RAISE EXCEPTION ''Integração exclusiva do proprietário'' USING ERRCODE=''42501''; END IF;\n');
END $change$;
NOTIFY pgrst,'reload schema';
