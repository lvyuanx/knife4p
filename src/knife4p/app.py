from __future__ import annotations

import json
from importlib import resources
from urllib.parse import urlsplit, urlunsplit

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .config import Knife4pConfig, OpenAPIGroup

ASSET_ROOT = resources.files("knife4p").joinpath("assets")
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
REQUEST_HEADER_ALLOWLIST = {
    "accept",
    "accept-encoding",
    "accept-language",
    "authorization",
    "content-type",
    "cookie",
    "user-agent",
    "x-api-key",
    "x-csrf-token",
    "x-request-id",
    "x-trace-id",
}
RESPONSE_HEADER_ALLOWLIST = {"content-type", "cache-control"}


def create_app(config: Knife4pConfig):
    routes = [
        Route("/docs", _docs_redirect(config), methods=["GET"]),
        Route(config.docs_path, _docs(config), methods=["GET"]),
        Route("/favicon.ico", _favicon, methods=["GET"]),
        Route("/v3/api-docs/swagger-config", _swagger_config(config), methods=["GET"]),
        Route("/swagger-resources", _swagger_resources(config), methods=["GET"]),
        Route("/swagger-resources/configuration/ui", _swagger_ui_config, methods=["GET"]),
        Route(f"{config.api_prefix}/openapi/{{group}}", _openapi(config), methods=["GET"]),
        Route(f"{config.api_prefix}/proxy/{{group}}/{{path:path}}", _proxy(config), methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]),
        Mount(config.assets_path, app=StaticFiles(directory=str(ASSET_ROOT.joinpath("webjars")))),
        Mount("/img", app=StaticFiles(directory=str(ASSET_ROOT.joinpath("img")))),
    ]
    return Starlette(routes=routes)


def mount_fastapi(app, config: Knife4pConfig):
    app.router.routes.insert(0, Route("/docs", _docs_redirect(config), methods=["GET"]))
    app.mount("", create_app(config))
    return app


def request_origin(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


def _docs(config: Knife4pConfig):
    async def endpoint(request: Request) -> Response:
        doc_file = ASSET_ROOT.joinpath("doc.html")
        if doc_file.is_file():
            body = doc_file.read_text(encoding="utf-8")
        else:
            body = "<!doctype html><html><head><title>Knife4p</title></head><body><div id=\"app\">Knife4p</div></body></html>"
        return HTMLResponse(body.replace("Knife4p", config.title, 1))

    return endpoint


def _docs_redirect(config: Knife4pConfig):
    async def endpoint(request: Request) -> Response:
        return RedirectResponse(config.docs_path)

    return endpoint


def _swagger_config(config: Knife4pConfig):
    async def endpoint(request: Request) -> Response:
        return JSONResponse(
            {
                "configUrl": "/v3/api-docs/swagger-config",
                "urls": [{"name": group.name, "url": f"{config.api_prefix}/openapi/{group.slug}"} for group in config.groups],
                "validatorUrl": "",
            }
        )

    return endpoint


def _swagger_resources(config: Knife4pConfig):
    async def endpoint(request: Request) -> Response:
        return JSONResponse(
            [
                {"name": group.name, "url": f"{config.api_prefix}/openapi/{group.slug}", "location": f"{config.api_prefix}/openapi/{group.slug}"}
                for group in config.groups
            ]
        )

    return endpoint


async def _swagger_ui_config(request: Request) -> Response:
    return JSONResponse({"deepLinking": True, "displayOperationId": False, "defaultModelsExpandDepth": 1, "tryItOutEnabled": True})


async def _favicon(request: Request) -> Response:
    svg_icon = ASSET_ROOT.joinpath("webjars/knife4j-ui-react/knife4j-next-mark.svg")
    if svg_icon.is_file():
        return Response(svg_icon.read_bytes(), media_type="image/svg+xml")

    png_icon = ASSET_ROOT.joinpath("img/icons/favicon-32x32.png")
    if png_icon.is_file():
        return Response(png_icon.read_bytes(), media_type="image/png")

    return Response("Not found", status_code=404)


def _openapi(config: Knife4pConfig):
    async def endpoint(request: Request) -> Response:
        group = config.group_by_slug(request.path_params["group"])
        if group is None:
            return JSONResponse({"detail": "OpenAPI group not found"}, status_code=404)

        origin = request_origin(request)
        try:
            async with httpx.AsyncClient(timeout=group.timeout) as client:
                upstream = await client.get(group.resolve_openapi_url(origin), headers=dict(group.headers))
        except httpx.TimeoutException:
            return JSONResponse({"detail": "OpenAPI upstream timed out"}, status_code=504)
        except httpx.HTTPError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)

        if upstream.status_code >= 400:
            return JSONResponse({"detail": "OpenAPI upstream error", "status_code": upstream.status_code}, status_code=502)

        headers = _copy_response_headers(upstream.headers)
        content_type = upstream.headers.get("content-type", "")
        if "json" not in content_type and upstream.content:
            content_type = "application/json"
        try:
            payload = upstream.json()
        except json.JSONDecodeError:
            return Response(upstream.content, status_code=upstream.status_code, media_type=content_type, headers=headers)

        if group.allow_try_it and isinstance(payload, dict) and str(payload.get("openapi", "")).startswith("3."):
            payload = dict(payload)
            payload["servers"] = [{"url": f"{config.api_prefix}/proxy/{group.slug}"}]
        return JSONResponse(payload, headers=headers)

    return endpoint


def _proxy(config: Knife4pConfig):
    async def endpoint(request: Request) -> Response:
        group = config.group_by_slug(request.path_params["group"])
        if group is None:
            return JSONResponse({"detail": "OpenAPI group not found"}, status_code=404)
        if not group.allow_try_it:
            return JSONResponse({"detail": "Try it out is disabled for this group"}, status_code=403)

        target = _build_proxy_url(group, request_origin(request), request.path_params.get("path", ""), request.url.query)
        body = await request.body()
        headers = _copy_request_headers(request.headers)
        try:
            async with httpx.AsyncClient(timeout=group.timeout) as client:
                upstream = await client.request(request.method, target, headers=headers, content=body)
        except httpx.TimeoutException:
            return JSONResponse({"detail": "Proxy upstream timed out"}, status_code=504)
        except httpx.HTTPError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)

        return Response(upstream.content, status_code=upstream.status_code, headers=_copy_response_headers(upstream.headers))

    return endpoint


def _build_proxy_url(group: OpenAPIGroup, origin: str, path: str, query: str) -> str:
    base = group.resolve_proxy_base_url(origin).rstrip("/")
    parsed = urlsplit(base)
    clean_path = "/".join(segment for segment in path.split("/") if segment not in {"", ".", ".."})
    joined_path = "/".join(part.strip("/") for part in [parsed.path, clean_path] if part.strip("/"))
    return urlunsplit((parsed.scheme, parsed.netloc, "/" + joined_path if joined_path else "", query, ""))


def _copy_request_headers(headers) -> dict[str, str]:
    copied = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in HOP_BY_HOP_HEADERS or lower == "host":
            continue
        if lower in REQUEST_HEADER_ALLOWLIST or lower.startswith("x-"):
            copied[key] = value
    return copied


def _copy_response_headers(headers) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key.lower() in RESPONSE_HEADER_ALLOWLIST}
