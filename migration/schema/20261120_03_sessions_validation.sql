ALTER TABLE public.usuarios ADD COLUMN session_version bigint NOT NULL DEFAULT 0;
CREATE OR REPLACE FUNCTION financeiropro_operacoes.password_session_version_v1() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $f$
BEGIN
 IF NEW.senha IS DISTINCT FROM OLD.senha OR NEW.status IS DISTINCT FROM OLD.status THEN NEW.session_version=OLD.session_version+1; END IF;
 RETURN NEW;
END $f$;
REVOKE ALL ON FUNCTION financeiropro_operacoes.password_session_version_v1() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER fp_password_session_version_v1 BEFORE UPDATE ON public.usuarios FOR EACH ROW EXECUTE FUNCTION financeiropro_operacoes.password_session_version_v1();
CREATE OR REPLACE FUNCTION public.fp_signup_pending(p_usuario text, p_senha_hash text, p_telefone text, p_ip_hash text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE count_hits integer;bucket timestamptz=date_trunc('hour',now());new_id bigint;
BEGIN
 IF p_usuario IS NULL OR length(trim(p_usuario)) NOT BETWEEN 3 AND 80 OR trim(p_usuario) !~ '^[[:alnum:]_.-]+$' OR p_senha_hash IS NULL OR p_senha_hash !~ '^[a-f0-9]{64}$' OR p_telefone IS NULL OR p_telefone !~ '^[0-9]{10,15}$' OR p_ip_hash IS NULL OR p_ip_hash !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Cadastro inválido'; END IF;
 INSERT INTO financeiropro_operacoes.signup_limits(ip_hash,window_start,hits) VALUES(p_ip_hash,bucket,1) ON CONFLICT(ip_hash,window_start) DO UPDATE SET hits=signup_limits.hits+1 RETURNING hits INTO count_hits;
 IF count_hits>5 THEN RETURN jsonb_build_object('limitado',true);END IF;
 DELETE FROM financeiropro_operacoes.signup_limits WHERE window_start<now()-interval '2 days';
 PERFORM pg_advisory_xact_lock(hashtextextended('fp-signup:'||lower(trim(p_usuario)),0));
 IF NOT EXISTS(SELECT 1 FROM public.usuarios WHERE lower(usuario)=lower(trim(p_usuario))) THEN
  INSERT INTO public.usuarios(usuario,senha,is_admin,status,valor_mensalidade,role,telefone) VALUES(trim(p_usuario),p_senha_hash,false,'ativo',0,'user',p_telefone) RETURNING id INTO new_id;
  INSERT INTO financeiropro_operacoes.user_access(usuario_id,mode,trial_started_at,trial_expires_at) VALUES(new_id,'trial',now(),now()+interval '7 days');
 END IF;
 RETURN jsonb_build_object('recebido',true);
END $function$;

REVOKE TRUNCATE,REFERENCES,TRIGGER ON ALL TABLES IN SCHEMA public FROM authenticated;
