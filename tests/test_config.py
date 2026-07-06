import pytest

from knife4p import Knife4pConfig, OpenAPIGroup


def test_config_generates_stable_slugs_and_defaults():
    config = Knife4pConfig(
        groups=[
            OpenAPIGroup(name="Default API", openapi_url="/openapi.json"),
            OpenAPIGroup(name="Billing/API", openapi_url="https://billing.example.com/openapi.json"),
        ]
    )

    assert [group.slug for group in config.groups] == ["default-api", "billing-api"]
    assert config.docs_path == "/doc.html"
    assert config.assets_path == "/webjars"
    assert config.api_prefix == "/knife4p"
    assert config.groups[0].timeout == 10.0
    assert config.groups[0].allow_try_it is True


def test_config_rejects_duplicate_group_names_even_with_different_case():
    with pytest.raises(ValueError, match="duplicate group"):
        Knife4pConfig(
            groups=[
                OpenAPIGroup(name="Default API", openapi_url="/openapi.json"),
                OpenAPIGroup(name="default api", openapi_url="/v2/openapi.json"),
            ]
        )


def test_config_rejects_empty_openapi_url_and_invalid_timeout():
    with pytest.raises(ValueError, match="openapi_url"):
        OpenAPIGroup(name="default", openapi_url="")

    with pytest.raises(ValueError, match="timeout"):
        OpenAPIGroup(name="default", openapi_url="/openapi.json", timeout=0)


def test_group_url_resolution_uses_request_origin_and_openapi_origin():
    relative = OpenAPIGroup(name="Default", openapi_url="/openapi.json")
    absolute = OpenAPIGroup(name="Remote", openapi_url="https://api.example.com/spec/openapi.json")

    assert relative.resolve_openapi_url("http://testserver") == "http://testserver/openapi.json"
    assert relative.resolve_proxy_base_url("http://testserver") == "http://testserver"
    assert absolute.resolve_openapi_url("http://testserver") == "https://api.example.com/spec/openapi.json"
    assert absolute.resolve_proxy_base_url("http://testserver") == "https://api.example.com"


def test_explicit_relative_proxy_base_url_resolves_against_request_origin():
    group = OpenAPIGroup(
        name="Default",
        openapi_url="/openapi.json",
        proxy_base_url="/api",
    )

    assert group.resolve_proxy_base_url("https://docs.example.com") == "https://docs.example.com/api"
