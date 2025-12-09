"""
Shared HTTP client with connection pooling for improved performance.

This module provides a singleton AsyncClient that can be reused across
multiple service calls, enabling HTTP/2 connection reuse and proper
connection pool management.

Usage:
    from shared.services.http_client import get_http_client, close_http_client

    # Use the shared client
    client = get_http_client()
    response = await client.get("https://example.com")

    # At application shutdown
    await close_http_client()
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Global client instance (lazy initialized)
_client: Optional[httpx.AsyncClient] = None

# Default configuration - conservative limits suitable for Azure Functions
DEFAULT_LIMITS = httpx.Limits(
    max_keepalive_connections=20,
    max_connections=100,
    keepalive_expiry=30.0,  # Close idle connections after 30s
)

DEFAULT_TIMEOUT = httpx.Timeout(
    connect=10.0,   # Time to establish connection
    read=30.0,      # Time to read response
    write=30.0,     # Time to send request
    pool=5.0,       # Time to acquire connection from pool
)


def get_http_client(
    *,
    limits: Optional[httpx.Limits] = None,
    timeout: Optional[httpx.Timeout] = None,
    http2: bool = False,
) -> httpx.AsyncClient:
    """
    Get the shared HTTP client instance.

    The client is lazily initialized on first call and reused for subsequent calls.
    This enables connection pooling and HTTP/2 multiplexing for better performance.

    Args:
        limits: Optional custom connection limits (only used on first call)
        timeout: Optional custom timeout configuration (only used on first call)
        http2: Enable HTTP/2 support (requires httpx[http2] package)

    Returns:
        The shared AsyncClient instance
    """
    global _client

    if _client is None:
        _limits = limits or DEFAULT_LIMITS
        _timeout = timeout or DEFAULT_TIMEOUT

        _client = httpx.AsyncClient(
            limits=_limits,
            timeout=_timeout,
            follow_redirects=True,
            http2=http2,  # Enable HTTP/2 if package is installed
        )
        logger.debug(
            "Initialized shared HTTP client with limits=%s, timeout=%s, http2=%s",
            _limits,
            _timeout,
            http2,
        )

    return _client


async def close_http_client() -> None:
    """
    Close the shared HTTP client and release all connections.

    Call this during application shutdown to ensure clean resource cleanup.
    After calling this, the next call to get_http_client() will create a new client.
    """
    global _client

    if _client is not None:
        await _client.aclose()
        _client = None
        logger.debug("Closed shared HTTP client")


def is_client_initialized() -> bool:
    """Check if the shared client has been initialized."""
    return _client is not None


class ManagedHttpClient:
    """
    Context manager for the shared HTTP client.

    This is useful for ensuring the client is properly closed at the end
    of a scope, particularly in Azure Functions or test scenarios.

    Usage:
        async with ManagedHttpClient() as client:
            response = await client.get("https://example.com")
    """

    def __init__(
        self,
        *,
        limits: Optional[httpx.Limits] = None,
        timeout: Optional[httpx.Timeout] = None,
    ):
        self._limits = limits
        self._timeout = timeout

    async def __aenter__(self) -> httpx.AsyncClient:
        return get_http_client(limits=self._limits, timeout=self._timeout)

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # Note: We don't close the client here to allow reuse.
        # Call close_http_client() explicitly when you're done with all requests.
        pass


