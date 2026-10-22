"""HTTP error statuses become clear tool errors."""

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from tests.conftest import call


@pytest.mark.parametrize(
    ("status", "payload", "expected"),
    [
        (401, {"error": "unauthorized"}, "Authentication failed (401)"),
        (
            403,
            {"error": {"code": "LIMIT_EXCEEDED", "message": "List limit reached"}},
            "Not permitted for this account (403): List limit reached",
        ),
        (
            404,
            {"error": {"code": "not_found", "message": "Company not found"}},
            "Not found (404): Company not found",
        ),
        (
            409,
            {
                "error": {
                    "message": "Multiple listings",
                    "details": {
                        "matches": [{"symbol": "SPY", "exchange": "Arca", "name": "SPDR S&P 500"}]
                    },
                }
            },
            "Candidates: SPY / Arca / SPDR S&P 500",
        ),
        (500, {"error": "boom"}, "FilingExplorer API error (500)"),
    ],
)
async def test_status_mapping(api, status, payload, expected):
    api.get("/v1/companies/ZZEXA/profile").respond(status, json=payload)
    with pytest.raises(ToolError) as err:
        await call("get_company_profile", {"company": "ZZEXA"})
    assert expected in str(err.value)


async def test_rate_limit_reports_retry_after(api):
    api.get("/v1/forms/4/clusters").respond(429, headers={"Retry-After": "30"}, text="")
    with pytest.raises(ToolError, match=r"Rate limited .*429.* Retry after 30 seconds"):
        await call("get_form4_clusters", {})


async def test_missing_token(monkeypatch):
    monkeypatch.delenv("FILING_EXPLORER_API_TOKEN")
    with pytest.raises(ToolError, match="FILING_EXPLORER_API_TOKEN"):
        await call("list_watchlists")


async def test_bad_accession_rejected_before_request():
    with pytest.raises(ToolError, match="not an accession number"):
        await call("get_form4_filing", {"accession_number": "abc"})


async def test_non_numeric_cik_rejected():
    with pytest.raises(ToolError, match="not a CIK"):
        await call("get_13f_submission", {"cik": "BRK"})
