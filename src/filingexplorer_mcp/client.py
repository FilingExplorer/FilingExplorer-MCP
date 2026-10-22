"""Thin async HTTP client for the FilingExplorer API."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import httpx
from mcp.server.fastmcp.exceptions import ToolError

from filingexplorer_mcp import __version__

DEFAULT_BASE_URL = "https://api.filingexplorer.com"
TOKEN_ENV = "FILING_EXPLORER_API_TOKEN"
BASE_URL_ENV = "FILING_EXPLORER_API_URL"
TIMEOUT_ENV = "FILING_EXPLORER_TIMEOUT"


class ApiError(ToolError):
    """An error response from the API, rendered as a readable tool error."""

    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


def segment(value: str) -> str:
    """Percent-encode one path segment (list names may contain spaces or slashes)."""
    return quote(str(value), safe="")


def _base_url() -> str:
    return os.environ.get(BASE_URL_ENV, DEFAULT_BASE_URL).rstrip("/")


def _token() -> str:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise ApiError(
            401,
            f"No API token configured. Set the {TOKEN_ENV} environment variable "
            "to your FilingExplorer API token.",
        )
    return token


def _timeout() -> float:
    try:
        return float(os.environ.get(TIMEOUT_ENV, "60"))
    except ValueError:
        return 60.0


def clean_params(params: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Drop unset values, render booleans as true/false, expand lists."""
    out: list[tuple[str, str]] = []
    for key, value in (params or {}).items():
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, (list, tuple)):
            out.extend((key, str(v)) for v in value)
        elif isinstance(value, bool):
            out.append((key, "true" if value else "false"))
        else:
            out.append((key, str(value)))
    return out


def _error_detail(response: httpx.Response) -> tuple[str, Any]:
    try:
        body = response.json()
    except ValueError:
        text = response.text.strip()
        return (text[:300] if text and "<html" not in text.lower() else ""), None
    if isinstance(body, dict):
        err = body.get("error", body.get("errors", body))
        if isinstance(err, str):
            return err, None
        if isinstance(err, dict):
            message = str(err.get("message") or err.get("code") or "")
            hint = err.get("hint")
            if hint:
                message = f"{message} ({hint})" if message else str(hint)
            return message, err.get("details")
        if isinstance(err, list):
            return "; ".join(str(e) for e in err), None
    return "", None


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status < 400:
        return
    message, details = _error_detail(response)
    suffix = f": {message}" if message else ""
    if status == 400:
        text = f"Invalid request (400){suffix}"
    elif status == 401:
        text = (
            "Authentication failed (401): the API token is missing, invalid or expired. "
            f"Check {TOKEN_ENV}."
        )
    elif status == 402:
        text = f"This request needs a paid FilingExplorer plan (402){suffix}"
    elif status == 403:
        text = f"Not permitted for this account (403){suffix}"
    elif status == 404:
        text = f"Not found (404){suffix}"
    elif status == 409:
        text = f"Ambiguous identifier (409){suffix}"
        matches = details.get("matches") if isinstance(details, dict) else None
        if matches:
            options = []
            for m in matches[:10]:
                if isinstance(m, dict):
                    parts = [str(m[k]) for k in ("symbol", "exchange", "cusip", "name") if m.get(k)]
                    options.append(" / ".join(parts))
            text += ". Candidates: " + "; ".join(options) + ". Retry with a more specific value."
    elif status == 413:
        text = f"Document too large to extract (413){suffix}"
    elif status == 422:
        text = f"Validation failed (422){suffix}"
        if isinstance(details, dict) and details:
            text += " " + "; ".join(
                f"{k} {', '.join(map(str, v)) if isinstance(v, list) else v}"
                for k, v in details.items()
            )
    elif status == 429:
        retry = response.headers.get("Retry-After")
        wait = f" Retry after {retry} seconds." if retry else " Wait a moment and retry."
        text = f"Rate limited by the FilingExplorer API (429).{wait}"
    elif status >= 500:
        text = f"FilingExplorer API error ({status}){suffix}. Try again later."
    else:
        text = f"Request failed ({status}){suffix}"
    raise ApiError(status, text)


async def request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    text: bool = False,
) -> Any:
    """Call the API and return parsed JSON (or text when ``text`` is true).

    Returns ``None`` for 204 responses.
    """
    headers = {
        "Authorization": f"Bearer {_token()}",
        "Accept": "text/plain" if text else "application/json",
        "User-Agent": f"filingexplorer-mcp/{__version__}",
    }
    try:
        async with httpx.AsyncClient(base_url=_base_url(), timeout=_timeout()) as client:
            response = await client.request(
                method, path, params=clean_params(params), json=body, headers=headers
            )
    except httpx.TimeoutException as exc:
        raise ApiError(504, "The FilingExplorer API did not respond in time. Try again.") from exc
    except httpx.HTTPError as exc:
        raise ApiError(503, f"Could not reach the FilingExplorer API: {exc}") from exc
    _raise_for_status(response)
    if response.status_code == 204 or not response.content:
        return None
    if text:
        return response.text
    try:
        return response.json()
    except ValueError as exc:
        raise ApiError(502, "The FilingExplorer API returned an unreadable response.") from exc
