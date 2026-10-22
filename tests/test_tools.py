"""Contract tests: one per tool, against hand-written fixtures."""

import json

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from tests import fixtures as fx
from tests.conftest import call

ACC = fx.ACC
ACC_10K = fx.ACC_10K
ACC_FORM4 = fx.ACC_FORM4
LIST_ID = fx.LIST["id"]
ITEM_ID = fx.ITEM["id"]


def body(route) -> dict:
    return json.loads(route.calls.last.request.content)


def params(route) -> httpx.QueryParams:
    return route.calls.last.request.url.params


async def test_search(api):
    route = api.get("/v1/search").respond(json=fx.SEARCH)
    out = await call("search", {"query": "ZZEXA", "types": ["company", "security"], "limit": 5})
    assert params(route)["q"] == "ZZEXA"
    assert params(route)["type"] == "company,security"
    assert route.calls.last.request.headers["Authorization"] == "Bearer test-token"
    assert "entity_type: company" in out
    assert "cusip: 00000A101" in out
    assert "id: 42" not in out


async def test_get_company_profile(api):
    api.get("/v1/companies/ZZEXA/profile").respond(json=fx.PROFILE)
    out = await call("get_company_profile", {"company": "ZZEXA"})
    assert "name: Example Corp" in out
    assert "sic_description: Electronic Computers" in out


async def test_get_company_filings_resolves_ticker(api):
    api.get("/v1/companies/ZZEXA/profile").respond(json=fx.PROFILE)
    route = api.get(f"/v1/companies/{fx.CIK}/filings").respond(json=fx.FILINGS)
    out = await call(
        "get_company_filings", {"company": "ZZEXA", "form_types": ["10-Q", "10-K"], "limit": 1}
    )
    assert params(route).get_list("form_types[]") == ["10-Q", "10-K"]
    assert params(route)["page[size]"] == "1"
    assert f"accession_number: {ACC}" in out
    assert "offset=1" in out


async def test_get_company_calendar(api):
    api.get(f"/v1/companies/{fx.CIK}/calendar").respond(json=fx.CALENDAR)
    out = await call("get_company_calendar", {"company": "1"})
    assert "current_fiscal_quarter: Q4" in out


async def test_get_company_financials(api):
    route = api.get("/v1/companies/ZZEXA/financials").respond(json=fx.FINANCIALS)
    out = await call(
        "get_company_financials",
        {"company": "ZZEXA", "timeframe": "annual", "period_count": 1, "detail": "compact"},
    )
    assert params(route)["fields"] == "compact"
    assert params(route)["period_count"] == "1"
    assert "revenue: 4000000000" in out
    assert "diluted_eps: 2.05" in out


async def test_list_filing_documents(api):
    route = api.get(f"/v1/sec_filings/{ACC}/documents").respond(json=fx.DOCUMENTS)
    out = await call("list_filing_documents", {"accession_number": ACC.replace("-", "")})
    assert "cik" not in params(route)
    assert "filename: ex31-1.htm" in out
    assert "unused" not in out


async def test_get_filing_document_text_windows(api):
    api.get(f"/v1/sec_filings/{ACC}/documents").respond(json=fx.DOCUMENTS)
    text = "A" * 3000 + "B" * 3000
    route = api.get(f"/v1/documents/{ACC}").respond(text=text)
    out = await call(
        "get_filing_document_text",
        {"accession_number": ACC, "filename": "zzexa-20260630.htm", "max_chars": 2000},
    )
    assert params(route)["cik"] == fx.CIK
    assert params(route)["format"] == "text"
    assert out.startswith("[characters 0-2000 of 6000; call again with offset=2000")
    assert "B" not in out


async def test_list_filing_sections_passes_listed_fields_only(api):
    api.get(f"/v1/sec_filings/{ACC_10K}/sections").respond(json=fx.SECTIONS)
    out = await call("list_filing_sections", {"accession_number": ACC_10K})
    assert "section_key: item_1a" in out
    assert "supported_section_keys: [item_1, item_1a, item_7]" in out
    assert "unused" not in out and "Section index" not in out


async def test_get_filing_section_verbatim_only(api):
    route = api.get(f"/v1/sec_filings/{ACC_10K}/sections/item_1a").respond(json=fx.SECTION)
    out = await call("get_filing_section", {"accession_number": ACC_10K, "section_key": "item_1a"})
    assert params(route)["raw_only"] == "true"
    assert "general economic conditions" in out
    assert "section_title: Risk Factors" in out
    assert "unused" not in out


async def test_search_13f_managers(api):
    route = api.get("/v1/forms/13f").respond(json=fx.MANAGERS)
    out = await call("search_13f_managers", {"query": "example"})
    assert params(route)["search"] == "example"
    assert "name: Example Capital Management LLC" in out


