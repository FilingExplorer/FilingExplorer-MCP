"""FilingExplorer MCP server: direct tools over the FilingExplorer API."""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from filingexplorer_mcp import __version__, client
from filingexplorer_mcp.client import segment
from filingexplorer_mcp.formatting import page_note, slice_text, to_text

DISCLAIMER = "0.x: tool names, parameters and outputs may change between minor versions."

INSTRUCTIONS = f"""FilingExplorer: data from public SEC filings.

Covers company profiles and filing lists, reported financials, verbatim filing text
(documents and 10-K/10-Q sections), Form 13-F institutional holdings, Form 4 insider
trades, ETF holdings from N-PORT, and the user's own watchlists.

Typical flow:
1. Resolve names and tickers with `search` to get a CIK, ticker or CUSIP.
2. Call the specific tool with that identifier.
3. For filing text: `get_company_filings` -> `list_filing_documents` or
   `list_filing_sections` -> `get_filing_document_text` or `get_filing_section`.

Outputs are compact YAML-like text. Long lists are paginated with `limit`/`offset`;
long texts are windowed with `offset`/`max_chars`. Figures come from the filings as
reported; check the period and units shown with each value.

{DISCLAIMER}"""

mcp = FastMCP("filingexplorer", instructions=INSTRUCTIONS)
mcp._mcp_server.version = __version__  # report this package's version to clients

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
UPDATE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
DELETE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True
)

_ACCESSION = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_CUSIP = re.compile(r"^[0-9A-Z]{8}[0-9]$")

Limit = Annotated[int | None, Field(ge=1, le=100, description="Maximum results to return.")]
Offset = Annotated[int | None, Field(ge=0, description="Number of results to skip.")]
Date = Annotated[str | None, Field(description="Date as YYYY-MM-DD.")]


def tool(annotations: ToolAnnotations):
    return mcp.tool(annotations=annotations, structured_output=False)


# --------------------------------------------------------------------------- helpers


def _pad_cik(value: str) -> str:
    digits = str(value).strip()
    if not digits.isdigit():
        raise ToolError(f"'{value}' is not a CIK. CIKs are numeric; use `search` to find one.")
    return digits.zfill(10)


async def _company_cik(company: str) -> str:
    """Accept a CIK or a ticker and return a 10-digit CIK."""
    company = company.strip()
    if company.isdigit():
        return company.zfill(10)
    data = await client.request("GET", f"/v1/companies/{segment(company)}/profile")
    cik = ((data or {}).get("company") or {}).get("cik")
    if not cik:
        raise ToolError(f"Could not resolve '{company}' to a CIK. Use `search` first.")
    return str(cik).zfill(10)


def _accession(value: str) -> str:
    raw = str(value).strip()
    digits = raw.replace("-", "")
    if digits.isdigit() and len(digits) == 18:
        raw = f"{digits[:10]}-{digits[10:12]}-{digits[12:]}"
    if not _ACCESSION.match(raw):
        raise ToolError(
            f"'{value}' is not an accession number. Expected the form 0000320193-24-000123."
        )
    return raw


def _render(data: Any, note: str = "") -> str:
    return to_text(data) + note


# Caveats always pass through, including ones the API adds later.
_CAVEAT_KEY = re.compile(
    r"^(?:warnings?|caveats?|notes?|notice|data_quality|coverage|meta|not_covered|withheld\w*)$",
    re.IGNORECASE,
)


def _pick(value: Any, fields: tuple[str, ...]) -> dict:
    """Keep the listed fields of a mapping, in the listed order, plus any caveat fields."""
    if not isinstance(value, dict):
        return {}
    out = {k: value[k] for k in fields if k in value}
    out.update({k: v for k, v in value.items() if k not in out and _CAVEAT_KEY.match(k)})
    return out


def _pick_rows(rows: Any, fields: tuple[str, ...]) -> list:
    return [_pick(row, fields) for row in rows] if isinstance(rows, list) else []


def _pagination_note(pagination: dict | None) -> str:
    if not isinstance(pagination, dict):
        return ""
    return page_note(
        pagination.get("total_count"),
        int(pagination.get("offset") or 0),
        int(pagination.get("returned") or pagination.get("limit") or 0),
        pagination.get("has_more"),
    )


def _count_note(pagination: dict | None, returned: int) -> str:
    if not isinstance(pagination, dict):
        return ""
    return page_note(
        pagination.get("total_count"),
        int(pagination.get("offset") or 0),
        returned,
        pagination.get("has_more"),
    )


