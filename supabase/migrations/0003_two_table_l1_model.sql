-- CPASS migration 0003: Two-Table Supabase Data Model for L1 Workflow
-- Application Data Table A: ddugky_candidates (full 76 source columns preserved + raw_data JSONB)
-- Application Data Table B: candidate_documents (Google Drive metadata, month-wise salary/bank statements)

-- 1. Candidate Master Data Table
CREATE TABLE IF NOT EXISTS ddugky_candidates (
  candidate_id                     bigint PRIMARY KEY,
  sl_no                            text,
  kaushal_panjee_id                text,
  state_name                       text,
  district_name                    text,
  block_name                       text,
  sanction_order_number            text,
  kb_project_id                    text,
  permanent_address_village        text,
  permanent_pincode                text,
  candidate_email                  text,
  candidate_qualification          text,
  candidate_father_name            text,
  mpr_project_id                   text,
  tc_name                          text,
  tc_mpr_id                        text,
  tc_id                            bigint,
  tc_state_name                    text,
  tc_district_name                 text,
  parliamentary_constituency_name  text,
  assembly_constituency_name       text,
  kb_batch_id                      bigint,
  batch_mpr_id                     text,
  batch_code                       text,
  batch_start_date                 date,
  batch_end_date                   date,
  candidate_mpr_id                 text,
  candidate_first_name             text,
  candidate_last_name              text,
  gender                           text,
  category                         text,
  pwd                              text,
  minority                         text,
  trade_name                       text,
  trade_code                       text,
  sector                           text,
  religion                         text,
  date_of_birth                    date,
  mobile_number                    text,
  nature_of_training               text,
  aadhar                           text,
  bank_account                     text,
  house_number                     text,
  permanent_address                text,
  trained                          text,
  dropout_status                   text,
  assessed_date                    text,
  certified_status                 text,
  certified_date                   text,
  appointed                        boolean NOT NULL DEFAULT false,
  employer_name                    text,
  employer_workplace_location      text,
  workplace_contact_details        text,
  monthly_ctc                      numeric(12,2),
  gross_salary                     numeric(12,2),
  net_salary                       numeric(12,2),
  joining_date                     text,
  employer_state                   text,
  employer_district                text,
  work_place_state                 text,
  work_place_district              text,
  appointment_letter_ref           text,
  bs1                              text,
  bs2                              text,
  bs3                              text,
  ps1                              text,
  ps2                              text,
  ps3                              text,
  pps_1                            text,
  pps_1_date                       text,
  pps_2                            text,
  pps_2_date                       text,
  pps_3                            text,
  pps_3_date                       text,
  tp3_uploaded                     text,
  verified_in_kb                   text,
  raw_data                         jsonb NOT NULL DEFAULT '{}',
  created_at                       timestamptz NOT NULL DEFAULT now(),
  updated_at                       timestamptz NOT NULL DEFAULT now()
);

-- Indexes for high-performance L1 cascading dropdowns
CREATE INDEX IF NOT EXISTS idx_ddugky_cand_state ON ddugky_candidates (state_name);
CREATE INDEX IF NOT EXISTS idx_ddugky_cand_tc_state ON ddugky_candidates (tc_state_name);
CREATE INDEX IF NOT EXISTS idx_ddugky_cand_tc ON ddugky_candidates (tc_id, tc_name);
CREATE INDEX IF NOT EXISTS idx_ddugky_cand_sanction ON ddugky_candidates (sanction_order_number);
CREATE INDEX IF NOT EXISTS idx_ddugky_cand_batch ON ddugky_candidates (kb_batch_id, batch_code);
CREATE INDEX IF NOT EXISTS idx_ddugky_cand_cascade ON ddugky_candidates (tc_state_name, tc_id, sanction_order_number, kb_batch_id);

-- 2. Document Uploads Table
CREATE TABLE IF NOT EXISTS candidate_documents (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id        bigint NOT NULL REFERENCES ddugky_candidates(candidate_id) ON DELETE CASCADE,
  document_type       text NOT NULL CHECK (document_type IN ('APPOINTMENT_LETTER', 'SALARY_SLIP', 'BANK_STATEMENT')),
  reporting_month     int CHECK (reporting_month IS NULL OR (reporting_month >= 1 AND reporting_month <= 12)),
  reporting_year      int CHECK (reporting_year IS NULL OR (reporting_year >= 2000 AND reporting_year <= 2050)),
  drive_file_id       text,
  drive_folder_id     text,
  drive_folder_path   text,
  file_name           text NOT NULL,
  mime_type           text,
  file_size_bytes     bigint,
  upload_status       text NOT NULL DEFAULT 'PENDING' CHECK (upload_status IN ('PENDING', 'SUCCESS', 'FAILED')),
  uploaded_by         text,
  error_message       text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Constraint: At most one active appointment/offer letter per candidate
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_appointment 
  ON candidate_documents(candidate_id) 
  WHERE document_type = 'APPOINTMENT_LETTER' AND upload_status != 'FAILED';

-- Constraint: Prevent duplicate records for same candidate, doc type, and reporting month/year
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_candidate_doc_month 
  ON candidate_documents(candidate_id, document_type, reporting_month, reporting_year) 
  WHERE document_type IN ('SALARY_SLIP', 'BANK_STATEMENT') AND upload_status != 'FAILED';

CREATE INDEX IF NOT EXISTS idx_candidate_docs_cand_id ON candidate_documents (candidate_id);
CREATE INDEX IF NOT EXISTS idx_candidate_docs_type ON candidate_documents (document_type);

-- 3. Profiles table for user authentication
CREATE TABLE IF NOT EXISTS profiles (
  id         uuid PRIMARY KEY,
  full_name  text NOT NULL,
  email      text,
  role       text NOT NULL DEFAULT 'L1_COORDINATOR',
  is_active  boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);
