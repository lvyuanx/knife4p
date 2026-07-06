from __future__ import annotations

import sys
from typing import Literal

from django.conf import settings


if not settings.configured:
    settings.configure(
        SECRET_KEY="knife4p-example",
        DEBUG=True,
        ALLOWED_HOSTS=["127.0.0.1", "localhost", "testserver"],
        ROOT_URLCONF=__name__,
        MIDDLEWARE=[],
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
        ],
        DEFAULT_CHARSET="utf-8",
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        USE_TZ=True,
    )

import django
from django.core.management import execute_from_command_line
from django.core.wsgi import get_wsgi_application
from django.urls import include, path
from ninja import NinjaAPI, Schema

from knife4p import Knife4pConfig, OpenAPIGroup, django_urls

django.setup()

api = NinjaAPI(
    title="Knife4p Django Ninja Example",
    version="0.1.0",
    description="A small Django Ninja app wired to Knife4p / Knife4p UI.",
)


class ItemCreate(Schema):
    name: str
    category: Literal["kitchen", "outdoor", "tool"] = "kitchen"
    price: float
    in_stock: bool = True


class Item(ItemCreate):
    id: int


items: dict[int, Item] = {
    1: Item(id=1, name="Chef knife", category="kitchen", price=39.9),
    2: Item(id=2, name="Pocket knife", category="outdoor", price=24.5),
}


@api.get("/health", tags=["system"])
def health(request):
    return {"status": "ok"}


@api.get("/items", response=list[Item], tags=["items"])
def list_items(request, category: Literal["kitchen", "outdoor", "tool"] | None = None, in_stock: bool | None = None):
    results = list(items.values())
    if category is not None:
        results = [item for item in results if item.category == category]
    if in_stock is not None:
        results = [item for item in results if item.in_stock is in_stock]
    return results


@api.get("/items/{item_id}", response=Item, tags=["items"])
def read_item(request, item_id: int):
    return items.get(item_id) or api.create_response(request, {"detail": "Item not found"}, status=404)


@api.post("/items", response={201: Item}, tags=["items"])
def create_item(request, payload: ItemCreate):
    item_id = max(items) + 1 if items else 1
    item = Item(id=item_id, **payload.dict())
    items[item_id] = item
    return 201, item


urlpatterns = [
    path("api/", api.urls),
    path(
        "",
        include(
            django_urls(
                Knife4pConfig(
                    title="Knife4p Django Ninja Example",
                    groups=[
                        OpenAPIGroup(
                            name="default",
                            openapi_url="/api/openapi.json",
                            proxy_base_url="http://127.0.0.1:8766",
                        )
                    ],
                )
            )
        ),
    ),
]

application = get_wsgi_application()


if __name__ == "__main__":
    execute_from_command_line(sys.argv)