# --------------------------------------------------------------------------- search & company


_SEARCH_FIELDS = (
    "name",
    "cik",
    "crd_number",
    "ticker",
    "primary_ticker",
    "symbol",
    "cusip",
    "exchange",
    "link",
)


@tool(READ)
async def search(
    query: Annotated[
        str, Field(description="Company name, ticker, CIK, CUSIP or TICKER:EXCHANGE.")
    ],
    types: Annotated[
        list[Literal["company", "security", "filer"]] | None,
        Field(description="Entity types to search. Default: all three."),
    ] = None,
    limit: Annotated[int | None, Field(ge=1, le=50, description="Max results per type.")] = None,
    include_inactive: Annotated[
        bool | None, Field(description="Include delisted or dormant records.")
    ] = None,
) -> str:
    """Find companies, securities and 13F filers by name, ticker, CIK or CUSIP.

    Start here to turn a name into the identifiers other tools take (CIK for companies and
    filers, ticker or CUSIP for securities)."""
    data = await client.request(
        "GET",
        "/v1/search",
        params={
            "q": query,
            "type": ",".join(types) if types else None,
            "limit": limit,
            "include_inactive": include_inactive,
        },
    )
    results = []
    for row in (data or {}).get("data", []):
        fields = row.get("data") if isinstance(row.get("data"), dict) else row
        item = {"entity_type": row.get("entity_type"), "match": row.get("match_type")}
        item.update(_pick(fields, _SEARCH_FIELDS))
        results.append(item)
    if not results:
        return f"No matches for '{query}'."
    return _render({"results": results})


@tool(READ)
async def get_company_profile(
    company: Annotated[str, Field(description="CIK or ticker symbol.")],
) -> str:
    """Company identity: name, CIK, ticker, exchange, SIC industry, fiscal year end and the
    latest reported shares outstanding."""
    data = await client.request("GET", f"/v1/companies/{segment(company.strip())}/profile")
    return _render((data or {}).get("company", data))


@tool(READ)
async def get_company_filings(
    company: Annotated[str, Field(description="CIK or ticker symbol.")],
    form_types: Annotated[
        list[str] | None, Field(description="Only these form types, e.g. ['10-K', '8-K'].")
    ] = None,
    filed_after: Date = None,
    filed_before: Date = None,
    sort: Annotated[
        Literal["filing_date", "-filing_date", "form_type", "-form_type"] | None,
        Field(description="Sort order; '-' prefix means descending. Default newest first."),
    ] = None,
    limit: Limit = None,
    offset: Offset = None,
    include_same_day: Annotated[
        bool | None, Field(description="Also include filings made today (some plans only).")
    ] = None,
    include_historical: Annotated[
        bool | None, Field(description="Include the complete filing history (some plans only).")
    ] = None,
) -> str:
    """List a company's SEC filings with accession numbers, dates, form types and primary
    document names. Use the accession number with the document and section tools."""
    cik = await _company_cik(company)
    data = await client.request(
        "GET",
        f"/v1/companies/{cik}/filings",
        params={
            "form_types[]": form_types,
            "filed_after": filed_after,
            "filed_before": filed_before,
            "sort": sort,
            "page[size]": limit,
            "page[offset]": offset,
            "include_same_day": include_same_day,
            "include_historical": include_historical,
        },
    )
    data = data or {}
    filings = []
    for row in data.get("data", []):
        item = dict(row.get("attributes") or {})
        item.pop("cik", None)
        index_url = (row.get("links") or {}).get("index")
        if index_url:
            item["index_url"] = index_url
        filings.append(item)
    meta = data.get("meta") or {}
    header = {k: meta.get(k) for k in ("cik", "company_name", "data_freshness", "total_count")}
    note = page_note(
        meta.get("total_count"), int(meta.get("offset") or 0), len(filings), meta.get("has_more")
    )
    if not filings:
        return _render({**header, "filings": "none matched"})
    return _render({**header, "filings": filings}, note)


@tool(READ)
async def get_company_calendar(
    company: Annotated[str, Field(description="CIK or ticker symbol.")],
    max_quarters: Annotated[
        int | None, Field(ge=1, le=200, description="Quarters to show, newest first. Default 12.")
    ] = None,
) -> str:
    """Fiscal calendar: the company's current fiscal year and quarter, and the start and end
    date of each fiscal quarter."""
    cik = await _company_cik(company)
    data = await client.request("GET", f"/v1/companies/{cik}/calendar")
    data = dict(data or {})
    quarters = data.get("quarters") or []
    keep = max_quarters or 12
    note = ""
    if len(quarters) > keep:
        data["quarters"] = quarters[:keep]
        note = f"\n\n[showing {keep} of {len(quarters)} quarters; raise max_quarters for more]"
    return _render(data, note)