async def test_get_13f_submission(api):
    route = api.get(f"/v1/forms/13f/{fx.MANAGER_CIK}").respond(json=fx.SUBMISSION)
    out = await call(
        "get_13f_submission", {"cik": "2", "period_of_report": "2026-06-30", "top_n": 5}
    )
    assert params(route)["period_of_report"] == "2026-06-30"
    assert "issuer: EXAMPLE CORP" in out
    assert "holdings_count: 40" in out
    assert "unused" not in out
    assert "offset=1" in out


async def test_get_security_holders_detects_cusip(api):
    route = api.get(f"/v1/securities/{fx.CUSIP}/holders").respond(json=fx.HOLDERS)
    out = await call("get_security_holders", {"identifier": fx.CUSIP, "limit": 1})
    assert params(route)["type"] == "cusip"
    assert "name: Example Capital Management LLC" in out


async def test_list_form4_filings(api):
    route = api.get("/v1/forms/4").respond(json=fx.FORM4_LIST)
    out = await call("list_form4_filings", {"ticker": "ZZEXA", "has_10b5_1": True, "limit": 1})
    assert params(route)["has_10b5_1"] == "true"
    assert "direction: sell" in out
    assert "offset=1" in out


async def test_list_form4_filings_requires_filter():
    with pytest.raises(ToolError, match="at least one"):
        await call("list_form4_filings", {})


async def test_get_form4_filing(api):
    api.get(f"/v1/forms/4/{ACC_FORM4}").respond(json=fx.FORM4)
    out = await call("get_form4_filing", {"accession_number": ACC_FORM4})
    assert "officer_title: CFO" in out
    assert 'price_per_share: "25.00"' in out or "price_per_share: 25.00" in out


async def test_get_form4_clusters(api):
    route = api.get("/v1/forms/4/clusters").respond(json=fx.CLUSTERS)
    out = await call("get_form4_clusters", {"direction": "buy", "window": 7})
    assert params(route)["window"] == "7"
    assert "insider_count: 3" in out


async def test_get_etf_holdings(api):
    api.get("/v1/etfs/ZZEXF/holdings").respond(json=fx.ETF)
    out = await call("get_etf_holdings", {"identifier": "ZZEXF", "limit": 1})
    assert "ticker: ZZEXA" in out
    assert "offset=1" in out


async def test_get_etf_holdings_empty_explains(api):
    api.get("/v1/etfs/ZZZ/holdings").respond(json=fx.ETF_EMPTY)
    out = await call("get_etf_holdings", {"identifier": "ZZZ"})
    assert "no_data_reason: not_covered" in out


async def test_etf_description_states_coverage_caveat():
    from filingexplorer_mcp.server import mcp

    tools = {t.name: t for t in await mcp.list_tools()}
    assert "not that the fund holds nothing" in tools["get_etf_holdings"].description


async def test_list_watchlists(api):
    api.get("/v1/lists").respond(json=fx.LISTS)
    out = await call("list_watchlists")
    assert "name: Tech" in out


async def test_get_watchlist_by_name_is_encoded(api):
    route = api.get("/v1/lists/My%20Tech%2FAI").respond(json=fx.LIST_SHOW)
    out = await call("get_watchlist", {"watchlist": "My Tech/AI"})
    assert route.called
    assert "symbol: ZZEXA" in out


async def test_create_watchlist(api):
    route = api.post("/v1/lists").respond(201, json={"data": {"list": fx.LIST}})
    out = await call("create_watchlist", {"name": "Tech", "notes": "big caps"})
    assert body(route) == {"list": {"name": "Tech", "notes": "big caps"}}
    assert out.startswith("Created watchlist:")


async def test_update_watchlist(api):
    route = api.patch(f"/v1/lists/{LIST_ID}").respond(json={"data": {"list": fx.LIST}})
    out = await call("update_watchlist", {"watchlist": LIST_ID, "name": "Tech"})
    assert body(route) == {"list": {"name": "Tech"}}
    assert out.startswith("Updated watchlist:")


async def test_delete_watchlist(api):
    api.delete(f"/v1/lists/{LIST_ID}").respond(204)
    out = await call("delete_watchlist", {"watchlist": LIST_ID})
    assert "Deleted" in out


async def test_add_watchlist_item(api):
    route = api.post(f"/v1/lists/{LIST_ID}/items").respond(201, json={"data": {"item": fx.ITEM}})
    out = await call("add_watchlist_item", {"watchlist": LIST_ID, "symbol": "zzexa"})
    assert body(route) == {"item": {"symbol": "ZZEXA"}}
    assert "symbol: ZZEXA" in out


