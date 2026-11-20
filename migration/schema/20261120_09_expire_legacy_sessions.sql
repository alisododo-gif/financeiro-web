-- Apply once after deploying the session-version-aware Worker.
UPDATE public.usuarios SET session_version=session_version+1;
