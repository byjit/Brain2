"""MCP server for Brain2: exposes the save/retrieve tools over streamable HTTP.

The transport is mounted into the FastAPI app (see ``brain2.main``). Tools reuse the
same entries/search services as the REST layer so there is one implementation (DRY).
"""
