from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urljoin, urlsplit, urlunsplit


def _clean_path(path: str, default: str) -> str:
    value = path or default
    return value if value.startswith("/") else f"/{value}"


def slugify(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return value or "default"


def origin_from(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"URL does not have an origin: {url!r}")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def join_origin(origin: str, url: str) -> str:
    if urlsplit(url).scheme:
        return url
    return urljoin(origin.rstrip("/") + "/", url.lstrip("/"))


@dataclass(frozen=True)
class OpenAPIGroup:
    name: str
    openapi_url: str
    proxy_base_url: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    timeout: float = 10.0
    allow_try_it: bool = True

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("group name must not be empty")
        if not self.openapi_url or not self.openapi_url.strip():
            raise ValueError("openapi_url must not be empty")
        if self.timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "openapi_url", self.openapi_url.strip())
        if self.proxy_base_url is not None:
            object.__setattr__(self, "proxy_base_url", self.proxy_base_url.strip())
        object.__setattr__(self, "headers", dict(self.headers))
        object.__setattr__(self, "slug", slugify(self.name))

    slug: str = field(init=False)

    def resolve_openapi_url(self, request_origin: str) -> str:
        return join_origin(request_origin, self.openapi_url)

    def resolve_proxy_base_url(self, request_origin: str) -> str:
        if self.proxy_base_url:
            return join_origin(request_origin, self.proxy_base_url).rstrip("/")
        openapi_url = self.resolve_openapi_url(request_origin)
        return origin_from(openapi_url)


@dataclass(frozen=True)
class Knife4pConfig:
    groups: list[OpenAPIGroup]
    docs_path: str = "/doc.html"
    assets_path: str = "/webjars"
    api_prefix: str = "/knife4p"
    title: str = "Knife4p"

    def __post_init__(self) -> None:
        if not self.groups:
            raise ValueError("at least one OpenAPI group is required")

        seen: set[str] = set()
        normalized_groups: list[OpenAPIGroup] = []
        for group in self.groups:
            key = slugify(group.name)
            if key in seen:
                raise ValueError(f"duplicate group name: {group.name}")
            seen.add(key)
            normalized_groups.append(group)

        object.__setattr__(self, "groups", normalized_groups)
        object.__setattr__(self, "docs_path", _clean_path(self.docs_path, "/doc.html"))
        object.__setattr__(self, "assets_path", _clean_path(self.assets_path, "/webjars").rstrip("/"))
        object.__setattr__(self, "api_prefix", _clean_path(self.api_prefix, "/knife4p").rstrip("/"))

    def group_by_slug(self, slug: str) -> OpenAPIGroup | None:
        for group in self.groups:
            if group.slug == slug:
                return group
        return None
