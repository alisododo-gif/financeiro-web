CREATE OR REPLACE FUNCTION public.fp_sessions_revoke_v1(p_usuario bigint,p_version bigint) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $f$
BEGIN
 UPDATE public.usuarios SET session_version=session_version+1 WHERE id=p_usuario AND session_version=p_version;
 RETURN FOUND;
END $f$;
REVOKE ALL ON FUNCTION public.fp_sessions_revoke_v1(bigint,bigint) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.fp_sessions_revoke_v1(bigint,bigint) TO service_role;
