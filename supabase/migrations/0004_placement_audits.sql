-- CPASS migration 0004: Placement Audits Table for Candidate Placement Audit & Sign-off Statement
-- Reversible migration: creates placement_audits table with JSONB structure for L1 coordinator workflow

CREATE TABLE IF NOT EXISTS placement_audits (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id        bigint NOT NULL UNIQUE REFERENCES ddugky_candidates(candidate_id) ON DELETE CASCADE,
  candidate_snapshot  jsonb NOT NULL DEFAULT '{}'::jsonb,
  employer_details    jsonb NOT NULL DEFAULT '[]'::jsonb,
  salary_details      jsonb NOT NULL DEFAULT '[]'::jsonb,
  document_audit      jsonb NOT NULL DEFAULT '{}'::jsonb,
  signoff_details     jsonb NOT NULL DEFAULT '{}'::jsonb,
  cpass_status        text NOT NULL DEFAULT 'PENDING',
  audit_status        text NOT NULL DEFAULT 'DRAFT' CHECK (audit_status IN ('DRAFT', 'SUBMITTED')),
  remarks             text,
  created_by          text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  finalized_at        timestamptz
);

-- Performance and lookup indexes
CREATE INDEX IF NOT EXISTS idx_placement_audits_candidate_id ON placement_audits (candidate_id);
CREATE INDEX IF NOT EXISTS idx_placement_audits_status ON placement_audits (audit_status);
CREATE INDEX IF NOT EXISTS idx_placement_audits_created_by ON placement_audits (created_by);

-- Enable Row Level Security (RLS)
ALTER TABLE placement_audits ENABLE ROW LEVEL SECURITY;

-- Server service-role bypasses RLS; policy for authenticated operations
CREATE POLICY "authenticated users can access placement audits" ON placement_audits
  FOR ALL USING (true) WITH CHECK (true);

-- Refresh PostgREST schema cache
NOTIFY pgrst, 'reload schema';
