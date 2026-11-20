CREATE OR REPLACE FUNCTION public.fp_backup_snapshot_v2(p_actor bigint) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $f$
DECLARE descriptor jsonb; tab record; rows jsonb; data jsonb='{}'; counts jsonb='{}';
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.usuarios WHERE id=p_actor AND status='ativo' AND (is_admin OR role='admin')) THEN RAISE EXCEPTION 'Somente administrador' USING ERRCODE='42501'; END IF;
 SELECT jsonb_build_object(
 'tables',(SELECT jsonb_agg(jsonb_build_object('schema',n.nspname,'name',c.relname,'rls',c.relrowsecurity,'columns',(SELECT jsonb_agg(jsonb_build_object('name',a.attname,'type',format_type(a.atttypid,a.atttypmod),'notnull',a.attnotnull,'identity',a.attidentity,'default',pg_get_expr(d.adbin,d.adrelid)) ORDER BY a.attnum) FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped))) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','financeiropro_operacoes') AND c.relkind='r'),
 'constraints',(SELECT jsonb_agg(jsonb_build_object('schema',n.nspname,'table',c.relname,'name',co.conname,'definition',pg_get_constraintdef(co.oid),'type',co.contype)) FROM pg_constraint co JOIN pg_class c ON c.oid=co.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','financeiropro_operacoes')),
 'sequences',(SELECT jsonb_agg(jsonb_build_object('schema',schemaname,'name',sequencename,'type',data_type::text,'start',start_value::text,'increment',increment_by::text,'min',min_value::text,'max',max_value::text,'cycle',cycle,'last',last_value::text)) FROM pg_sequences WHERE schemaname IN ('public','financeiropro_operacoes')),
 'routines',(SELECT jsonb_agg(jsonb_build_object('definition',pg_get_functiondef(p.oid),'identity',p.oid::regprocedure::text)) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='financeiropro_operacoes' OR (n.nspname='public' AND p.proname LIKE 'fp_%')),
 'views',(SELECT jsonb_agg(jsonb_build_object('schema',n.nspname,'name',c.relname,'definition',pg_get_viewdef(c.oid,true),'options',c.reloptions)) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='v'),
 'triggers',(SELECT jsonb_agg(jsonb_build_object('definition',pg_get_triggerdef(t.oid))) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE NOT t.tgisinternal AND n.nspname IN ('public','financeiropro_operacoes')),
 'indexes',(SELECT jsonb_agg(jsonb_build_object('definition',pg_get_indexdef(i.indexrelid))) FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','financeiropro_operacoes') AND NOT EXISTS(SELECT 1 FROM pg_constraint co WHERE co.conindid=i.indexrelid)),
 'policies',(SELECT jsonb_agg(to_jsonb(p)) FROM pg_policies p WHERE schemaname IN ('public','financeiropro_operacoes')),
 'grants',(SELECT jsonb_agg(jsonb_build_object('schema',table_schema,'table',table_name,'grantee',grantee,'privilege',privilege_type)) FROM information_schema.table_privileges WHERE table_schema IN ('public','financeiropro_operacoes') AND grantee IN ('service_role','anon','authenticated'))
 ) INTO descriptor;
 FOR tab IN SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','financeiropro_operacoes') AND c.relkind='r' ORDER BY 1,2 LOOP
  EXECUTE format('SELECT coalesce(jsonb_agg(to_jsonb(t)),''[]''::jsonb) FROM %I.%I t',tab.nspname,tab.relname) INTO rows;
  counts=counts||jsonb_build_object(tab.nspname||'.'||tab.relname,jsonb_array_length(rows));
  data=data||jsonb_build_object(tab.nspname||'.'||tab.relname,rows);
 END LOOP;
 RETURN jsonb_build_object('format','FinanceiroProDatabaseBackupV2','version',2,'project','hkfyvhthfshnddduckjs','scope','application_database','consistent',true,'created_at',now(),'definition',descriptor,'tables',data,'counts',counts,'external_dependencies',jsonb_build_array('extensions.pgcrypto','auth.users (provided by the target Supabase project)'));
END $f$;
REVOKE ALL ON FUNCTION public.fp_backup_snapshot_v2(bigint) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.fp_backup_snapshot_v2(bigint) TO service_role;
