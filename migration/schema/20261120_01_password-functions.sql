-- Service-only password verification. SHA-256 is a prehash; bcrypt supplies salt and work factor.
CREATE OR REPLACE FUNCTION public.fp_password_verify_v1(p_usuario bigint,p_digest text) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $fn$
DECLARE stored text;
BEGIN
 IF p_digest IS NULL OR p_digest !~ '^[a-f0-9]{64}$' THEN RETURN false; END IF;
 SELECT senha INTO stored FROM public.usuarios WHERE id=p_usuario AND status='ativo';
 IF stored LIKE 'bcrypt-sha256$%' THEN
  RETURN extensions.crypt(p_digest,substring(stored from 15))=substring(stored from 15);
 END IF;
 -- Transitional compatibility until all existing hashes are upgraded in the next migration.
 RETURN coalesce(stored ~ '^[a-f0-9]{64}$' AND stored=p_digest,false);
END $fn$;
REVOKE ALL ON FUNCTION public.fp_password_verify_v1(bigint,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.fp_password_verify_v1(bigint,text) TO service_role;

CREATE OR REPLACE FUNCTION public.fp_password_change_v1(p_usuario bigint,p_atual text,p_nova text) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $fn$
BEGIN
 IF p_nova IS NULL OR p_nova !~ '^[a-f0-9]{64}$' THEN RETURN false; END IF;
 PERFORM 1 FROM public.usuarios WHERE id=p_usuario FOR UPDATE;
 IF public.fp_password_verify_v1(p_usuario,p_atual) IS NOT TRUE THEN RETURN false; END IF;
 UPDATE public.usuarios SET senha='bcrypt-sha256$'||extensions.crypt(p_nova,extensions.gen_salt('bf',12)) WHERE id=p_usuario AND status='ativo';
 RETURN FOUND;
END $fn$;
REVOKE ALL ON FUNCTION public.fp_password_change_v1(bigint,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.fp_password_change_v1(bigint,text,text) TO service_role;
