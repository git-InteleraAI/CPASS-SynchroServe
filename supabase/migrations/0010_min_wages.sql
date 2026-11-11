-- CPASS migration 0010: State-wise Semi-Skilled Minimum Wages Master Table
-- Stores statutory semi-skilled monthly minimum wage revisions (2010-2026) for 13 states.

CREATE TABLE IF NOT EXISTS public.min_wages (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  state            text NOT NULL,
  month            int NOT NULL CHECK (month >= 1 AND month <= 12),
  year             int NOT NULL CHECK (year >= 2000 AND year <= 2050),
  effective_date   date NOT NULL,
  skill_category   text NOT NULL DEFAULT 'SEMI-SKILLED',
  minimum_wage     numeric(10, 2) NOT NULL CHECK (minimum_wage > 0),
  source           text NOT NULL DEFAULT 'Minimum Wages Semi-Skilled Register (2010-2026)',
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

-- Unique constraint: exactly one revision per state, effective date, and skill category
CREATE UNIQUE INDEX IF NOT EXISTS idx_min_wages_state_effective_skill
  ON public.min_wages (state, effective_date, skill_category);

-- Lookup index for effective date queries: state + effective_date DESC
CREATE INDEX IF NOT EXISTS idx_min_wages_lookup
  ON public.min_wages (state, effective_date DESC);

-- Enable Row Level Security
ALTER TABLE public.min_wages ENABLE ROW LEVEL SECURITY;

-- Allow authenticated users read-only SELECT access
DROP POLICY IF EXISTS "authenticated users can read min_wages" ON public.min_wages;
CREATE POLICY "authenticated users can read min_wages"
  ON public.min_wages
  FOR SELECT
  TO authenticated
  USING (true);

COMMENT ON TABLE public.min_wages IS 'Authoritative master table for state-wise semi-skilled minimum wage revisions (2010-2026).';

