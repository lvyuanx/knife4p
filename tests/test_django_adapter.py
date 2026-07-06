from knife4p import Knife4pConfig, OpenAPIGroup, django_urls


def test_django_urls_adapter_exposes_docs_and_openapi(httpx_mock):
    import django
    from django.conf import settings
    from django.test import Client
    from django.urls import include, path

    httpx_mock.add_response(
        url="http://testserver/openapi.json",
        json={"openapi": "3.1.0", "info": {"title": "Django", "version": "1"}},
    )

    if not settings.configured:
        settings.configure(
            SECRET_KEY="test",
            ALLOWED_HOSTS=["testserver"],
            ROOT_URLCONF=__name__,
            DEFAULT_CHARSET="utf-8",
        )
    django.setup()

    global urlpatterns
    urlpatterns = [
        path("", include(django_urls(Knife4pConfig(groups=[OpenAPIGroup(name="default", openapi_url="/openapi.json")])))),
    ]

    client = Client()
    docs = client.get("/doc.html")
    spec = client.get("/knife4p/openapi/default")

    assert docs.status_code == 200
    assert b'id="root"' in docs.content
    assert spec.status_code == 200
    assert spec.json()["servers"] == [{"url": "/knife4p/proxy/default"}]


def test_django_urls_adapter_preserves_request_port_for_relative_openapi_url(httpx_mock):
    import django
    from django.conf import settings
    from django.test import Client, override_settings
    from django.urls import include, path

    httpx_mock.add_response(
        url="http://testserver:8766/openapi.json",
        json={"openapi": "3.1.0", "info": {"title": "Django", "version": "1"}},
    )

    if not settings.configured:
        settings.configure(
            SECRET_KEY="test",
            ALLOWED_HOSTS=["testserver"],
            ROOT_URLCONF=__name__,
            DEFAULT_CHARSET="utf-8",
        )
    django.setup()

    global urlpatterns
    urlpatterns = [
        path("", include(django_urls(Knife4pConfig(groups=[OpenAPIGroup(name="default", openapi_url="/openapi.json")])))),
    ]

    client = Client()
    with override_settings(ALLOWED_HOSTS=["testserver"]):
        spec = client.get("/knife4p/openapi/default", HTTP_HOST="testserver:8766")

    assert spec.status_code == 200
    assert httpx_mock.get_requests()[0].url == "http://testserver:8766/openapi.json"
