import pytest
import respx

from filingexplorer_mcp.server import mcp

BASE = "https://api.test.example"


@pytest.fixture(autouse=True)
def _env(monkeypatch, request):
    if request.node.get_closest_marker("live"):
        return
    monkeypatch.setenv("FILING_EXPLORER_API_TOKEN", "test-token")
    monkeypatch.setenv("FILING_EXPLORER_API_URL", BASE)


@pytest.fixture
def api():
    with respx.mock(base_url=BASE, assert_all_called=True) as router:
        yield router


async def call(name: str, args: dict | None = None) -> str:
    result = await mcp.call_tool(name, args or {})
    if isinstance(result, tuple):
        result = result[0]
    return "\n".join(block.text for block in result)
