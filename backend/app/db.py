import logging
import time
from typing import Callable, TypeVar
import httpcore
import httpx
from supabase import Client, ClientOptions, create_client

from .config import settings

logger = logging.getLogger("cpass.db")

TRANSIENT_ERRORS = (
    httpx.TransportError,
    httpcore.NetworkError,
    httpcore.ProtocolError,
    BlockingIOError,
    ConnectionError,
    TimeoutError,
    OSError,
)
T = TypeVar("T")

# Shared HTTP client configured with HTTP/1.1 (disabling HTTP/2 to prevent
# idle multiplexing TLS disconnects / WinError 10035 / UNEXPECTED_EOF on Windows),
# bounded connection pooling, and proactive keep-alive expiry.
_http_client: httpx.Client = httpx.Client(
    http2=False,
    limits=httpx.Limits(
        max_connections=50,
        max_keepalive_connections=10,
        keepalive_expiry=30.0,
    ),
    timeout=httpx.Timeout(20.0, connect=5.0),
    follow_redirects=True,
    verify=True,
)

# Service-role client: bypasses RLS, so it must only ever be used here on the server,
# and every route must do its own role / centre checks.
supabase: Client = create_client(
    settings.supabase_url,
    settings.supabase_service_role_key,
    options=ClientOptions(httpx_client=_http_client),
)


def get_auth_client() -> Client:
    """Create a stateless, non-persisting client dedicated to authentication operations.

    Isolates client authentication state from the server service-role client while
    reusing the robust HTTP/1.1 transport pool.
    """
    key = settings.supabase_anon_key or settings.supabase_service_role_key
    return create_client(
        settings.supabase_url,
        key,
        options=ClientOptions(
            persist_session=False,
            auto_refresh_token=False,
            httpx_client=_http_client,
        ),
    )


def close_db_clients() -> None:
    """Close underlying HTTP client and connection pools on application shutdown."""
    try:
        if not _http_client.is_closed:
            _http_client.close()
    except Exception as exc:
        logger.warning("Error closing Supabase HTTP client pool: %s", exc)


def retry_read_query(query_func: Callable[[], T], max_attempts: int = 3, base_delay: float = 0.1) -> T:
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


