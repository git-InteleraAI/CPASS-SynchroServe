import logging
import time
from typing import Callable, TypeVar
import httpx
from supabase import Client, ClientOptions, create_client

from .config import settings

logger = logging.getLogger("cpass.db")

TRANSIENT_ERRORS = (httpx.TransportError, BlockingIOError, OSError)
T = TypeVar("T")

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


def retry_read_query(query_func: Callable[[], T], max_attempts: int = 3, base_delay: float = 0.05) -> T:
    """Execute an idempotent read query with bounded retries for transient transport/socket errors.

    SAFE ONLY for idempotent GET / SELECT operations.
    NEVER use for document uploads, final submissions, or database mutations.
    """
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return query_func()
        except TRANSIENT_ERRORS as exc:
            last_exc = exc
            if attempt == max_attempts - 1:
                logger.error("Read query failed after %d attempts: %s", max_attempts, exc)
                raise
            sleep_time = base_delay * (attempt + 1)
            logger.warning(
                "Transient error on read query attempt %d (%s), retrying in %.2fs...",
                attempt + 1,
                exc,
                sleep_time,
            )
            time.sleep(sleep_time)
    if last_exc:
        raise last_exc

