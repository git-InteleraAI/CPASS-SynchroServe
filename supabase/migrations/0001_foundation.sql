-- CPASS foundation schema (draft v0.1). Statuses/doc types are text-friendly so they can change after confirmation.

create type app_role as enum ('ADMIN','L1_COORDINATOR','L2_MANAGER','L3_LEADER');
create type submission_status as enum
  ('DRAFT','SUBMITTED_TO_L2','L2_RETURNED','L2_APPROVED','L3_RETURNED','L3_FINAL_APPROVED');

-- ---------- master data (imported from Excel) ----------
create table training_centres (
  tc_id         bigint primary key,
  name          text not null,
  state_name    text,
  district_name text,
  mpr_id        text
);

create table batches (
  kb_batch_id     bigint primary key,
  batch_code      text,
  tc_id           bigint not null references training_centres(tc_id),
  sanction_order  text,
  trade_name      text,
  start_date      date,
  end_date        date
);
create index on batches (tc_id, sanction_order);

create table candidates (
  candidate_id  bigint primary key,
  kb_batch_id   bigint not null references batches(kb_batch_id),
  state_name    text,
  first_name    text,
  last_name     text,
  father_name   text,
  gender        text,
  dob           date,
  mobile        text,
  appointed     boolean not null default false,
  employer_name text,
  raw           jsonb not null default '{}'   -- full original Excel row, nothing lost
);
create index on candidates (kb_batch_id);

-- ---------- users ----------
create table profiles (
  id         uuid primary key references auth.users(id) on delete cascade,
  full_name  text not null,
  email      text,
  role       app_role not null,
  is_active  boolean not null default true,
  created_at timestamptz not null default now()
);

create table user_centres (           -- which centres a user may work on (L1/L2; L3 and ADMIN see all)
  user_id uuid   not null references profiles(id) on delete cascade,
  tc_id   bigint not null references training_centres(tc_id),
  primary key (user_id, tc_id)
);

-- ---------- workflow ----------
create table submissions (
  id                   uuid primary key default gen_random_uuid(),
  candidate_id         bigint not null unique references candidates(candidate_id),
  status               submission_status not null default 'DRAFT',
  salary_amount        numeric(12,2),
  salary_received_date date,
  details              jsonb not null default '{}',   -- extra placement fields once confirmed
  created_by           uuid references profiles(id),
  submitted_at         timestamptz,
  l2_reviewer_id       uuid references profiles(id),
  l2_reviewed_at       timestamptz,
  l3_reviewer_id       uuid references profiles(id),
  l3_reviewed_at       timestamptz,
  return_count         int not null default 0,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);
create index on submissions (status);

create table documents (
  id               uuid primary key default gen_random_uuid(),
  submission_id    uuid not null references submissions(id) on delete cascade,
  doc_type         text not null,                       -- e.g. OFFER_LETTER, PAYSLIP (list to be confirmed)
  version          int  not null default 1,
  is_current       boolean not null default true,
  file_name        text not null,
  mime_type        text,
  size_bytes       bigint,
  storage_provider text not null default 'supabase',    -- later: 'gdrive'
  storage_file_id  text not null,                       -- storage path or Drive file ID
  uploaded_by      uuid references profiles(id),
  uploaded_at      timestamptz not null default now()
);
create index on documents (submission_id);

create table status_history (
  id            bigserial primary key,
  submission_id uuid not null references submissions(id) on delete cascade,
  from_status   submission_status,
  to_status     submission_status not null,
  acted_by      uuid references profiles(id),
  remark        text,
  created_at    timestamptz not null default now()
);

create table edit_log (
  id            bigserial primary key,
  submission_id uuid not null references submissions(id) on delete cascade,
  field_name    text not null,
  old_value     text,
  new_value     text,
  reason        text,
  edited_by     uuid references profiles(id),
  created_at    timestamptz not null default now()
);

create table audit_log (
  id         bigserial primary key,
  user_id    uuid,
  action     text not null,
  entity     text,
  entity_id  text,
  details    jsonb,
  created_at timestamptz not null default now()
);

-- ---------- security: RLS on everywhere ----------
alter table training_centres enable row level security;
alter table batches          enable row level security;
alter table candidates       enable row level security;
alter table profiles         enable row level security;
alter table user_centres     enable row level security;
alter table submissions      enable row level security;
alter table documents        enable row level security;
alter table status_history   enable row level security;
alter table edit_log         enable row level security;
alter table audit_log        enable row level security;

-- A signed-in user may read only their own profile directly; everything else goes through the backend (service role).
create policy "own profile" on profiles for select using (auth.uid() = id);
