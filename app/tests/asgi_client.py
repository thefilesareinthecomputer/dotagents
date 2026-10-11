"""A standard-library stand-in for starlette's TestClient.

starlette.testclient needs a third-party HTTP client package that this
project does not depend on, so the endpoint tests drive the ASGI app
through this instead.
It covers the subset the suite uses: get, post and delete with `json=` and
`params=`, and a response with status_code, headers, content, text and
json(). Like TestClient used without a `with` block, each request runs the
app on a fresh event loop with no lifespan events, the whole body is
collected (SSE included) before the call returns, and an exception the app
raises propagates to the test.
"""

import asyncio
import json
import urllib.parse


class Headers(dict):
    """Response headers with case-insensitive lookup; repeated headers
    are joined with ", " as an HTTP client would."""

    def __getitem__(self, name: str) -> str:
        return super().__getitem__(name.lower())

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and super().__contains__(name.lower())

    def get(self, name: str, default=None):
        return super().get(name.lower(), default)


class Response:
    def __init__(self, status_code: int, headers: Headers, content: bytes):
        self.status_code = status_code
        self.headers = headers
        self.content = content

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.content)


class TestClient:
    __test__ = False  # not a test class, despite the name

    def __init__(self, app, peer: str = "127.0.0.1"):
        self.app = app
        # The app answers loopback peers only, so the default peer is one.
        self.peer = peer

    def get(self, url: str, params: dict | None = None,
            headers: dict | None = None) -> Response:
        return self.request("GET", url, params=params, headers=headers)

    def post(self, url: str, json=None, params: dict | None = None,
             headers: dict | None = None) -> Response:
        return self.request("POST", url, json_body=json, params=params, headers=headers)

    def delete(self, url: str, params: dict | None = None) -> Response:
        return self.request("DELETE", url, params=params)

    def request(self, method: str, url: str, json_body=None,
                params: dict | None = None, headers: dict | None = None) -> Response:
        path, _, query = url.partition("?")
        if params:
            extra = urllib.parse.urlencode(params, doseq=True)
            query = f"{query}&{extra}" if query else extra
        body = b"" if json_body is None else json.dumps(json_body).encode()
        # The app accepts loopback hosts only, so the default Host is one.
        sent = {"host": "127.0.0.1", "user-agent": "testclient"}
        sent.update({k.lower(): v for k, v in (headers or {}).items()})
        headers = [(k.encode(), v.encode()) for k, v in sent.items()]
        if json_body is not None:
            headers += [(b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode())]
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": urllib.parse.unquote(path),
            "raw_path": path.encode(),
            "root_path": "",
            "query_string": query.encode(),
            "headers": headers,
            "client": (self.peer, 50000),
            "server": ("127.0.0.1", 80),
            "state": {},
        }
        return asyncio.run(self._call(scope, body))

    async def _call(self, scope: dict, body: bytes) -> Response:
        complete = asyncio.Event()
        request_sent = False
        start: dict = {}
        chunks: list[bytes] = []

        async def receive() -> dict:
            nonlocal request_sent
            if request_sent:
                # A streaming response listens for a disconnect while it
                # sends; hold that back until the body is complete.
                await complete.wait()
                return {"type": "http.disconnect"}
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message: dict) -> None:
            if message["type"] == "http.response.start":
                start.update(message)
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    complete.set()

        await self.app(scope, receive, send)
        assert start, "the app sent no response"
        headers = Headers()
        for name, value in start.get("headers", []):
            key, text = name.decode("latin-1").lower(), value.decode("latin-1")
            headers[key] = f"{dict.get(headers, key)}, {text}" \
                if key in headers else text
        return Response(start["status"], headers, b"".join(chunks))
