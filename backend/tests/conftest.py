"""Test configuration and integration fixtures for CPASS backend test suite.

Provides default browser-simulated headers (trusted Origin and custom header)
for integration tests while ensuring dedicated CSRF attack tests in
`test_csrf_protection.py` execute with raw, unaugmented requests.
"""

import pytest
from starlette.testclient import TestClient


@pytest.fixture(autouse=True)
def configure_browser_headers_for_integration_tests(request, monkeypatch):
    """Augment TestClient requests with default browser headers for integration tests.

    Skips augmentation for test_csrf_protection so negative CSRF scenarios
    (missing headers, untrusted origins, malformed headers) are tested directly.
    """
    if "test_csrf_protection" in request.node.nodeid:
        return

    orig_request = TestClient.request

    def request_with_browser_headers(self, method, url, *args, **kwargs):
        headers = dict(kwargs.get("headers") or {})
        method_upper = method.upper()
        if method_upper not in ("GET", "HEAD", "OPTIONS"):
            if "Origin" not in headers and "origin" not in headers:
                headers["Origin"] = "http://localhost:5173"
            if "X-Requested-With" not in headers and "x-requested-with" not in headers:
                headers["X-Requested-With"] = "XMLHttpRequest"
        kwargs["headers"] = headers
        return orig_request(self, method, url, *args, **kwargs)

    monkeypatch.setattr(TestClient, "request", request_with_browser_headers)