async def test_update_watchlist_item(api):
    route = api.patch(f"/v1/lists/{LIST_ID}/items/{ITEM_ID}").respond(
        json={"data": {"item": fx.ITEM}}
    )
    await call("update_watchlist_item", {"watchlist": LIST_ID, "item_id": ITEM_ID, "notes": "x"})
    assert body(route) == {"item": {"notes": "x"}}


async def test_delete_watchlist_item(api):
    api.delete(f"/v1/lists/{LIST_ID}/items/{ITEM_ID}").respond(204)
    out = await call("delete_watchlist_item", {"watchlist": LIST_ID, "item_id": ITEM_ID})
    assert "Removed item" in out


async def test_tool_set():
    from filingexplorer_mcp.server import mcp

    names = {t.name for t in await mcp.list_tools()}
    assert names == {
        "search",
        "get_company_profile",
        "get_company_filings",
        "get_company_calendar",
        "get_company_financials",
        "list_filing_documents",
        "get_filing_document_text",
        "list_filing_sections",
        "get_filing_section",
        "search_13f_managers",
        "get_13f_submission",
        "get_security_holders",
        "list_form4_filings",
        "get_form4_filing",
        "get_form4_clusters",
        "get_etf_holdings",
        "list_watchlists",
        "get_watchlist",
        "create_watchlist",
        "update_watchlist",
        "delete_watchlist",
        "add_watchlist_item",
        "update_watchlist_item",
        "delete_watchlist_item",
    }


async def test_instructions_carry_disclaimer():
    from filingexplorer_mcp.server import DISCLAIMER, mcp

    assert DISCLAIMER == (
        "0.x: tool names, parameters and outputs may change between minor versions."
    )
    assert DISCLAIMER in mcp.instructions


async def test_list_filing_documents_falls_back_to_accession_cik(api):
    route = api.get(f"/v1/sec_filings/{ACC}/documents")
    route.side_effect = [
        httpx.Response(400, json={"error": {"message": "Could not resolve a CIK"}}),
        httpx.Response(200, json=fx.DOCUMENTS),
    ]
    out = await call("list_filing_documents", {"accession_number": ACC})
    assert route.calls[1].request.url.params["cik"] == fx.CIK
    assert "filename: zzexa-20260630.htm" in out


async def test_list_filing_documents_asks_for_cik_when_unresolvable(api):
    api.get(f"/v1/sec_filings/{ACC}/documents").respond(
        400, json={"error": {"message": "Could not resolve a CIK"}}
    )
    with pytest.raises(ToolError, match="Pass `cik`"):
        await call("list_filing_documents", {"accession_number": ACC})


async def test_get_company_calendar_trims_quarters(api):
    quarters = [
        {
            "fiscal_year": 2026 - i // 4,
            "quarter": f"Q{4 - i % 4}",
            "start_date": "x",
            "end_date": "y",
        }
        for i in range(20)
    ]
    api.get(f"/v1/companies/{fx.CIK}/calendar").respond(json={**fx.CALENDAR, "quarters": quarters})
    out = await call("get_company_calendar", {"company": "1", "max_quarters": 4})
    assert out.count("- fiscal_year") == 4
    assert "showing 4 of 20 quarters" in out


@pytest.mark.parametrize(
    ("tool", "path", "payload", "args"),
    [
        ("list_filing_sections", f"/v1/sec_filings/{ACC_10K}/sections", "SECTIONS", {}),
        ("get_13f_submission", f"/v1/forms/13f/{fx.MANAGER_CIK}", "SUBMISSION", {"cik": "2"}),
        ("list_filing_documents", f"/v1/sec_filings/{ACC}/documents", "DOCUMENTS", {}),
    ],
)
async def test_allowlists_keep_unknown_caveat_fields(api, tool, path, payload, args):
    import copy

    data = copy.deepcopy(getattr(fx, payload))
    target = data.get("data", data)
    target["warnings"] = ["synthetic caveat zz-top"]
    rows = target.get("sections") or target.get("holdings") or target.get("documents")
    rows[0]["data_quality"] = "synthetic row caveat zz-row"
    rows[0]["withheld_reason"] = "synthetic zz-withheld"
    api.get(path).respond(json=data)
    if tool == "get_13f_submission":
        out = await call(tool, args)
    else:
        acc = ACC_10K if tool == "list_filing_sections" else ACC
        out = await call(tool, {"accession_number": acc, **args})
    assert "synthetic caveat zz-top" in out
    assert "synthetic row caveat zz-row" in out
    assert "synthetic zz-withheld" in out
    assert "unused" not in out
