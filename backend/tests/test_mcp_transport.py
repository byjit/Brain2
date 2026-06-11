"""End-to-end MCP transport test: tools are registered and round-trip over HTTP.

Exercises the FastMCP server mounted into FastAPI via a real streamable-HTTP MCP client
(in-process ASGI), proving the Bearer header flows through to per-user DB routing.
"""

import os

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
    # The spec §10 tools plus the `list` browse/filter tool are registered.
    assert set(by_name) == {"save", "retrieve", "delete", "get_tags", "list"}
    assert by_name["retrieve"].annotations.readOnlyHint is True
    # list is a read-only, non-destructive browse complement to retrieve.
    assert by_name["list"].annotations.readOnlyHint is True
    assert by_name["list"].annotations.destructiveHint is False
    assert by_name["save"].annotations.destructiveHint is True
    # delete: destructive but idempotent and not read-only (spec M6).
    assert by_name["delete"].annotations.readOnlyHint is False
    assert by_name["delete"].annotations.destructiveHint is True
    assert by_name["delete"].annotations.idempotentHint is True
    # get_tags is read-only.
    assert by_name["get_tags"].annotations.readOnlyHint is True
    # Inputs carry typed JSON schemas.
    assert "query" in by_name["retrieve"].inputSchema["properties"]
    assert "type" in by_name["save"].inputSchema["properties"]
    assert "id" in by_name["delete"].inputSchema["properties"]
    assert "sort" in by_name["get_tags"].inputSchema["properties"]


@pytest.mark.anyio
async def test_save_then_retrieve_round_trip_over_http():
    app = create_app(mcp_transport_security=_TEST_SECURITY)

    async with app.router.lifespan_context(app):
        http_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            headers={"Authorization": f"Bearer {os.environ['AUTH_API_KEY']}"},
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


@pytest.mark.anyio
async def test_delete_and_get_tags_round_trip_over_http():
    app = create_app(mcp_transport_security=_TEST_SECURITY)

    async with app.router.lifespan_context(app):
        http_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            headers={"Authorization": f"Bearer {os.environ['AUTH_API_KEY']}"},
        )
        async with streamable_http_client(MCP_URL, http_client=http_client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Save a note carrying agent tags, then list tags and delete it.
                saved = await session.call_tool(
                    "save",
                    {"type": "note", "note": "tokio runtime trick", "tags": ["rust", "async"]},
                )
                entry_id = saved.structuredContent["id"]

                tags = await session.call_tool("get_tags", {})
                names = {t["tag"] for t in tags.structuredContent["result"]}
                assert {"rust", "async"} <= names

                deleted = await session.call_tool("delete", {"id": entry_id})
                assert deleted.structuredContent["deleted"] is True
                # Idempotent: deleting again returns false.
                again = await session.call_tool("delete", {"id": entry_id})
                assert again.structuredContent["deleted"] is False


@pytest.mark.anyio
async def test_tool_call_without_valid_bearer_is_rejected():
    """M7: an MCP tool call with no/garbage Bearer must not resolve to a user."""
    app = create_app(mcp_transport_security=_TEST_SECURITY)

    async with app.router.lifespan_context(app):
        http_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            headers={"Authorization": "Bearer br2_live_not_a_real_key"},
        )
        async with streamable_http_client(MCP_URL, http_client=http_client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("retrieve", {"query": "anything"})
                # The unauthenticated call surfaces as a tool error, not a successful result.
                assert result.isError


@pytest.mark.anyio
async def test_mcp_metadata_endpoints():
    app = create_app(mcp_transport_security=_TEST_SECURITY)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            # Test Protected Resource Metadata (RFC 9728)
            resp = await client.get("/.well-known/oauth-protected-resource")
            assert resp.status_code == 200
            data = resp.json()
            assert data["resource"] == "http://testserver/connect/mcp"
            assert data["authorization_servers"] == ["http://testserver"]

            # Test Authorization Server Metadata (RFC 8414)
            for path in ["/.well-known/oauth-authorization-server", "/.well-known/openid-configuration"]:
                resp = await client.get(path)
                assert resp.status_code == 200
                data = resp.json()
                assert data["issuer"] == "http://testserver"
                assert data["authorization_endpoint"] == "http://testserver/oauth/authorize"
                assert data["token_endpoint"] == "http://testserver/oauth/token"
                assert "authorization_code" in data["grant_types_supported"]


@pytest.mark.anyio
async def test_mcp_unauthorized_connection_challenges_401():
    app = create_app(mcp_transport_security=_TEST_SECURITY)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            # Requesting without Authorization header should return 401 with WWW-Authenticate pointing to PRM metadata
            resp = await client.post("/connect/mcp", json={})
            assert resp.status_code == 401
            assert "WWW-Authenticate" in resp.headers
            challenge = resp.headers["WWW-Authenticate"]
            assert 'resource_metadata="http://testserver/.well-known/oauth-protected-resource"' in challenge

            # Preflight OPTIONS request should pass through with 200 (not challenged)
            resp_options = await client.options(
                "/connect/mcp",
                headers={
                    "Origin": "https://claude.ai",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert resp_options.status_code == 200


@pytest.fixture
def anyio_backend():
    return "asyncio"