@tool(READ)
async def get_company_financials(
    company: Annotated[str, Field(description="CIK or ticker symbol.")],
    timeframe: Annotated[
        Literal["annual", "quarterly", "semi_annual"] | None,
        Field(description="Reporting cadence. Default annual."),
    ] = None,
    period_count: Annotated[
        int | None, Field(ge=1, le=20, description="Most recent N periods.")
    ] = None,
    fiscal_year_gte: Annotated[int | None, Field(description="Earliest fiscal year.")] = None,
    fiscal_year_lte: Annotated[int | None, Field(description="Latest fiscal year.")] = None,
    order: Annotated[
        Literal["asc", "desc"] | None, Field(description="Period order. Default oldest first.")
    ] = None,
    detail: Annotated[
        Literal["compact", "full"] | None,
        Field(
            description="compact (default): one row per period with headline figures. "
            "full: complete statements and ratio groups as parallel arrays aligned to periods."
        ),
    ] = None,
    view: Annotated[
        Literal["raw", "vertical"] | None,
        Field(
            description="raw (default): reported amounts, with split-adjusted per-share "
            "companions where a split applies. vertical (full only): common-size percentages."
        ),
    ] = None,
    ratios: Annotated[
        list[
            Literal[
                "margin",
                "return",
                "liquidity",
                "leverage",
                "per_share",
                "activity",
                "cash_flow",
                "capital_allocation",
            ]
        ]
        | None,
        Field(description="full only: ratio groups to include. Default all."),
    ] = None,
) -> str:
    """Reported fundamentals from 10-K/10-Q filings: revenue, profit, EPS, cash flow, balance
    sheet items and computed margins, per fiscal period, with the source form for each period.
    Quarterly Q4 values derived from the annual filing are flagged.

    Per-share and share-count figures (diluted_eps, shares_outstanding, EPS and average-share
    rows) are as each period's filing reported them, so a series that spans a stock split
    mixes share bases. When a recorded split separates a period from today's basis, the raw
    view adds diluted_eps_split_adjusted and shares_outstanding_split_adjusted to compact
    periods (full statement rows add split_adjusted_values, aligned to periods), and
    meta.split_adjustment lists the splits applied. Use the split-adjusted figures for trends
    and the as-reported ones to match a filing. A split-adjusted value shown as "withheld"
    (compact) or null (full) could not be put on today's basis; split_adjustment_withheld
    gives the reason, and meta.split_adjustment.unexplained_share_breaks lists share-count
    jumps the recorded splits do not explain. Read meta.warnings before comparing periods."""
    data = await client.request(
        "GET",
        f"/v1/companies/{segment(company.strip())}/financials",
        params={
            "timeframe": timeframe,
            "period_count": period_count,
            "fiscal_year_gte": fiscal_year_gte,
            "fiscal_year_lte": fiscal_year_lte,
            "order": order,
            "fields": detail,
            "view": view,
            "ratios": ",".join(ratios) if ratios else None,
        },
    )
    return _render(_mark_withheld_companions(data))


_SPLIT_COMPANIONS = ("diluted_eps_split_adjusted", "shares_outstanding_split_adjusted")


def _mark_withheld_companions(data: Any) -> Any:
    """Keep withheld split-adjusted companions visible in compact periods.

    The API serves a withheld companion as null beside a reason. Rendering drops null
    mapping values, which would leave only the as-reported figure in that period's row,
    so a withheld companion is shown as the word "withheld" instead.
    """
    if not isinstance(data, dict) or not isinstance(data.get("periods"), list):
        return data
    periods = []
    for period in data["periods"]:
        if isinstance(period, dict) and period.get("split_adjustment_withheld"):
            period = dict(period)
            for key in _SPLIT_COMPANIONS:
                if key in period and period[key] is None:
                    period[key] = "withheld"
        periods.append(period)
    return {**data, "periods": periods}


# --------------------------------------------------------------------------- SEC documents


