DO $change$
DECLARE definition text; old text; replacement text;
BEGIN
 SELECT pg_get_functiondef(p.oid) INTO definition FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='financeiropro_operacoes' AND p.proname='financeiro_core_v1';
 old=$old$regexp_replace(after_row->>'telefone','[^0-9]','','g') !~ '^[0-9]{8,15}$'$old$;
 replacement=$new$(regexp_replace(after_row->>'telefone','[^0-9]','','g') !~ '^[0-9]{8,15}$' AND NOT (after_row->>'telefone'='' AND after_row->'referencia_tv' IS NOT NULL AND after_row->'referencia_tv'<>'null'::jsonb))$new$;
 IF position(old IN definition)=0 THEN RAISE EXCEPTION 'Validação de telefone não reconhecida'; END IF;
 EXECUTE replace(definition,old,replacement);
END $change$;
