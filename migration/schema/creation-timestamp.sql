-- Historical rows stay NULL: financial date is not evidence of creation date.
ALTER TABLE public.movimentacoes ADD COLUMN IF NOT EXISTS created_at timestamptz;
ALTER TABLE public.movimentacoes ALTER COLUMN created_at SET DEFAULT now();
CREATE OR REPLACE FUNCTION financeiropro_operacoes.preserve_movement_created_at()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $fn$
BEGIN
 IF TG_OP='INSERT' THEN NEW.created_at=now();
 ELSE NEW.created_at=OLD.created_at;
 END IF;
 RETURN NEW;
END;
$fn$;
REVOKE ALL ON FUNCTION financeiropro_operacoes.preserve_movement_created_at() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER fp_movement_created_at BEFORE INSERT OR UPDATE ON public.movimentacoes
 FOR EACH ROW EXECUTE FUNCTION financeiropro_operacoes.preserve_movement_created_at();
COMMENT ON COLUMN public.movimentacoes.created_at IS 'Actual insertion timestamp; NULL for legacy rows with unknown creation date. Immutable on update.';
