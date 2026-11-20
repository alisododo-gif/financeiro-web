CREATE TABLE financeiropro_operacoes.signup_limits(ip_hash text NOT NULL,window_start timestamptz NOT NULL,hits integer NOT NULL,PRIMARY KEY(ip_hash,window_start));
ALTER TABLE financeiropro_operacoes.signup_limits ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON financeiropro_operacoes.signup_limits FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE,DELETE ON financeiropro_operacoes.signup_limits TO service_role;
CREATE FUNCTION public.fp_signup_pending(p_usuario text,p_senha_hash text,p_telefone text,p_ip_hash text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $fn$
DECLARE count_hits integer; bucket timestamptz=date_trunc('hour',now());
BEGIN
 IF p_usuario IS NULL OR length(trim(p_usuario)) NOT BETWEEN 3 AND 80 OR p_usuario ~ '[[:cntrl:]]' OR p_senha_hash IS NULL OR p_senha_hash !~ '^[a-f0-9]{64}$' OR p_telefone IS NULL OR p_telefone !~ '^[0-9]{10,15}$' OR p_ip_hash IS NULL OR p_ip_hash !~ '^[a-f0-9]{64}$' THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Cadastro inválido'; END IF;
 INSERT INTO financeiropro_operacoes.signup_limits(ip_hash,window_start,hits) VALUES(p_ip_hash,bucket,1)
 ON CONFLICT(ip_hash,window_start) DO UPDATE SET hits=financeiropro_operacoes.signup_limits.hits+1 RETURNING hits INTO count_hits;
 IF count_hits>5 THEN RETURN jsonb_build_object('limitado',true); END IF;
 DELETE FROM financeiropro_operacoes.signup_limits WHERE window_start<now()-interval '2 days';
 PERFORM pg_advisory_xact_lock(hashtextextended('fp-signup:'||lower(trim(p_usuario)),0));
 IF NOT EXISTS(SELECT 1 FROM public.usuarios WHERE lower(usuario)=lower(trim(p_usuario))) THEN
  INSERT INTO public.usuarios(usuario,senha,is_admin,status,valor_mensalidade,role,telefone)
  VALUES(trim(p_usuario),p_senha_hash,false,'pendente',0,'user',p_telefone);
 END IF;
 RETURN jsonb_build_object('recebido',true);
END;
$fn$;
REVOKE ALL ON FUNCTION public.fp_signup_pending(text,text,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.fp_signup_pending(text,text,text,text) TO service_role;
NOTIFY pgrst,'reload schema';
