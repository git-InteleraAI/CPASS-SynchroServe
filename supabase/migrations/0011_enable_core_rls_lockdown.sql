-- 0011_enable_core_rls_lockdown.sql
-- CPASS Phase 1.5 Migration: Core Row Level Security Lockdown & PostgREST Exposure Neutralization
--
-- Security Objective (SEC-AUTHZ-01):
-- 1. Enable Row Level Security (RLS) on core operational tables:
--    - public.ddugky_candidates (candidate master records & PII)
--    - public.candidate_documents (Google Drive document metadata)
--    - public.revoked_tokens (authoritative token revocation blacklist)
-- 2. Dynamically enumerate and drop all existing policies on these three tables to ensure zero client policies.
-- 3. Revoke all table-level privileges from anon, authenticated, and PUBLIC.
-- 4. Ensure service_role retains explicit USAGE on schema public and all table privileges.
-- 5. Safeguard A: Halt and fail migration if any target table is missing from the public schema.
-- 6. Safeguard B: Post-lockdown validation verifying:
--    - service_role possesses BYPASSRLS attribute.
--    - service_role has USAGE privilege on schema public.
--    - Row Level Security is actively enabled on all target tables.
--    - Zero active RLS policies remain on target tables.
--    - Both anon and authenticated roles have zero effective privileges across all seven table operations
--      (SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER), including inherited privileges.
--    - service_role retains all required table privileges (SELECT, INSERT, UPDATE, DELETE).
-- 7. Force immediate PostgREST schema cache reload.

BEGIN;

-- 1. Ensure service_role has explicit schema USAGE
GRANT USAGE ON SCHEMA public TO service_role;

-- 2. Dynamic execution and comprehensive validation block
DO $$
DECLARE
  target_tables CONSTANT text[] := ARRAY['ddugky_candidates', 'candidate_documents', 'revoked_tokens'];
  client_roles  CONSTANT text[] := ARRAY['anon', 'authenticated'];
  table_privs   CONSTANT text[] := ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'];
  target_table  text;
  client_role   text;
  priv          text;
  pol           RECORD;
BEGIN
  -- =========================================================================
  -- SAFEGUARD A: Pre-flight Missing-Table Validation
  -- =========================================================================
  FOREACH target_table IN ARRAY target_tables
  LOOP
    IF to_regclass('public.' || target_table) IS NULL THEN
      RAISE EXCEPTION 'CPASS Lockdown Safeguard A Failed: Target table public.% does not exist', target_table;
    END IF;
  END LOOP;

  -- =========================================================================
  -- LOCKDOWN EXECUTION: Enable RLS, Purge Policies, Configure Privileges
  -- =========================================================================
  FOREACH target_table IN ARRAY target_tables
  LOOP
    -- A. Enable Row Level Security
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', target_table);

    -- B. Dynamically drop all existing policies on this table
    FOR pol IN
      SELECT policyname
      FROM pg_policies
      WHERE schemaname = 'public' 
        AND tablename = target_table
    LOOP
      EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', pol.policyname, target_table);
    END LOOP;

    -- C. Revoke all table privileges from client roles and PUBLIC
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated, PUBLIC', target_table);

    -- D. Ensure backend service_role retains full operational permissions
    EXECUTE format('GRANT ALL ON TABLE public.%I TO service_role', target_table);
  END LOOP;

  -- =========================================================================
  -- SAFEGUARD B: Post-Lockdown Permission & Security Validation
  -- =========================================================================
  -- B1. Validate service_role has BYPASSRLS attribute
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'service_role' AND rolbypassrls = true
  ) THEN
    RAISE EXCEPTION 'CPASS Lockdown Safeguard B Failed: role service_role does not possess BYPASSRLS attribute';
  END IF;

  -- B2. Validate service_role has USAGE privilege on schema public
  IF NOT has_schema_privilege('service_role', 'public', 'USAGE') THEN
    RAISE EXCEPTION 'CPASS Lockdown Safeguard B Failed: service_role lacks USAGE privilege on schema public';
  END IF;

  -- B3. Per-table validation checks
  FOREACH target_table IN ARRAY target_tables
  LOOP
    -- B3.1 Verify Row Level Security is active
    IF NOT EXISTS (
      SELECT 1 FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'public' 
        AND c.relname = target_table 
        AND c.relrowsecurity = true
    ) THEN
      RAISE EXCEPTION 'CPASS Lockdown Safeguard B Failed: RLS is not enabled on public.%', target_table;
    END IF;

    -- B3.2 Verify zero active RLS policies remain
    IF EXISTS (
      SELECT 1 FROM pg_policies
      WHERE schemaname = 'public' AND tablename = target_table
    ) THEN
      RAISE EXCEPTION 'CPASS Lockdown Safeguard B Failed: active RLS policies remain on public.%', target_table;
    END IF;

    -- B3.3 Verify anon and authenticated retain zero effective privileges across all seven operations
    FOREACH client_role IN ARRAY client_roles
    LOOP
      FOREACH priv IN ARRAY table_privs
      LOOP
        IF has_table_privilege(client_role, 'public.' || target_table, priv) THEN
          RAISE EXCEPTION 'CPASS Lockdown Safeguard B Failed: role % retains effective % privilege on public.%', client_role, priv, target_table;
        END IF;
      END LOOP;
    END LOOP;

    -- B3.4 Verify service_role retains required table privileges
    FOREACH priv IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE']
    LOOP
      IF NOT has_table_privilege('service_role', 'public.' || target_table, priv) THEN
        RAISE EXCEPTION 'CPASS Lockdown Safeguard B Failed: service_role lacks required % privilege on public.%', priv, target_table;
      END IF;
    END LOOP;
  END LOOP;

END $$;

COMMIT;

-- 3. Notify PostgREST to reload its schema cache immediately
NOTIFY pgrst, 'reload schema';
