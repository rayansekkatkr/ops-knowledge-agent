"""Hanbit Ops MCP server: exposes the RAG pipeline and an ops check as MCP tools.

Tools
  - search_docs(query, k)   -> top passages from the company documents, with citations
  - ask_docs(question)      -> grounded answer generated from those passages
  - check_endpoint(url)     -> HTTP status, latency and TLS certificate expiry of a public URL

Run
  python mcp_server/server.py                       # Streamable HTTP on http://127.0.0.1:8000/mcp
  python mcp_server/server.py --transport stdio     # for a local MCP client (VS Code, IDE agents)
  python mcp_server/server.py --public-host <tunnel-host>   # accept requests through a dev tunnel

Optional security
  MCP_API_KEY=...                 clients must send header  x-api-key: <value>
  MCP_ALLOW_PRIVATE_TARGETS=1     let check_endpoint reach private / loopback addresses
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rag"))
from rag_core import Index, answer  # noqa: E402

from mcp.server.mcpserver import MCPServer  # noqa: E402

mcp = MCPServer(
    name="hanbit-ops",
    instructions=(
        "Tools for Hanbit Logistics operations. Use search_docs or ask_docs for questions about "
        "the incident runbook, support plans and SLAs, or security and patch policy. "
        "Use check_endpoint to check whether a public HTTP(S) endpoint is up."
    ),
)

_index: Index | None = None


def get_index() -> Index:
    """Build the index lazily, once, on the first tool call."""
    global _index
    if _index is None:
        _index = Index.load_or_build()
    return _index


# ---------------------------------------------------------------------------
# Tool 1 and 2: RAG over the company documents
# ---------------------------------------------------------------------------

class Passage(BaseModel):
    citation: str = Field(description="Source document and section")
    score: float = Field(description="Relevance score, higher is better")
    text: str


class DocsAnswer(BaseModel):
    answer: str
    sources: list[str] = Field(description="Passages retrieved to build the answer")
    mode: str = Field(description="generative, extractive or no-context")


@mcp.tool()
def search_docs(query: str, k: int = 4) -> list[Passage]:
    """Search Hanbit Logistics internal documents (incident runbook, support and SLA policy,
    security and patch policy) and return the most relevant passages with their source.
    Use this when you want the raw passages to reason over yourself."""
    k = max(1, min(k, 8))
    return [
        Passage(citation=h.chunk.citation(), score=round(h.score, 3), text=h.chunk.text)
        for h in get_index().search(query, k=k)
    ]


@mcp.tool()
def ask_docs(question: str) -> DocsAnswer:
    """Answer a question about Hanbit Logistics incident handling, support plans, SLAs,
    service credits, access control, secrets or patch deadlines, using only the internal
    documents. The answer cites its sources."""
    result = answer(question, get_index())
    return DocsAnswer(
        answer=result["answer"],
        sources=[s["citation"] for s in result["sources"]],
        mode=result["mode"],
    )


# ---------------------------------------------------------------------------
# Tool 3: an ops check, with an SSRF guard
# ---------------------------------------------------------------------------

class EndpointStatus(BaseModel):
    url: str
    ok: bool
    status_code: int | None = None
    latency_ms: int | None = None
    tls_days_left: int | None = Field(None, description="Days before the TLS certificate expires")
    error: str | None = None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # A redirect could send us to an internal address after the check below,
    # so we report it instead of following it.
    def redirect_request(self, *args, **kwargs):
        return None


def _blocked_reason(host: str) -> str | None:
    """Return why a host must not be contacted, or None if it resolves to public IPs only."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return f"Cannot resolve host {host}"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return f"{host} resolves to a non-public address ({ip}), refused to prevent SSRF"
    return None


def _tls_days_left(host: str, port: int) -> int | None:
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=5) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            not_after = tls.getpeercert()["notAfter"]
    expires = datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), tz=timezone.utc)
    return (expires - datetime.now(timezone.utc)).days


@mcp.tool()
def check_endpoint(url: str) -> EndpointStatus:
    """Check that a public HTTP(S) endpoint is reachable: returns the HTTP status code,
    the response time in milliseconds and, for HTTPS, the number of days before the TLS
    certificate expires. Use it during an incident to confirm whether a service is up."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return EndpointStatus(url=url, ok=False, error="Only http:// and https:// URLs are allowed")
    if os.environ.get("MCP_ALLOW_PRIVATE_TARGETS") != "1":
        reason = _blocked_reason(parsed.hostname)
        if reason:
            return EndpointStatus(url=url, ok=False, error=reason)

    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, headers={"User-Agent": "hanbit-ops-mcp/1.0"})
    start = time.perf_counter()
    try:
        with opener.open(request, timeout=5) as resp:
            status = resp.status
    except urllib.error.HTTPError as e:  # 4xx/5xx and unfollowed 3xx still give a status
        status = e.code
    except Exception as e:  # DNS, timeout, TLS errors...
        return EndpointStatus(url=url, ok=False, error=f"{type(e).__name__}: {e}")
    latency = int((time.perf_counter() - start) * 1000)

    days = None
    if parsed.scheme == "https":
        try:
            days = _tls_days_left(parsed.hostname, parsed.port or 443)
        except Exception:
            pass
    return EndpointStatus(
        url=url, ok=200 <= status < 400, status_code=status, latency_ms=latency, tls_days_left=days
    )


# ---------------------------------------------------------------------------
# HTTP app with optional API key
# ---------------------------------------------------------------------------

class ApiKeyMiddleware:
    """Reject HTTP requests without the right x-api-key header (pure ASGI)."""

    def __init__(self, app, api_key: str):
        self.app, self.api_key = app, api_key.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            if headers.get(b"x-api-key") != self.api_key:
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"Missing or invalid x-api-key"})
                return
        await self.app(scope, receive, send)


def build_http_app(public_host: str | None = None):
    from mcp.server.transport_security import TransportSecuritySettings

    allowed = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    if public_host:  # e.g. abc123-8000.asse.devtunnels.ms
        allowed.append(public_host)
    app = mcp.streamable_http_app(
        stateless_http=True,  # no server-side session: simpler behind tunnels and load balancers
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed,
            allowed_origins=[f"https://{public_host}"] if public_host else [],
        ),
    )
    api_key = os.environ.get("MCP_API_KEY")
    return ApiKeyMiddleware(app, api_key) if api_key else app


def main() -> None:
    parser = argparse.ArgumentParser(description="Hanbit Ops MCP server")
    parser.add_argument("--transport", choices=["http", "stdio"], default="http")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--public-host", help="host name of a dev tunnel / reverse proxy to accept")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run("stdio")
        return

    import uvicorn

    print(f"MCP endpoint: http://127.0.0.1:{args.port}/mcp", file=sys.stderr)
    if os.environ.get("MCP_API_KEY"):
        print("API key required (header x-api-key)", file=sys.stderr)
    uvicorn.run(build_http_app(args.public_host), host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
