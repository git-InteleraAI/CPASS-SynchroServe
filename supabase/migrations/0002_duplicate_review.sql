-- CPASS migration 0002: Duplicate Detection and Review Workflow
-- Preserves all candidate records and Candidate_IDs.
-- Adds review cases, case members, auditable history, and submission hold tracking.

-- 1. Status enum for duplicate review workflow
create type duplicate_case_status as enum (
  'PENDING',
  'UNDER_REVIEW',
  'CONFIRMED_DUPLICATE',
  'DISTINCT_CANDIDATES',
  'DATA_CORRECTION_REQUIRED',
  'UNRESOLVED'
);

-- 2. Duplicate review cases
create table duplicate_cases (
  id               uuid primary key default gen_random_uuid(),
  rule_code        text not null,                       -- e.g. 'NAME_DOB', 'NAME_DOB_FATHER', 'SHARED_MOBILE', 'SIMILAR_NAME_DOB', 'CONFLICTING_IDENTIFIER'
  rule_description text not null,
  status           duplicate_case_status not null default 'PENDING',
  severity         text not null default 'POTENTIAL',   -- 'POTENTIAL' vs 'CRITICAL'
  tc_id            bigint references training_centres(tc_id), -- context centre if case is localized to a centre
  last_reviewed_by uuid references profiles(id),
  last_reviewed_at timestamptz,
  last_decision    text,
  last_reason      text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create index on duplicate_cases (status);
create index on duplicate_cases (rule_code);
create index on duplicate_cases (tc_id);

-- 3. Case members: links to candidates without duplicating sensitive PII
create table duplicate_case_members (
  id             uuid primary key default gen_random_uuid(),
  case_id        uuid not null references duplicate_cases(id) on delete cascade,
  candidate_id   bigint not null references candidates(candidate_id) on delete cascade,
  match_metadata jsonb not null default '{}',          -- non-sensitive match metadata (e.g. normalized match tokens)
  created_at     timestamptz not null default now(),
  unique (case_id, candidate_id)
);
create index on duplicate_case_members (case_id);
create index on duplicate_case_members (candidate_id);

-- 4. Audit trail for review actions and status transitions
create table duplicate_review_history (
  id          bigserial primary key,
  case_id     uuid not null references duplicate_cases(id) on delete cascade,
  from_status duplicate_case_status,
  to_status   duplicate_case_status not null,
  decision    text not null,
  reason      text not null,                            -- mandatory for consequential transitions
  acted_by    uuid not null references profiles(id),
  created_at  timestamptz not null default now()
);
create index on duplicate_review_history (case_id);
create index on duplicate_review_history (acted_by);

-- 5. Candidate submission holds
-- Unresolved duplicate cases produce warnings by default and DO NOT block submission.
-- Submission is blocked ONLY when an active hold is placed by an authorized reviewer or critical integrity rule.
create table candidate_holds (
  id             uuid primary key default gen_random_uuid(),
  candidate_id   bigint not null references candidates(candidate_id) on delete cascade,
  case_id        uuid references duplicate_cases(id) on delete set null,
  is_active      boolean not null default true,
  hold_reason    text not null,
  placed_by      uuid not null references profiles(id),
  placed_at      timestamptz not null default now(),
  released_by    uuid references profiles(id),
  released_at    timestamptz,
  release_reason text
);
create index on candidate_holds (candidate_id, is_active);

-- ---------- Security: Row Level Security on all review tables ----------
alter table duplicate_cases          enable row level security;
alter table duplicate_case_members   enable row level security;
alter table duplicate_review_history enable row level security;
alter table candidate_holds          enable row level security;

-- Policies: ADMIN and L3_LEADER see all cases; L1 and L2 see cases matching their centre scope.
create policy "users can view duplicate cases in their centres" on duplicate_cases
  for select using (
    exists (
      select 1 from profiles p
      where p.id = auth.uid()
        and (
          p.role in ('ADMIN', 'L3_LEADER')
          or (
            duplicate_cases.tc_id is not null
            and exists (
              select 1 from user_centres uc
              where uc.user_id = auth.uid() and uc.tc_id = duplicate_cases.tc_id
            )
          )
        )
    )
  );

create policy "users can view duplicate case members in their centres" on duplicate_case_members
  for select using (
    exists (
      select 1 from duplicate_cases dc
      where dc.id = duplicate_case_members.case_id
        and exists (
          select 1 from profiles p
          where p.id = auth.uid()
            and (
              p.role in ('ADMIN', 'L3_LEADER')
              or (
                dc.tc_id is not null
                and exists (
                  select 1 from user_centres uc
                  where uc.user_id = auth.uid() and uc.tc_id = dc.tc_id
                )
              )
            )
        )
    )
  );

create policy "users can view duplicate review history in their centres" on duplicate_review_history
  for select using (
    exists (
      select 1 from duplicate_cases dc
      where dc.id = duplicate_review_history.case_id
        and exists (
          select 1 from profiles p
          where p.id = auth.uid()
            and (
              p.role in ('ADMIN', 'L3_LEADER')
              or (
                dc.tc_id is not null
                and exists (
                  select 1 from user_centres uc
                  where uc.user_id = auth.uid() and uc.tc_id = dc.tc_id
                )
              )
            )
        )
    )
  );

create policy "users can view candidate holds in their centres" on candidate_holds
  for select using (
    exists (
      select 1 from profiles p
      where p.id = auth.uid()
        and (
          p.role in ('ADMIN', 'L3_LEADER')
          or exists (
            select 1 from candidates c
            join batches b on b.kb_batch_id = c.kb_batch_id
            join user_centres uc on uc.tc_id = b.tc_id
            where c.candidate_id = candidate_holds.candidate_id
              and uc.user_id = auth.uid()
          )
        )
    )
  );
