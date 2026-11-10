-- 0010_auth_revocation_timestamps.sql
-- Migration 0010: Authoritative token-level and password revocation mechanisms.
--
-- 1. Profiles table: password_changed_at (for user-level password revocation)
-- 2. Revoked tokens table: token-level blacklist for session-specific logout and refresh rotation

ALTER TABLE IF EXISTS public.profiles
  ADD COLUMN IF NOT EXISTS password_changed_at timestamptz;

COMMENT ON COLUMN public.profiles.password_changed_at IS 'Authoritative timestamp of password change. Tokens issued (iat) prior to this timestamp are rejected on cache miss across all sessions.';

CREATE INDEX IF NOT EXISTS idx_profiles_password_changed_at ON public.profiles (id, password_changed_at);

-- Shared authoritative blacklist of revoked access tokens (keyed by SHA-256 digest)
CREATE TABLE IF NOT EXISTS public.revoked_tokens (
  token_hash text PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE public.revoked_tokens IS 'Authoritative blacklist of revoked access tokens (SHA-256 digests) for session-specific logout and refresh rotation.';
COMMENT ON COLUMN public.revoked_tokens.token_hash IS 'SHA-256 hexadecimal hash of the revoked access token. Never raw token.';
COMMENT ON COLUMN public.revoked_tokens.user_id IS 'Profile ID of the user owning the revoked session.';
COMMENT ON COLUMN public.revoked_tokens.expires_at IS 'Original JWT expiration timestamp for automatic pruning and cleanup.';

CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires_at ON public.revoked_tokens (expires_at);
CREATE INDEX IF NOT EXISTS idx_revoked_tokens_user_id ON public.revoked_tokens (user_id);
