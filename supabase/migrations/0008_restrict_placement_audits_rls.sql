-- CPASS Fix 2 of 13: remove unrestricted authenticated access to placement audits.
--
-- The CPASS frontend accesses application data through the FastAPI backend.
-- The backend uses the Supabase service-role client and must enforce authorization
-- in each route. The service-role key bypasses RLS; ordinary authenticated users
-- should not receive blanket direct API access to placement_audits.
--
-- This is a forward-only corrective migration. Do not edit the already-applied
-- 0004_placement_audits.sql migration.

BEGIN;

ALTER TABLE public.placement_audits ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "authenticated users can access placement audits"
  ON public.placement_audits;

COMMIT;

NOTIFY pgrst, 'reload schema';
