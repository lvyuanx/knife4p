import json

import httpx
import pytest

from knife4p import Knife4pConfig, OpenAPIGroup, create_app, mount_fastapi


async def request(app, method, url, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, url, **kwargs)


@pytest.mark.anyio
async def test_docs_and_assets_are_served():
    app = create_app(Knife4pConfig(groups=[OpenAPIGroup(name="default", openapi_url="/openapi.json")]))

    docs = await request(app, "GET", "/doc.html")
    swagger_docs = await request(app, "GET", "/docs", follow_redirects=False)
    script = await request(app, "GET", "/webjars/knife4j-ui-react/assets/index.js")
    stylesheet = await request(app, "GET", "/webjars/knife4j-ui-react/assets/index.css")
    favicon = await request(app, "GET", "/favicon.ico")

    assert docs.status_code == 200
    assert "text/html" in docs.headers["content-type"]
    assert '<div id="root">' in docs.text
    assert swagger_docs.status_code == 307
    assert swagger_docs.headers["location"] == "/doc.html"
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    assert b"Knife4p" in script.content
    assert b"Knife4jp" not in script.content
    assert b"Knife4p Next" not in script.content
    assert b"Knife4j Next" not in script.content
    assert stylesheet.status_code == 200
    assert "text/css" in stylesheet.headers["content-type"]
    assert favicon.status_code == 200
    assert favicon.headers["content-type"] in {"image/svg+xml", "image/png"}


@pytest.mark.anyio
async def test_swagger_config_endpoints_expose_group_urls():
    app = create_app(
        Knife4pConfig(
            title="Docs",
            groups=[
                OpenAPIGroup(name="Default API", openapi_url="/openapi.json"),
                OpenAPIGroup(name="Billing", openapi_url="https://billing.example.com/openapi.json"),
            ],
        )
    )

    springdoc = await request(app, "GET", "/v3/api-docs/swagger-config")
    resources = await request(app, "GET", "/swagger-resources")
    ui = await request(app, "GET", "/swagger-resources/configuration/ui")

    assert springdoc.status_code == 200
    assert springdoc.json()["urls"] == [
        {"name": "Default API", "url": "/knife4p/openapi/default-api"},
        {"name": "Billing", "url": "/knife4p/openapi/billing"},
    ]
    assert resources.status_code == 200
    assert resources.json()[0]["location"] == "/knife4p/openapi/default-api"
    assert ui.status_code == 200
    assert ui.json()["deepLinking"] is True


@pytest.mark.anyio
async def test_openapi_endpoint_fetches_remote_json_and_rewrites_servers(httpx_mock):
    httpx_mock.add_response(
        url="https://api.example.com/openapi.json",
        json={"openapi": "3.1.0", "info": {"title": "Remote", "version": "1"}, "servers": [{"url": "/old"}]},
        headers={"x-upstream": "ignored", "cache-control": "max-age=30"},
    )
    app = create_app(
        Knife4pConfig(
            groups=[
                OpenAPIGroup(
                    name="Remote",
                    openapi_url="https://api.example.com/openapi.json",
                    headers={"authorization": "Bearer token"},
                )
            ]
        )
    )

    response = await request(app, "GET", "/knife4p/openapi/remote")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "max-age=30"
    assert response.json()["servers"] == [{"url": "/knife4p/proxy/remote"}]
    sent = httpx_mock.get_requests()[0]
    assert sent.headers["authorization"] == "Bearer token"


@pytest.mark.anyio
async def test_openapi_endpoint_preserves_servers_when_try_it_disabled(httpx_mock):
    httpx_mock.add_response(
        url="http://testserver/openapi.json",
        json={"openapi": "3.0.3", "info": {"title": "Local", "version": "1"}, "servers": [{"url": "/api"}]},
    )
    app = create_app(
        Knife4pConfig(groups=[OpenAPIGroup(name="default", openapi_url="/openapi.json", allow_try_it=False)])
    )

    response = await request(app, "GET", "/knife4p/openapi/default")

    assert response.status_code == 200
    assert response.json()["servers"] == [{"url": "/api"}]


@pytest.mark.anyio
async def test_openapi_endpoint_reports_upstream_error_and_timeout(httpx_mock):
    httpx_mock.add_response(url="https://api.example.com/openapi.json", status_code=503, json={"error": "down"})
    httpx_mock.add_exception(httpx.TimeoutException("slow"), url="https://slow.example.com/openapi.json")
    app = create_app(
        Knife4pConfig(
            groups=[
                OpenAPIGroup(name="Remote", openapi_url="https://api.example.com/openapi.json"),
                OpenAPIGroup(name="Slow", openapi_url="https://slow.example.com/openapi.json"),
            ]
        )
    )

    error = await request(app, "GET", "/knife4p/openapi/remote")
    timeout = await request(app, "GET", "/knife4p/openapi/slow")

    assert error.status_code == 502
    assert error.json()["status_code"] == 503
    assert timeout.status_code == 504


@pytest.mark.anyio
async def test_proxy_forwards_business_requests_to_group_base_url(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://api.example.com/widgets?debug=1",
        status_code=201,
        json={"created": True},
        headers={"content-type": "application/json", "cache-control": "no-store", "x-hidden": "no"},
    )
    app = create_app(
        Knife4pConfig(
            groups=[
                OpenAPIGroup(
                    name="Remote",
                    openapi_url="https://api.example.com/openapi.json",
                    proxy_base_url="https://api.example.com",
                )
            ]
        )
    )

    response = await request(
        app,
        "POST",
        "/knife4p/proxy/remote/widgets?debug=1",
        json={"name": "knife"},
        headers={"x-request-id": "abc", "connection": "close"},
    )

    assert response.status_code == 201
    assert response.json() == {"created": True}
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert "x-hidden" not in response.headers
    sent = httpx_mock.get_requests()[0]
    assert sent.url == "https://api.example.com/widgets?debug=1"
    assert sent.headers["x-request-id"] == "abc"
    assert sent.headers.get("connection") != "close"
    assert json.loads(sent.content) == {"name": "knife"}


@pytest.mark.anyio
async def test_proxy_rejects_unknown_group_and_disabled_try_it(httpx_mock):
    app = create_app(
        Knife4pConfig(groups=[OpenAPIGroup(name="default", openapi_url="/openapi.json", allow_try_it=False)])
    )

    missing = await request(app, "GET", "/knife4p/proxy/missing/widgets")
    disabled = await request(app, "GET", "/knife4p/proxy/default/widgets")

    assert missing.status_code == 404
    assert disabled.status_code == 403
    assert httpx_mock.get_requests() == []


@pytest.mark.anyio
async def test_fastapi_mount_helper_exposes_knife4p_routes(httpx_mock):
    from fastapi import FastAPI

    httpx_mock.add_response(url="http://testserver/openapi.json", json={"openapi": "3.1.0", "info": {"title": "x", "version": "1"}})
    app = FastAPI()

    mount_fastapi(app, Knife4pConfig(groups=[OpenAPIGroup(name="default", openapi_url="/openapi.json")]))

    docs = await request(app, "GET", "/doc.html")
    swagger_docs = await request(app, "GET", "/docs", follow_redirects=False)
    spec = await request(app, "GET", "/knife4p/openapi/default")

    assert docs.status_code == 200
    assert swagger_docs.status_code == 307
    assert swagger_docs.headers["location"] == "/doc.html"
    assert spec.status_code == 200
