"""Comprehensive automated tests for Stateless Pure ASGI CSRF Protection.

Verifies:
- Strict Origin validation per RFC 6454.
- Exact trusted origin matching (rejects localhost.attacker.com, localhost-phish.com, wrong ports).
- Safe Referer fallback ONLY when Origin header is genuinely absent.
- Rejection of Origin: null (never falls back to Referer).
- Rejection of malformed origins, credentials, paths, query strings, and fragments.
- Rejection of duplicate Origin, Referer, or X-Requested-With headers.
- Mandatory X-Requested-With: XMLHttpRequest custom header on all browser mutations.
- Bearer-only API client compatibility (bypasses CSRF when NO ambient session cookies exist).
- Enforcement of CSRF when ambient session cookies are present, even if Bearer is also sent.
- Login CSRF protection on unauthenticated /auth/login.
- Multipart document upload protection before endpoint or storage execution.
- Systematic protection across ALL registered state-changing endpoints (all 31 identified endpoints).
- CORS preflight and CORS header attachment on CSRF 403 rejections.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, get_current_user
from app.config import settings
from app.main import (
    app,
    compute_trusted_origins,
    parse_origin,
    parse_referer,
)

client = TestClient(app)

TRUSTED_ORIGIN = "http://localhost:5173"
VALID_XHR = "XMLHttpRequest"

AUTH_USER = CurrentUser(
    id="test-csrf-user-123",
    email="testuser@cpass.org",
    full_name="CSRF Test User",
    role="L1_COORDINATOR",
    assigned_state="ODISHA",
)


# ---------------------------------------------------------------------------
# 1. Unit Tests for parse_origin and parse_referer
# ---------------------------------------------------------------------------


def test_parse_origin_rfc6454_compliance():
    # Valid serialized origins
    assert parse_origin("http://localhost:5173") == "http://localhost:5173"
    assert parse_origin("https://cpass.synchroserve.in") == "https://cpass.synchroserve.in"
    assert parse_origin("HTTP://LOCALHOST:5173") == "http://localhost:5173"

    # Default port normalization
    assert parse_origin("http://localhost:80") == "http://localhost"
    assert parse_origin("https://localhost:443") == "https://localhost"

    # Rejection: null
    assert parse_origin("null") is None
    assert parse_origin("NULL") is None

    # Rejection: invalid schemes
    assert parse_origin("ftp://localhost:5173") is None
    assert parse_origin("javascript:alert(1)") is None
    assert parse_origin("data:text/html,abc") is None

    # Rejection: user info
    assert parse_origin("http://user:pass@localhost:5173") is None
    assert parse_origin("http://admin@localhost:5173") is None

    # Rejection: paths, queries, fragments
    assert parse_origin("http://localhost:5173/") is None
    assert parse_origin("http://localhost:5173/path") is None
    assert parse_origin("http://localhost:5173?key=val") is None
    assert parse_origin("http://localhost:5173#frag") is None

    # Rejection: ports
    assert parse_origin("http://localhost:0") is None
    assert parse_origin("http://localhost:65536") is None
    assert parse_origin("http://localhost:-1") is None
    assert parse_origin("http://localhost:abc") is None

    # Rejection: non-string / empty
    assert parse_origin("") is None
    assert parse_origin("   ") is None
    assert parse_origin(None) is None


def test_parse_referer_extraction():
    # Valid full Referer URLs
    assert parse_referer("http://localhost:5173") == "http://localhost:5173"
    assert parse_referer("http://localhost:5173/") == "http://localhost:5173"
    assert parse_referer("http://localhost:5173/candidates/101/documents?tab=l1#top") == "http://localhost:5173"
    assert parse_referer("https://cpass.synchroserve.in/dashboard") == "https://cpass.synchroserve.in"

    # Default port normalization
    assert parse_referer("http://localhost:80/candidates") == "http://localhost"
    assert parse_referer("https://localhost:443/candidates") == "https://localhost"

    # Rejection: null / empty
    assert parse_referer("null") is None
    assert parse_referer("") is None
    assert parse_referer(None) is None

    # Rejection: credentials in Referer
    assert parse_referer("http://user:pass@localhost:5173/path") is None

    # Rejection: invalid schemes / ports
    assert parse_referer("ftp://localhost:5173/path") is None
    assert parse_referer("http://localhost:0/path") is None
    assert parse_referer("http://localhost:70000/path") is None


def test_compute_trusted_origins():
    origins = ["http://localhost:5173/", " https://cpass.synchroserve.in ", "invalid-origin", "null"]
    trusted = compute_trusted_origins(origins)
    assert "http://localhost:5173" in trusted
    assert "https://cpass.synchroserve.in" in trusted
    assert "invalid-origin" not in trusted
    assert "null" not in trusted
    assert len(trusted) == 2


# ---------------------------------------------------------------------------
# 2. Origin Validation & Attacker Variants
# ---------------------------------------------------------------------------


def test_trusted_exact_origin_accepted():
    res = client.post(
        "/auth/login",
        json={"email": "wrong@cpass.org", "password": "wrong", "selected_role": "L1_COORDINATOR"},
        headers={"Origin": TRUSTED_ORIGIN, "X-Requested-With": VALID_XHR},
    )
    # Passed CSRF check, proceeded to authentication handler (which returns 401 for invalid credentials)
    assert res.status_code != 403


def test_untrusted_origin_rejected():
    res = client.post(
        "/auth/login",
        json={"email": "user@cpass.org", "password": "password"},
        headers={"Origin": "https://attacker.evil.com", "X-Requested-With": VALID_XHR},
    )
    assert res.status_code == 403
    assert "untrusted Origin" in res.json().get("detail", "")


def test_attacker_subdomain_and_suffix_rejected():
    attacker_origins = [
        "http://localhost.attacker.com",
        "http://localhost-phish.com",
        "http://attacker-localhost:5173",
        "http://localhost:8080",
        "http://localhost:3000",
        "https://cpass.synchroserve.in.attacker.com",
    ]
    for origin in attacker_origins:
        res = client.post(
            "/auth/login",
            json={"email": "user@cpass.org", "password": "password"},
            headers={"Origin": origin, "X-Requested-With": VALID_XHR},
        )
        assert res.status_code == 403, f"Expected 403 for attacker origin {origin}, got {res.status_code}"
        assert "untrusted Origin" in res.json().get("detail", "")


def test_origin_null_rejected():
    res = client.post(
        "/auth/login",
        json={"email": "user@cpass.org", "password": "password"},
        headers={"Origin": "null", "X-Requested-With": VALID_XHR},
    )
    assert res.status_code == 403
    assert "invalid Origin header" in res.json().get("detail", "")


def test_malformed_and_edge_case_origins_rejected():
    invalid_origins = [
        "http://user:pass@localhost:5173",
        "http://localhost:0",
        "http://localhost:65536",
        "http://localhost:abc",
        "http://localhost:5173/",
        "http://localhost:5173/path",
        "http://localhost:5173?query=1",
        "http://localhost:5173#fragment",
        "ftp://localhost:5173",
    ]
    for origin in invalid_origins:
        res = client.post(
            "/auth/login",
            json={"email": "user@cpass.org", "password": "password"},
            headers={"Origin": origin, "X-Requested-With": VALID_XHR},
        )
        assert res.status_code == 403, f"Expected 403 for invalid origin {origin}, got {res.status_code}"
        assert "invalid Origin header" in res.json().get("detail", "")


def test_duplicate_origin_headers_rejected():
    # Send duplicate Origin headers via raw headers list
    res = client.post(
        "/auth/login",
        json={"email": "user@cpass.org", "password": "password"},
        headers=[
            ("Origin", TRUSTED_ORIGIN),
            ("Origin", TRUSTED_ORIGIN),
            ("X-Requested-With", VALID_XHR),
        ],
    )
    assert res.status_code == 403
    assert "duplicate Origin header" in res.json().get("detail", "")


# ---------------------------------------------------------------------------
# 3. Referer Fallback & Safe Handling
# ---------------------------------------------------------------------------


def test_referer_fallback_success_when_origin_absent():
    res = client.post(
        "/auth/login",
        json={"email": "wrong@cpass.org", "password": "wrong", "selected_role": "L1_COORDINATOR"},
        headers={
            "Referer": f"{TRUSTED_ORIGIN}/login?redirect=/dashboard",
            "X-Requested-With": VALID_XHR,
        },
    )
    # Passed CSRF check via Referer fallback; hit auth handler
    assert res.status_code != 403


def test_untrusted_referer_rejected():
    res = client.post(
        "/auth/login",
        json={"email": "user@cpass.org", "password": "password"},
        headers={
            "Referer": "http://evil.attacker.com/exploit",
            "X-Requested-With": VALID_XHR,
        },
    )
    assert res.status_code == 403
    assert "untrusted Referer origin" in res.json().get("detail", "")


def test_missing_both_origin_and_referer_rejected():
    res = client.post(
        "/auth/login",
        json={"email": "user@cpass.org", "password": "password"},
        headers={"X-Requested-With": VALID_XHR},
    )
    assert res.status_code == 403
    assert "missing Origin and Referer headers" in res.json().get("detail", "")


def test_invalid_referer_rejected():
    res = client.post(
        "/auth/login",
        json={"email": "user@cpass.org", "password": "password"},
        headers={
            "Referer": "http://user:pass@localhost:5173/path",
            "X-Requested-With": VALID_XHR,
        },
    )
    assert res.status_code == 403
    assert "invalid Referer header" in res.json().get("detail", "")


def test_origin_null_never_falls_back_to_valid_referer():
    res = client.post(
        "/auth/login",
        json={"email": "user@cpass.org", "password": "password"},
        headers={
            "Origin": "null",
            "Referer": f"{TRUSTED_ORIGIN}/login",
            "X-Requested-With": VALID_XHR,
        },
    )
    assert res.status_code == 403
    assert "invalid Origin header" in res.json().get("detail", "")


def test_invalid_origin_never_falls_back_to_valid_referer():
    res = client.post(
        "/auth/login",
        json={"email": "user@cpass.org", "password": "password"},
        headers={
            "Origin": "http://user:pass@localhost:5173",
            "Referer": f"{TRUSTED_ORIGIN}/login",
            "X-Requested-With": VALID_XHR,
        },
    )
    assert res.status_code == 403
    assert "invalid Origin header" in res.json().get("detail", "")


def test_duplicate_referer_headers_rejected():
    res = client.post(
        "/auth/login",
        json={"email": "user@cpass.org", "password": "password"},
        headers=[
            ("Referer", f"{TRUSTED_ORIGIN}/login"),
            ("Referer", f"{TRUSTED_ORIGIN}/login"),
            ("X-Requested-With", VALID_XHR),
        ],
    )
    assert res.status_code == 403
    assert "duplicate Referer header" in res.json().get("detail", "")


# ---------------------------------------------------------------------------
# 4. Custom Header (X-Requested-With) Enforcement
# ---------------------------------------------------------------------------


def test_missing_custom_header_rejected():
    res = client.post(
        "/auth/login",
        json={"email": "user@cpass.org", "password": "password"},
        headers={"Origin": TRUSTED_ORIGIN},
    )
    assert res.status_code == 403
    assert "missing or invalid X-Requested-With header" in res.json().get("detail", "")


def test_incorrect_custom_header_rejected():
    for bad_xhr in ["Fetch", "true", "1", "XMLHttpRequest2", ""]:
        res = client.post(
            "/auth/login",
            json={"email": "user@cpass.org", "password": "password"},
            headers={"Origin": TRUSTED_ORIGIN, "X-Requested-With": bad_xhr},
        )
        assert res.status_code == 403
        assert "missing or invalid X-Requested-With header" in res.json().get("detail", "")


def test_case_insensitive_custom_header_accepted():
    res = client.post(
        "/auth/login",
        json={"email": "wrong@cpass.org", "password": "wrong", "selected_role": "L1_COORDINATOR"},
        headers={"Origin": TRUSTED_ORIGIN, "X-Requested-With": "xmlhttprequest"},
    )
    assert res.status_code != 403


def test_duplicate_custom_header_rejected():
    res = client.post(
        "/auth/login",
        json={"email": "user@cpass.org", "password": "password"},
        headers=[
            ("Origin", TRUSTED_ORIGIN),
            ("X-Requested-With", VALID_XHR),
            ("X-Requested-With", VALID_XHR),
        ],
    )
    assert res.status_code == 403
    assert "duplicate X-Requested-With header" in res.json().get("detail", "")


def test_custom_header_alone_with_untrusted_origin_rejected():
    res = client.post(
        "/auth/login",
        json={"email": "user@cpass.org", "password": "password"},
        headers={"Origin": "https://attacker.com", "X-Requested-With": VALID_XHR},
    )
    assert res.status_code == 403
    assert "untrusted Origin" in res.json().get("detail", "")


# ---------------------------------------------------------------------------
# 5. Authentication Context: Bearer-Only vs Cookie Sessions
# ---------------------------------------------------------------------------


def test_bearer_only_request_bypasses_csrf():
    # Pure Bearer API clients (e.g., CLI tools, scripts) without cookies bypass CSRF
    res = client.post(
        "/auth/change-password",
        json={"current_password": "foo", "new_password": "bar", "confirm_password": "bar"},
        headers={"Authorization": "Bearer sample-token"},
    )
    # Should bypass CSRF; may fail authentication/validation (401/400), but NOT 403 CSRF
    assert res.status_code != 403


def test_cookie_request_without_csrf_headers_rejected():
    client.cookies.set("cpass_access_token", "sample-access-token")
    res = client.post(
        "/auth/logout",
    )
    assert res.status_code == 403
    assert "missing or invalid X-Requested-With header" in res.json().get("detail", "")
    client.cookies.clear()


def test_cookie_plus_bearer_still_enforces_csrf():
    # An attacker providing a Bearer header cannot bypass CSRF if ambient session cookies exist
    client.cookies.set("cpass_access_token", "sample-access-token")
    res = client.post(
        "/auth/logout",
        headers={"Authorization": "Bearer dummy-token"},
    )
    assert res.status_code == 403
    assert "missing or invalid X-Requested-With header" in res.json().get("detail", "")

    # With trusted Origin and custom header, the request passes CSRF and reaches auth logic
    res_valid = client.post(
        "/auth/logout",
        headers={
            "Authorization": "Bearer dummy-token",
            "Origin": TRUSTED_ORIGIN,
            "X-Requested-With": VALID_XHR,
        },
    )
    assert res_valid.status_code != 403
    client.cookies.clear()


# ---------------------------------------------------------------------------
# 6. Safe Methods Unconditionally Exempt
# ---------------------------------------------------------------------------


def test_safe_methods_bypass_csrf():
    # GET /health without any Origin or custom header
    res_get = client.get("/health")
    assert res_get.status_code == 200

    # HEAD /health without headers: must not be rejected by CSRF middleware
    res_head = client.head("/health")
    assert res_head.status_code != 403

    # OPTIONS preflight without CSRF headers
    res_options = client.options(
        "/auth/login",
        headers={
            "Origin": TRUSTED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Requested-With,Content-Type",
        },
    )
    assert res_options.status_code == 200
    assert res_options.headers.get("access-control-allow-origin") == TRUSTED_ORIGIN


# ---------------------------------------------------------------------------
# 7. Multipart Upload Protection (L1 Document Submissions)
# ---------------------------------------------------------------------------


def test_cross_origin_multipart_upload_rejected_before_execution():
    fake_file = ("document.pdf", b"%PDF-1.4 fake content", "application/pdf")
    with patch("app.routers.documents.supabase") as mock_sb, patch(
        "app.routers.documents.GoogleDriveService"
    ) as mock_drive:
        res = client.post(
            "/candidates/99999/documents",
            files={"file": fake_file},
            data={"document_type": "APPOINTMENT_LETTER"},
            headers={"Origin": "https://attacker.com", "X-Requested-With": VALID_XHR},
        )
        assert res.status_code == 403
        assert "untrusted Origin" in res.json().get("detail", "")

        # Verify no database or Drive storage interaction occurred
        mock_sb.table.assert_not_called()
        mock_drive.assert_not_called()


def test_valid_multipart_upload_passes_csrf():
    app.dependency_overrides[get_current_user] = lambda: AUTH_USER
    try:
        with patch("app.routers.documents.check_candidate_access"), patch(
            "app.routers.documents.supabase"
        ) as mock_sb:
            mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
                {"candidate_id": 99901, "state_name": "Odisha", "tc_state_name": "Odisha"}
            ]
            fake_file = ("doc.pdf", b"%PDF-1.4 test", "application/pdf")
            res = client.post(
                "/candidates/99901/documents",
                files={"file": fake_file},
                data={"document_type": "OTHER"},
                headers={"Origin": TRUSTED_ORIGIN, "X-Requested-With": VALID_XHR},
            )
            # Request passed CSRF and reached document endpoint
            assert "CSRF verification failed" not in res.json().get("detail", "")
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 8. Systematic Coverage of All 31 State-Changing Mutation Endpoints
# ---------------------------------------------------------------------------

ALL_31_IDENTIFIED_MUTATION_ENDPOINTS = {
    # Auth endpoints (5)
    ("POST", "/auth/login"),
    ("POST", "/auth/refresh"),
    ("POST", "/auth/logout"),
    ("PATCH", "/auth/profile"),
    ("POST", "/auth/change-password"),
    # Document endpoints (4)
    ("POST", "/candidates/{candidate_id}/documents"),
    ("POST", "/candidates/{candidate_id}/documents/submit"),
    ("DELETE", "/candidates/{candidate_id}/documents/{document_id}"),
    ("POST", "/candidates/{candidate_id}/documents/sync-audit"),
    # Audit endpoints (18)
    ("POST", "/candidates/{candidate_id}/audit/draft"),
    ("POST", "/candidates/{candidate_id}/audit/submit"),
    ("POST", "/candidates/{candidate_id}/audit/l2-review/checklist"),
    ("POST", "/candidates/{candidate_id}/audit/l2-review/corrections"),
    ("POST", "/candidates/{candidate_id}/audit/l2-review/approve"),
    ("POST", "/candidates/{candidate_id}/audit/l2-review/reject"),
    ("POST", "/candidates/{candidate_id}/audit/l2-review/return-to-l1"),
    ("POST", "/candidates/{candidate_id}/audit/l3-review/approve"),
    ("POST", "/candidates/{candidate_id}/audit/l3-review/reject"),
    ("POST", "/candidates/{candidate_id}/audit/l3-review/return"),
    ("POST", "/candidates/{candidate_id}/audit/l3-review/return-to-l1"),
    ("POST", "/candidates/{candidate_id}/audit/l4-review/approve"),
    ("POST", "/candidates/{candidate_id}/audit/l4-review/reject"),
    ("POST", "/candidates/{candidate_id}/audit/l4-review/return"),
    ("POST", "/candidates/{candidate_id}/audit/l5-review/return"),
    ("POST", "/candidates/{candidate_id}/audit/l5-review/approve"),
    ("POST", "/candidates/{candidate_id}/audit/l5-review/reject"),
    ("POST", "/candidates/{candidate_id}/audit/sync-documents"),
    # Dashboard endpoint (1)
    ("POST", "/dashboard/candidates/{candidate_id}/payslip-availability"),
    # Duplicates endpoints (3)
    ("POST", "/duplicates/cases/{case_id}/review"),
    ("POST", "/duplicates/candidates/{candidate_id}/hold"),
    ("POST", "/duplicates/candidates/{candidate_id}/release-hold"),
}


def test_all_31_endpoints_accounted_for_in_registered_routes():
    """Verify that all 31 previously identified mutation routes exist in FastAPI app.routes."""
    registered_mutations = set()
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if methods and path:
            for m in methods:
                if m not in ("GET", "HEAD", "OPTIONS"):
                    registered_mutations.add((m, path))

    missing = ALL_31_IDENTIFIED_MUTATION_ENDPOINTS - registered_mutations
    assert not missing, f"Missing expected mutation endpoints in app.routes: {missing}"
    assert len(ALL_31_IDENTIFIED_MUTATION_ENDPOINTS) == 31


def test_systematic_csrf_rejection_across_all_mutation_routes():
    """Systematically test that every registered mutation route returns 403 when CSRF headers are omitted."""
    client.cookies.clear()
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue

        for method in methods:
            if method in ("GET", "HEAD", "OPTIONS"):
                continue

            # Concrete test path with dummy parameters
            test_path = (
                path.replace("{candidate_id}", "99999")
                .replace("{document_id}", "88888")
                .replace("{case_id}", "77777")
            )

            # Test A: completely missing headers
            res_no_headers = client.request(method, test_path)
            assert res_no_headers.status_code == 403, (
                f"Expected 403 for unprotected {method} {test_path}, got {res_no_headers.status_code}"
            )
            assert "CSRF verification failed" in res_no_headers.json().get("detail", "")

            # Test B: untrusted origin with X-Requested-With
            res_bad_origin = client.request(
                method,
                test_path,
                headers={"Origin": "https://malicious-site.com", "X-Requested-With": VALID_XHR},
            )
            assert res_bad_origin.status_code == 403, (
                f"Expected 403 for untrusted origin on {method} {test_path}, got {res_bad_origin.status_code}"
            )
            assert "untrusted Origin" in res_bad_origin.json().get("detail", "")


# ---------------------------------------------------------------------------
# 9. CORS Integration and Error Response Headers
# ---------------------------------------------------------------------------


def test_cors_headers_present_on_csrf_403_rejection_from_trusted_origin():
    # Request missing X-Requested-With from trusted origin should return 403 WITH CORS headers
    res = client.post(
        "/auth/login",
        json={"email": "user@cpass.org", "password": "password"},
        headers={"Origin": TRUSTED_ORIGIN},
    )
    assert res.status_code == 403
    assert res.headers.get("access-control-allow-origin") == TRUSTED_ORIGIN
    assert res.headers.get("access-control-allow-credentials") == "true"
