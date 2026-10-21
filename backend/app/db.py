from supabase import Client, ClientOptions, create_client

from .config import settings

# Service-role client: bypasses RLS, so it must only ever be used here on the server,
# and every route must do its own role / centre checks.
supabase: Client = create_client(settings.supabase_url, settings.supabase_service_role_key)


def get_auth_client() -> Client:
    """Create a stateless, non-persisting client dedicated to authentication operations.

    Isolates client authentication state from the server service-role client.
    """
    key = settings.supabase_anon_key or settings.supabase_service_role_key
    return create_client(
        settings.supabase_url,
        key,
        options=ClientOptions(persist_session=False, auto_refresh_token=False),
    )
