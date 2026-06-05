"""End-to-end MCP transport test: tools are registered and round-trip over HTTP.

Exercises the FastMCP server mounted into FastAPI via a real streamable-HTTP MCP client
(in-process ASGI), proving the Bearer header flows through to per-user DB routing.
"""

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.transport_security import TransportSecuritySettings

from brain2.main import MCP_MOUNT, create_app
from brain2.mcp.server import build_mcp_server

MCP_URL = f"http://testserver{MCP_MOUNT}/mcp"

# Permissive transport security so the in-process ASGI host ("testserver") passes
# the SDK's DNS-rebinding check; production keeps the secure default allow-list.
_TEST_SECURITY = TransportSecuritySettings(enable_dns_rebinding_protection=False)


@pytest.fixture(autouse=True)
def temp_data_dir(tmp_path, monkeypatch):
    from brain2.config import get_settings

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_tools_are_registered_with_annotations():
    mcp = build_mcp_server()
    listed = await mcp.list_tools()
    by_name = {t.name: t for t in listed}
    assert set(by_name) == {"save", "retrieve"}
    assert by_name["retrieve"].annotations.readOnlyHint is True
    assert by_name["save"].annotations.destructiveHint is True
    # Inputs carry typed JSON schemas.
    assert "query" in by_name["retrieve"].inputSchema["properties"]
    assert "type" in by_name["save"].inputSchema["properties"]


@pytest.mark.anyio
async def test_save_then_retrieve_round_trip_over_http():
    app = create_app(mcp_transport_security=_TEST_SECURITY)

    async with app.router.lifespan_context(app):
        http_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            headers={"Authorization": "Bearer br2_live_test"},
        )
        async with streamable_http_client(MCP_URL, http_client=http_client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                saved = await session.call_tool(
                    "save",
                    {"type": "page", "url": "https://ex.com/tokio", "title": "Tokio async runtime"},
                )
                entry_id = saved.structuredContent["id"]
                assert saved.structuredContent["status"] == "saved"

                found = await session.call_tool("retrieve", {"query": "tokio"})
                hits = found.structuredContent["result"]
                assert any(h["id"] == entry_id for h in hits)


@pytest.fixture
def anyio_backend():
    return "asyncio"
