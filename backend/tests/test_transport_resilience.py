"""Tests for Supabase HTTP/TLS transport resilience, bounded retries, and safe failure handling."""

import os
from unittest.mock import MagicMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.db import TRANSIENT_ERRORS, retry_read_query
from app.main import app

client = TestClient(app)


def test_retry_read_query_succeeds_after_transient_failures():
    """Verify that retry_read_query recovers if transient socket drops succeed on a subsequent attempt."""
    mock_func = MagicMock()
    # Fail twice with SSL unexpected EOF and WinError 10035, then succeed on attempt 3
    mock_func.side_effect = [
        httpx.ConnectError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol"),
        httpx.ReadError("[WinError 10035] A non-blocking socket operation could not be completed immediately"),
        {"status": "success", "count": 42},
    ]

    result = retry_read_query(mock_func, max_attempts=3, base_delay=0.01)
    assert result == {"status": "success", "count": 42}
    assert mock_func.call_count == 3


def test_retry_read_query_exhaustion_raises():
    """Verify that retry_read_query raises the original transport error when all attempts are exhausted."""
    mock_func = MagicMock()
    mock_func.side_effect = httpx.ConnectError("[SSL: UNEXPECTED_EOF_WHILE_READING]")

    with pytest.raises(httpx.ConnectError):
        retry_read_query(mock_func, max_attempts=3, base_delay=0.01)

    assert mock_func.call_count == 3


def test_get_current_user_raises_503_on_transport_failure():
    """Verify that get_current_user returns HTTP 503 instead of 401 or 500 on transport failure,
    and NEVER bypasses authentication.
    """
    mock_request = MagicMock()
    mock_request.cookies = {}

    with patch("app.auth.supabase") as mock_sb:
        mock_sb.auth.get_user.side_effect = httpx.ConnectError("[SSL: UNEXPECTED_EOF_WHILE_READING]")

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(mock_request, authorization="Bearer some_token")

        assert exc_info.value.status_code == 503
        assert "temporarily unreachable" in exc_info.value.detail.lower()
        assert exc_info.value.headers.get("Retry-After") == "1"


def test_check_candidate_centre_raises_503_on_transport_failure():
    """Verify that _check_candidate_centre returns HTTP 503 instead of 404 or 500 on transport failure,
    and NEVER treats a network drop as evidence that a candidate does not exist.
    """
    from app.auth import CurrentUser
    from app.routers.audits import _check_candidate_centre

    dummy_user = CurrentUser(
        id="user-123",
        email="coord@example.com",
        full_name="Test Coordinator",
        role="L1_COORDINATOR",
        assigned_state="TAMIL NADU",
    )

    with patch("app.routers.audits.supabase") as mock_sb:
        mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = (
            httpx.ReadError("[WinError 10035] A non-blocking socket operation could not be completed immediately")
        )

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _check_candidate_centre(dummy_user, candidate_id=99999)

        # Must be 503 Service Unavailable, NEVER 404 Not Found or 500
        assert exc_info.value.status_code == 503
        assert "temporarily unreachable" in exc_info.value.detail.lower()
        assert exc_info.value.headers.get("Retry-After") == "1"


def test_global_transient_error_handler_returns_503():
    """Verify that unhandled transport errors reaching FastAPI return 503 with Retry-After header."""
    from fastapi import APIRouter

    test_router = APIRouter()

    @test_router.get("/test-transient-error")
    def fail_with_transport():
        raise httpx.ConnectError("[SSL: UNEXPECTED_EOF_WHILE_READING]")

    app.include_router(test_router)

    res = client.get("/test-transient-error")
    assert res.status_code == 503
    assert res.headers.get("retry-after") == "1"
    assert "temporarily unreachable" in res.json().get("detail", "").lower()
