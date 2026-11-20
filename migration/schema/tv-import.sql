ALTER TABLE public.clientes ADD COLUMN IF NOT EXISTS referencia_tv jsonb;
CREATE UNIQUE INDEX IF NOT EXISTS clientes_tv_usuario_origem ON public.clientes(usuario_id,(referencia_tv->>'id')) WHERE referencia_tv IS NOT NULL;

CREATE OR REPLACE FUNCTION public.fp_clientes_tv_v1(p_usuario bigint,p_registros jsonb,p_aplicar boolean DEFAULT false)
RETURNS jsonb LANGUAGE plpgsql SET search_path=pg_catalog AS $fn$
DECLARE r jsonb; due date; amount numeric; phone text; identifier text; seen text[]='{}'; existing bigint; created integer=0; updated integer=0; unchanged integer=0; access jsonb;
BEGIN
 IF NOT public.fp_tv_habilitado_v1(p_usuario) THEN RAISE EXCEPTION 'Integração exclusiva do proprietário' USING ERRCODE='42501'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.usuarios WHERE id=p_usuario AND status='ativo') THEN RAISE EXCEPTION 'Usuário sem acesso ativo' USING ERRCODE='42501'; END IF;
 access=public.fp_access_v1(p_usuario,'clientes');
 IF NOT coalesce((access->>'allowed')::boolean,false) THEN RAISE EXCEPTION 'Módulo sem acesso' USING ERRCODE='42501'; END IF;
 IF jsonb_typeof(p_registros) IS DISTINCT FROM 'array' OR jsonb_array_length(p_registros) NOT BETWEEN 1 AND 2000 THEN RAISE EXCEPTION 'Importação inválida'; END IF;
 -- Validate the entire batch before any insertion; no credentials are accepted.
 FOR r IN SELECT * FROM jsonb_array_elements(p_registros) LOOP
  IF jsonb_typeof(r) IS DISTINCT FROM 'object' OR EXISTS(SELECT 1 FROM jsonb_object_keys(r) k WHERE k NOT IN ('origem_id','nome','telefone','valor','data_vencimento','plano','situacao_origem')) THEN RAISE EXCEPTION 'Campos inválidos'; END IF;
  identifier=r->>'origem_id';
  IF identifier IS NULL OR identifier !~ '^[A-Za-z0-9_-]{1,80}$' OR identifier=ANY(seen) THEN RAISE EXCEPTION 'Identificador de origem inválido ou repetido'; END IF;
  seen=array_append(seen,identifier);
  IF jsonb_typeof(r->'nome') IS DISTINCT FROM 'string' OR length(trim(r->>'nome')) NOT BETWEEN 1 AND 240 OR coalesce(length(r->>'plano'),0)>240 OR coalesce(length(r->>'situacao_origem'),0)>80 THEN RAISE EXCEPTION 'Nome ou plano inválido'; END IF;
  IF jsonb_typeof(r->'valor') IS DISTINCT FROM 'number' THEN RAISE EXCEPTION 'Valor inválido'; END IF;
  amount=(r->>'valor')::numeric;
  IF amount NOT BETWEEN .01 AND 1000000 OR amount<>round(amount,2) THEN RAISE EXCEPTION 'Valor inválido'; END IF;
  IF coalesce(r->>'data_vencimento','') !~ '^20[0-9]{2}-[0-9]{2}-[0-9]{2}$' THEN RAISE EXCEPTION 'Vencimento inválido'; END IF;
  due=(r->>'data_vencimento')::date;
  IF due NOT BETWEEN date '2020-01-01' AND date '2099-12-31' THEN RAISE EXCEPTION 'Vencimento inválido'; END IF;
  IF jsonb_typeof(r->'telefone') IS DISTINCT FROM 'string' OR length(r->>'telefone')>40 THEN RAISE EXCEPTION 'Telefone inválido'; END IF;
  phone=regexp_replace(r->>'telefone','[^0-9]','','g');
  IF phone<>'' AND phone !~ '^[0-9]{8,15}$' THEN RAISE EXCEPTION 'Telefone inválido'; END IF;
 END LOOP;
 IF p_aplicar THEN LOCK TABLE public.clientes IN SHARE ROW EXCLUSIVE MODE; END IF;
 FOR r IN SELECT * FROM jsonb_array_elements(p_registros) LOOP
  SELECT id INTO existing FROM public.clientes WHERE usuario_id=p_usuario AND referencia_tv->>'id'=r->>'origem_id';
  IF existing IS NULL THEN
   created=created+1;
   IF p_aplicar THEN
    INSERT INTO public.clientes(nome,telefone,valor,status,data_vencimento,usuario_id,referencia_tv)
    VALUES(trim(r->>'nome'),regexp_replace(r->>'telefone','[^0-9]','','g'),(r->>'valor')::numeric,'Pendente',(r->>'data_vencimento')::date,p_usuario,
      jsonb_build_object('id',r->>'origem_id','usuario',r->>'nome','plano',r->>'plano','situacao',r->>'situacao_origem','origem','painel.newbr.top'));
   END IF;
  ELSE
   IF NOT EXISTS(SELECT 1 FROM public.clientes c WHERE c.id=existing AND c.usuario_id=p_usuario AND
      (c.valor IS DISTINCT FROM (r->>'valor')::numeric OR c.data_vencimento IS DISTINCT FROM (r->>'data_vencimento')::date OR
       c.referencia_tv IS DISTINCT FROM jsonb_build_object('id',r->>'origem_id','usuario',r->>'nome','plano',r->>'plano','situacao',r->>'situacao_origem','origem','painel.newbr.top'))) THEN
    unchanged=unchanged+1;CONTINUE;
   END IF;
   updated=updated+1;
   IF p_aplicar THEN
    -- Local name, contact, payment status and bank association remain user-managed.
    UPDATE public.clientes SET valor=(r->>'valor')::numeric,data_vencimento=(r->>'data_vencimento')::date,
     referencia_tv=jsonb_build_object('id',r->>'origem_id','usuario',r->>'nome','plano',r->>'plano','situacao',r->>'situacao_origem','origem','painel.newbr.top')
     WHERE id=existing AND usuario_id=p_usuario;
   END IF;
  END IF;
 END LOOP;
 RETURN jsonb_build_object('novos',created,'atualizados',updated,'inalterados',unchanged,'total',jsonb_array_length(p_registros),'aplicado',p_aplicar);
END $fn$;
REVOKE ALL ON FUNCTION public.fp_clientes_tv_v1(bigint,jsonb,boolean) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.fp_clientes_tv_v1(bigint,jsonb,boolean) TO service_role;

-- Preserve shortcut URL/columns; every customer uses the full due date and valid phone.
CREATE OR REPLACE VIEW public.clientes_cobrar_amanha WITH (security_invoker=true) AS
 SELECT c.id,c.nome,c.telefone,c.valor,c.data_vencimento,c.usuario_id,u.usuario,u.telegram_id
 FROM public.clientes c LEFT JOIN public.usuarios u ON c.usuario_id=u.id
 WHERE c.data_vencimento=((CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date+1)
 AND c.telefone ~ '^[0-9]{8,15}$';
NOTIFY pgrst,'reload schema';
