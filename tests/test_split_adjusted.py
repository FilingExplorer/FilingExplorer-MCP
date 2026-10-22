"""Split-adjusted per-share companions on get_company_financials.

Fixtures are synthetic financials payloads for a fictional company, shaped like the
API's split-adjustment output: periods with applied companions, a period withheld
because the split date is unconfirmed, and periods withheld behind an unexplained
share-count break.
"""

import json
from pathlib import Path

from tests.conftest import call

SYNTHETIC = Path(__file__).parent / "synthetic"


def synthetic(name: str) -> dict:
    return json.loads((SYNTHETIC / name).read_text())


def period_block(out: str, end_date: str) -> str:
    start = out.index(f"end_date: {end_date}")
    nxt = out.find("\n  - ", start)
    return out[start : nxt if nxt != -1 else len(out)]


async def test_compact_passes_companions_and_marks_withheld(api):
    api.get("/v1/companies/ZZEXA/financials").respond(
        json=synthetic("financials_split_compact.json")
    )
    out = await call("get_company_financials", {"company": "ZZEXA", "period_count": 6})

    applied = period_block(out, "2021-12-31")
    assert "diluted_eps: 3.2" in applied
    assert "diluted_eps_split_adjusted: 1.6" in applied
    assert "shares_outstanding_split_adjusted: 150000000" in applied

    withheld = period_block(out, "2020-12-31")
    assert "diluted_eps: 4.5" in withheld
    assert "diluted_eps_split_adjusted: withheld" in withheld
    assert "shares_outstanding_split_adjusted: withheld" in withheld
    assert "split_adjustment_withheld: unexplained_share_break" in withheld

    unconfirmed = period_block(out, "2023-12-31")
    assert "split_adjustment_withheld: split_date_unconfirmed" in unconfirmed
    assert "diluted_eps_split_adjusted: withheld" in unconfirmed
    assert "companions_present: true" in out
    assert "unexplained_share_breaks:" in out
    assert "use diluted_eps_split_adjusted and shares_outstanding_split_adjusted" in out


async def test_full_keeps_split_adjusted_values_aligned_to_periods(api):
    api.get("/v1/companies/ZZEXA/financials").respond(json=synthetic("financials_split_full.json"))
    out = await call(
        "get_company_financials", {"company": "ZZEXA", "period_count": 6, "detail": "full"}
    )
    assert "split_adjusted_values: [null, null, 1.6, 1.8, null, 2.05]" in out
    assert (
        "split_adjusted_withheld: [unexplained_share_break, unexplained_share_break, "
        "null, null, split_date_unconfirmed, null]"
    ) in out
    # Ordinary rows with gaps keep their alignment too.
    assert "values: [1000000, 1000000, null, null, 1200000, 1200000]" in out


async def test_description_explains_split_basis():
    from filingexplorer_mcp.server import mcp

    tools = {t.name: t for t in await mcp.list_tools()}
    text = tools["get_company_financials"].description
    assert "diluted_eps_split_adjusted" in text
    assert "split_adjusted_values" in text
    assert "meta.split_adjustment" in text
