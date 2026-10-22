-- CPASS migration 0005: Add OTHER_DOCUMENT support to candidate_documents
-- Preserves existing data, allows optional other document type and custom document title

ALTER TABLE candidate_documents DROP CONSTRAINT IF EXISTS candidate_documents_document_type_check;
ALTER TABLE candidate_documents ADD CONSTRAINT candidate_documents_document_type_check 
  CHECK (document_type IN ('APPOINTMENT_LETTER', 'SALARY_SLIP', 'BANK_STATEMENT', 'OTHER_DOCUMENT'));

ALTER TABLE candidate_documents ADD COLUMN IF NOT EXISTS document_title text;

-- Refresh PostgREST schema cache
NOTIFY pgrst, 'reload schema';
