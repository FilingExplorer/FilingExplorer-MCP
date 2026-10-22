"""Synthetic API payloads shaped like the FilingExplorer API's responses.

Every company, fund, person, identifier and figure here is made up.
"""

CIK = "0000000001"
TICKER = "ZZEXA"
CUSIP = "00000A101"
ACC = "0000000001-26-000001"
ACC_10K = "0000000001-25-000002"
ACC_FORM4 = "0000000001-26-000003"
MANAGER_CIK = "0000000002"

SEARCH = {
    "data": [
        {
            "entity_type": "company",
            "match_type": "ticker",
            "match_quality": "exact",
            "data": {"cik": CIK, "name": "Example Corp", "ticker": TICKER},
            "links": {},
        },
        {
            "entity_type": "security",
            "match_type": "identifier",
            "match_quality": "exact",
            "type": "security",
            "id": 42,
            "symbol": TICKER,
            "cusip": CUSIP,
            "exchange": "NASDAQ",
        },
    ],
    "meta": {"query": TICKER, "result_count": 2},
}

PROFILE = {
    "company": {
        "cik": CIK,
        "name": "Example Corp",
        "ticker": TICKER,
        "exchange": "Nasdaq",
        "sic": "3571",
        "sic_description": "Electronic Computers",
        "fiscal_year_end": "1231",
        "shares_outstanding": 150000000,
        "shares_outstanding_date": "2026-07-18",
    }
}

FILINGS = {
    "data": [
        {
            "type": "filing",
            "id": ACC,
            "attributes": {
                "accession_number": ACC,
                "cik": CIK,
                "form_type": "10-Q",
                "filing_date": "2026-08-01",
                "report_date": "2026-06-30",
                "primary_document": "zzexa-20260630.htm",
                "is_xbrl": True,
            },
            "links": {"index": "https://www.sec.gov/Archives/edgar/data/1/x/"},
        }
    ],
    "meta": {
        "cik": CIK,
        "company_name": "Example Corp",
        "total_count": 40,
        "page_size": 1,
        "offset": 0,
        "has_more": True,
    },
}

CALENDAR = {
    "company": {"cik": CIK, "name": "Example Corp", "ticker": TICKER},
    "current_fiscal_year": 2026,
    "current_fiscal_quarter": "Q4",
    "quarters": [
        {"fiscal_year": 2026, "quarter": "Q3", "start_date": "2026-07-01", "end_date": "2026-09-30"}
    ],
}

FINANCIALS = {
    "company": {"cik": CIK, "name": "Example Corp"},
    "periods": [
        {
            "fy": 2025,
            "fiscal_period": "FY",
            "end_date": "2025-12-31",
            "form": "10-K",
            "revenue": 4000000000,
            "net_income": 300000000,
            "diluted_eps": 2.05,
            "gross_margin_pct": 41.5,
        }
    ],
    "meta": {"timeframe": "annual", "fields": "compact"},
}

DOCUMENTS = {
    "data": {
        "accession_number": ACC,
        "cik": CIK,
        "lookup": "unused",
        "index_url": "https://www.sec.gov/Archives/edgar/data/1/x/",
        "document_count": 2,
        "documents": [
            {
                "sequence": 1,
                "filename": "zzexa-20260630.htm",
                "description": "10-Q",
                "document_type": "10-Q",
                "size": 812345,
            },
            {
                "sequence": 2,
                "filename": "ex31-1.htm",
                "description": "Certification",
                "document_type": "EX-31.1",
                "size": 9000,
            },
        ],
    }
}

SECTIONS = {
    "accession_number": ACC_10K,
    "form_type": "10-K",
    "sections": [
        {
            "section_key": "item_1a",
            "section_title": "Risk Factors",
            "has_text": True,
            "raw_text_chars": 64000,
            "extra": "unused",
        }
    ],
    "_meta": {
        "supported_section_keys": ["item_1", "item_1a", "item_7"],
        "description": "Section index",
    },
}

SECTION = {
    "section": {
        "accession_number": ACC_10K,
        "section_key": "item_1a",
        "section_title": "Risk Factors",
        "form_type": "10-K",
        "fiscal_year": "2025",
        "raw_text": "Our results depend on general economic conditions in the markets we serve.",
        "raw_text_chars": 74,
        "extra": "unused",
    }
}

MANAGERS = {
    "pagination": {"total_count": 1, "limit": 50, "offset": 0, "has_more": False},
    "filers": [
        {
            "cik": MANAGER_CIK,
            "name": "Example Capital Management LLC",
            "state_or_country": "NY",
            "portfolio_value": "2500000000",
            "latest_period_of_report": "2026-06-30",
        }
    ],
}