@tool(READ)
async def list_filing_documents(
    accession_number: Annotated[
        str, Field(description="Accession number, e.g. 0000320193-24-000123.")
    ],
    cik: Annotated[
        str | None, Field(description="Filer CIK. Optional; resolved automatically when known.")
    ] = None,
) -> str:
    """List the documents inside one filing (main document, exhibits, XBRL files) with their
    filenames, types, descriptions and sizes. Pass a filename to `get_filing_document_text`."""
    acc = _accession(accession_number)
    payload = await _document_index(acc, cik)
    out = _pick(payload, _DOCUMENT_INDEX_FIELDS)
    out["documents"] = _pick_rows(payload.get("documents"), _DOCUMENT_FIELDS)
    return _render(out)


_DOCUMENT_INDEX_FIELDS = ("accession_number", "cik", "index_url", "document_count")
_DOCUMENT_FIELDS = ("sequence", "filename", "description", "document_type", "group", "size", "url")


async def _document_index(acc: str, cik: str | None) -> dict:
    """Fetch a filing's document index.

    Without a CIK the API looks one up from its records. When it cannot, retry with the
    CIK embedded in the accession number, which identifies the filer for self-filed
    documents (filings submitted by an agent carry the agent's CIK instead)."""
    path = f"/v1/sec_filings/{acc}/documents"
    if cik:
        data = await client.request("GET", path, params={"cik": _pad_cik(cik)})
    else:
        try:
            data = await client.request("GET", path)
        except client.ApiError as exc:
            if exc.status != 400:
                raise
            try:
                data = await client.request("GET", path, params={"cik": acc[:10]})
            except client.ApiError:
                raise ToolError(
                    "Could not determine the filer for this filing. Pass `cik` (the "
                    "company's CIK, from `search` or `get_company_filings`)."
                ) from exc
    return (data or {}).get("data", data) or {}


@tool(READ)
async def get_filing_document_text(
    accession_number: Annotated[str, Field(description="Accession number of the filing.")],
    filename: Annotated[
        str | None,
        Field(description="Document filename from `list_filing_documents`. Omit for the index."),
    ] = None,
    cik: Annotated[
        str | None, Field(description="Filer CIK. Optional; looked up from the filing if omitted.")
    ] = None,
    output_format: Annotated[
        Literal["text", "markdown"] | None,
        Field(description="text (default) or markdown (best for PDF documents)."),
    ] = None,
    offset: Annotated[int | None, Field(ge=0, description="Character offset to start at.")] = None,
    max_chars: Annotated[
        int | None, Field(ge=1000, le=200000, description="Characters to return. Default 40000.")
    ] = None,
) -> str:
    """Verbatim text of one document in an SEC filing, with markup stripped. Long documents
    are returned in windows; follow the offset hint in the header to read further."""
    acc = _accession(accession_number)
    if cik:
        cik_value = _pad_cik(cik)
    else:
        cik_value = (await _document_index(acc, None)).get("cik")
        if not cik_value:
            raise ToolError("Could not determine the filer CIK for this filing; pass `cik`.")
    text = await client.request(
        "GET",
        f"/v1/documents/{acc}",
        params={"cik": cik_value, "filename": filename, "format": output_format or "text"},
        text=True,
    )
    if not text:
        return "(document is empty)"
    return slice_text(text, offset or 0, max_chars or 40000)


_SECTION_INDEX_FIELDS = ("accession_number", "form_type")
_SECTION_ROW_FIELDS = (
    "section_key",
    "section_title",
    "form_type",
    "fiscal_year",
    "fiscal_period",
    "filing_date",
    "has_text",
    "raw_text_chars",
)
_SECTION_FIELDS = (
    "accession_number",
    "section_key",
    "section_title",
    "form_type",
    "fiscal_year",
    "fiscal_period",
    "filing_date",
    "period_of_report",
    "raw_text_chars",
)


@tool(READ)
async def list_filing_sections(
    accession_number: Annotated[
        str, Field(description="Accession number of a 10-K, 10-Q, 20-F, S-1 or F-1 filing.")
    ],
) -> str:
    """List the extracted sections of a filing (for example Item 1 Business, Item 1A Risk
    Factors, Item 7 MD&A) with their keys and lengths. Use a key with `get_filing_section`."""
    acc = _accession(accession_number)
    data = await client.request("GET", f"/v1/sec_filings/{acc}/sections")
    data = data or {}
    out = _pick(data, _SECTION_INDEX_FIELDS)
    out["sections"] = _pick_rows(data.get("sections"), _SECTION_ROW_FIELDS)
    supported = (data.get("_meta") or {}).get("supported_section_keys")
    if supported:
        out["supported_section_keys"] = supported
    return _render(out)


