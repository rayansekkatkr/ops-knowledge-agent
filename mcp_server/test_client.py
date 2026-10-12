"""Small MCP client: lists the server's tools and calls each one.

    python mcp_server/test_client.py                          # local server on :8000
    python mcp_server/test_client.py --url https://<tunnel>/mcp
    MCP_API_KEY=... python mcp_server/test_client.py          # if the server requires a key
"""

import argparse
import asyncio
import json
import os

from mcp import Client


def _transport(url: str):
    api_key = os.environ.get("MCP_API_KEY")
    if not api_key:
        return url  # a plain URL means Streamable HTTP
    import httpx2
    from mcp.client.streamable_http import streamable_http_client

    return streamable_http_client(url, http_client=httpx2.AsyncClient(headers={"x-api-key": api_key}))


def show(result) -> None:
    if result.is_error:
        print("  ERROR:", result.content)
    elif result.structured_content is not None:
        print(json.dumps(result.structured_content, indent=2, ensure_ascii=False)[:1500])
    else:
        print(result.content)


async def main(url: str) -> None:
    async with Client(_transport(url)) as client:
        tools = await client.list_tools()
        print("Tools exposed by the server:")
        for tool in tools.tools:
            print(f"  - {tool.name}: {tool.description.splitlines()[0]}")
            print(f"    input schema: {json.dumps(tool.input_schema.get('properties', {}))}")

        print("\n> search_docs('error budget release freeze', k=2)")
        show(await client.call_tool("search_docs", {"query": "error budget release freeze", "k": 2}))

        print("\n> ask_docs('Who approves a patch exception and for how long?')")
        show(await client.call_tool("ask_docs", {"question": "Who approves a patch exception and for how long?"}))

        print("\n> check_endpoint('http://169.254.169.254/latest/meta-data')  # cloud metadata, must be refused")
        show(await client.call_tool("check_endpoint", {"url": "http://169.254.169.254/latest/meta-data"}))

        print("\n> check_endpoint('https://www.microsoft.com')")
        show(await client.call_tool("check_endpoint", {"url": "https://www.microsoft.com"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    asyncio.run(main(parser.parse_args().url))