SUBMISSION = {
    "cik": MANAGER_CIK,
    "name": "Example Capital Management LLC",
    "period_of_report": "2026-06-30",
    "filing_date": "2026-08-14",
    "accession_number": "0000000002-26-000001",
    "fields": "compact",
    "total_value": "2500000000",
    "holdings_count": 40,
    "top_holdings": [
        {
            "issuer": "EXAMPLE CORP",
            "cusip": CUSIP,
            "value": "600000000",
            "shares": "2800000",
            "pct_of_portfolio": "24.0",
            "extra": "unused",
        }
    ],
    "activity_summary": {"holdings_count": 40, "extra": "unused"},
    "extra": "unused",
    "holdings_pagination": {"total_count": 40, "limit": 1, "offset": 0, "has_more": True},
    "holdings": [{"security_name": "EXAMPLE CORP", "cusip": CUSIP, "extra": "unused"}],
}

HOLDERS = {
    "security": {"symbol": TICKER, "name": "Example Corp", "cusip": CUSIP},
    "period": {"current": "2026-06-30", "previous": "2026-03-31"},
    "summary": {"total_institutional_value": 20000000000, "net_activity": "accumulation"},
    "holders": [
        {
            "fund": {"cik": MANAGER_CIK, "name": "Example Capital Management LLC"},
            "position": {"shares": 2800000, "value": 600000000, "percent_of_portfolio": 24.0},
            "changes": {"shares_change": 10000, "is_new_position": False},
        }
    ],
    "meta": {"total_holders": 500, "returned": 1, "limit": 1},
}

FORM4_LIST = {
    "pagination": {"total_count": 3, "limit": 1, "offset": 0, "has_more": True},
    "filings": [
        {
            "accession_number": ACC_FORM4,
            "form_type": "4",
            "filing_date": "2026-10-03",
            "issuer": {"name": "Example Corp", "cik": CIK, "trading_symbol": TICKER},
            "transaction_summary": {"total_value": "500000", "direction": "sell"},
            "rule_10b5_1_plan": True,
            "reporting_owners": [{"name": "Doe Jane", "cik": "0000000004"}],
        }
    ],
}

FORM4 = {
    "accession_number": ACC_FORM4,
    "filing_date": "2026-10-03",
    "issuer": {"name": "Example Corp", "cik": CIK, "trading_symbol": TICKER},
    "reporting_owners": [
        {"name": "Doe Jane", "relationships": {"is_officer": True, "officer_title": "CFO"}}
    ],
    "non_derivative_transactions": [
        {
            "title": "Common Stock",
            "transaction_date": "2026-10-01",
            "transaction_code": "S",
            "shares": 2000,
            "price_per_share": "25.00",
            "shares_owned_after": 10000,
        }
    ],
    "footnotes": {"F1": "Sold under a Rule 10b5-1 trading plan adopted May 1, 2026."},
}

CLUSTERS = {
    "pagination": {"total_count": 1, "limit": 20, "offset": 0, "has_more": False},
    "clusters": [
        {
            "id": "c1",
            "issuer": {"cik": CIK, "name": "Example Corp", "trading_symbol": TICKER},
            "direction": "buy",
            "window_days": 7,
            "insider_count": 3,
            "aggregate_value_formatted": "$1.2M",
            "insider_names": ["A", "B", "C"],
        }
    ],
    "summary": {"total_buying_clusters": 1, "total_selling_clusters": 0},
}

ETF = {
    "data": {
        "etf": {"symbol": "ZZEXF", "name": "Example Technology ETF"},
        "filing": {"reporting_period_end": "2026-06-30", "total_net_assets": 700000000},
        "holdings": [
            {
                "ticker": TICKER,
                "name": "Example Corp",
                "valuation": 90000000,
                "percentage_of_net_assets": 13.0,
                "asset_category": "EC",
            }
        ],
        "pagination": {"total_count": 70, "limit": 1, "offset": 0, "has_more": True},
    },
    "meta": {"timestamp": "2026-10-19T00:00:00Z"},
}

ETF_EMPTY = {
    "data": {"etf": {"symbol": "ZZZ"}, "holdings": []},
    "meta": {
        "no_data_reason": "not_covered",
        "hint": "This fund's holdings are not in N-PORT coverage.",
    },
}

LIST = {
    "id": "6f1c1f9e-0f5e-4a59-9a43-1b2c3d4e5f60",
    "name": "Tech",
    "notes": None,
    "item_count": 1,
    "created_at": "2026-10-01T00:00:00Z",
    "updated_at": "2026-10-01T00:00:00Z",
}

ITEM = {
    "id": "a1b2c3d4-0000-4000-8000-000000000001",
    "notes": "core",
    "position": 1,
    "resolved": {"name": "Example Corp"},
    "entity_type": "security",
    "symbol": TICKER,
}

LISTS = {"data": {"lists": [LIST]}, "meta": {"version": "v1"}}
LIST_SHOW = {
    "data": {
        "list": LIST,
        "items": [ITEM],
        "pagination": {"total_count": 1, "limit": 50, "offset": 0, "has_more": False},
    }
}
