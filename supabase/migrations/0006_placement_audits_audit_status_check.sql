-- CPASS migration 0006: Expand placement_audits_audit_status_check check constraint
-- Permits canonical audit statuses: 'DRAFT', 'SUBMITTED', 'RETURNED_TO_L1', 'REJECTED', 'APPROVED'
-- Preserves existing permitted statuses ('DRAFT', 'SUBMITTED') and allows return/rejection/approval workflows.

DO $$
BEGIN
  -- Drop existing check constraint if it exists
  IF EXISTS (
    SELECT 1 FROM pg_constraint 
    WHERE conname = 'placement_audits_audit_status_check' 
      AND conrelid = 'placement_audits'::regclass
  ) THEN
    ALTER TABLE placement_audits DROP CONSTRAINT placement_audits_audit_status_check;
  END IF;

  -- Add updated check constraint with all canonical statuses
  ALTER TABLE placement_audits ADD CONSTRAINT placement_audits_audit_status_check
    CHECK (audit_status IN ('DRAFT', 'SUBMITTED', 'RETURNED_TO_L1', 'REJECTED', 'APPROVED'));
END $$;

-- Refresh PostgREST schema cache
NOTIFY pgrst, 'reload schema';
