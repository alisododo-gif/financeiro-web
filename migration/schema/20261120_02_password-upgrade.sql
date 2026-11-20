CREATE OR REPLACE FUNCTION financeiropro_operacoes.protect_password_v1() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
BEGIN
 IF NEW.senha ~ '^[a-fA-F0-9]{64}$' THEN
  NEW.senha='bcrypt-sha256$'||extensions.crypt(lower(NEW.senha),extensions.gen_salt('bf',12));
 END IF;
 RETURN NEW;
END $fn$;
REVOKE ALL ON FUNCTION financeiropro_operacoes.protect_password_v1() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER fp_protect_password_v1 BEFORE INSERT OR UPDATE OF senha ON public.usuarios
FOR EACH ROW EXECUTE FUNCTION financeiropro_operacoes.protect_password_v1();
UPDATE public.usuarios SET senha=senha WHERE senha ~ '^[a-fA-F0-9]{64}$';