@tool(READ)
async def get_filing_section(
    accession_number: Annotated[str, Field(description="Accession number of the filing.")],
    section_key: Annotated[
        str, Field(description="Section key from `list_filing_sections`, e.g. item_1a.")
    ],
    offset: Annotated[int | None, Field(ge=0, description="Character offset to start at.")] = None,
    max_chars: Annotated[
        int | None, Field(ge=1000, le=200000, description="Characters to return. Default 40000.")
    ] = None,
) -> str:
    """Verbatim text of one section of a filing, exactly as filed. Long sections are
    returned in windows; follow the offset hint to read further."""
    acc = _accession(accession_number)
    data = await client.request(
        "GET",
        f"/v1/sec_filings/{acc}/sections/{segment(section_key.strip())}",
        params={"raw_only": True},
    )
    section = (data or {}).get("section", data) or {}
    body = (section.get("raw_text") or "").strip()
    header = to_text(_pick(section, _SECTION_FIELDS))
    if not body:
        return header + "\n\n(no text extracted for this section)"
    return header + "\n\n" + slice_text(body, offset or 0, max_chars or 40000)


# --------------------------------------------------------------------------- 13F


@tool(READ)
async def search_13f_managers(
    query: Annotated[str | None, Field(description="Manager name or 10-digit CIK.")] = None,
    limit: Limit = None,
    offset: Offset = None,
) -> str:
    """Find institutional investment managers that file Form 13-F, with their latest reported
    portfolio value and period. Use the CIK with `get_13f_submission`."""
    data = await client.request(
        "GET", "/v1/forms/13f", params={"search": query, "limit": limit, "offset": offset}
    )
    data = data or {}
    filers = data.get("filers", [])
    if not filers:
        return "No 13F filers matched."
    return _render({"filers": filers}, _count_note(data.get("pagination"), len(filers)))


@tool(READ)
async def get_13f_submission(
    cik: Annotated[str, Field(description="13F filer CIK.")],
    period_of_report: Annotated[
        str | None, Field(description="Quarter end date YYYY-MM-DD. Default latest.")
    ] = None,
    symbols: Annotated[
        list[str] | None,
        Field(description="Only these holdings (tickers or CUSIPs). Skips the summary tables."),
    ] = None,
    detail: Annotated[
        Literal["compact", "full"] | None,
        Field(
            description="compact (default): totals and top holdings. full: adds activity "
            "tables (new, increased, reduced, exited positions)."
        ),
    ] = None,
    top_n: Annotated[
        int | None, Field(ge=1, le=50, description="compact only: number of top holdings.")
    ] = None,
    limit: Annotated[int | None, Field(ge=1, le=500, description="Holdings per page.")] = None,
    offset: Offset = None,
) -> str:
    """A manager's Form 13-F portfolio for one quarter: total reported value, holdings count,
    largest positions, and quarter-over-quarter changes. Values are as reported in the 13F."""
    data = await client.request(
        "GET",
        f"/v1/forms/13f/{_pad_cik(cik)}",
        params={
            "period_of_report": period_of_report,
            "symbols": ",".join(symbols) if symbols else None,
            "fields": detail,
            "top_n": top_n,
            "limit": limit,
            "offset": offset,
        },
    )
    data = data or {}
    out = _pick(data, _SUBMISSION_FIELDS)
    for key in _POSITION_LISTS:
        if key in out:
            out[key] = _positions(out[key])
    if "activity_summary" in out:
        activity = _pick(out["activity_summary"], _ACTIVITY_FIELDS)
        for key in _POSITION_LISTS:
            if key in activity:
                activity[key] = _positions(activity[key])
        if "sector_summary" in activity:
            activity["sector_summary"] = _pick_rows(activity["sector_summary"], _SECTOR_FIELDS)
        out["activity_summary"] = activity
    holdings = out.get("holdings")
    pagination = data.get("holdings_pagination")
    note = _count_note(pagination, len(holdings)) if isinstance(holdings, list) else ""
    return _render(out, note)


