-- CPASS migration 0005: State-based authorization for L1 Placement Coordinators
-- Adds assigned_state to profiles table and creates index for fast state lookups.

ALTER TABLE IF EXISTS profiles ADD COLUMN IF NOT EXISTS assigned_state text;

COMMENT ON COLUMN profiles.assigned_state IS 'Canonical state name permitted for L1 Placement Coordinators (e.g. TAMIL NADU, KERALA). NULL for unrestricted executive roles.';

CREATE INDEX IF NOT EXISTS idx_profiles_assigned_state ON profiles (assigned_state);

-- Refresh PostgREST schema cache
NOTIFY pgrst, 'reload schema';
