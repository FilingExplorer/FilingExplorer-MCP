"""Live smoke test against the real API. Skipped unless FILING_EXPLORER_API_TOKEN is set."""

import os
import re
import uuid

import pytest

from tests.conftest import call

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("FILING_EXPLORER_API_TOKEN"),
        reason="FILING_EXPLORER_API_TOKEN not set",
    ),
]

APPLE = "0000320193"
BERKSHIRE = "0001067983"


def _accession(text: str) -> str:
    match = re.search(r"\d{10}-\d{2}-\d{6}", text)
    assert match, text
    return match.group(0)


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("search", {"query": "Apple", "limit": 3}),
        ("get_company_profile", {"company": "AAPL"}),
        ("get_company_calendar", {"company": APPLE}),
        ("get_company_financials", {"company": "AAPL", "period_count": 2}),
        ("search_13f_managers", {"query": "Berkshire", "limit": 3}),
        ("get_13f_submission", {"cik": BERKSHIRE, "top_n": 3}),
        ("get_security_holders", {"identifier": "AAPL", "limit": 3}),
        ("list_form4_filings", {"ticker": "AAPL", "limit": 2}),
        ("get_form4_clusters", {"limit": 2}),
        ("get_etf_holdings", {"identifier": "XLK", "limit": 3}),
        ("list_watchlists", {}),
    ],
)
async def test_read_tools(tool, args):
    out = await call(tool, args)
    assert out.strip()


async def test_filing_text_chain():
    filings = await call(
        "get_company_filings", {"company": APPLE, "form_types": ["10-K"], "limit": 1}
    )
    acc = _accession(filings)
    docs = await call("list_filing_documents", {"accession_number": acc})
    assert "filename:" in docs
    text = await call(
        "get_filing_document_text", {"accession_number": acc, "cik": APPLE, "max_chars": 2000}
    )
    assert text.strip()
    sections = await call("list_filing_sections", {"accession_number": acc})
    key = re.search(r"section_key: (\S+)", sections)
    if key:
        section = await call(
            "get_filing_section",
            {"accession_number": acc, "section_key": key.group(1), "max_chars": 2000},
        )
        assert section.strip()


async def test_form4_detail():
    listing = await call("list_form4_filings", {"ticker": "AAPL", "limit": 1})
    out = await call("get_form4_filing", {"accession_number": _accession(listing)})
    assert "issuer:" in out


async def test_watchlist_round_trip():
    name = f"mcp-smoke-{uuid.uuid4().hex[:8]}"
    await call("create_watchlist", {"name": name})
    try:
        await call("update_watchlist", {"watchlist": name, "notes": "smoke test"})
        added = await call("add_watchlist_item", {"watchlist": name, "symbol": "AAPL"})
        item_id = re.search(r"^id: (\S+)", added, re.MULTILINE).group(1)
        await call("update_watchlist_item", {"watchlist": name, "item_id": item_id, "notes": "x"})
        shown = await call("get_watchlist", {"watchlist": name})
        assert "AAPL" in shown
        await call("delete_watchlist_item", {"watchlist": name, "item_id": item_id})
    finally:
        await call("delete_watchlist", {"watchlist": name})


async def test_financials_split_companions():
    out = await call("get_company_financials", {"company": "NVDA", "period_count": 4})
    assert "diluted_eps_split_adjusted:" in out
    assert "split_adjustment:" in out
