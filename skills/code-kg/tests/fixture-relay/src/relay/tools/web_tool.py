"""Web tool: fetch a URL through a pluggable fetcher with a size cap.

The default fetcher refuses everything - the fixture never touches the
network - and tests install a fake. The scheme/host validation above the
seam is the code that matters.
"""
from __future__ import annotations

from typing import Callable
from urllib.parse import urlparse

from relay.errors import ToolFailed
from relay.tools.registry import tool

_SIZE_CAP = 200_000
_BLOCKED_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254")

Fetcher = Callable[[str], str]


def _refusing_fetcher(url: str) -> str:
    raise ToolFailed("web", "network disabled in fixture", retryable=False)


_fetcher: Fetcher = _refusing_fetcher


def install_fetcher(fetcher: Fetcher) -> None:
    """Test seam: replace the transport, keep the validation."""
    global _fetcher
    _fetcher = fetcher


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ToolFailed("web", f"scheme {parsed.scheme!r} refused",
                         retryable=False)
    host = (parsed.hostname or "").lower()
    if not host or host in _BLOCKED_HOSTS:
        raise ToolFailed("web", f"host {host!r} refused", retryable=False)
    return url


@tool("web", "Fetch one http(s) URL and return its text", timeout_s=30,
      tags=("network", "read"))
def fetch_url(url: str) -> str:
    text = _fetcher(validate_url(url))
    if len(text) > _SIZE_CAP:
        return text[:_SIZE_CAP] + f"\n[TRUNCATED at {_SIZE_CAP} chars]"
    return text