_SUBMISSION_FIELDS = (
    "cik",
    "name",
    "period_of_report",
    "filing_date",
    "accession_number",
    "total_value",
    "holdings_count",
    "top_holdings",
    "activity_summary",
    "holdings",
)
_ACTIVITY_FIELDS = (
    "market_value",
    "previous_market_value",
    "market_value_diff",
    "holdings_count",
    "previous_holdings_count",
    "new_holdings",
    "new_holdings_value",
    "holdings_increased",
    "holdings_increased_value",
    "holdings_reduced_but_not_exited",
    "holdings_reduced_but_not_exited_value",
    "holdings_exited",
    "holdings_exited_value",
    "top_ten_concentration",
    "sector_summary",
    "top_holdings",
    "top_new_positions",
    "top_net_increases",
    "top_net_decreases",
    "top_exits",
)
_POSITION_LISTS = (
    "top_holdings",
    "top_new_positions",
    "top_net_increases",
    "top_net_decreases",
    "top_exits",
    "holdings",
)
_POSITION_FIELDS = (
    "issuer",
    "security_name",
    "symbol",
    "cusip",
    "holding_type",
    "sector",
    "shares",
    "previous_shares",
    "change_in_shares",
    "change_in_shares_percent",
    "value",
    "previous_value",
    "pct_of_portfolio",
    "percent_of_portfolio",
    "previous_percent_of_portfolio",
    "first_owned",
    "first_owned_approximate",
    "voting_authority",
)
_VOTING_FIELDS = ("sole", "shared", "none")
_SECTOR_FIELDS = ("sector", "value", "percent_of_portfolio")


def _positions(rows: Any) -> list:
    out = _pick_rows(rows, _POSITION_FIELDS)
    for row in out:
        if "voting_authority" in row:
            row["voting_authority"] = _pick(row["voting_authority"], _VOTING_FIELDS)
    return out


@tool(READ)
async def get_security_holders(
    identifier: Annotated[str, Field(description="Ticker symbol or 9-character CUSIP.")],
    identifier_type: Annotated[
        Literal["ticker", "cusip"] | None,
        Field(description="Default: detected from the identifier's shape."),
    ] = None,
    period: Annotated[
        str | None, Field(description="Quarter end date YYYY-MM-DD. Default latest available.")
    ] = None,
    limit: Annotated[int | None, Field(ge=1, le=50, description="Holders to return.")] = None,
    holding_type: Annotated[
        str | None, Field(description="Filter by holding type, e.g. SH, PUT or CALL.")
    ] = None,
) -> str:
    """Top institutional holders of a security from Form 13-F filings, with each holder's
    shares, reported value, portfolio share and change from the prior quarter, plus totals.
    13F data typically appears about 45 days after quarter end."""
    ident = identifier.strip().upper()
    kind = identifier_type or ("cusip" if _CUSIP.match(ident) else "ticker")
    data = await client.request(
        "GET",
        f"/v1/securities/{segment(ident)}/holders",
        params={"type": kind, "period": period, "limit": limit, "holding_type": holding_type},
    )
    return _render(data)


# --------------------------------------------------------------------------- Form 4


@tool(READ)
async def list_form4_filings(
    ticker: Annotated[str | None, Field(description="Issuer ticker symbol.")] = None,
    issuer_cik: Annotated[str | None, Field(description="Issuer (company) CIK.")] = None,
    owner_cik: Annotated[str | None, Field(description="Reporting insider's CIK.")] = None,
    direction: Annotated[
        Literal["buy", "sell", "all"] | None, Field(description="Transaction direction.")
    ] = None,
    filed_after: Date = None,
    filed_before: Date = None,
    has_10b5_1: Annotated[
        bool | None,
        Field(
            description="true: only filings disclosing a Rule 10b5-1 plan; false: only "
            "filings stating there was none."
        ),
    ] = None,
    limit: Limit = None,
    offset: Offset = None,
) -> str:
    """List Form 4 insider-transaction filings for a company or an insider, newest first, with
    the reporting owners, their roles, and the transactions in each filing. Give at least one
    of ticker, issuer_cik or owner_cik."""
    if not (ticker or issuer_cik or owner_cik):
        raise ToolError("Provide at least one of ticker, issuer_cik or owner_cik.")
    data = await client.request(
        "GET",
        "/v1/forms/4",
        params={
            "ticker": ticker,
            "issuer_cik": _pad_cik(issuer_cik) if issuer_cik else None,
            "owner_cik": _pad_cik(owner_cik) if owner_cik else None,
            "direction": direction,
            "filed_after": filed_after,
            "filed_before": filed_before,
            "has_10b5_1": has_10b5_1,
            "limit": limit,
            "offset": offset,
        },
    )
    data = data or {}
    filings = data.get("filings", [])
    if not filings:
        return "No Form 4 filings matched."
    return _render({"filings": filings}, _count_note(data.get("pagination"), len(filings)))


