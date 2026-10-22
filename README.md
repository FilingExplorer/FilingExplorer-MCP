# filingexplorer-mcp

A [Model Context Protocol](https://modelcontextprotocol.io) server for the
[FilingExplorer](https://www.filingexplorer.com) API. It gives an MCP client (Claude Desktop,
Claude Code, or any other MCP host) direct tools for public SEC filing data: company profiles
and filing lists, reported financials, verbatim filing text, Form 13-F institutional holdings,
Form 4 insider trades, ETF holdings, and your own watchlists.

> **0.x: tool names, parameters and outputs may change between minor versions.**

The server runs locally on your machine and calls the FilingExplorer API with your own API
token. There is no hosted endpoint.

## Requirements

- Python 3.10 or newer, or [uv](https://docs.astral.sh/uv/)
- A FilingExplorer API token (create one in your FilingExplorer account settings)

## Install and run

```bash
uvx filingexplorer-mcp
```

or install it into an environment and run the script:

```bash
pip install filingexplorer-mcp
filingexplorer-mcp
```

The server speaks MCP over stdio, so it is normally started by your MCP client rather than by
hand.

## Configuration

| Variable | Required | Purpose |
|---|---|---|
| `FILING_EXPLORER_API_TOKEN` | yes | Your FilingExplorer API token. |
| `FILING_EXPLORER_API_URL` | no | API base URL. Default `https://api.filingexplorer.com`. |
| `FILING_EXPLORER_TIMEOUT` | no | Request timeout in seconds. Default `60`. |

All data, including filing documents, is fetched through the FilingExplorer API. The server
makes no direct requests to sec.gov.

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "filingexplorer": {
      "command": "uvx",
      "args": ["filingexplorer-mcp"],
      "env": { "FILING_EXPLORER_API_TOKEN": "your-token" }
    }
  }
}
```

### Claude Code

```bash
claude mcp add filingexplorer --env FILING_EXPLORER_API_TOKEN=your-token -- uvx filingexplorer-mcp
```

## Tools

| Area | Tool | What it returns |
|---|---|---|
| Search and company | `search` | Companies, securities and 13F filers matching a name, ticker, CIK or CUSIP. |
| | `get_company_profile` | Name, CIK, ticker, exchange, SIC industry, fiscal year end, shares outstanding. |
| | `get_company_filings` | A company's SEC filings with accession numbers, dates and form types. |
| | `get_company_calendar` | Fiscal year and quarter boundaries. |
| Financials | `get_company_financials` | Reported fundamentals and margins per fiscal year or quarter. |
| SEC documents | `list_filing_documents` | The documents inside one filing (main document, exhibits). |
| | `get_filing_document_text` | Verbatim text of one document, windowed for long documents. |
| | `list_filing_sections` | The extracted sections of a 10-K, 10-Q, 20-F, S-1 or F-1. |
| | `get_filing_section` | Verbatim text of one section, such as Item 1A Risk Factors. |
| 13F | `search_13f_managers` | Institutional managers that file Form 13-F. |
| | `get_13f_submission` | One manager's quarterly portfolio, top positions and changes. |
| | `get_security_holders` | Top institutional holders of a security, with quarter-over-quarter changes. |
| Insiders | `list_form4_filings` | Form 4 filings for a company or an insider. |
| | `get_form4_filing` | One Form 4 in full, including footnotes and Rule 10b5-1 disclosure. |
| | `get_form4_clusters` | Groups of insiders buying or selling the same stock within a short window. |
| Funds | `get_etf_holdings` | An ETF's holdings from its N-PORT filing. |
| Watchlists | `list_watchlists`, `get_watchlist` | Your watchlists and their items. |
| | `create_watchlist`, `update_watchlist`, `delete_watchlist` | Manage your watchlists. |
| | `add_watchlist_item`, `update_watchlist_item`, `delete_watchlist_item` | Manage watchlist items. |

Notes:

- **Verbatim text only.** The document and section tools return text exactly as filed.
- **ETF coverage is incomplete.** Some ETFs have no holdings data. The tool says so when that
  happens; an empty result means the data is not available, not that the fund holds nothing.
- **Watchlist tools act only on your own account.** The API scopes every list request to the
  owner of the token.
- Some requests (same-day or full-history filing lists, longer insider-cluster windows) need a
  paid FilingExplorer plan. These return a clear error on other plans.

## Output format

Tools return compact, YAML-like text: empty fields are omitted, and lists include a hint such
as `call again with offset=50 for more` when more results exist. Long texts come in windows
of `max_chars` characters with the next `offset` stated in a header line.

Errors come back as tool errors with the HTTP status and the API's message, for example
`Not found (404): Company not found` or `Rate limited by the FilingExplorer API (429). Retry
after 30 seconds.`

## Development

```bash
uv sync
uv run ruff check .
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the commit hooks and the publication check.

The contract tests use hand-written fixtures and no network. A live smoke test runs only when
`FILING_EXPLORER_API_TOKEN` is set:

```bash
FILING_EXPLORER_API_TOKEN=your-token uv run pytest -m live
```

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
