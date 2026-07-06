from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from knife4p import Knife4pConfig, OpenAPIGroup, mount_fastapi

app = FastAPI(
    title="Knife4p FastAPI Example",
    version="0.1.0",
    description="A small FastAPI app wired to Knife4p / Knife4p UI.",
)


class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1, examples=["Chef knife"])
    category: Literal["kitchen", "outdoor", "tool"] = "kitchen"
    price: float = Field(..., gt=0, examples=[39.9])
    in_stock: bool = True


class Item(ItemCreate):
    id: int


items: dict[int, Item] = {
    1: Item(id=1, name="Chef knife", category="kitchen", price=39.9),
    2: Item(id=2, name="Pocket knife", category="outdoor", price=24.5),
}


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


@app.get("/items", response_model=list[Item], tags=["items"])
def list_items(
    category: Literal["kitchen", "outdoor", "tool"] | None = Query(default=None),
    in_stock: bool | None = Query(default=None),
):
    results = list(items.values())
    if category is not None:
        results = [item for item in results if item.category == category]
    if in_stock is not None:
        results = [item for item in results if item.in_stock is in_stock]
    return results


@app.get("/items/{item_id}", response_model=Item, tags=["items"])
def read_item(item_id: int):
    try:
        return items[item_id]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Item not found") from exc


@app.post("/items", response_model=Item, status_code=201, tags=["items"])
def create_item(payload: ItemCreate):
    item_id = max(items) + 1 if items else 1
    item = Item(id=item_id, **payload.model_dump())
    items[item_id] = item
    return item


@app.delete("/admin/items/{item_id}", status_code=204, tags=["admin"])
def delete_item(item_id: int):
    if item_id not in items:
        raise HTTPException(status_code=404, detail="Item not found")
    del items[item_id]


mount_fastapi(
    app,
    Knife4pConfig(
        title="Knife4p FastAPI Example",
        groups=[
            OpenAPIGroup(
                name="default",
                openapi_url="/openapi.json",
                proxy_base_url="http://127.0.0.1:8765",
            )
        ],
    ),
)
