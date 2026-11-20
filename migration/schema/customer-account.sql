ALTER TABLE public.clientes ADD COLUMN conta_id integer REFERENCES public.contas(id) ON DELETE RESTRICT;
CREATE FUNCTION financeiropro_operacoes.validate_customer_account() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $f$
BEGIN
 IF NEW.conta_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.contas c WHERE c.id=NEW.conta_id AND c.usuario_id=NEW.usuario_id) THEN
  RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='A conta bancária deve pertencer ao mesmo usuário do cliente';
 END IF;
 RETURN NEW;
END $f$;
CREATE TRIGGER customer_account_owner BEFORE INSERT OR UPDATE OF conta_id,usuario_id ON public.clientes FOR EACH ROW EXECUTE FUNCTION financeiropro_operacoes.validate_customer_account();
REVOKE ALL ON FUNCTION financeiropro_operacoes.validate_customer_account() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION financeiropro_operacoes.validate_customer_account() TO service_role;
DO $patch$
DECLARE source text;
BEGIN
 SELECT pg_get_functiondef('financeiropro_operacoes.financeiro_core_v1(bigint,text,text,bigint,jsonb,text,uuid)'::regprocedure) INTO source;
 IF position('allowed=ARRAY[''nome'',''telefone'',''valor'',''data_vencimento'',''status'']' in source)=0 THEN RAISE EXCEPTION 'Client schema marker not found';END IF;
 source=replace(source,'allowed=ARRAY[''nome'',''telefone'',''valor'',''data_vencimento'',''status'']','allowed=ARRAY[''nome'',''telefone'',''valor'',''data_vencimento'',''status'',''conta_id'']');
 EXECUTE source;
END $patch$;
NOTIFY pgrst,'reload schema';
