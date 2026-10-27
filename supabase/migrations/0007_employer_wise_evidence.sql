-- CPASS migration 0007: Employer-wise placement evidence and consolidated bank statements
-- Supports:
-- 1. Linking documents to specific employers via employer_id
-- 2. Appointment letter uniqueness per candidate and employer
-- 3. Consolidated bank statements covering multiple months without duplicate uploads
-- 4. Preserves backward compatibility for single-employer records (employer_id IS NULL)

-- 1. Add employer_id and coverage columns to candidate_documents
ALTER TABLE candidate_documents ADD COLUMN IF NOT EXISTS employer_id text;
ALTER TABLE candidate_documents ADD COLUMN IF NOT EXISTS is_consolidated boolean NOT NULL DEFAULT false;
ALTER TABLE candidate_documents ADD COLUMN IF NOT EXISTS coverage_start_month int CHECK (coverage_start_month IS NULL OR (coverage_start_month >= 1 AND coverage_start_month <= 12));
ALTER TABLE candidate_documents ADD COLUMN IF NOT EXISTS coverage_start_year int CHECK (coverage_start_year IS NULL OR (coverage_start_year >= 2000 AND coverage_start_year <= 2050));
ALTER TABLE candidate_documents ADD COLUMN IF NOT EXISTS coverage_end_month int CHECK (coverage_end_month IS NULL OR (coverage_end_month >= 1 AND coverage_end_month <= 12));
ALTER TABLE candidate_documents ADD COLUMN IF NOT EXISTS coverage_end_year int CHECK (coverage_end_year IS NULL OR (coverage_end_year >= 2000 AND coverage_end_year <= 2050));
ALTER TABLE candidate_documents ADD COLUMN IF NOT EXISTS covered_months jsonb NOT NULL DEFAULT '[]'::jsonb;

-- 2. Update unique index for APPOINTMENT_LETTER to be unique per (candidate_id, employer_id)
DROP INDEX IF EXISTS idx_unique_active_appointment;
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_appointment_per_emp 
  ON candidate_documents(candidate_id, COALESCE(employer_id, '')) 
  WHERE document_type = 'APPOINTMENT_LETTER' AND upload_status != 'FAILED';

-- 3. Update unique index for single-month SALARY_SLIP and BANK_STATEMENT to include employer_id
DROP INDEX IF EXISTS idx_unique_candidate_doc_month;
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_candidate_doc_emp_month 
  ON candidate_documents(candidate_id, COALESCE(employer_id, ''), document_type, reporting_month, reporting_year) 
  WHERE document_type IN ('SALARY_SLIP', 'BANK_STATEMENT') AND is_consolidated IS NOT TRUE AND upload_status != 'FAILED';

-- 4. Index for fast employer lookup
CREATE INDEX IF NOT EXISTS idx_candidate_docs_emp ON candidate_documents (candidate_id, employer_id);

-- 5. Refresh PostgREST schema cache
NOTIFY pgrst, 'reload schema';