@tool(READ)
async def get_form4_filing(
    accession_number: Annotated[str, Field(description="Accession number of the Form 4.")],
) -> str:
    """One Form 4 filing in full: issuer, reporting owners and relationships, every
    non-derivative and derivative transaction and holding, footnotes, and Rule 10b5-1 plan
    disclosure."""
    data = await client.request("GET", f"/v1/forms/4/{_accession(accession_number)}")
    return _render(data)


@tool(READ)
async def get_form4_clusters(
    ticker: Annotated[str | None, Field(description="Issuer ticker symbol.")] = None,
    issuer_cik: Annotated[str | None, Field(description="Issuer CIK.")] = None,
    direction: Annotated[
        Literal["buy", "sell"] | None, Field(description="Buying or selling.")
    ] = None,
    window: Annotated[
        Literal[7, 14, 30] | None,
        Field(description="Cluster window in days. Some plans allow 7 only."),
    ] = None,
    min_insiders: Annotated[int | None, Field(ge=2, description="Minimum insiders.")] = None,
    min_value: Annotated[
        int | None, Field(ge=0, description="Minimum aggregate value in USD.")
    ] = None,
    include_filings: Annotated[
        bool | None, Field(description="Include the individual filings in each cluster.")
    ] = None,
    limit: Annotated[int | None, Field(ge=1, le=50, description="Clusters to return.")] = None,
    offset: Offset = None,
) -> str:
    """Clusters of insider trades: several insiders at the same company buying or selling
    within a short window. Omit ticker and issuer_cik to see recent clusters market-wide."""
    data = await client.request(
        "GET",
        "/v1/forms/4/clusters",
        params={
            "ticker": ticker,
            "issuer_cik": _pad_cik(issuer_cik) if issuer_cik else None,
            "direction": direction,
            "window": window,
            "min_insiders": min_insiders,
            "min_value": min_value,
            "include_filings": include_filings,
            "limit": limit,
            "offset": offset,
        },
    )
    data = data or {}
    clusters = data.get("clusters", [])
    note = _count_note(data.get("pagination"), len(clusters))
    if not clusters:
        return _render({"clusters": "none matched", "summary": data.get("summary")})
    return _render({"clusters": clusters, "summary": data.get("summary")}, note)


# --------------------------------------------------------------------------- funds


@tool(READ)
async def get_etf_holdings(
    identifier: Annotated[
        str, Field(description="ETF ticker (SPY), TICKER:EXCHANGE (SPY:Arca) or CUSIP.")
    ],
    quarter: Annotated[
        str | None, Field(description="Quarter as YYYY-MM-DD or YYYY-Q#. Default latest.")
    ] = None,
    limit: Limit = None,
    offset: Offset = None,
    sort_direction: Annotated[
        Literal["desc", "asc"] | None, Field(description="By value; default largest first.")
    ] = None,
) -> str:
    """What an ETF holds, from its N-PORT filing: each position's value, share of net assets,
    asset category and country, plus the fund's total net assets.

    Coverage caveat: some ETFs have no holdings data here (for example funds that do not
    file N-PORT under their own series). When that happens the response says so and gives
    the reason when known. An empty result means the data is not available,
    not that the fund holds nothing."""
    data = await client.request(
        "GET",
        f"/v1/etfs/{segment(identifier.strip())}/holdings",
        params={
            "quarter": quarter,
            "limit": limit,
            "offset": offset,
            "sort_direction": sort_direction,
        },
    )
    data = data or {}
    body = dict(data.get("data") or {})
    meta = data.get("meta") or {}
    pagination = body.pop("pagination", None)
    for key in ("no_data_reason", "hint"):
        if meta.get(key):
            body[key] = meta[key]
    holdings = body.get("holdings") or []
    if not holdings and not body.get("no_data_reason"):
        body["no_data_reason"] = "No holdings available for this fund in our N-PORT coverage."
    return _render(body, _count_note(pagination, len(holdings)))


# --------------------------------------------------------------------------- watchlists

WatchlistRef = Annotated[str, Field(description="Watchlist id or exact name (case-insensitive).")]


def _watchlist_path(watchlist: str) -> str:
    return f"/v1/lists/{segment(watchlist.strip())}"


