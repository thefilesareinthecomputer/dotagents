"""Ollama HTTP client: the one place the app speaks to the local daemon.

Factored out of chat.py so the chat lane and later consumers (the
gap-assess embedding shortlister, EPIC-000041) share one seam. Plain HTTP
on the standard library's urllib; no SDK and no third-party HTTP client.
Every request bypasses proxy settings, so traffic for the loopback daemon
never leaves the machine through an HTTP_PROXY.
"""

import asyncio
import http.client
import json
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request

from second_brain import config


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}

# A cold model can take minutes to load before the first byte streams, so
# the streaming chat call allows that long per read; connect stays tight
# because the daemon is local.
_CONNECT_TIMEOUT = 5.0
_READ_TIMEOUT = 300.0


def _base() -> str:
    """The daemon URL, HARD-GUARDED to loopback. This app never sends
    traffic to a public Ollama web API; cloud models (`:cloud` tags) are
    reached only as proxied through the local daemon. A non-local
    OLLAMA_URL is refused, not honored."""
    url = config.ollama_url()
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    if host not in _LOCAL_HOSTS:
        raise OllamaError(0, f"refusing non-local OLLAMA_URL: {url} "
                             "(only a loopback daemon is ever contacted)")
    return url


class OllamaError(Exception):
    """A non-2xx /api/chat response; .no_tools flags the model rejecting
    the tools parameter (the degrade-to-plain-chat signal)."""

    def __init__(self, status: int, message: str):
        super().__init__(f"ollama {status}: {message}")
        self.status = status
        self.no_tools = "does not support tools" in message


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """The loopback guard checks the URL this module builds; a redirect would
    substitute one it never checked, so none is followed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# Short calls (tags, ps, unload) share one opener with proxies disabled.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _post_request(path: str, payload: dict) -> urllib.request.Request:
    return urllib.request.Request(
        f"{_base()}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")


def _get_json(path: str, timeout: float):
    with _opener.open(f"{_base()}{path}", timeout=timeout) as response:
        return json.load(response)


def tags() -> list[str]:
    """Live model tags from the daemon; [] when it does not answer."""
    try:
        return [entry["name"]
                for entry in _get_json("/api/tags", 1.0).get("models", [])]
    except Exception:
        return []


def loaded() -> list[str]:
    """Model names currently resident in daemon memory; [] when it does
    not answer."""
    try:
        return [entry["name"]
                for entry in _get_json("/api/ps", 1.0).get("models", [])]
    except Exception:
        return []


def unload(model: str) -> bool:
    """Ask the daemon to release a model now (keep_alive 0 on an empty
    call). Best-effort: False when the daemon does not answer."""
    try:
        request = _post_request("/api/chat",
                                {"model": model, "messages": [],
                                 "keep_alive": 0, "stream": False})
        with _opener.open(request, timeout=10.0):
            pass
        return True
    except Exception:
        return False


def tool_schemas(schemas: list[dict]) -> list[dict]:
    """KB tool schemas (name, description, input_schema) in Ollama's
    function-calling shape."""
    return [{
        "type": "function",
        "function": {
            "name": schema["name"],
            "description": schema["description"],
            "parameters": schema["input_schema"],
        },
    } for schema in schemas]


# --- streaming chat ---

class _StreamConnectionMixin:
    """Connects under the request's timeout (_CONNECT_TIMEOUT), then
    allows _READ_TIMEOUT on every read. The connected socket goes to
    on_connect so the consuming coroutine can shut it down: closing a
    response from another thread does not wake a read blocked on it, and
    a socket shutdown does."""

    def __init__(self, *args, on_connect=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_connect = on_connect

    def connect(self):
        super().connect()
        self.sock.settimeout(_READ_TIMEOUT)
        if self._on_connect is not None:
            self._on_connect(self.sock)


class _StreamHTTPConnection(_StreamConnectionMixin,
                            http.client.HTTPConnection):
    pass


class _StreamHTTPSConnection(_StreamConnectionMixin,
                             http.client.HTTPSConnection):
    pass


class _StreamHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, on_connect):
        super().__init__()
        self._on_connect = on_connect

    def http_open(self, req):
        return self.do_open(_StreamHTTPConnection, req,
                            on_connect=self._on_connect)


class _StreamHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, on_connect):
        super().__init__()
        self._on_connect = on_connect

    def https_open(self, req):
        return self.do_open(_StreamHTTPSConnection, req,
                            context=self._context,
                            on_connect=self._on_connect)


def _shutdown(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def _error_from(err: urllib.error.HTTPError) -> OllamaError:
    """Map a non-2xx response to OllamaError, reading the body first so
    the daemon's error text (e.g. the no-tool-support message) survives."""
    try:
        body = err.read().decode(errors="replace")
    finally:
        err.close()
    try:
        body = json.loads(body).get("error", body)
    except ValueError:
        pass
    return OllamaError(err.code, body)


_END = object()


async def chat_stream(model: str, messages: list[dict],
                      tools: list[dict] | None = None):
    """Yield parsed JSON chunks from a streaming /api/chat call.

    Raises OllamaError on a non-2xx response (read before raising so the
    daemon's error text - e.g. the no-tool-support message - survives).

    The blocking urllib read runs in a worker thread and hands raw lines
    to this coroutine through an asyncio.Queue. When the consumer stops
    early (an aclose, a cancelled task, a broken-off loop), the socket is
    shut down, which ends the worker's read and closes the response.
    """
    payload: dict = {"model": model, "messages": messages, "stream": True,
                     "keep_alive": config.ollama_keep_alive()}
    if tools:
        payload["tools"] = tools
    request = _post_request("/api/chat", payload)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    stopped = threading.Event()
    sockets: list[socket.socket] = []

    def on_connect(sock: socket.socket) -> None:
        sockets.append(sock)
        if stopped.is_set():  # the consumer left while this was connecting
            _shutdown(sock)

    def put(item) -> bool:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
            return True
        except RuntimeError:  # the event loop is closed; nobody is reading
            return False

    def pump() -> None:
        try:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                _NoRedirect(),
                _StreamHTTPHandler(on_connect),
                _StreamHTTPSHandler(on_connect))
            try:
                response = opener.open(request, timeout=_CONNECT_TIMEOUT)
            except urllib.error.HTTPError as err:
                put(_error_from(err))
                return
            with response:
                for line in response:
                    if stopped.is_set() or not put(line):
                        return
        except Exception as exc:
            if not stopped.is_set():
                put(exc)
        finally:
            put(_END)

    loop.run_in_executor(None, pump)
    try:
        while True:
            item = await queue.get()
            if item is _END:
                return
            if isinstance(item, Exception):
                raise item
            line = item.strip()
            if line:
                yield json.loads(line)
    finally:
        stopped.set()
        for sock in sockets:
            _shutdown(sock)
