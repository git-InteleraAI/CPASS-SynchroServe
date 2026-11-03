-- CPASS migration 0009: Unified Five-Level Workflow, Multi-State Scoping, and Audit Status Check
-- Supports:
-- 1. Multi-state assignments for L4 Business Leaders (BL) via assigned_states text[]
-- 2. Backwards-compatible fallback with existing assigned_state text
-- 3. Expands placement_audits_audit_status_check to accommodate flexible returns (L1, L2, L3, L4)
-- 4. Preserves all existing records and RLS policies

-- 1. Add assigned_states text[] to profiles table
ALTER TABLE IF EXISTS profiles ADD COLUMN IF NOT EXISTS assigned_states text[];
COMMENT ON COLUMN profiles.assigned_states IS 'Array of canonical state names permitted for multi-state roles (e.g. BL users). NULL/empty for single-state or national roles.';

CREATE INDEX IF NOT EXISTS idx_profiles_assigned_states ON profiles USING GIN (assigned_states);

-- Backfill assigned_states from assigned_state for existing profiles
UPDATE profiles 
SET assigned_states = ARRAY[assigned_state] 
WHERE assigned_state IS NOT NULL AND (assigned_states IS NULL OR cardinality(assigned_states) = 0);

-- 2. Update placement_audits_audit_status_check constraint
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint 
    WHERE conname = 'placement_audits_audit_status_check' 
      AND conrelid = 'placement_audits'::regclass
  ) THEN
    ALTER TABLE placement_audits DROP CONSTRAINT placement_audits_audit_status_check;
  END IF;

  ALTER TABLE placement_audits ADD CONSTRAINT placement_audits_audit_status_check
    CHECK (audit_status IN ('DRAFT', 'SUBMITTED', 'RETURNED_TO_L1', 'RETURNED_TO_L2', 'RETURNED_TO_L3', 'RETURNED_TO_L4', 'REJECTED', 'APPROVED'));
END $$;

-- 3. Refresh PostgREST schema cache
NOTIFY pgrst, 'reload schema';

