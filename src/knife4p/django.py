from __future__ import annotations

from urllib.parse import urlsplit

from .app import create_app
from .config import Knife4pConfig


def django_urls(config: Knife4pConfig):
    from asgiref.sync import async_to_sync
    from django.http import HttpResponse
    from django.urls import re_path

    app = create_app(config)

    def view(request, path=""):
        body = request.body
        captured = {}
        server = _server_from_host(request.get_host(), request.is_secure())

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                captured["status"] = message["status"]
                captured["headers"] = message.get("headers", [])
            elif message["type"] == "http.response.body":
                captured["body"] = captured.get("body", b"") + message.get("body", b"")

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": request.method,
            "scheme": "https" if request.is_secure() else "http",
            "path": request.path,
            "raw_path": request.path.encode(),
            "query_string": request.META.get("QUERY_STRING", "").encode(),
            "headers": [(key.lower().encode(), value.encode()) for key, value in request.headers.items()],
            "server": server,
            "client": ("127.0.0.1", 0),
            "root_path": "",
        }
        async_to_sync(app)(scope, receive, send)
        response = HttpResponse(captured.get("body", b""), status=captured.get("status", 500))
        for key, value in captured.get("headers", []):
            header = key.decode()
            if header.lower() not in {"content-length"}:
                response[header] = value.decode()
        return response

    return [
        re_path(r"^(?P<path>.*)$", view),
    ]


def _server_from_host(host: str, secure: bool) -> tuple[str, int]:
    default_port = 443 if secure else 80
    parsed = urlsplit(f"//{host}")
    return parsed.hostname or host, parsed.port or default_port