@tool(READ)
async def list_watchlists() -> str:
    """List the signed-in user's watchlists with ids, names, notes and item counts."""
    data = await client.request("GET", "/v1/lists")
    lists = ((data or {}).get("data") or {}).get("lists", [])
    if not lists:
        return "You have no watchlists."
    return _render({"watchlists": lists})


@tool(READ)
async def get_watchlist(
    watchlist: WatchlistRef,
    limit: Limit = None,
    offset: Offset = None,
) -> str:
    """Show one of the user's watchlists and its items (securities by symbol, institutional
    investors by CIK), with each item's id and notes."""
    data = await client.request(
        "GET", _watchlist_path(watchlist), params={"limit": limit, "offset": offset}
    )
    body = dict((data or {}).get("data") or {})
    pagination = body.pop("pagination", None)
    items = body.get("items") or []
    return _render(body, _count_note(pagination, len(items)))


@tool(WRITE)
async def create_watchlist(
    name: Annotated[str, Field(min_length=1, description="Name for the new watchlist.")],
    notes: Annotated[str | None, Field(description="Optional description.")] = None,
) -> str:
    """Create a new watchlist in the user's own account."""
    body: dict[str, Any] = {"name": name}
    if notes is not None:
        body["notes"] = notes
    data = await client.request("POST", "/v1/lists", body={"list": body})
    return "Created watchlist:\n" + _render(((data or {}).get("data") or {}).get("list", data))


@tool(UPDATE)
async def update_watchlist(
    watchlist: WatchlistRef,
    name: Annotated[str | None, Field(min_length=1, description="New name.")] = None,
    notes: Annotated[str | None, Field(description="New notes; empty string clears them.")] = None,
) -> str:
    """Rename one of the user's watchlists or change its notes."""
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if notes is not None:
        body["notes"] = notes
    if not body:
        raise ToolError("Nothing to update: pass a new name and/or notes.")
    data = await client.request("PATCH", _watchlist_path(watchlist), body={"list": body})
    return "Updated watchlist:\n" + _render(((data or {}).get("data") or {}).get("list", data))


@tool(DELETE)
async def delete_watchlist(watchlist: WatchlistRef) -> str:
    """Permanently delete one of the user's watchlists and all of its items."""
    await client.request("DELETE", _watchlist_path(watchlist))
    return f"Deleted watchlist '{watchlist}'."


@tool(WRITE)
async def add_watchlist_item(
    watchlist: WatchlistRef,
    symbol: Annotated[str | None, Field(description="Security ticker to add.")] = None,
    exchange: Annotated[
        str | None, Field(description="Exchange, to pick one listing of a ticker.")
    ] = None,
    cik: Annotated[
        str | None, Field(description="CIK of an institutional investor to add.")
    ] = None,
    notes: Annotated[str | None, Field(description="Optional note for the item.")] = None,
) -> str:
    """Add a security (by symbol) or an institutional investor (by CIK) to one of the user's
    watchlists."""
    if not symbol and not cik:
        raise ToolError("Provide a symbol (security) or a cik (institutional investor).")
    item: dict[str, Any] = {}
    if symbol:
        item["symbol"] = symbol.strip().upper()
    if exchange:
        item["exchange"] = exchange.strip()
    if cik:
        item["cik"] = _pad_cik(cik)
    if notes is not None:
        item["notes"] = notes
    data = await client.request("POST", f"{_watchlist_path(watchlist)}/items", body={"item": item})
    return "Added item:\n" + _render(((data or {}).get("data") or {}).get("item", data))


@tool(UPDATE)
async def update_watchlist_item(
    watchlist: WatchlistRef,
    item_id: Annotated[str, Field(description="Item id from `get_watchlist`.")],
    notes: Annotated[str, Field(description="New notes for the item; empty string clears them.")],
) -> str:
    """Change the notes on an item in one of the user's watchlists."""
    data = await client.request(
        "PATCH",
        f"{_watchlist_path(watchlist)}/items/{segment(item_id.strip())}",
        body={"item": {"notes": notes}},
    )
    return "Updated item:\n" + _render(((data or {}).get("data") or {}).get("item", data))


@tool(DELETE)
async def delete_watchlist_item(
    watchlist: WatchlistRef,
    item_id: Annotated[str, Field(description="Item id from `get_watchlist`.")],
) -> str:
    """Remove an item from one of the user's watchlists."""
    await client.request("DELETE", f"{_watchlist_path(watchlist)}/items/{segment(item_id.strip())}")
    return f"Removed item {item_id} from '{watchlist}'."


def main() -> None:
    """Run the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
